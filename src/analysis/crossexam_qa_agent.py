"""
AI-QMS — Cross-Examination Quality Assurance Agent (3rd Agent)
===============================================================

Meta-analysis agent that evaluates cross-examination quality when ≥10
records exist in the crossexam_store. Detects:
  - Quality degradation over time
  - Over-fitting / repetitive patterns
  - Country bias (disproportionate focus on one country)
  - Question type imbalance (delta vs exceeds vs overlap)
  - Answer depth/specificity decline

Produces:
  - Structured quality assessment
  - Prompt tuning recommendations
  - Downloadable standalone QA report (or section in deep report)

Uses the bilingual prompt pattern: {"zh": ..., "en": ...}
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.database.crossexam_store import CrossExamStore, get_crossexam_store
from src.utils.safe_io import atomic_write_json

logger = logging.getLogger(__name__)

__all__ = [
    "run_meta_analysis",
    "MetaAnalysisResult",
    "get_latest_meta_analysis",
]

META_DIR = Path("./data/crossexam_history")


# ============================================================
# i18n helper
# ============================================================

from src.chainlit_app.lang_config import lang_key as _lang_key_central  # noqa: E402


def _get_prompt_lang(lang: str) -> str:
    """Normalize lang code to 'zh' or 'en' for prompt selection.

    This file's prompt dicts only have zh/en keys, so ja falls back to en.
    """
    lk = _lang_key_central(lang)
    return "zh" if lk == "zh" else "en"


# ============================================================
# System prompts
# ============================================================


_META_ANALYSIS_SYSTEM_PROMPTS = {
    "zh": """你是品質管理系統的「交叉詰問品質評估專家」，具備 ISO 13485:2016 稽核實務與 AI 系統品質評估的雙重背景。你的任務是分析多次交叉詰問的歷史記錄，從稽核品質與 AI 輸出可靠性兩個維度評估趨勢。

你需要檢查：
1. **品質趨勢**: 問題品質是否隨時間退化？回答是否變得公式化或越來越簡短？
2. **國家偏差**: 是否過度偏向詢問某一國法規？各國 delta 要求的覆蓋是否均衡？
3. **問題類型分布**: delta / exceeds / overlap 問題是否均衡？某類型是否被系統性忽略？
4. **回答深度**: 分析者和驗證者的回答是否引用具體原文而非泛稱？是否有越來越簡短的趨勢？
5. **同意率異常**: 同意率異常偏高（> 85%，表示驗證者質疑不夠嚴格）或偏低（< 30%，標準過嚴）？
6. **過度學習跡象**: 是否出現重複的問題模式或套路化回答？AI 是否在「表演合規」而非真正分析？
7. **幻覺引用偵測**: 分析者或驗證者是否引用了泛泛的、非文件特定的證據描述（可能為 AI 生成的通用說法）？
8. **法規更新對齊**: 交叉詰問是否考量 FDA QMSR 2024 與 ISO 13485 的最新對齊要求？

回答必須使用以下 JSON 格式：
{
  "summary": "品質評估的整體摘要（2-3 句話）",
  "quality_score": 0.0-1.0,
  "findings": [
    {
      "category": "quality_trend | country_bias | question_balance | answer_depth | agreement_anomaly | overfitting | hallucination_risk | regulatory_alignment",
      "severity": "low | medium | high | critical",
      "description": "具體描述，附數據支持",
      "evidence": "支持證據（引用具體記錄數據）",
      "recommendation": "建議改善措施"
    }
  ],
  "recommendations": ["具體的 prompt 修改建議"],
  "prompt_tuning": {
    "analyzer_adjustment": "分析者 prompt 需要的調整（如有）",
    "verifier_adjustment": "驗證者 prompt 需要的調整（如有）",
    "question_adjustment": "問題生成需要的調整（如有）"
  }
}""",
    "en": """You are a "Cross-Examination Quality Assessment Expert" for a quality management system, with dual expertise in ISO 13485:2016 audit practice and AI system output reliability evaluation. Your task is to analyze historical cross-examination records and assess quality trends across both audit quality and AI output trustworthiness dimensions.

You need to check:
1. **Quality Trends**: Are question quality degrading over time? Are answers becoming formulaic or increasingly brief?
2. **Country Bias**: Is there disproportionate focus on one country's regulations? Are delta requirements for all countries covered equitably?
3. **Question Type Distribution**: Are delta / exceeds / overlap questions balanced? Is any type systematically underrepresented?
4. **Answer Depth**: Do analyzer/verifier answers cite specific document text rather than generic descriptions? Is there a trend toward brevity?
5. **Agreement Rate Anomaly**: Is the agreement rate abnormally high (>85%, indicating insufficient challenge) or low (<30%, too strict)?
6. **Overfitting Signs**: Are there repeated question patterns or templated answers? Is the AI "performing compliance" rather than genuinely analyzing?
7. **Hallucination Detection**: Are analyzer/verifier responses citing generic, non-document-specific evidence (potential AI-generated boilerplate)?
8. **Regulatory Alignment**: Are cross-examinations accounting for FDA QMSR 2024 harmonization with ISO 13485?

Respond in the following JSON format:
{
  "summary": "Overall quality assessment summary (2-3 sentences)",
  "quality_score": 0.0-1.0,
  "findings": [
    {
      "category": "quality_trend | country_bias | question_balance | answer_depth | agreement_anomaly | overfitting | hallucination_risk | regulatory_alignment",
      "severity": "low | medium | high | critical",
      "description": "Specific description with data support",
      "evidence": "Supporting evidence (citing specific record data)",
      "recommendation": "Recommended improvement"
    }
  ],
  "recommendations": ["Specific prompt modification suggestions"],
  "prompt_tuning": {
    "analyzer_adjustment": "Adjustments needed for analyzer prompt (if any)",
    "verifier_adjustment": "Adjustments needed for verifier prompt (if any)",
    "question_adjustment": "Adjustments needed for question generation (if any)"
  }
}""",
}


_META_ANALYSIS_USER_TEMPLATES = {
    "zh": """## 交叉詰問品質分析任務

以下是 {record_count} 份交叉詰問記錄的統計數據和樣本：

### 統計摘要
- 記錄總數: {record_count}
- 時間範圍: {time_range}
- 平均同意率: {avg_agreement_rate:.1%}
- 平均輪次: {avg_rounds:.1f}
- 總標記 RA: {total_flagged}

### 國家分布
{country_distribution}

### 問題類型分布
{question_type_distribution}

### 同意率趨勢（從舊到新）
{agreement_trend}

### 樣本記錄
{sample_records}

請根據以上數據，進行品質評估並提出建議。""",
    "en": """## Cross-Examination Quality Analysis Task

Below are statistics and samples from {record_count} cross-examination records:

### Statistical Summary
- Total Records: {record_count}
- Time Range: {time_range}
- Average Agreement Rate: {avg_agreement_rate:.1%}
- Average Rounds: {avg_rounds:.1f}
- Total Flagged for RA: {total_flagged}

### Country Distribution
{country_distribution}

### Question Type Distribution
{question_type_distribution}

### Agreement Rate Trend (oldest to newest)
{agreement_trend}

### Sample Records
{sample_records}

Please evaluate quality based on the above data and provide recommendations.""",
}


# ============================================================
# Data class
# ============================================================


class MetaAnalysisResult:
    """Result of a meta-analysis run."""

    def __init__(
        self,
        *,
        analysis_id: str = "",
        timestamp: str = "",
        record_count: int = 0,
        llm_response: dict | None = None,
        raw_response: str = "",
        model: str = "",
        usage: dict | None = None,
        tuning_applied: bool = False,
        tuning_history: list[dict] | None = None,
    ):
        self.analysis_id = analysis_id or f"ma_{int(time.time())}"
        self.timestamp = timestamp or datetime.now().isoformat()
        self.record_count = record_count
        self.llm_response = llm_response or {}
        self.raw_response = raw_response
        self.model = model
        self.usage = usage or {}
        self.tuning_applied = tuning_applied
        self.tuning_history = tuning_history or []

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "timestamp": self.timestamp,
            "record_count": self.record_count,
            "llm_response": self.llm_response,
            "raw_response": self.raw_response,
            "model": self.model,
            "usage": self.usage,
            "tuning_applied": self.tuning_applied,
            "tuning_history": self.tuning_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MetaAnalysisResult":
        import inspect

        valid_params = set(inspect.signature(cls.__init__).parameters.keys()) - {"self"}
        return cls(**{k: v for k, v in data.items() if k in valid_params})

    @property
    def summary(self) -> str:
        return self.llm_response.get("summary", "")

    @property
    def quality_score(self) -> float:
        return self.llm_response.get("quality_score", 0.0)

    @property
    def findings(self) -> list[dict]:
        return self.llm_response.get("findings", [])

    @property
    def recommendations(self) -> list[str]:
        return self.llm_response.get("recommendations", [])

    @property
    def prompt_tuning(self) -> dict:
        return self.llm_response.get("prompt_tuning", {})


# ============================================================
# Core analysis function
# ============================================================


def run_meta_analysis(
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    lang: str = "zh-TW",
    store: CrossExamStore | None = None,
) -> MetaAnalysisResult:
    """Run meta-analysis on cross-examination history.

    Requires ≥10 records in the store.
    Calls LLM to analyze quality trends and generate recommendations.

    Args:
        llm_completion_fn: LLM completion function
        model: LLM model name
        temperature: LLM temperature
        max_tokens: Max response tokens
        lang: Language code
        store: CrossExamStore instance (uses singleton if not provided)

    Returns:
        MetaAnalysisResult with analysis findings and recommendations
    """
    if store is None:
        store = get_crossexam_store()

    records = store.get_all_records()
    if len(records) < 10:
        return MetaAnalysisResult(
            llm_response={
                "summary": f"記錄不足（{len(records)}/10），無法進行品質分析。",
                "quality_score": 0.0,
                "findings": [],
                "recommendations": [],
                "prompt_tuning": {},
            },
            record_count=len(records),
        )

    _lang_key = _get_prompt_lang(lang)

    # Build analysis context
    country_dist = store.get_country_distribution()
    qtype_dist = store.get_question_type_distribution()
    trend = store.get_agreement_trend()

    # Calculate statistics
    total_clauses = sum(r.total_clauses for r in records)
    total_agreed = sum(r.total_agreed for r in records)
    total_flagged = sum(r.total_flagged for r in records)
    total_rounds = sum(r.total_rounds for r in records)
    avg_agreement = total_agreed / max(total_clauses, 1)
    avg_rounds = total_rounds / max(total_clauses, 1)

    time_range = (
        f"{records[-1].timestamp} ~ {records[0].timestamp}" if records else "N/A"
    )

    # Format distributions
    country_text = "\n".join(
        f"  - {c}: {n} 次" for c, n in sorted(country_dist.items(), key=lambda x: -x[1])
    )
    qtype_text = "\n".join(
        f"  - {t}: {n} 次" for t, n in sorted(qtype_dist.items(), key=lambda x: -x[1])
    )

    # Format trend
    trend_text = "\n".join(
        f"  - {t['timestamp'][:10]}: agreement={t['agreement_rate']:.1%}, "
        f"clauses={t['total_clauses']}, flagged={t['total_flagged']}"
        for t in trend[-20:]  # Last 20 entries
    )

    # Build sample records (most recent 3, with full round details)
    sample_text_parts = []
    for r in records[:3]:
        sample_text_parts.append(
            f"--- Record {r.record_id} ({r.timestamp}) ---\n"
            f"Regulations: {', '.join(r.selected_regulations)}\n"
            f"Clauses: {r.total_clauses}, Agreed: {r.total_agreed}, Flagged: {r.total_flagged}\n"
        )
        for clause in r.clauses[:3]:  # Show up to 3 clauses per record
            sample_text_parts.append(
                f"  Clause {clause.get('clause_id', '')}: "
                f"agreed={clause.get('agreed')}, "
                f"rounds={len(clause.get('rounds', []))}\n"
            )
            for rd in clause.get("rounds", [])[:1]:  # Show first round
                analyzer = rd.get("analyzer", {})
                verifier = rd.get("verifier", {})
                sample_text_parts.append(
                    f"    Analyzer (R{rd.get('round', '?')}): "
                    f"confidence={analyzer.get('confidence', 'N/A')}, "
                    f"position={str(analyzer.get('position', ''))[:200]}\n"
                    f"    Verifier (R{rd.get('round', '?')}): "
                    f"agreement={verifier.get('agreement_level', 'N/A')}, "
                    f"challenges={str(verifier.get('challenges', []))[:200]}\n"
                )

    sample_text = "".join(sample_text_parts)

    # Build prompt
    user_prompt = _META_ANALYSIS_USER_TEMPLATES[_lang_key].format(
        record_count=len(records),
        time_range=time_range,
        avg_agreement_rate=avg_agreement,
        avg_rounds=avg_rounds,
        total_flagged=total_flagged,
        country_distribution=country_text or "  （無國家資料）",
        question_type_distribution=qtype_text or "  （無問題類型資料）",
        agreement_trend=trend_text or "  （無趨勢資料）",
        sample_records=sample_text or "  （無樣本記錄）",
    )

    messages = [
        {"role": "system", "content": _META_ANALYSIS_SYSTEM_PROMPTS[_lang_key]},
        {"role": "user", "content": user_prompt},
    ]

    result = MetaAnalysisResult(record_count=len(records))

    try:
        response = llm_completion_fn(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        response_text = response.get("content", "")
        usage = response.get("usage", {})
        result.raw_response = response_text
        result.model = response.get("model", model)
        result.usage = usage

        # Parse JSON response
        parsed = _parse_meta_response(response_text)
        result.llm_response = parsed

        # Save result to disk
        _save_meta_analysis(result)

        logger.info(
            "Meta-analysis complete: score=%.2f, findings=%d",
            result.quality_score,
            len(result.findings),
        )

    except Exception as e:
        logger.error(f"Meta-analysis failed: {e}")
        result.llm_response = {
            "summary": f"品質分析失敗: {str(e)[:200]}",
            "quality_score": 0.0,
            "findings": [],
            "recommendations": [],
            "prompt_tuning": {},
        }

    return result


# ============================================================
# Prompt tuning
# ============================================================


def apply_prompt_tuning(
    meta_result: MetaAnalysisResult,
) -> dict:
    """Apply prompt tuning based on meta-analysis findings.

    Returns a dict of tuning actions taken.
    Does NOT directly modify module-level prompts (they're constants),
    but records tuning recommendations that can be used as additional
    system prompt context in future runs.
    """
    tuning = meta_result.prompt_tuning
    if not tuning:
        return {"applied": False, "reason": "No tuning recommendations"}

    tuning_record = {
        "timestamp": datetime.now().isoformat(),
        "analysis_id": meta_result.analysis_id,
        "quality_score": meta_result.quality_score,
        "tuning": tuning,
        "applied": True,
    }

    # Save tuning history
    history_file = META_DIR / "tuning_history.json"
    META_DIR.mkdir(parents=True, exist_ok=True)

    history: list[dict] = []
    if history_file.exists():
        try:
            import json

            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    history.append(tuning_record)
    atomic_write_json(history_file, history)

    meta_result.tuning_applied = True
    meta_result.tuning_history = history

    logger.info("Applied prompt tuning from analysis %s", meta_result.analysis_id)
    return {"applied": True, "tuning": tuning, "history_count": len(history)}


def get_active_tuning() -> dict:
    """Get the most recent active prompt tuning adjustments.

    Returns an empty dict if no tuning history exists.
    The tuning dict contains:
      - analyzer_adjustment: str
      - verifier_adjustment: str
      - question_adjustment: str
    """
    history_file = META_DIR / "tuning_history.json"
    if not history_file.exists():
        return {}

    try:
        import json

        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
        if history:
            latest = history[-1]
            return latest.get("tuning", {})
    except (json.JSONDecodeError, OSError):
        pass

    return {}


# ============================================================
# Persistence helpers
# ============================================================


def _save_meta_analysis(result: MetaAnalysisResult) -> None:
    """Save meta-analysis result to disk."""
    META_DIR.mkdir(parents=True, exist_ok=True)
    filepath = META_DIR / f"meta_analysis_{result.analysis_id}.json"
    atomic_write_json(filepath, result.to_dict())


def get_latest_meta_analysis() -> Optional[MetaAnalysisResult]:
    """Load the most recent meta-analysis result from disk."""
    META_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(META_DIR.glob("meta_analysis_*.json"), reverse=True)
    if not files:
        return None

    try:
        import json

        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        return MetaAnalysisResult.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


# ============================================================
# Response parsing
# ============================================================


def _parse_meta_response(response_text: str) -> dict:
    """Parse the LLM meta-analysis response (JSON).

    Handles code-fenced JSON and raw JSON.
    """
    import re

    text = response_text.strip()

    # Try to extract JSON from code fence
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    try:
        parsed = json.loads(text)
        # Validate expected structure
        if isinstance(parsed, dict) and "summary" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        try:
            parsed = json.loads(text[brace_start : brace_end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Fallback: return raw text as summary
    return {
        "summary": text[:500],
        "quality_score": 0.0,
        "findings": [],
        "recommendations": [],
        "prompt_tuning": {},
    }
