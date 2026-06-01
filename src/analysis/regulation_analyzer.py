"""
AI-QMS — Regulation Analyzer (LLM-Based)
==========================================

Automatically analyzes crawled regulatory text against ISO 13485 clauses
to generate a RegulationProfile for any country.

This is the "8th country" engine — enables dynamic regulation analysis
for countries beyond the predefined 7.

Flow:
  1. Receive crawled markdown text for a country
  2. Batch ISO 13485 clauses (~10 per LLM call)
  3. LLM maps each clause → MappingStatus (full/partial/na/exceeds)
  4. LLM identifies unique/delta requirements beyond ISO 13485
  5. Build RegulationProfile, save to data/regulations/, register in memory
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Callable, Optional

from src.analysis.compliance_rules import (
    ISO_13485_CHECKLIST,
    RegulationProfile,
    ClauseMapping,
    UniqueRequirement,
    WithinClauseDelta,
    MappingStatus,
    MappingMethod,
    save_crawled_regulation,
    generate_profile_id_from_region,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 24  # clauses per LLM call (71 clauses → 3 batches)
_MAX_CONCURRENT_BATCHES = 3
_MAX_RETRIES_BATCH = 2  # retry on timeout (3 total attempts)
_MAX_REGULATORY_TEXT_CHARS = 12000  # truncate crawled text per LLM call
_MAX_UNIQUE_REQ_TEXT_CHARS = 12000  # more context for unique requirements

# Local model providers — smaller context windows, conservative defaults
_LOCAL_PROVIDERS = {"ollama", "lmstudio"}

_CLOUD_PARAMS: dict = {
    "batch_size": _BATCH_SIZE,
    "max_regulatory_chars": _MAX_REGULATORY_TEXT_CHARS,
    "max_unique_req_chars": _MAX_UNIQUE_REQ_TEXT_CHARS,
    "max_tokens_clause": 16384,
    "max_tokens_unique": 16384,
}

# Language-aware local params:
#   CJK (Chinese/Japanese/Korean): ~2 tokens/char → 50,000 chars ≈ 100K tokens (safe within 128K)
#   Latin/English: ~0.25 tokens/char → 80,000 chars ≈ 20K tokens
# batch_size 6: fewer clauses per call → more focused context per clause
_LOCAL_PARAMS_CJK: dict = {
    "batch_size": 6,
    "max_regulatory_chars": 50000,
    "max_unique_req_chars": 40000,
    "max_tokens_clause": 8000,
    "max_tokens_unique": 8000,
}

_LOCAL_PARAMS_LATIN: dict = {
    "batch_size": 6,
    "max_regulatory_chars": 80000,
    "max_unique_req_chars": 60000,
    "max_tokens_clause": 8000,
    "max_tokens_unique": 8000,
}

# Keep backward-compatible alias (resolved at runtime via _get_model_params)
_LOCAL_PARAMS: dict = _LOCAL_PARAMS_CJK

# Broad keywords for unique-requirement pass (market-access signals)
_UNIQUE_REQ_KEYWORDS: list[str] = [
    "registration", "listing", "notif", "import", "export",
    "authorized representative", "local agent", "label",
    "adverse event", "vigilance", "report", "deadline",
    "UDI", "unique device", "post-market", "PSUR",
    "clinical", "conformity", "approval", "license", "permit", "certif",
]

# Per-clause keyword index for focused text pre-filtering (Direction C)
_CLAUSE_KEYWORDS: dict[str, list[str]] = {
    "4.1":    ["quality management system", "QMS", "quality system", "process", "outsourc"],
    "4.2.1":  ["document", "record", "quality manual", "procedure"],
    "4.2.2":  ["quality manual"],
    "4.2.3":  ["document control", "document approval", "document review", "master list"],
    "4.2.4":  ["record control", "record retention", "records"],
    "4.2.5":  ["technical file", "device master record", "DHF", "device history"],
    "5.1":    ["management commitment", "top management", "quality policy", "resource"],
    "5.2":    ["customer focus", "customer requirement", "customer satisfaction"],
    "5.3":    ["quality policy"],
    "5.4.1":  ["quality objective"],
    "5.4.2":  ["QMS planning", "quality planning"],
    "5.5.1":  ["responsibility", "authority", "organiz"],
    "5.5.2":  ["management representative"],
    "5.5.3":  ["internal communication"],
    "5.6.1":  ["management review"],
    "5.6.2":  ["management review input", "review input"],
    "5.6.3":  ["management review output", "review output"],
    "6.1":    ["resource", "provision of resource"],
    "6.2":    ["human resource", "competence", "training", "awareness", "qualification"],
    "6.3":    ["infrastructure", "facility", "equipment", "maintenance"],
    "6.4.1":  ["work environment", "contamination", "environment control"],
    "6.4.2":  ["contamination control", "sterile", "cleanroom"],
    "7.1":    ["product realization", "planning", "risk management"],
    "7.2.1":  ["customer requirement", "product requirement", "applicable regulation"],
    "7.2.2":  ["review of requirement", "contract review"],
    "7.2.3":  ["customer communication", "complaint", "feedback"],
    "7.3.1":  ["design", "development planning"],
    "7.3.2":  ["design input", "design requirement"],
    "7.3.3":  ["design output"],
    "7.3.4":  ["design review"],
    "7.3.5":  ["design verification"],
    "7.3.6":  ["design validation", "clinical evaluation"],
    "7.3.7":  ["design transfer"],
    "7.3.8":  ["design change", "design control change"],
    "7.3.9":  ["design history file", "DHF"],
    "7.3.10": ["software", "software lifecycle"],
    "7.4.1":  ["purchasing", "supplier", "procurement", "approved supplier"],
    "7.4.2":  ["purchasing information", "purchase order"],
    "7.4.3":  ["incoming inspection", "verification of purchased product"],
    "7.5.1":  ["production", "service provision", "manufacturing control"],
    "7.5.2":  ["cleanliness", "contamination", "sterile product"],
    "7.5.3":  ["identification", "traceability", "lot number", "UDI", "unique device"],
    "7.5.4":  ["customer property", "customer-supplied"],
    "7.5.5":  ["preservation", "storage", "handling"],
    "7.5.6":  ["process validation", "special process"],
    "7.5.7":  ["sterile medical device"],
    "7.5.8":  ["implantable device"],
    "7.5.9":  ["traceability"],
    "7.5.9.1":["active implantable", "implantable device", "traceability"],
    "7.5.9.2":["particular requirement for traceability"],
    "7.5.10": ["customer property"],
    "7.5.11": ["preservation of product"],
    "7.6":    ["monitoring equipment", "measuring equipment", "calibrat", "measurement"],
    "8.1":    ["measurement", "analysis", "improvement"],
    "8.2.1":  ["feedback", "customer feedback", "post-market"],
    "8.2.2":  ["complaint", "complaint handling", "adverse event", "vigilance"],
    "8.2.3":  ["regulatory reporting", "adverse event report", "competent authority"],
    "8.2.4":  ["internal audit"],
    "8.2.4.1":["internal audit"],
    "8.2.4.2":["audit"],
    "8.2.5":  ["monitoring", "measurement of process"],
    "8.2.6":  ["monitoring of product", "acceptance criteria"],
    "8.3":    ["nonconforming product", "nonconformance", "non-conforming"],
    "8.3.1":  ["nonconforming product general"],
    "8.3.2":  ["response to nonconforming product"],
    "8.3.3":  ["rework"],
    "8.3.4":  ["returned product"],
    "8.4":    ["data analysis", "analysis of data"],
    "8.5.1":  ["improvement", "continual improvement"],
    "8.5.2":  ["corrective action", "CAPA", "root cause"],
    "8.5.3":  ["preventive action", "CAPA"],
}

# ============================================================
# Multilingual Clause Keywords (CJK + Arabic)
# ============================================================

_CLAUSE_KEYWORDS_ZH: dict[str, list[str]] = {
    "4.1":    ["品質管理系統", "品質系統", "外包", "過程"],
    "4.2.1":  ["文件", "記錄", "品質手冊", "程序書"],
    "4.2.2":  ["品質手冊"],
    "4.2.3":  ["文件管制", "文件審查", "文件核准", "文件版次", "主清單"],
    "4.2.4":  ["記錄管制", "記錄保存", "記錄保管"],
    "4.2.5":  ["技術文件", "器材主記錄", "設計歷史"],
    "5.6.1":  ["管理審查", "管理階層審查"],
    "6.2":    ["人力資源", "職能", "訓練", "資格", "教育訓練"],
    "6.3":    ["基礎設施", "設施", "設備維護"],
    "7.2.1":  ["顧客要求", "產品要求", "適用法規"],
    "7.3.2":  ["設計輸入", "設計要求"],
    "7.3.5":  ["設計驗證"],
    "7.3.6":  ["設計確認", "臨床評估"],
    "7.4.1":  ["採購", "供應商", "核准供應商"],
    "7.5.3":  ["識別", "追溯", "批號", "唯一器材識別"],
    "7.5.6":  ["製程驗證", "特殊製程"],
    "7.6":    ["量測設備", "校正", "量測管理"],
    "8.2.1":  ["回饋", "顧客回饋", "上市後監視"],
    "8.2.2":  ["抱怨", "客訴", "抱怨處理", "不良事件"],
    "8.2.3":  ["法規通報", "不良事件通報", "主管機關"],
    "8.2.4":  ["內部稽核"],
    "8.3":    ["不符合品", "不符合事項"],
    "8.5.2":  ["矯正措施", "根本原因"],
    "8.5.3":  ["預防措施"],
}

_CLAUSE_KEYWORDS_JA: dict[str, list[str]] = {
    "4.2.3":  ["文書管理", "文書の承認", "文書の版管理", "マスターリスト"],
    "4.2.4":  ["記録管理", "記録の保管"],
    "5.6.1":  ["マネジメントレビュー"],
    "6.2":    ["人的資源", "力量", "トレーニング", "教育訓練"],
    "7.3.2":  ["設計入力", "設計要求事項"],
    "7.4.1":  ["購買", "供給者管理", "承認業者"],
    "7.5.3":  ["識別", "トレーサビリティ"],
    "8.2.1":  ["市販後調査", "フィードバック"],
    "8.2.2":  ["苦情処理", "クレーム", "不具合"],
    "8.2.3":  ["規制当局への報告", "副作用報告"],
    "8.5.2":  ["是正処置", "根本原因分析"],
}

_CLAUSE_KEYWORDS_KO: dict[str, list[str]] = {
    "4.2.3":  ["문서 관리", "문서 승인", "문서 개정"],
    "6.2":    ["인적 자원", "역량", "교육 훈련"],
    "7.3.2":  ["설계 입력", "설계 요구사항"],
    "7.4.1":  ["구매", "공급자 관리"],
    "7.5.3":  ["식별", "추적성"],
    "8.2.1":  ["시판 후 조사", "피드백"],
    "8.2.2":  ["불만 처리", "이상 사례"],
    "8.2.3":  ["규제 기관 보고"],
    "8.5.2":  ["시정 조치", "근본 원인"],
}

_ALL_CLAUSE_KW_DICTS: list[dict] = [
    _CLAUSE_KEYWORDS,
    _CLAUSE_KEYWORDS_ZH,
    _CLAUSE_KEYWORDS_JA,
    _CLAUSE_KEYWORDS_KO,
]

# Multilingual unique-requirement keywords (market access signals)
_UNIQUE_REQ_KEYWORDS_ZH: list[str] = [
    "登記", "許可", "上市", "申請", "核准", "認證",
    "唯一器材識別", "標籤", "標示",
    "不良事件", "上市後監視", "上市後追蹤",
    "授權代理人", "負責人", "本地代理",
    "進口", "輸入", "市場准入",
]

_UNIQUE_REQ_KEYWORDS_JA: list[str] = [
    "認証", "承認", "届出", "申請", "登録",
    "外国製造業者", "選任外国製造業者",
    "副作用報告", "不具合報告",
    "市販後調査", "市販後安全管理",
]

_UNIQUE_REQ_KEYWORDS_KO: list[str] = [
    "허가", "인증", "신고", "등록", "승인",
    "이상 사례", "시판 후 조사",
    "국내 대리인", "수입",
]

_ALL_UNIQUE_REQ_KEYWORDS: list[str] = (
    _UNIQUE_REQ_KEYWORDS
    + _UNIQUE_REQ_KEYWORDS_ZH
    + _UNIQUE_REQ_KEYWORDS_JA
    + _UNIQUE_REQ_KEYWORDS_KO
)


# ============================================================
# Provider & Parameter Helpers
# ============================================================


def _is_local_provider(provider_id: str) -> bool:
    return provider_id.lower() in _LOCAL_PROVIDERS


def _detect_content_language(crawled_texts: list[dict]) -> str:
    """Detect dominant script in crawled content to select safe char limits.

    Samples first 1,000 chars of combined content. Returns 'cjk' if CJK
    characters (Chinese/Japanese/Korean) exceed 20% of sampled chars, else
    'latin'. Arabic script is treated as latin for token estimation purposes
    (Arabic tokenizes similarly to Latin in Gemma).
    """
    sample = ""
    for ct in crawled_texts:
        sample += (ct.get("content_markdown") or "")[:300]
        if len(sample) >= 1000:
            break
    if not sample:
        return "latin"
    cjk_count = sum(
        1 for c in sample
        if (
            "一" <= c <= "鿿"   # CJK Unified Ideographs
            or "぀" <= c <= "ゟ" # Hiragana
            or "゠" <= c <= "ヿ" # Katakana
            or "가" <= c <= "힯" # Hangul Syllables
        )
    )
    return "cjk" if cjk_count / max(len(sample), 1) > 0.20 else "latin"


def _get_model_params(is_local: bool, crawled_texts: list[dict] | None = None) -> dict:
    """Return parameter set based on provider type and detected content language.

    For local models, selects CJK-safe limits (50K chars) or Latin limits (80K)
    based on detected script to avoid context-window overflow with CJK text.
    """
    if not is_local:
        return _CLOUD_PARAMS
    lang = _detect_content_language(crawled_texts or [])
    return _LOCAL_PARAMS_CJK if lang == "cjk" else _LOCAL_PARAMS_LATIN


def _get_batch_keywords(clause_ids: list[str]) -> list[str]:
    """Collect keywords for a batch of ISO 13485 clause IDs (with parent fallback).

    Merges English, Chinese, Japanese, and Korean keyword dicts so paragraph
    scoring works correctly for non-English regulatory text.
    """
    keywords: set[str] = set()
    for kw_dict in _ALL_CLAUSE_KW_DICTS:
        for cid in clause_ids:
            if cid in kw_dict:
                keywords.update(kw_dict[cid])
            parts = cid.split(".")
            for i in range(1, len(parts)):
                parent = ".".join(parts[:i])
                if parent in kw_dict:
                    keywords.update(kw_dict[parent])
    return list(keywords)


def _filter_relevant_paragraphs(text: str, keywords: list[str], max_chars: int) -> str:
    """Return up to max_chars of text, prioritising keyword-matching paragraphs."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        return text[:max_chars]

    kw_lower = [kw.lower() for kw in keywords]
    scored: list[tuple[int, str]] = [
        (sum(1 for kw in kw_lower if kw in p.lower()), p)
        for p in paragraphs
    ]
    scored.sort(key=lambda x: -x[0])

    result: list[str] = []
    total = 0
    for _score, para in scored:
        if total + len(para) + 2 > max_chars:
            break
        result.append(para)
        total += len(para) + 2

    if not result:
        result = [paragraphs[0][:max_chars]]

    return "\n\n".join(result)


def _build_focused_regulatory_text(
    crawled_texts: list[dict],
    clause_keywords: list[str],
    max_chars: int,
) -> str:
    """Build a focused regulatory text excerpt.

    G2 — doc_type-aware char distribution:
      portal       sites are excluded entirely (no regulatory content).
      primary      sites receive 2× weight relative to qms_guidance.
      qms_guidance sites receive 1× weight.

    Direction C: within each site's budget, prioritise keyword-matching
    paragraphs so the LLM sees the most relevant content.
    """
    try:
        from src.services.regulatory_crawler import get_site_doc_type as _gdt
    except ImportError:
        _gdt = None

    # Filter out portal sites; classify remaining
    valid: list[dict] = []
    weights: list[int] = []
    for ct in crawled_texts:
        if not (ct.get("content_markdown") or "").strip():
            continue
        doc_type = ct.get("doc_type") or (_gdt(ct) if _gdt else "primary")
        if doc_type == "portal":
            continue
        valid.append(ct)
        weights.append(2 if doc_type == "primary" else 1)

    if not valid:
        return ""

    _ANCHOR_RATIO = 0.20  # Reserve 20% of budget as structural anchor (preamble/TOC)

    total_weight = sum(weights)
    parts: list[str] = []
    for ct, w in zip(valid, weights):
        site_chars = max(int(max_chars * w / total_weight), 300)
        agency = ct.get("agency", "")
        raw = ct["content_markdown"]

        # Front-load structural anchor: preserve first 20% to retain article hierarchy
        anchor_chars = int(site_chars * _ANCHOR_RATIO)
        body_chars = site_chars - anchor_chars
        anchor = raw[:anchor_chars]
        body_raw = raw[anchor_chars:]
        body = (
            _filter_relevant_paragraphs(body_raw, clause_keywords, body_chars)
            if clause_keywords
            else body_raw[:body_chars]
        )
        excerpt = (anchor + "\n\n" + body) if anchor.strip() else body

        header = f"[{agency}]" if agency else "[Source]"
        parts.append(f"{header}\n{excerpt}")

    return "\n---\n".join(parts)[:max_chars]


# ============================================================
# QMS Relevance Classifier (G2 — P-11/P-16)
# ============================================================

_QMS_GUIDANCE_KEYWORDS = frozenset([
    "quality management", "qms", "document control", "management review",
    "capa", "corrective action", "internal audit", "supplier control",
    "design control", "risk management", "post-market surveillance",
    "vigilance", "udi", "traceability", "notified body", "annex ix",
    "annex xi", "good manufacturing practice", "gmp", "quality system",
    "inspection criteria", "audit procedure", "iso 13485", "manufacturing control",
    "complaint handling", "nonconforming product", "process validation",
])

_NON_QMS_KEYWORDS = frozenset([
    "clinical evaluation only", "ivdr classification", "ecodesign",
    "transition timeline news", "general timeline", "fees schedule",
])


def classify_qms_relevance(title: str, content_preview: str = "") -> str:
    """Three-tier QMS relevance classification.

    Returns: 'qms_relevant' | 'not_relevant' | 'uncertain'
    """
    combined = (title + " " + content_preview[:500]).lower()
    qms_hits = sum(1 for kw in _QMS_GUIDANCE_KEYWORDS if kw in combined)
    non_qms_hits = sum(1 for kw in _NON_QMS_KEYWORDS if kw in combined)
    if qms_hits >= 1 and non_qms_hits == 0:
        return "qms_relevant"
    if non_qms_hits >= 1 and qms_hits == 0:
        return "not_relevant"
    return "uncertain"


# ============================================================
# Supplemental Guidance Analysis (G2 — P-10/MDCG)
# ============================================================


async def analyze_supplemental_guidance(
    region_name: str,
    guidance_texts: list[dict],
    llm_completion_fn: Callable,
    model: str = "default",
    provider_id: str = "ollama",
    is_local_override: Optional[bool] = None,
    max_guidance_docs: int = 5,
) -> list:
    """Analyze supplemental guidance documents for additional QMS requirements.

    For each guidance doc (up to max_guidance_docs most relevant ones), asks LLM:
    'What QMS requirements does this guidance add BEYOND ISO 13485 base requirements?'

    Returns list of UniqueRequirement objects to append to the country's profile.
    """
    from src.analysis.compliance_rules import (
        UniqueRequirement, MappingMethod, MappingStatus,
    )

    if not guidance_texts:
        return []

    is_local = is_local_override if is_local_override is not None else _is_local_provider(provider_id)
    max_chars = 4000 if is_local else 8000

    # Score and rank guidance docs by QMS relevance
    scored: list[tuple[int, dict]] = []
    for ct in guidance_texts:
        title = ct.get("agency", "") + " " + ct.get("url", "")
        preview = (ct.get("content_markdown") or "")[:300]
        rel = classify_qms_relevance(title, preview)
        score = {"qms_relevant": 2, "uncertain": 1, "not_relevant": 0}[rel]
        if score > 0:
            scored.append((score, ct))

    scored.sort(key=lambda x: -x[0])
    selected = [ct for _, ct in scored[:max_guidance_docs]]

    all_reqs: list[UniqueRequirement] = []
    seen_titles: set[str] = set()

    for ct in selected:
        agency = ct.get("agency", "Unknown")
        content = (ct.get("content_markdown") or "")[:max_chars]
        if not content.strip():
            continue

        prompt = f"""You are analyzing regulatory guidance for medical device QMS compliance.

Agency/Document: {agency}
Region: {region_name}

GUIDANCE CONTENT:
{content}

TASK: Identify QMS requirements in this guidance that ADD to or EXCEED the base ISO 13485:2016 requirements.
Focus on concrete requirements that a manufacturer's QMS must address.
Ignore general information, clinical/device-specific requirements, and things already covered by ISO 13485.

Respond with a JSON array (max 5 items). Each item:
{{
  "title_en": "short requirement title (max 60 chars)",
  "requirement_en": "specific QMS requirement description (1-2 sentences)",
  "related_iso_clauses": ["4.2.3", "8.2.2"],
  "audit_impact": "major|minor|informational",
  "source_agency": "{agency}"
}}

If no additional QMS requirements found, return empty array: []"""

        messages = [{"role": "user", "content": prompt}]
        try:
            resp = await llm_completion_fn(
                messages=messages,
                model=model,
                temperature=0.1,
                max_tokens=2048,
                stream=False,
            )
            raw = resp.get("content", "") if isinstance(resp, dict) else str(resp)
            # Extract JSON array
            import re as _re
            m = _re.search(r'\[.*?\]', raw, _re.DOTALL)
            if not m:
                continue
            items = json.loads(m.group())
            for item in items:
                title_key = item.get("title_en", "")[:40].lower()
                if title_key in seen_titles or not title_key:
                    continue
                seen_titles.add(title_key)
                req = UniqueRequirement(
                    req_id=f"{agency.upper().replace('-','_')[:8]}_{len(all_reqs)+1:03d}",
                    regulation_ref=agency,
                    title_en=item.get("title_en", ""),
                    title_zh=item.get("title_zh", item.get("title_en", "")),
                    requirement_en=item.get("requirement_en", ""),
                    requirement_zh=item.get("requirement_zh", ""),
                    related_iso_clauses=item.get("related_iso_clauses", []),
                    audit_impact=item.get("audit_impact", "major"),
                    audit_question_en=f"Does the QMS address: {item.get('title_en','')}?",
                    audit_question_zh=f"QMS 是否涵蓋：{item.get('title_en','')}？",
                    expected_evidence=["Documented procedure", "Records"],
                    rationale_en=f"Required by {agency} guidance for {region_name}",
                    rationale_zh=f"{region_name} {agency} 指引要求",
                    method=MappingMethod.LLM_ANALYSIS,
                    confidence=0.75,
                    is_within_clause_delta=False,
                )
                all_reqs.append(req)
        except Exception as exc:
            logger.warning(f"analyze_supplemental_guidance failed for {agency}: {exc}")

    return all_reqs


# ============================================================
# Public API
# ============================================================


async def analyze_regulation_with_llm(
    region_name: str,
    crawled_texts: list[dict],
    llm_completion_fn: Callable,
    model: str = "default",
    send_progress_fn: Optional[Callable] = None,
    lang: str = "zh-TW",
    provider_id: str = "ollama",
    is_local_override: Optional[bool] = None,
) -> Optional[RegulationProfile]:
    """Analyze crawled regulatory text and generate a RegulationProfile.

    Args:
        region_name: REGION_SITES key, e.g., "新加坡 (Singapore)"
        crawled_texts: List of crawl result dicts, each with keys:
            - region: str
            - agency: str (optional)
            - content_markdown: str
            - url: str (optional)
        llm_completion_fn: LLM completion function matching codebase pattern:
            fn(messages, model, temperature, max_tokens, stream) -> dict
        model: LLM model name
        send_progress_fn: Optional async callback for UI progress messages

    Returns:
        RegulationProfile or None if analysis fails completely
    """
    zh_name, en_name = _extract_region_parts(region_name)
    profile_id = generate_profile_id_from_region(region_name)
    # Solution C: use predefined profile's ISO code as ground truth when available.
    # profile_id[:2] is unreliable for names like "TAIWAN"→"TA" or "JAPAN"→"JA".
    try:
        from src.analysis.compliance_rules import _REGION_TO_PROFILE_STATIC, PREDEFINED_REGULATIONS as _PREDEF
        _pred_id = _REGION_TO_PROFILE_STATIC.get(region_name)
        _pred = _PREDEF.get(_pred_id) if _pred_id else None
        country_code = (_pred.country if (_pred and _pred.country)
                        else (profile_id.split("_")[0] if "_" in profile_id else profile_id[:2]))
    except Exception:
        country_code = profile_id.split("_")[0] if "_" in profile_id else profile_id[:2]

    # is_local_override lets callers (e.g. app.py) pass the provider manager's
    # actual is_local flag, bypassing the static _LOCAL_PROVIDERS name check.
    is_local = is_local_override if is_local_override is not None else _is_local_provider(provider_id)
    _params = _get_model_params(is_local, crawled_texts)
    _batch_size = _params["batch_size"]
    logger.info(
        f"analyze_regulation_with_llm: provider={provider_id} is_local={is_local} "
        f"batch_size={_batch_size} max_tokens_clause={_params['max_tokens_clause']}"
    )

    # Quick emptiness check (Direction B: don't combine yet — text is built per batch)
    if not any((ct.get("content_markdown") or "").strip() for ct in crawled_texts):
        logger.warning(
            f"No crawled text available for {region_name}, skipping analysis"
        )
        return None

    first_url = ""
    for ct in crawled_texts:
        if ct.get("url"):
            first_url = ct["url"]
            break

    if send_progress_fn:
        if lang.startswith("ja"):
            _msg_start = f"🔍 {zh_name} ({en_name}) の規制と ISO 13485 の重複度を分析中..."
        elif lang.startswith("zh"):
            _msg_start = f"🔍 開始分析 {zh_name} ({en_name}) 法規與 ISO 13485 的重疊度..."
        else:
            _msg_start = f"🔍 Analyzing {en_name} regulations vs ISO 13485 clause coverage..."
        await send_progress_fn(_msg_start)

    # ── Step 1: Batch clause mapping ──
    clause_ids = list(ISO_13485_CHECKLIST.keys())
    batches = [
        clause_ids[i : i + _batch_size] for i in range(0, len(clause_ids), _batch_size)
    ]
    total_batches = len(batches)

    iso_mapped: dict[str, ClauseMapping] = {}
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if send_progress_fn:
        if lang.startswith("ja"):
            _msg_batch = (
                f"🔍 ISO 13485 条項を {total_batches} バッチで並行分析中 "
                f"(各 {_batch_size} 条、計 {len(clause_ids)} 条)..."
            )
        elif lang.startswith("zh"):
            _msg_batch = (
                f"🔍 並行分析 {total_batches} 批 ISO 13485 條款 "
                f"(每批 {_batch_size} 條，共 {len(clause_ids)} 條)..."
            )
        else:
            _msg_batch = (
                f"🔍 Running {total_batches} parallel batches across "
                f"{len(clause_ids)} ISO 13485 clauses ({_batch_size} per batch)..."
            )
        await send_progress_fn(_msg_batch)

    # Local servers (Ollama / LM Studio) process requests sequentially.
    # Sending 3 concurrent batches means the 3rd waits 12+ minutes in
    # queue before even starting, reliably triggering the timeout.
    semaphore = asyncio.Semaphore(1 if is_local else _MAX_CONCURRENT_BATCHES)

    async def _run_batch(batch_idx: int, batch: list[str]) -> None:
        batch_clauses = [
            {
                "clause_id": cid,
                "title": ISO_13485_CHECKLIST.get(cid, {}).get("title", ""),
                "audit_question": ISO_13485_CHECKLIST.get(cid, {}).get(
                    "audit_question", ""
                ),
            }
            for cid in batch
        ]

        # Direction B+C: per-batch focused text with clause-specific keywords
        batch_kw = _get_batch_keywords([c["clause_id"] for c in batch_clauses])
        focused_text = _build_focused_regulatory_text(
            crawled_texts, batch_kw, _params["max_regulatory_chars"]
        )
        if is_local:
            messages = _build_clause_batch_prompt_compact(
                batch_clauses, focused_text, zh_name, en_name
            )
        else:
            messages = _build_clause_batch_prompt(
                batch_clauses, focused_text, zh_name, en_name
            )

        for _attempt in range(1 + _MAX_RETRIES_BATCH):
            try:
                async with semaphore:
                    response = await asyncio.to_thread(
                        llm_completion_fn,
                        messages=messages,
                        model=model,
                        temperature=0.1,
                        max_tokens=_params["max_tokens_clause"],
                        stream=False,
                    )
            except Exception as e:
                # asyncio.to_thread itself failed (rare); treat as non-retriable
                logger.error(f"Unexpected exception in batch {batch_idx} (attempt {_attempt + 1}): {e}")
                _fill_batch_fallback(iso_mapped, batch)
                return

            response_text = response.get("content", "")
            usage = response.get("usage", {})
            _accumulate_usage(total_usage, usage)

            # completion() catches all LLM exceptions and returns error dicts —
            # the try/except above never fires for timeouts.  Check the response
            # content for timeout errors and handle retries here instead.
            _is_error = (
                not response_text
                or response_text.startswith("[ERROR]")
                or response.get("all_failed")
            )
            if _is_error:
                _e_str = response_text.lower()
                _is_timeout = "timeout" in _e_str or "timed out" in _e_str
                if _is_timeout and _attempt < _MAX_RETRIES_BATCH:
                    _delay = 2 * (2 ** _attempt)  # 2s, 4s
                    logger.warning(
                        f"Timeout in batch {batch_idx}, retry {_attempt + 1}/{_MAX_RETRIES_BATCH} in {_delay}s"
                    )
                    if send_progress_fn:
                        if lang.startswith("ja"):
                            _retry_msg = f"⏳ バッチ {batch_idx} タイムアウト、{_delay}秒後に再試行 ({_attempt + 1}/{_MAX_RETRIES_BATCH})..."
                        elif lang.startswith("zh"):
                            _retry_msg = f"⏳ 批次 {batch_idx} 逾時，{_delay} 秒後重試 ({_attempt + 1}/{_MAX_RETRIES_BATCH})..."
                        else:
                            _retry_msg = f"⏳ Batch {batch_idx} timed out, retrying in {_delay}s ({_attempt + 1}/{_MAX_RETRIES_BATCH})..."
                        await send_progress_fn(_retry_msg)
                    await asyncio.sleep(_delay)
                    continue
                logger.warning(
                    f"LLM call failed for batch {batch_idx}: "
                    f"{response_text[:200] if response_text else 'empty'}"
                )
                _fill_batch_fallback(iso_mapped, batch)
                return

            parsed = _parse_json_from_response(response_text)
            if parsed and isinstance(parsed, list):
                for item in parsed:
                    cid = item.get("clause_id", "")
                    if cid and cid in ISO_13485_CHECKLIST:
                        # Parse within_clause_deltas if present
                        raw_deltas = item.get("within_clause_deltas", [])
                        deltas = []
                        if isinstance(raw_deltas, list):
                            for didx, dd in enumerate(raw_deltas, 1):
                                if isinstance(dd, dict):
                                    deltas.append(WithinClauseDelta(
                                        delta_id=dd.get("delta_id", f"{profile_id}-WITHIN-{cid}-{didx:03d}"),
                                        iso_clause=cid,
                                        title_en=dd.get("title_en", ""),
                                        title_zh=dd.get("title_zh", ""),
                                        title_ja=dd.get("title_ja", ""),
                                        iso_baseline_en=dd.get("iso_baseline_en", ""),
                                        iso_baseline_zh=dd.get("iso_baseline_zh", ""),
                                        iso_baseline_ja=dd.get("iso_baseline_ja", ""),
                                        country_specific_en=dd.get("country_specific_en", ""),
                                        country_specific_zh=dd.get("country_specific_zh", ""),
                                        country_specific_ja=dd.get("country_specific_ja", ""),
                                        regulation_ref=dd.get("regulation_ref", ""),
                                        original_text=dd.get("original_text", ""),
                                        original_lang=dd.get("original_lang", ""),
                                        english_translation=dd.get("english_translation", ""),
                                        delta_type=dd.get("delta_type", "other"),
                                        audit_impact=dd.get("audit_impact", "major"),
                                        expected_evidence=dd.get("expected_evidence", []),
                                        confidence=min(1.0, max(0.0, float(dd.get("confidence", 0.5)))),
                                    ))

                        iso_mapped[cid] = ClauseMapping(
                            iso_clause=cid,
                            status=_parse_status(item.get("status", "na")),
                            regulation_ref=item.get("regulation_ref", ""),
                            rationale_en=item.get("rationale_en", ""),
                            rationale_zh=item.get("rationale_zh", ""),
                            method=MappingMethod.LLM_ANALYSIS,
                            confidence=min(
                                1.0, max(0.0, float(item.get("confidence", 0.5)))
                            ),
                            notes=item.get("notes", ""),
                            original_text=item.get("original_text", ""),
                            original_lang=item.get("original_lang", ""),
                            english_translation=item.get("english_translation", ""),
                            semantic_note=item.get("semantic_note", ""),
                            within_clause_deltas=deltas,
                        )
            else:
                logger.warning(
                    f"Failed to parse JSON for batch {batch_idx}, using fallback"
                )
                _fill_batch_fallback(iso_mapped, batch)

            if send_progress_fn:
                if lang.startswith("ja"):
                    _batch_done_msg = f"✅ バッチ {batch_idx}/{total_batches} 完了 ({batch[0]}–{batch[-1]})"
                elif lang.startswith("zh"):
                    _batch_done_msg = f"✅ 批次 {batch_idx}/{total_batches} 完成 ({batch[0]}–{batch[-1]})"
                else:
                    _batch_done_msg = f"✅ Batch {batch_idx}/{total_batches} done ({batch[0]}–{batch[-1]})"
                await send_progress_fn(_batch_done_msg)
            return

    await asyncio.gather(
        *[_run_batch(idx, batch) for idx, batch in enumerate(batches, 1)]
    )

    # Fill any missing clauses with NA
    for cid in clause_ids:
        if cid not in iso_mapped:
            iso_mapped[cid] = ClauseMapping(
                iso_clause=cid,
                status=MappingStatus.NOT_APPLICABLE,
                regulation_ref="",
                rationale_en="No mapping data available",
                rationale_zh="無可用的映射資料",
                method=MappingMethod.LLM_ANALYSIS,
                confidence=0.1,
            )

    # ── Step 2: Identify unique requirements ──
    if send_progress_fn:
        if lang.startswith("ja"):
            _msg_unique = f"🔍 {zh_name} ({en_name}) の条款内デルタ要件と独自要件を識別中..."
        elif lang.startswith("zh"):
            _msg_unique = f"🔍 識別 {zh_name} ({en_name}) 的條款內差異與獨有法規要求..."
        else:
            _msg_unique = f"🔍 Identifying within-clause deltas and unique requirements for {en_name}..."
        await send_progress_fn(_msg_unique)

    unique_reqs: list[UniqueRequirement] = []
    _unique_messages: list[dict] = []
    try:
        focused_unique = _build_focused_regulatory_text(
            crawled_texts, _ALL_UNIQUE_REQ_KEYWORDS, _params["max_unique_req_chars"]
        )
        if is_local:
            _unique_messages = _build_unique_requirements_prompt_compact(
                focused_unique, zh_name, en_name, profile_id
            )
        else:
            _unique_messages = _build_unique_requirements_prompt(
                focused_unique, zh_name, en_name, profile_id
            )
    except Exception as e:
        logger.error(f"Failed to build unique requirements prompt: {e}")

    if _unique_messages:
        for _uq_attempt in range(1 + _MAX_RETRIES_BATCH):
            try:
                response = await asyncio.to_thread(
                    llm_completion_fn,
                    messages=_unique_messages,
                    model=model,
                    temperature=0.1,
                    max_tokens=_params["max_tokens_unique"],
                    stream=False,
                )
            except Exception as e:
                logger.error(f"Unexpected exception during unique requirements analysis (attempt {_uq_attempt + 1}): {e}")
                break

            response_text = response.get("content", "")
            usage = response.get("usage", {})
            _accumulate_usage(total_usage, usage)

            # Check for timeout error dicts (completion() swallows exceptions)
            _uq_is_error = (
                not response_text
                or response_text.startswith("[ERROR]")
                or response.get("all_failed")
            )
            if _uq_is_error:
                _e_str = response_text.lower()
                _is_timeout = "timeout" in _e_str or "timed out" in _e_str
                if _is_timeout and _uq_attempt < _MAX_RETRIES_BATCH:
                    _delay = 2 * (2 ** _uq_attempt)
                    logger.warning(f"Timeout during unique requirements analysis, retry {_uq_attempt + 1} in {_delay}s")
                    if send_progress_fn:
                        if lang.startswith("ja"):
                            _uq_retry = f"⏳ 固有要件分析タイムアウト、{_delay}秒後に再試行 ({_uq_attempt + 1}/{_MAX_RETRIES_BATCH})..."
                        elif lang.startswith("zh"):
                            _uq_retry = f"⏳ 獨有要求分析逾時，{_delay} 秒後重試 ({_uq_attempt + 1}/{_MAX_RETRIES_BATCH})..."
                        else:
                            _uq_retry = f"⏳ Unique requirements analysis timed out, retrying in {_delay}s ({_uq_attempt + 1}/{_MAX_RETRIES_BATCH})..."
                        await send_progress_fn(_uq_retry)
                    await asyncio.sleep(_delay)
                    continue
                logger.error(f"Unique requirements analysis failed (attempt {_uq_attempt + 1}): {response_text[:200]}")
                break

            parsed = _parse_json_from_response(response_text)
            if parsed and isinstance(parsed, list):
                for idx, item in enumerate(parsed, 1):
                    req_id = item.get("req_id", f"{profile_id}-{idx:03d}")
                    unique_reqs.append(
                        UniqueRequirement(
                            req_id=req_id,
                            regulation_ref=item.get("regulation_ref", ""),
                            title_en=item.get("title_en", ""),
                            title_zh=item.get("title_zh", ""),
                            requirement_en=item.get("requirement_en", ""),
                            requirement_zh=item.get("requirement_zh", ""),
                            related_iso_clauses=item.get("related_iso_clauses", []),
                            audit_impact=item.get("audit_impact", "major"),
                            audit_question_en=item.get("audit_question_en", ""),
                            audit_question_zh=item.get("audit_question_zh", ""),
                            expected_evidence=item.get("expected_evidence", []),
                            rationale_en=item.get("rationale_en", ""),
                            rationale_zh=item.get("rationale_zh", ""),
                            method=MappingMethod.LLM_ANALYSIS,
                            confidence=min(
                                1.0, max(0.0, float(item.get("confidence", 0.5)))
                            ),
                            original_text=item.get("original_text", ""),
                            original_lang=item.get("original_lang", ""),
                            english_translation=item.get("english_translation", ""),
                            semantic_note=item.get("semantic_note", ""),
                            is_within_clause_delta=item.get("is_within_clause_delta", False),
                            within_clause_delta_vs_iso=item.get("within_clause_delta_vs_iso", ""),
                        )
                    )
            break

    # ── Step 3: Build and save profile ──
    # D-2: compute content_quality based on non-na ratio
    _non_na_count = sum(
        1 for m in iso_mapped.values()
        if m.status != MappingStatus.NOT_APPLICABLE
    )
    _total_clauses = max(len(iso_mapped), 1)
    _non_na_ratio = _non_na_count / _total_clauses
    _fallback_used = any(
        ct.get("content_source") == "pre-written" for ct in crawled_texts
    )
    if _fallback_used:
        _content_quality = "fallback_used"
    elif _non_na_ratio < 0.05:
        _content_quality = "low"
    else:
        _content_quality = "ok"

    profile = RegulationProfile(
        regulation_id=profile_id,
        name_en=f"{en_name} Medical Device QMS Regulation",
        name_zh=f"{zh_name}醫療器材品質管理法規",
        country=country_code,
        country_name_en=en_name,
        country_name_zh=zh_name,
        source="crawled",
        source_url=first_url,
        last_updated=datetime.now().strftime("%Y-%m-%d"),
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
        content_quality=_content_quality,
    )

    try:
        filepath = save_crawled_regulation(profile)
        logger.info(
            f"RegulationProfile saved: {profile_id} → {filepath} "
            f"({len(iso_mapped)} clauses, {len(unique_reqs)} unique reqs, "
            f"{total_usage.get('total_tokens', 0)} tokens used)"
        )
    except Exception as e:
        logger.error(f"Failed to save RegulationProfile for {profile_id}: {e}")

    # ── Upgrade predefined profile if this region maps to one (P-01/P-02/P-03) ──
    try:
        from src.analysis.compliance_rules import (
            _REGION_TO_PROFILE_STATIC,
            get_regulation,
            merge_profiles,
            backup_predefined_profile,
        )
        _predefined_id = _REGION_TO_PROFILE_STATIC.get(region_name)
        if _predefined_id and _predefined_id != profile_id:
            _base = get_regulation(_predefined_id)
            if _base is not None:
                _merged = merge_profiles(_base, profile)
                if _merged is not None:
                    backup_predefined_profile(_predefined_id)
                    _upgraded_path = save_crawled_regulation(_merged, as_id=_predefined_id)
                    logger.info(
                        f"Upgraded predefined profile {_predefined_id} "
                        f"via merge with {profile_id} → {_upgraded_path}"
                    )
                    # Solution B: remove standalone crawled entry from memory so it
                    # does not generate a duplicate country column in the Excel report.
                    from src.analysis.compliance_rules import PREDEFINED_REGULATIONS as _PR
                    if profile_id in _PR and profile_id != _predefined_id:
                        del _PR[profile_id]
                        logger.info(
                            f"Removed standalone crawled entry {profile_id!r} "
                            f"from memory (merged into predefined {_predefined_id!r})"
                        )
                else:
                    logger.info(
                        f"Crawled profile {profile_id} quality below threshold "
                        f"— predefined {_predefined_id} retained unchanged"
                    )
    except Exception as _upg_err:
        logger.warning(f"Profile upgrade step failed for {profile_id}: {_upg_err}")

    # Coverage diagnostic: warn when clauses were missed or N/A ratio is suspiciously high
    _all_clause_ids = set(ISO_13485_CHECKLIST.keys())
    _analyzed_ids = set(iso_mapped.keys())
    _not_analyzed = _all_clause_ids - _analyzed_ids
    _na_count = sum(1 for m in iso_mapped.values() if m.status == MappingStatus.NOT_APPLICABLE)
    _na_ratio = _na_count / max(len(iso_mapped), 1)
    if _not_analyzed:
        logger.warning(
            "[Coverage] %s: %d clauses not analyzed: %s",
            profile_id, len(_not_analyzed), sorted(_not_analyzed),
        )
    if _na_ratio > 0.5:
        logger.warning(
            "[Coverage] %s: N/A ratio %.0f%% unusually high "
            "(possible context truncation — consider re-running with more context or RAG)",
            profile_id, _na_ratio * 100,
        )
    else:
        logger.info(
            "[Coverage] %s: %d/%d clauses analyzed, N/A ratio %.0f%%",
            profile_id, len(_analyzed_ids), len(_all_clause_ids), _na_ratio * 100,
        )

    if send_progress_fn:
        mapped_count = sum(
            1 for m in iso_mapped.values() if m.status != MappingStatus.NOT_APPLICABLE
        )
        _type1_reqs = [r for r in unique_reqs if not r.is_within_clause_delta]
        _type2_reqs = [r for r in unique_reqs if r.is_within_clause_delta]

        # ── TYPE 2 detail lines (two sources) ───────────────────────────────
        # Source A: WithinClauseDelta inside ClauseMapping (status=exceeds)
        _t2_lines: list[str] = []
        for _cid in sorted(iso_mapped.keys()):
            for _wd in iso_mapped[_cid].within_clause_deltas:
                if lang.startswith("ja"):
                    _t = _wd.title_ja or _wd.title_en or _wd.title_zh
                    _spec = (_wd.country_specific_ja or _wd.country_specific_en or "")
                elif lang.startswith("zh"):
                    _t = _wd.title_zh or _wd.title_en
                    _spec = (_wd.country_specific_zh or _wd.country_specific_en or "")
                else:
                    _t = _wd.title_en or _wd.title_zh
                    _spec = _wd.country_specific_en or ""
                _spec_s = (_spec[:65] + "…") if len(_spec) > 65 else _spec
                _t2_lines.append(f"    - {_cid} ── {_t}" + (f"（{_spec_s}）" if _spec_s else ""))
        # Source B: UniqueRequirement with is_within_clause_delta=True
        for _r in _type2_reqs:
            if lang.startswith("zh"):
                _t = _r.title_zh or _r.title_en
            else:
                _t = _r.title_en or _r.title_zh
            _clauses = ", ".join(_r.related_iso_clauses[:4]) if _r.related_iso_clauses else "?"
            _delta = _r.within_clause_delta_vs_iso or ""
            _delta_s = (_delta[:65] + "…") if len(_delta) > 65 else _delta
            _t2_lines.append(f"    - [{_clauses}] {_t}" + (f"：{_delta_s}" if _delta_s else ""))

        _t2_total = len(_t2_lines)
        _t2_show = _t2_lines  # show all items, no cap

        # ── TYPE 1 detail lines ─────────────────────────────────────────────
        _impact_icon = {"critical": "🔴", "major": "🟡", "minor": "🟢"}
        _t1_lines: list[str] = []
        for _r in _type1_reqs:
            if lang.startswith("zh"):
                _t = _r.title_zh or _r.title_en
            else:
                _t = _r.title_en or _r.title_zh
            _icon = _impact_icon.get(_r.audit_impact, "⚪")
            _ref = f" ({_r.regulation_ref})" if _r.regulation_ref else ""
            _t1_lines.append(f"    {_icon} {_t}{_ref}")
        _t1_total = len(_t1_lines)
        _t1_show = _t1_lines  # show all items, no cap

        # ── Assemble final message ───────────────────────────────────────────
        if lang.startswith("ja"):
            _msg_lines = [
                f"✅ {zh_name} ({en_name}) 分析完了：",
                f"  • ISO 13485 マッピング：{mapped_count}/{len(clause_ids)} 条",
            ]
            if _t2_show:
                _msg_lines.append(f"  • TYPE 2 ── ISO より厳格・追加要件（{_t2_total} 件）、対象条項：")
                _msg_lines.extend(_t2_show)
            else:
                _msg_lines.append(f"  • TYPE 2 ── ISO より厳格・追加要件：0 件")
            if _t1_show:
                _msg_lines.append(f"  • TYPE 1 ── ISO 13485 以外の独自要件（{_t1_total} 件）：")
                _msg_lines.extend(_t1_show)
            else:
                _msg_lines.append(f"  • TYPE 1 ── ISO 13485 以外の独自要件：0 件")
            _msg_lines.append(f"  • トークン使用量：{total_usage.get('total_tokens', 0):,}")
        elif lang.startswith("zh"):
            _msg_lines = [
                f"✅ {zh_name} ({en_name}) 法規分析完成：",
                f"  • ISO 13485 對應：{mapped_count}/{len(clause_ids)} 條",
            ]
            if _t2_show:
                _msg_lines.append(f"  • TYPE 2 ── 比 ISO 13485 更嚴格的特殊要求（{_t2_total} 項），涉及條款：")
                _msg_lines.extend(_t2_show)
            else:
                _msg_lines.append(f"  • TYPE 2 ── 比 ISO 13485 更嚴格的特殊要求：0 項")
            if _t1_show:
                _msg_lines.append(f"  • TYPE 1 ── 獨立於 ISO 13485 以外的要求（{_t1_total} 項）：")
                _msg_lines.extend(_t1_show)
            else:
                _msg_lines.append(f"  • TYPE 1 ── 獨立於 ISO 13485 以外的要求：0 項")
            _msg_lines.append(f"  • Token 用量：{total_usage.get('total_tokens', 0):,}")
        else:
            _msg_lines = [
                f"✅ {en_name} analysis complete:",
                f"  • ISO 13485 mappings: {mapped_count}/{len(clause_ids)} clauses",
            ]
            if _t2_show:
                _msg_lines.append(f"  • TYPE 2 — stricter/additional vs ISO 13485 ({_t2_total} items), affecting clauses:")
                _msg_lines.extend(_t2_show)
            else:
                _msg_lines.append(f"  • TYPE 2 — stricter/additional vs ISO 13485: 0 items")
            if _t1_show:
                _msg_lines.append(f"  • TYPE 1 — independent of ISO 13485 ({_t1_total} items):")
                _msg_lines.extend(_t1_show)
            else:
                _msg_lines.append(f"  • TYPE 1 — independent of ISO 13485: 0 items")
            _msg_lines.append(f"  • Tokens used: {total_usage.get('total_tokens', 0):,}")

        await send_progress_fn("\n".join(_msg_lines))

    return profile


# ============================================================
# Prompt Builders — Compact (local models: smaller context, lower token budget)
# ============================================================


def _build_clause_batch_prompt_compact(
    clauses: list[dict],
    regulatory_text: str,
    country_zh: str,
    country_en: str,
) -> list[dict]:
    """Compact clause-batch prompt for local models (~200 token system prompt vs ~900)."""
    clause_list = "\n".join(f"- {c['clause_id']}: {c['title']}" for c in clauses)
    clause_ids_str = ", ".join(c["clause_id"] for c in clauses)

    system_prompt = (
        "You are a medical device QMS regulatory specialist.\n"
        "Analyze how a country's medical device regulation maps to ISO 13485:2016 clauses.\n\n"
        "Status values:\n"
        '- "full": covers ALL requirements of the ISO clause\n'
        '- "partial": covers main intent but misses sub-requirements\n'
        '- "exceeds": stricter or additional requirements beyond ISO 13485\n'
        '- "na": no evidence in the provided text\n\n'
        "Rules:\n"
        "1. Base ALL analysis ONLY on the provided regulatory text.\n"
        "2. Cite the specific article/section for each finding.\n"
        "3. Set confidence < 0.4 when text evidence is insufficient.\n"
        "4. Populate within_clause_deltas ONLY for \"exceeds\" status; leave [] otherwise.\n\n"
        "Output ONLY a valid JSON array. Each element:\n"
        "{\n"
        '  "clause_id": "4.1",\n'
        '  "status": "full|partial|na|exceeds",\n'
        '  "regulation_ref": "Article/Section reference",\n'
        '  "rationale_en": "Evidence-based explanation citing specific text",\n'
        '  "rationale_zh": "中文說明，引用具體法規條文",\n'
        '  "original_text": "Direct quote from regulatory text",\n'
        '  "original_lang": "language code",\n'
        '  "english_translation": "English translation if not English",\n'
        '  "semantic_note": "Terminology or scope notes",\n'
        '  "confidence": 0.8,\n'
        '  "within_clause_deltas": []\n'
        "}"
    )

    user_prompt = (
        f"Country: {country_zh} ({country_en})\n\n"
        f"Clauses to analyze ({len(clauses)}): {clause_ids_str}\n"
        f"{clause_list}\n\n"
        f"Regulatory text:\n```\n{regulatory_text}\n```\n\n"
        f"Output JSON array for all {len(clauses)} clauses. "
        f'If evidence is absent set status "na" and confidence 0.25.'
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_unique_requirements_prompt_compact(
    regulatory_text: str,
    country_zh: str,
    country_en: str,
    profile_id: str,
) -> list[dict]:
    """Compact unique-requirements prompt for local models."""
    system_prompt = (
        "You are a medical device QMS specialist.\n"
        "Identify requirements in a country's medical device regulation that go "
        "BEYOND ISO 13485:2016 — items a manufacturer already certified to ISO 13485 "
        "would STILL need to address separately for market access.\n\n"
        "Two types:\n"
        "TYPE 1 (is_within_clause_delta: false): No equivalent in ISO 13485 at all.\n"
        "TYPE 2 (is_within_clause_delta: true): ISO covers the area but this country "
        "is stricter or more specific (e.g. numeric deadlines, mandatory forms).\n\n"
        "Rules:\n"
        "1. Base ALL analysis STRICTLY on the provided text.\n"
        "2. Set confidence < 0.4 when text evidence is insufficient.\n"
        "3. Output at most 8 requirements; prioritise critical then major audit_impact.\n\n"
        "Output ONLY a valid JSON array. Each element:\n"
        "{\n"
        f'  "req_id": "{profile_id}-001",\n'
        '  "regulation_ref": "Article/Section",\n'
        '  "title_en": "Short English title",\n'
        '  "title_zh": "中文標題",\n'
        '  "requirement_en": "Full requirement description in English",\n'
        '  "requirement_zh": "完整中文需求描述",\n'
        '  "related_iso_clauses": ["8.2.3"],\n'
        '  "audit_impact": "critical|major|minor",\n'
        '  "audit_question_en": "Audit verification question",\n'
        '  "audit_question_zh": "稽核驗證問題",\n'
        '  "expected_evidence": ["Document or record"],\n'
        '  "rationale_en": "Why unique to this country",\n'
        '  "rationale_zh": "為何獨有",\n'
        '  "original_text": "Verbatim regulatory text",\n'
        '  "original_lang": "language code",\n'
        '  "english_translation": "Translation if needed",\n'
        '  "semantic_note": "Practical impact on manufacturers",\n'
        '  "confidence": 0.75,\n'
        '  "is_within_clause_delta": false,\n'
        '  "within_clause_delta_vs_iso": "ISO says X, this country says Y (TYPE 2 only)"\n'
        "}\n\n"
        "Output [] if no unique requirements found."
    )

    user_prompt = (
        f"Country: {country_zh} ({country_en})\n\n"
        f"Regulatory text:\n```\n{regulatory_text}\n```\n\n"
        f"Identify all requirements beyond ISO 13485 for {country_en} market access.\n"
        f'Use "{profile_id}-NNN" format for req_id (e.g. {profile_id}-001).\n'
        f"Output JSON array now:"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ============================================================
# Prompt Builders — Full (cloud models: large context, high token budget)
# ============================================================


def _build_clause_batch_prompt(
    clauses: list[dict],
    regulatory_text: str,
    country_zh: str,
    country_en: str,
) -> list[dict]:
    """Build LLM messages for analyzing a batch of ISO 13485 clauses."""

    clause_list = "\n".join(f"- {c['clause_id']}: {c['title']}" for c in clauses)
    clause_ids_str = ", ".join(c["clause_id"] for c in clauses)

    system_prompt = (
        "You are a senior medical device regulatory affairs specialist with extensive "
        "experience in ISO 13485:2016 audits, MDSAP (Medical Device Single Audit Program) "
        "multi-country assessments, and cross-jurisdictional QMS comparisons. "
        "You have conducted regulatory audits in Asia-Pacific, EU, and North America.\n\n"
        "Your task: Determine how a country's medical device regulation maps to ISO 13485 "
        "clauses. Apply the MDSAP audit principle: distinguish between regulations that "
        "MENTION a requirement versus those that SUBSTANTIVELY IMPLEMENT it.\n\n"
        "CRITICAL ANALYSIS RULES (from ISO 13485:2016 audit practice):\n"
        "1. Language plausibility ≠ legal correctness: a regulation may use similar "
        "   terminology but differ in scope, applicability threshold, or enforcement.\n"
        "2. Always cite the SPECIFIC article or section from the provided regulatory text.\n"
        "3. If a regulatory concept is functionally equivalent but uses different terminology "
        "   (e.g., 'product dossier' vs 'design history file'), note this as 'full' with a "
        "   semantic_note explaining the terminology difference.\n"
        "4. 'partial' = regulation covers the intent but omits ≥1 substantive sub-requirement.\n"
        "5. Set confidence < 0.4 when the crawled text is insufficient — do NOT infer from "
        "   general regulatory knowledge; base analysis ONLY on the provided text.\n\n"
        "STEP-BY-STEP REASONING for each clause:\n"
        "  Step 1: Search the regulatory text for explicit mention of the clause topic.\n"
        "  Step 2: Check if functionally equivalent requirements exist under different terms.\n"
        "  Step 3: Assess completeness — does it cover all sub-requirements of the clause?\n"
        "  Step 4: Assign status and calibrate confidence based on text evidence quality.\n\n"
        "For each clause, determine the mapping status:\n"
        '- "full": Regulation substantively covers ALL requirements of the ISO 13485 clause\n'
        '- "partial": Covers the main intent but omits ≥1 sub-requirement or has scope gaps\n'
        '- "exceeds": Has STRICTER or ADDITIONAL requirements beyond ISO 13485\n'
        '- "na": No evidence of coverage in the provided regulatory text\n\n'
        "Output ONLY a valid JSON array. No markdown, no explanation outside JSON.\n"
        "Each element must have these fields:\n"
        "{\n"
        '  "clause_id": "4.1",\n'
        '  "status": "full|partial|na|exceeds",\n'
        '  "regulation_ref": "Specific Article/Section reference (e.g., Art. 15, §3.2)",\n'
        '  "rationale_en": "Evidence-based explanation citing specific regulatory text",\n'
        '  "rationale_zh": "中文說明，引用具體法規條文",\n'
        '  "original_text": "Direct quote from regulatory text in native language",\n'
        "  \"original_lang\": \"Language code (e.g., 'en', 'zh', 'ko', 'ms', 'th')\",\n"
        '  "english_translation": "English translation if original is not English",\n'
        '  "semantic_note": "Terminology differences, scope nuances, implementation gaps",\n'
        '  "confidence": 0.8,\n'
        '  "within_clause_deltas": [\n'
        '    {\n'
        '      "delta_id": "{profile_id}-WITHIN-{clause_id}-001",\n'
        '      "title_en": "Short English title of the specific difference",\n'
        '      "title_zh": "中文簡短標題",\n'
        '      "title_ja": "日本語の短いタイトル",\n'
        '      "iso_baseline_en": "What ISO 13485 requires (one sentence)",\n'
        '      "iso_baseline_zh": "ISO 13485 的要求（一句話）",\n'
        '      "iso_baseline_ja": "ISO 13485 が要求する内容（一文）",\n'
        '      "country_specific_en": "What this country requires instead/additionally",\n'
        '      "country_specific_zh": "該國的特殊要求",\n'
        '      "country_specific_ja": "この国固有の要件",\n'
        '      "regulation_ref": "Specific article/section",\n'
        '      "original_text": "Verbatim regulatory text",\n'
        '      "original_lang": "language code",\n'
        '      "english_translation": "English translation if needed",\n'
        '      "delta_type": "stricter_timeline|additional_form|local_authority_specific|scope_extension|other",\n'
        '      "audit_impact": "critical|major|minor",\n'
        '      "expected_evidence": ["list of auditable documents"],\n'
        '      "confidence": 0.8\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        "IMPORTANT: Populate `within_clause_deltas` ONLY when `status == \"exceeds\"` AND you can "
        "identify the specific way the country is stricter. Leave as empty array `[]` for "
        "full/partial/na. Do NOT infer — base strictly on provided text.\n\n"
        "Example output:\n"
        "[\n"
        "  {\n"
        '    "clause_id": "4.1",\n'
        '    "status": "full",\n'
        '    "regulation_ref": "Section 3, Article 5 of Medical Device Act",\n'
        '    "rationale_en": "Article 5 explicitly requires establishment of a QMS covering '
        'all product lifecycle phases, directly equivalent to ISO 13485:2016 Clause 4.1 scope. '
        'All four sub-requirements (processes, interactions, outsourced processes, documentation) '
        'are addressed in Articles 5-7.",\n'
        '    "rationale_zh": "第5條明確要求建立涵蓋產品全生命週期的品質管理系統，直接對應 ISO 13485:2016 第4.1條，'
        '四項子要求均在第5至7條中得到涵蓋。",\n'
        '    "original_text": "제조업자는 품질경영시스템을 수립하고...",\n'
        '    "original_lang": "ko",\n'
        '    "english_translation": "Manufacturers shall establish a quality management system '
        'covering all phases of the product lifecycle...",\n'
        '    "semantic_note": "Uses \'lifecycle QMS\' terminology vs ISO 13485 \'product realization\'; '
        'functionally equivalent. Outsourced process control (4.1.6) confirmed in Article 7.",\n'
        '    "confidence": 0.88\n'
        "  }\n"
        "]"
    )

    user_prompt = (
        f"## Country: {country_zh} ({country_en})\n\n"
        f"## ISO 13485 Clauses to Analyze:\n{clause_list}\n\n"
        f"## Crawled Regulatory Text from {country_en}:\n"
        f"```\n{regulatory_text}\n```\n\n"
        f"Analyze how {country_en}'s regulation substantively covers each of these "
        f"ISO 13485 clauses: {clause_ids_str}\n\n"
        f"IMPORTANT: Base ALL analysis strictly on the regulatory text provided above. "
        f"Do NOT rely on general knowledge about {country_en}'s regulatory system.\n"
        f"For each clause, follow the 4-step reasoning process in your instructions.\n"
        f"If the text lacks sufficient evidence for a clause, "
        f'set status to "na", confidence to 0.25, and note "Insufficient evidence in crawled text".\n\n'
        f"Output the JSON array now:"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_unique_requirements_prompt(
    regulatory_text: str,
    country_zh: str,
    country_en: str,
    profile_id: str,
) -> list[dict]:
    """Build LLM messages for identifying unique/delta requirements."""

    system_prompt = (
        "You are a senior medical device regulatory affairs specialist with MDSAP "
        "multi-country audit experience and deep expertise in identifying country-specific "
        "regulatory delta requirements beyond ISO 13485.\n\n"
        "Your task: Identify requirements in a country's regulation that go BEYOND "
        "what ISO 13485:2016 requires. These are the DELTA items — country-specific "
        "requirements that a manufacturer fully certified to ISO 13485 would STILL need "
        "to satisfy separately for market access in this country.\n\n"
        "REQUIREMENT CATEGORIES — output ALL three types as separate JSON objects:\n\n"
        "TYPE 1 — FULLY OUTSIDE ISO 13485 (is_within_clause_delta: false):\n"
        "   Requirements the country imposes that have NO equivalent in ISO 13485 at all.\n"
        "   Examples: device registration/listing with a government authority, local authorized\n"
        "   representative mandate, import permits, country-specific UDI registry enrollment.\n"
        "   -> Set is_within_clause_delta: false\n\n"
        "TYPE 2 — WITHIN-CLAUSE DELTA (is_within_clause_delta: true):\n"
        "   ISO 13485 already requires something in this area, but this country imposes\n"
        "   a STRICTER or MORE SPECIFIC version: a numeric deadline, a mandatory government\n"
        "   form, a local authority notification step, or an extended scope threshold.\n"
        "   Examples: \"adverse event reporting within 7 working days\" (ISO just says promptly),\n"
        "   \"PMS summary report every 2 years\" (ISO does not specify frequency),\n"
        "   \"labeling must include local registration number\" (ISO only requires general labeling).\n"
        "   -> Set is_within_clause_delta: true, and populate related_iso_clauses with the\n"
        "     overlapping ISO clause(s).\n\n"
        "TYPE 3 — LANGUAGE PLAUSIBILITY ONLY (do NOT output):\n"
        "   Regulation uses similar terminology but imposes no substantive additional obligation.\n"
        "   -> Do NOT output these.\n\n"
        "CRITICAL: Do NOT skip TYPE 2 items because they overlap with ISO 13485 clauses.\n"
        "Both TYPE 1 and TYPE 2 must be captured — they represent different compliance risks.\n\n"
        "ADDITIONAL ANALYSIS RULES:\n"
        "1. Language plausibility ≠ legal obligation: a country's regulation may "
        "   MENTION a concept (e.g., UDI, PSUR) without imposing a substantive, "
        "   enforceable requirement. Do NOT flag a mention as a unique requirement.\n"
        "2. Base ALL analysis STRICTLY on the regulatory text provided. Do NOT "
        "   infer requirements from general knowledge about this country's regulatory "
        "   system — that knowledge may be outdated or jurisdiction-incorrect.\n"
        "3. Confidence calibration (base on text evidence quality, not assumption):\n"
        "   - 0.8-1.0: Explicit statutory article with clear obligation and penalty\n"
        "   - 0.5-0.7: Implied requirement or indirect reference with partial evidence\n"
        "   - 0.3-0.5: Regulatory intent unclear; text evidence limited\n"
        "   - < 0.3: Very limited crawled text — flag as insufficient evidence\n\n"
        "ANALYSIS APPROACH (apply for each unique requirement found):\n"
        "1. First determine: Is this requirement already covered by ISO 13485?\n"
        "   If YES → skip it (not a delta item).\n"
        "2. Check: Does this requirement impose a specific procedural, documentary, or "
        "   timeline obligation not present in ISO 13485?\n"
        "3. Assess audit_impact: 'critical' = market access blocked without it; "
        "   'major' = audit finding likely; 'minor' = best practice gap.\n"
        "4. Provide specific, auditable expected_evidence — what a MDSAP auditor "
        "   would physically inspect to verify compliance.\n\n"
        "Common categories of unique requirements:\n"
        "- Country-specific device registration/listing/notification requirements\n"
        "- Local authorized representative or agent requirements\n"
        "- Language/labeling requirements (local language mandatory fields)\n"
        "- Unique adverse event/vigilance reporting timelines (e.g., 15 vs 30 days)\n"
        "- Country-specific clinical data or performance study requirements\n"
        "- Post-market surveillance reporting frequency unique to the country\n"
        "- Import/export permits or customs documentation\n"
        "- Unique classification system or risk class mapping differences\n"
        "- Periodic safety update report (PSUR) requirements\n"
        "- Unique UDI/device traceability system requirements\n\n"
        "Output ONLY a valid JSON array. No markdown, no explanation outside JSON.\n"
        "Each element must have these fields:\n"
        "{\n"
        f'  "req_id": "{profile_id}-001",\n'
        '  "regulation_ref": "Article/Section reference",\n'
        '  "title_en": "Short English title",\n'
        '  "title_zh": "中文簡短標題",\n'
        '  "requirement_en": "Full requirement description in English",\n'
        '  "requirement_zh": "完整的中文需求描述",\n'
        '  "related_iso_clauses": ["4.2.3", "7.1"],\n'
        '  "audit_impact": "critical|major|minor",\n'
        '  "audit_question_en": "Audit question to verify compliance",\n'
        '  "audit_question_zh": "用於驗證合規性的稽核問題",\n'
        '  "expected_evidence": ["Document or record expected"],\n'
        '  "rationale_en": "Why this is unique to this country",\n'
        '  "rationale_zh": "為何此要求為該國獨有",\n'
        '  "original_text": "Original regulatory text in native language",\n'
        '  "original_lang": "Language code",\n'
        '  "english_translation": "English translation if not English",\n'
        '  "semantic_note": "Practical impact on manufacturers",\n'
        '  "confidence": 0.75,\n'
        '  "is_within_clause_delta": false,\n'
        '  "within_clause_delta_vs_iso": "Brief statement: ISO says X, this country says Y (only for TYPE 2)"\n'
        "}\n\n"
        "If no unique requirements are found, output an empty array: []\n"
        "Typically, most countries have 3-10 unique requirements beyond ISO 13485.\n"
        "If the crawled text is insufficient to identify requirements confidently, "
        "set confidence < 0.4 and note the limitation in semantic_note."
    )

    user_prompt = (
        f"## Country: {country_zh} ({country_en})\n\n"
        f"## Crawled Regulatory Text:\n"
        f"```\n{regulatory_text}\n```\n\n"
        f"IMPORTANT: Base ALL analysis STRICTLY on the regulatory text provided above. "
        f"Do NOT rely on general knowledge about {country_en}'s regulatory system — "
        f"use only requirements explicitly stated in the crawled text.\n"
        f"If the text lacks sufficient evidence for a specific requirement, "
        f'set confidence below 0.4 and note "Insufficient evidence in crawled text" '
        f"in semantic_note.\n\n"
        f"Identify ALL requirements in {country_en}'s medical device regulation "
        f"that go BEYOND ISO 13485. Focus on country-specific requirements that "
        f"a manufacturer certified to ISO 13485 would still need to address "
        f"separately for {country_en} market access.\n\n"
        f'Use "{profile_id}-NNN" format for req_id (e.g., {profile_id}-001).\n\n'
        f"Output the JSON array now:"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ============================================================
# Parsing Helpers
# ============================================================


def _parse_json_from_response(text: str) -> list | dict | None:
    """Extract and parse JSON from LLM response text.

    Handles:
    - Pure JSON
    - JSON wrapped in ```json ... ``` code blocks
    - JSON preceded/followed by explanatory text
    """
    if not text:
        return None

    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    code_block_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON array in text
    bracket_match = re.search(r"\[[\s\S]*\]", text)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in text
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        try:
            result = json.loads(brace_match.group(0))
            # Wrap single object in list for consistency
            return [result] if isinstance(result, dict) else result
        except json.JSONDecodeError:
            pass

    # Strategy 5: truncated array recovery — find last complete object
    first_bracket = text.find('[')
    last_brace = text.rfind('}')
    if first_bracket >= 0 and last_brace > first_bracket:
        try:
            candidate = text[first_bracket:last_brace + 1] + ']'
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    logger.warning(f"Failed to parse JSON from response: {text[:200]}...")
    return None


def _parse_status(status_str: str) -> MappingStatus:
    """Parse a status string into MappingStatus enum."""
    status_map = {
        "full": MappingStatus.FULL,
        "partial": MappingStatus.PARTIAL,
        "na": MappingStatus.NOT_APPLICABLE,
        "not_applicable": MappingStatus.NOT_APPLICABLE,
        "exceeds": MappingStatus.EXCEEDS,
    }
    return status_map.get(status_str.lower().strip(), MappingStatus.NOT_APPLICABLE)


def _extract_region_parts(region_name: str) -> tuple[str, str]:
    """Extract (zh_name, en_name) from region format like '新加坡 (Singapore)'.

    Returns:
        Tuple of (Chinese name, English name)
    """
    if " (" in region_name and region_name.endswith(")"):
        zh_name = region_name.split(" (")[0]
        en_name = region_name.split("(")[1].rstrip(")")
        return zh_name, en_name
    return region_name, region_name


def _combine_crawled_texts(crawled_texts: list[dict]) -> str:
    """Combine multiple crawled text entries into a single regulatory document."""
    parts = []
    for ct in crawled_texts:
        if not ct.get("content_markdown"):
            continue
        agency = ct.get("agency", "")
        url = ct.get("url", "")
        header = f"### Source: {agency}" if agency else "### Source"
        if url:
            header += f" ({url})"
        parts.append(f"{header}\n{ct['content_markdown']}")
    return "\n\n---\n\n".join(parts)


def _fill_batch_fallback(
    iso_mapped: dict[str, ClauseMapping],
    batch: list[str],
) -> None:
    """Fill a batch of clauses with NA fallback when LLM fails."""
    for cid in batch:
        if cid not in iso_mapped:
            iso_mapped[cid] = ClauseMapping(
                iso_clause=cid,
                status=MappingStatus.NOT_APPLICABLE,
                regulation_ref="",
                rationale_en="LLM analysis failed for this clause",
                rationale_zh="此條款的 LLM 分析失敗",
                method=MappingMethod.LLM_ANALYSIS,
                confidence=0.1,
            )


def _accumulate_usage(total: dict, usage: dict) -> None:
    """Accumulate token usage from an LLM response."""
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        total[key] = total.get(key, 0) + usage.get(key, 0)
