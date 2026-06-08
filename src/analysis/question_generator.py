"""
AI-QMS — Dynamic Audit Question Generator (Side B)
===================================================

Generates LLM-based audit questions for critical-impact clauses.
Used in the hybrid A/B question strategy:

  Side A (70%): Static questions from ISO_13485_CHECKLIST (major/minor clauses)
  Side B (30%): LLM-generated questions (critical clauses only)

Routing logic (get_audit_question_hybrid):
  - audit_impact == "critical"  → try B first, fallback to A on validation failure
  - audit_impact == "major"     → always A
  - audit_impact == "minor"     → always A

Quality gate: generated questions must satisfy ALL of:
  1. question_zh is 50–300 characters
  2. Contains ISO 13485 clause number pattern (e.g. §7.5.3) or "ISO 13485"
  3. regulation_refs list is non-empty

If any condition fails → automatic fallback to Side A.

i18n
----
The system prompt and user template are fully localized for ``zh`` / ``en`` /
``ja``.  Any other language code falls back to English (per project
convention).  The IFU full-content extractor (`_extract_ifu_context`) supplies
product, regulatory and manufacturing context that gets formatted into the
user template — no 800-char truncation is applied to IFU documents anymore.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from src.analysis.compliance_rules import ISO_13485_CHECKLIST, get_audit_question

logger = logging.getLogger(__name__)

__all__ = [
    "generate_question_b",
    "validate_question_b",
    "get_audit_question_hybrid",
    "SIDE_B_SYSTEM_PROMPTS",
    "SIDE_B_USER_TEMPLATES",
]


# ============================================================
# Language helper
# ============================================================

from src.chainlit_app.lang_config import lang_key as _lang_key  # noqa: E402


# ============================================================
# Side B — LLM system prompts (multilingual)
# ============================================================

SIDE_B_SYSTEM_PROMPTS: dict[str, str] = {
    "zh": """你是 ISO 13485:2016 醫療器材品質管理系統的資深稽核員，具備 MDSAP 主導員資格。
你的任務：根據提供的條款資訊與文件摘要，生成一個**高品質、可驗證**的稽核問題。
問題必須滿足以下所有條件：
1. **引用具體法規條號**：必須包含 ISO 13485:2016 條款編號（如「依 ISO 13485:2016 §7.5.3」）
2. **可驗證性**：問題必須能透過查看實際文件、記錄或程序來回答（不能是概念性問題）
3. **針對文件內容**：根據提供的文件摘要，聚焦於該文件最可能存在合規落差的面向
4. **具體查核點**：問題應指明「由誰執行、頻率、紀錄方式」等其中至少一項
5. **長度**：50–200 字之間
6. **避免重複**：不得與「現有標準問題」完全相同
7. **產品屬性**：考量文件所述的醫療器材類別、預期用途與製造要求
回答**只能**使用以下 JSON 格式，不要包含任何其他文字：
{
  "question_zh": "稽核問題（繁體中文）",
  "question_en": "Audit question (English)",
  "regulation_refs": ["ISO 13485:2016 §X.X.X"],
  "focus_area": "此問題聚焦的合規面向（一句話）",
  "verifiable_by": "可透過哪類文件/記錄驗證（一句話）"
}""",
    "en": """You are a senior auditor for ISO 13485:2016 Medical Device Quality Management Systems with MDSAP Lead Auditor qualification.
Your task: Based on the clause information and document content provided, generate one **high-quality, verifiable** audit question.
The question MUST meet ALL of the following criteria:
1. **Cite specific regulatory clause**: Must include an ISO 13485:2016 clause number (e.g. "per ISO 13485:2016 §7.5.3")
2. **Verifiability**: The question must be answerable by reviewing actual documents, records, or procedures (not conceptual)
3. **Document-specific**: Based on the document content, focus on the compliance gap most likely present in this document
4. **Specific audit checkpoint**: The question should specify at least one of: who performs it, frequency, or recording method
5. **Length**: 50–200 words
6. **Avoid duplication**: Must not be identical to the "existing standard question"
7. **Product attributes**: Consider the medical device class, intended use, and manufacturing requirements described
Respond **only** using the following JSON format, no other text:
{
  "question_zh": "稽核問題（繁體中文）",
  "question_en": "Audit question (English)",
  "regulation_refs": ["ISO 13485:2016 §X.X.X"],
  "focus_area": "Compliance aspect this question focuses on (one sentence)",
  "verifiable_by": "Type of document/record that can verify this (one sentence)"
}""",
    "ja": """あなたはISO 13485:2016医療機器品質マネジメントシステムの上級監査員であり、MDSAPリード監査員の資格を持っています。
タスク：提供された条項情報と文書内容に基づき、**高品質で検証可能な**監査質問を1つ生成してください。
質問は以下の全条件を満たす必要があります：
1. **具体的な規制条項番号の引用**：ISO 13485:2016の条項番号を含むこと（例：「ISO 13485:2016 §7.5.3に基づき」）
2. **検証可能性**：実際の文書、記録、手順書を確認することで回答可能な質問（概念的な質問は不可）
3. **文書特化**：提供された文書内容に基づき、コンプライアンスギャップが最も生じやすい側面に焦点を当てる
4. **具体的な監査チェックポイント**：誰が実施するか、頻度、記録方法のうち少なくとも1つを明示
5. **長さ**：50〜200字（日本語）
6. **重複回避**：「既存の標準質問」と完全に同じにしないこと
7. **製品属性**：文書に記載された医療機器のクラス、意図された使用目的、製造要件を考慮
回答は**以下のJSON形式のみ**を使用し、他のテキストは含めないこと：
{
  "question_zh": "稽核問題（繁體中文）",
  "question_en": "Audit question (English)",
  "regulation_refs": ["ISO 13485:2016 §X.X.X"],
  "focus_area": "この質問が焦点を当てるコンプライアンス側面（一文）",
  "verifiable_by": "検証可能な文書/記録の種類（一文）"
}""",
}


# ============================================================
# Side B — user message templates (multilingual)
# ============================================================

SIDE_B_USER_TEMPLATES: dict[str, str] = {
    "zh": """條款資訊：
- 條款 ID：{clause_id}
- 條款標題：{clause_title}
- 重要性：{audit_impact}
- 現有標準問題（請勿重複）：{existing_question}

文件資訊：
- 文件 ID：{doc_id}
- 文件標題：{doc_title}
- 產品類別：{product_category}
- 預期用途：{intended_use}
- 適用法規：{applicable_regulations}
- 製造要求摘要：{manufacturing_requirements}
- 完整文件內容：
{doc_full_content}

請生成一個針對此文件與此條款的高品質稽核問題，考量產品特性、適用法規及製造要求。""",
    "en": """Clause Information:
- Clause ID: {clause_id}
- Clause Title: {clause_title}
- Audit Impact: {audit_impact}
- Existing Standard Question (do not duplicate): {existing_question}

Document Information:
- Document ID: {doc_id}
- Document Title: {doc_title}
- Product Category: {product_category}
- Intended Use: {intended_use}
- Applicable Regulations: {applicable_regulations}
- Manufacturing Requirements Summary: {manufacturing_requirements}
- Full Document Content:
{doc_full_content}

Generate a high-quality audit question for this document and clause, considering product characteristics, applicable regulations, and manufacturing requirements.""",
    "ja": """条項情報：
- 条項ID：{clause_id}
- 条項タイトル：{clause_title}
- 監査影響度：{audit_impact}
- 既存の標準質問（重複不可）：{existing_question}

文書情報：
- 文書ID：{doc_id}
- 文書タイトル：{doc_title}
- 製品カテゴリ：{product_category}
- 意図された使用目的：{intended_use}
- 適用規制：{applicable_regulations}
- 製造要件サマリー：{manufacturing_requirements}
- 完全な文書内容：
{doc_full_content}

製品特性、適用規制、製造要件を考慮して、この文書と条項に対する高品質な監査質問を生成してください。""",
}


# ============================================================
# i18n labels for "missing context" placeholders
# ============================================================

_NOT_SPECIFIED: dict[str, str] = {
    "zh": "（未指定）",
    "en": "(Not specified)",
    "ja": "（未指定）",
}

_NO_CONTENT: dict[str, str] = {
    "zh": "（無內容）",
    "en": "(No content)",
    "ja": "（コンテンツなし）",
}


# ============================================================
# IFU full-content extraction
# ============================================================

_IFU_KEYWORDS = (
    "instructions for use",
    "ifu",
    "intended use",
    "indications for use",
    "contraindication",
    "使用說明書",
    "使用說明",
    "使用説明書",
    "使用説明",
    "禁忌",
    "適応",
    "適用",
    "用途",
)

# Regulation tokens we look for in raw text
_REG_PATTERNS = [
    r"ISO\s*13485(?:[:\-\s]\d{4})?",
    r"ISO\s*14971(?:[:\-\s]\d{4})?",
    r"ISO\s*10993(?:[:\-\s]\d+)?",
    r"ISO\s*11135",
    r"ISO\s*11137",
    r"ISO\s*15223",
    r"IEC\s*60601(?:[\-\s]\d+)?",
    r"IEC\s*62304",
    r"IEC\s*62366",
    r"FDA(?:\s*21\s*CFR\s*Part\s*\d+)?",
    r"21\s*CFR\s*Part\s*\d+",
    r"CE\s*Mark(?:ing)?",
    r"CE\s*標誌",
    r"EU\s*MDR(?:\s*2017/745)?",
    r"MDR\s*2017/745",
    r"PMDA",
    r"QMSR",
    r"MDSAP",
    r"TFDA",
    r"TPLGS",
    r"GB\s*\d+(?:\.\d+)*",
]

# Patterns indicating product / intended-use blocks
_INTENDED_USE_PATTERNS = (
    r"(?:intended\s+use|indications?\s+for\s+use|預期用途|預定用途|用途|意図された使用|使用目的)\s*[:：]?\s*([^\n]{10,800})",
)

_PRODUCT_CATEGORY_PATTERNS = (
    r"(?:product\s+(?:name|type|category)|device\s+class|產品(?:名稱|種類|類別|類型)|医療機器(?:クラス)?分類|製品名)\s*[:：]?\s*([^\n]{2,200})",
)

_MANUFACTURING_PATTERNS = (
    r"(?:steriliz(?:ation|ed)|sterile|sterilis|滅菌|無菌|滅菌方法)[^\n]{0,300}",
    r"(?:packag(?:ing|ed)|包裝|包装)[^\n]{0,300}",
    r"(?:storage|保存|貯藏|保管|貯蔵)[^\n]{0,300}",
    r"(?:shelf\s+life|expir(?:y|ation)|有效期|保存期間|使用期限)[^\n]{0,300}",
    r"(?:transport|運輸|輸送)[^\n]{0,300}",
)


def _extract_ifu_context(content: str, max_chars: int = 15000) -> dict:
    """Extract structured context from a (potentially IFU) document.

    Returns a dict with keys consumed by ``SIDE_B_USER_TEMPLATES``:

    - ``is_ifu``                 -- True if document looks like an IFU
    - ``product_category``       -- best-effort product category line
    - ``intended_use``           -- intended-use / indication block
    - ``applicable_regulations`` -- comma-separated list of detected regs
    - ``manufacturing_requirements`` -- sterilization / packaging / storage…
    - ``doc_full_content``       -- full text, truncated to ``max_chars``

    No truncation is applied below ``max_chars`` (default 15 000); for very
    large documents we keep the head + extracted-section anchors so the LLM
    sees the most regulation-relevant portion.
    """
    if not content:
        return {
            "is_ifu": False,
            "product_category": "",
            "intended_use": "",
            "applicable_regulations": "",
            "manufacturing_requirements": "",
            "doc_full_content": "",
        }

    text = content
    text_lower = text.lower()

    # ── Detect IFU ────────────────────────────────────────────────────────
    is_ifu = any(kw.lower() in text_lower for kw in _IFU_KEYWORDS)

    # ── Product category ─────────────────────────────────────────────────
    product_category = ""
    for pat in _PRODUCT_CATEGORY_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            product_category = m.group(1).strip()[:200]
            break

    # ── Intended use ─────────────────────────────────────────────────────
    intended_use = ""
    for pat in _INTENDED_USE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            intended_use = m.group(1).strip()[:800]
            break

    # ── Applicable regulations ───────────────────────────────────────────
    found_regs: list[str] = []
    for pat in _REG_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            token = re.sub(r"\s+", " ", m.group(0)).strip()
            if token and token not in found_regs:
                found_regs.append(token)
    applicable_regulations = ", ".join(found_regs[:25])

    # ── Manufacturing requirements ───────────────────────────────────────
    mfg_snippets: list[str] = []
    for pat in _MANUFACTURING_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            snippet = re.sub(r"\s+", " ", m.group(0)).strip()
            if snippet and snippet not in mfg_snippets:
                mfg_snippets.append(snippet[:300])
            if len(mfg_snippets) >= 12:
                break
        if len(mfg_snippets) >= 12:
            break
    manufacturing_requirements = "\n- ".join(mfg_snippets) if mfg_snippets else ""
    if manufacturing_requirements:
        manufacturing_requirements = "- " + manufacturing_requirements

    # ── Full content (smart truncation if needed) ────────────────────────
    if len(text) <= max_chars:
        doc_full_content = text
    else:
        # Keep the head (~60 %) plus extracted IFU-relevant sections at the tail.
        head_chars = int(max_chars * 0.6)
        head = text[:head_chars]

        anchor_keywords = (
            "intended use",
            "indications for use",
            "contraindication",
            "warning",
            "precaution",
            "sterili",
            "packag",
            "storage",
            "shelf life",
            "transport",
            "預期用途",
            "禁忌",
            "警告",
            "注意",
            "滅菌",
            "包裝",
            "保存",
            "意図された使用",
            "禁忌事項",
            "警告事項",
            "滅菌",
            "包装",
            "保管",
        )
        tail_parts: list[str] = []
        remaining = max_chars - head_chars
        for kw in anchor_keywords:
            idx = text_lower.find(kw, head_chars)
            if idx == -1:
                continue
            window = text[max(idx - 80, head_chars): idx + 600]
            tail_parts.append(window)
            remaining -= len(window)
            if remaining <= 0:
                break
        tail = "\n…\n".join(tail_parts)[: max_chars - head_chars]
        doc_full_content = head + ("\n…\n" + tail if tail else "")

    return {
        "is_ifu": is_ifu,
        "product_category": product_category,
        "intended_use": intended_use,
        "applicable_regulations": applicable_regulations,
        "manufacturing_requirements": manufacturing_requirements,
        "doc_full_content": doc_full_content,
    }


# ============================================================
# Core: generate & validate
# ============================================================


def generate_question_b(
    clause_id: str,
    clause_info: dict,
    doc_id: str,
    doc_title: str,
    doc_content_summary: str,
    llm_completion_fn: callable,
    model: str = "default",
    lang: str = "zh-TW",
    max_content_chars: int = 15000,
) -> Optional[dict]:
    """Call LLM to generate a dynamic audit question for a critical clause.

    Args:
        clause_id: Clause identifier (e.g. "7.5.3")
        clause_info: Clause metadata from ISO_13485_CHECKLIST
        doc_id: Document identifier
        doc_title: Document title
        doc_content_summary: Full document content (no longer truncated to 800
            chars — full text is passed and IFU-aware context extraction is
            applied automatically)
        llm_completion_fn: Provider abstraction (system + user → text, usage)
        model: Model name
        lang: UI language (controls prompt language)
        max_content_chars: Hard cap on document body fed to the LLM

    Returns a parsed dict with question fields, or ``None`` on failure.
    """
    lk = _lang_key(lang)
    existing_question = clause_info.get("audit_question", "")

    ctx = _extract_ifu_context(doc_content_summary or "", max_chars=max_content_chars)
    not_specified = _NOT_SPECIFIED[lk]
    no_content = _NO_CONTENT[lk]

    user_prompt = SIDE_B_USER_TEMPLATES[lk].format(
        clause_id=clause_id,
        clause_title=clause_info.get("title", ""),
        audit_impact=clause_info.get("audit_impact", "critical"),
        existing_question=(existing_question or "")[:200],
        doc_id=doc_id,
        doc_title=doc_title,
        product_category=ctx["product_category"] or not_specified,
        intended_use=ctx["intended_use"] or not_specified,
        applicable_regulations=ctx["applicable_regulations"] or not_specified,
        manufacturing_requirements=ctx["manufacturing_requirements"] or not_specified,
        doc_full_content=ctx["doc_full_content"] or no_content,
    )

    try:
        _messages = [
            {"role": "system", "content": SIDE_B_SYSTEM_PROMPTS[lk]},
            {"role": "user",   "content": user_prompt},
        ]
        _result = llm_completion_fn(
            _messages,
            model=model,
            temperature=0.7,
            max_tokens=512,
        )
        response_text = _result["content"] if isinstance(_result, dict) else _result
        return _parse_json_response(response_text)
    except Exception as exc:
        logger.warning(
            "Side B question generation failed for clause=%s doc=%s lang=%s: %s",
            clause_id,
            doc_id,
            lk,
            exc,
        )
        return None


def validate_question_b(q: dict) -> bool:
    """Quality gate for LLM-generated questions.

    Returns True only when ALL of the following pass:
      1. question_zh OR question_en exists and is 50–600 chars
      2. Contains ISO 13485 clause reference (§X.X or "ISO 13485")
      3. regulation_refs list is non-empty
    """
    if not q or not isinstance(q, dict):
        return False

    # Accept either zh or en as the primary text — len check on whichever is present
    primary_text = q.get("question_zh") or q.get("question_en") or ""
    if not primary_text or not (50 <= len(primary_text) <= 600):
        logger.debug(
            "Side B validation fail: primary question length=%d", len(primary_text)
        )
        return False

    has_ref = bool(
        re.search(r"[§§]\s*\d+\.\d+", primary_text)
        or re.search(r"ISO\s*13485", primary_text, re.IGNORECASE)
        or q.get("regulation_refs")
    )
    if not has_ref:
        logger.debug("Side B validation fail: no regulation reference found")
        return False

    return True


# ============================================================
# Public API: hybrid selector
# ============================================================


def get_audit_question_hybrid(
    clause_id: str,
    doc_id: str = "",
    doc_title: str = "",
    doc_content_summary: str = "",
    llm_completion_fn: Optional[callable] = None,
    model: str = "default",
    seed: Optional[int] = None,
    lang: str = "zh-TW",
) -> dict:
    """Hybrid A/B question selector.

    Routing:
      critical + llm_completion_fn available → try Side B, fallback to A
      major / minor, or no LLM fn provided   → Side A always

    Args:
        lang: UI language code (zh-*, en, ja).  Side B prompts and IFU
            context labels are localized; non-zh/ja codes fall back to English.

    Returns:
        {
            "question":          str,       # selected question text (primary lang)
            "question_en":       str,       # English version (B only, else "")
            "source":            "A"|"B",   # which side was used
            "clause_id":         str,
            "audit_impact":      str,
            "regulation_refs":   list,      # from B; [] for A
            "focus_area":        str,       # from B; "" for A
            "verifiable_by":     str,       # from B; "" for A
            "expected_evidence": list,      # static list from checklist (always)
        }
    """
    clause_info = ISO_13485_CHECKLIST.get(clause_id, {})
    audit_impact = clause_info.get("audit_impact", "major")
    lk = _lang_key(lang)
    # Language-aware expected evidence selection.
    # lk is one of "zh", "en", "ja" (see _lang_key).
    static_expected_evidence = (
        clause_info.get("expected_evidence_ja") if lk == "ja"
        else clause_info.get("expected_evidence_en") if lk == "en"
        else clause_info.get("expected_evidence")
    ) or clause_info.get("expected_evidence", [])

    # ── Side B: critical clauses with LLM available ──────────────────────────
    if audit_impact == "critical" and llm_completion_fn is not None:
        q_b = generate_question_b(
            clause_id=clause_id,
            clause_info=clause_info,
            doc_id=doc_id,
            doc_title=doc_title,
            doc_content_summary=doc_content_summary,
            llm_completion_fn=llm_completion_fn,
            model=model,
            lang=lang,
        )
        if q_b and validate_question_b(q_b):
            logger.info(
                "Side B question accepted for clause=%s doc=%s lang=%s",
                clause_id,
                doc_id,
                lk,
            )
            # Pick primary text by language: zh→question_zh, ja→question_ja
            # (if present), otherwise question_en.  Falls back across languages.
            primary = (
                q_b.get("question_zh")
                if lk == "zh"
                else q_b.get("question_ja") or q_b.get("question_en")
                if lk == "ja"
                else q_b.get("question_en") or q_b.get("question_zh")
            ) or q_b.get("question_zh", "") or q_b.get("question_en", "")
            return {
                "question": primary,
                "question_en": q_b.get("question_en", ""),
                "question_zh": q_b.get("question_zh", "") or q_b.get("question_en", ""),
                "question_ja": q_b.get("question_ja", "") or q_b.get("question_en", ""),
                "source": "B",
                "clause_id": clause_id,
                "audit_impact": audit_impact,
                "regulation_refs": q_b.get("regulation_refs", []),
                "focus_area": q_b.get("focus_area", ""),
                "verifiable_by": q_b.get("verifiable_by", ""),
                "expected_evidence": static_expected_evidence,
            }
        logger.info(
            "Side B fallback to A for clause=%s (validation failed or error)",
            clause_id,
        )

    # ── Side A: static pool with date + doc_id hash ──────────────────────────
    question_a = get_audit_question(clause_info, seed=seed, doc_id=doc_id, lang=lang)
    question_en_a = get_audit_question(clause_info, seed=seed, doc_id=doc_id, lang="en-US")
    question_zh_a = get_audit_question(clause_info, seed=seed, doc_id=doc_id, lang="zh-TW")
    question_ja_a = get_audit_question(clause_info, seed=seed, doc_id=doc_id, lang="ja-JP")
    return {
        "question": question_a,
        "question_en": question_en_a,
        "question_zh": question_zh_a,
        "question_ja": question_ja_a,
        "source": "A",
        "clause_id": clause_id,
        "audit_impact": audit_impact,
        "regulation_refs": [],
        "focus_area": "",
        "verifiable_by": "",
        "expected_evidence": static_expected_evidence,
    }


# ============================================================
# Internal helpers
# ============================================================


def _parse_json_response(text: str) -> Optional[dict]:
    """Extract and parse the first JSON object found in LLM response text."""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None
