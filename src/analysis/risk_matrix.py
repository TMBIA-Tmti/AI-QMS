"""
AI-QMS — Risk Matrix Engine
============================

Deterministic risk assessment: audit_impact × gap_severity → risk_level.
No LLM involved — pure rule-engine lookup.

Risk Matrix:
    ┌──────────┬──────────┬────────────┬────────────┬──────────┬──────┐
    │          │ Missing  │ Incomplete │ Inadequate │ Outdated │ None │
    ├──────────┼──────────┼────────────┼────────────┼──────────┼──────┤
    │ Critical │ 🔴       │ 🔴         │ 🔴         │ 🟠       │ ✅   │
    │ Major    │ 🟠       │ 🟡         │ 🟡         │ 🟡       │ ✅   │
    │ Minor    │ 🟡       │ 🟢         │ 🟢         │ 🟢       │ ✅   │
    └──────────┴──────────┴────────────┴────────────┴──────────┴──────┘

Risk Levels:
    🔴 = immediate_correction  (❌ 立即改正)
    🟠 = deadline_correction   (❌ 限期改正)
    🟡 = improvement_plan      (⚠️ 改善計畫)
    🟢 = suggested_improvement (⚠️ 建議改善)
    ✅ = compliant             (✅ 符合)
"""

from typing import Optional

__all__ = [
    "RiskLevel",
    "GapSeverity",
    "AuditImpact",
    "Verdict",
    "assess_risk",
    "determine_gap_severity",
    "risk_to_verdict",
    "RISK_MATRIX",
    "RISK_LEVEL_DISPLAY",
    "VERDICT_DISPLAY",
]


# ============================================================
# Type constants
# ============================================================


class AuditImpact:
    """Audit impact levels — predefined per clause in compliance_rules.py."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"

    ALL = (CRITICAL, MAJOR, MINOR)


class GapSeverity:
    """Gap severity — determined by code counting evidence search results."""

    MISSING = "missing"  # 預期證據全部沒找到
    INCOMPLETE = "incomplete"  # 找到部分，缺關鍵項目
    INADEQUATE = "inadequate"  # 全找到，但內容不足以涵蓋要求
    OUTDATED = "outdated"  # 找到且內容充分，但文件版本過期
    NONE = "none"  # 全找到且涵蓋所有要求（符合）

    ALL = (MISSING, INCOMPLETE, INADEQUATE, OUTDATED, NONE)


class RiskLevel:
    """Risk assessment result — lookup from matrix."""

    IMMEDIATE_CORRECTION = "immediate_correction"  # 🔴 立即改正
    DEADLINE_CORRECTION = "deadline_correction"  # 🟠 限期改正
    IMPROVEMENT_PLAN = "improvement_plan"  # 🟡 改善計畫
    SUGGESTED_IMPROVEMENT = "suggested_improvement"  # 🟢 建議改善
    COMPLIANT = "compliant"  # ✅ 符合

    ALL = (
        IMMEDIATE_CORRECTION,
        DEADLINE_CORRECTION,
        IMPROVEMENT_PLAN,
        SUGGESTED_IMPROVEMENT,
        COMPLIANT,
    )


class Verdict:
    """Final verdict displayed in the report."""

    FULL_COMPLIANCE = "full_compliance"  # ✅ 完全符合
    PARTIAL_COMPLIANCE = "partial_compliance"  # ⚠️ 部分符合
    NON_COMPLIANCE = "non_compliance"  # ❌ 未符合
    INSUFFICIENT_DATA = "insufficient_data"  # ⬜ 資料不足
    NOT_APPLICABLE = "not_applicable"  # ➖ 不適用（無證據項目，跳過 LLM 階段）

    ALL = (FULL_COMPLIANCE, PARTIAL_COMPLIANCE, NON_COMPLIANCE, INSUFFICIENT_DATA, NOT_APPLICABLE)

    # Verdicts that do not require LLM phases (P2/P4/P5)
    LLM_SKIP = (FULL_COMPLIANCE, NOT_APPLICABLE)


# ============================================================
# Display mappings (for UI / reports)
# ============================================================

RISK_LEVEL_DISPLAY = {
    RiskLevel.IMMEDIATE_CORRECTION: {
        "icon": "🔴",
        "label_zh": "立即改正",
        "label_en": "Immediate Correction",
        "action_zh": "❌ 需立即改正",
    },
    RiskLevel.DEADLINE_CORRECTION: {
        "icon": "🟠",
        "label_zh": "限期改正",
        "label_en": "Deadline Correction",
        "action_zh": "❌ 限期改正",
    },
    RiskLevel.IMPROVEMENT_PLAN: {
        "icon": "🟡",
        "label_zh": "改善計畫",
        "label_en": "Improvement Plan",
        "action_zh": "⚠️ 需提出改善計畫",
    },
    RiskLevel.SUGGESTED_IMPROVEMENT: {
        "icon": "🟢",
        "label_zh": "建議改善",
        "label_en": "Suggested Improvement",
        "action_zh": "⚠️ 建議改善",
    },
    RiskLevel.COMPLIANT: {
        "icon": "✅",
        "label_zh": "符合",
        "label_en": "Compliant",
        "action_zh": "✅ 符合要求",
    },
}

VERDICT_DISPLAY = {
    Verdict.FULL_COMPLIANCE: {
        "icon": "✅",
        "label_zh": "完全符合",
        "label_en": "Full Compliance",
    },
    Verdict.PARTIAL_COMPLIANCE: {
        "icon": "⚠️",
        "label_zh": "部分符合",
        "label_en": "Partial Compliance",
    },
    Verdict.NON_COMPLIANCE: {
        "icon": "❌",
        "label_zh": "未符合",
        "label_en": "Non-Compliance",
    },
    Verdict.INSUFFICIENT_DATA: {
        "icon": "⬜",
        "label_zh": "資料不足",
        "label_en": "Insufficient Data",
    },
    Verdict.NOT_APPLICABLE: {
        "icon": "➖",
        "label_zh": "不適用",
        "label_en": "Not Applicable",
    },
}


# ============================================================
# Risk Matrix (audit_impact × gap_severity → risk_level)
# ============================================================

RISK_MATRIX: dict[tuple[str, str], str] = {
    # Critical impact
    (AuditImpact.CRITICAL, GapSeverity.MISSING): RiskLevel.IMMEDIATE_CORRECTION,
    (AuditImpact.CRITICAL, GapSeverity.INCOMPLETE): RiskLevel.IMMEDIATE_CORRECTION,
    (AuditImpact.CRITICAL, GapSeverity.INADEQUATE): RiskLevel.IMMEDIATE_CORRECTION,
    (AuditImpact.CRITICAL, GapSeverity.OUTDATED): RiskLevel.DEADLINE_CORRECTION,
    (AuditImpact.CRITICAL, GapSeverity.NONE): RiskLevel.COMPLIANT,
    # Major impact
    (AuditImpact.MAJOR, GapSeverity.MISSING): RiskLevel.DEADLINE_CORRECTION,
    (AuditImpact.MAJOR, GapSeverity.INCOMPLETE): RiskLevel.IMPROVEMENT_PLAN,
    (AuditImpact.MAJOR, GapSeverity.INADEQUATE): RiskLevel.IMPROVEMENT_PLAN,
    (AuditImpact.MAJOR, GapSeverity.OUTDATED): RiskLevel.IMPROVEMENT_PLAN,
    (AuditImpact.MAJOR, GapSeverity.NONE): RiskLevel.COMPLIANT,
    # Minor impact
    (AuditImpact.MINOR, GapSeverity.MISSING): RiskLevel.IMPROVEMENT_PLAN,
    (AuditImpact.MINOR, GapSeverity.INCOMPLETE): RiskLevel.SUGGESTED_IMPROVEMENT,
    (AuditImpact.MINOR, GapSeverity.INADEQUATE): RiskLevel.SUGGESTED_IMPROVEMENT,
    (AuditImpact.MINOR, GapSeverity.OUTDATED): RiskLevel.SUGGESTED_IMPROVEMENT,
    (AuditImpact.MINOR, GapSeverity.NONE): RiskLevel.COMPLIANT,
}


# ============================================================
# Risk-level to verdict mapping
# ============================================================

_RISK_TO_VERDICT: dict[str, str] = {
    RiskLevel.IMMEDIATE_CORRECTION: Verdict.NON_COMPLIANCE,
    RiskLevel.DEADLINE_CORRECTION: Verdict.NON_COMPLIANCE,
    RiskLevel.IMPROVEMENT_PLAN: Verdict.PARTIAL_COMPLIANCE,
    RiskLevel.SUGGESTED_IMPROVEMENT: Verdict.PARTIAL_COMPLIANCE,
    RiskLevel.COMPLIANT: Verdict.FULL_COMPLIANCE,
}


# ============================================================
# Public API
# ============================================================


def assess_risk(audit_impact: str, gap_severity: str) -> str:
    """Look up risk level from the matrix.

    Args:
        audit_impact: One of AuditImpact.ALL ("critical", "major", "minor")
        gap_severity: One of GapSeverity.ALL ("missing", "incomplete",
                      "inadequate", "outdated", "none")

    Returns:
        Risk level string (one of RiskLevel.ALL)

    Raises:
        ValueError: If audit_impact or gap_severity is invalid
    """
    key = (audit_impact, gap_severity)
    result = RISK_MATRIX.get(key)
    if result is None:
        raise ValueError(
            f"Invalid risk matrix lookup: audit_impact={audit_impact!r}, "
            f"gap_severity={gap_severity!r}. "
            f"Valid audit_impact: {AuditImpact.ALL}, "
            f"valid gap_severity: {GapSeverity.ALL}"
        )
    return result


def risk_to_verdict(risk_level: str) -> str:
    """Convert risk level to display verdict.

    Args:
        risk_level: One of RiskLevel.ALL

    Returns:
        Verdict string (one of Verdict.ALL)

    Raises:
        ValueError: If risk_level is invalid
    """
    result = _RISK_TO_VERDICT.get(risk_level)
    if result is None:
        raise ValueError(
            f"Invalid risk level: {risk_level!r}. Valid values: {RiskLevel.ALL}"
        )
    return result


def determine_gap_severity(
    expected_count: int,
    found_count: int,
    has_inadequate: bool = False,
    has_outdated: bool = False,
) -> str:
    """Determine gap severity from evidence search results.

    This is the code-based (deterministic) logic that replaces LLM judgment.
    Called after Phase 1-2 (gap scan + checklist verification) complete.

    Args:
        expected_count: Total number of expected evidence items
        found_count: Number of evidence items actually found in documents
        has_inadequate: True if any found evidence was flagged as inadequate
                       (content exists but doesn't sufficiently address the requirement)
        has_outdated: True if any found evidence references an outdated document version

    Returns:
        Gap severity string (one of GapSeverity.ALL)

    Examples:
        >>> determine_gap_severity(3, 0)
        'missing'
        >>> determine_gap_severity(3, 2)
        'incomplete'
        >>> determine_gap_severity(3, 3, has_inadequate=True)
        'inadequate'
        >>> determine_gap_severity(3, 3, has_outdated=True)
        'outdated'
        >>> determine_gap_severity(3, 3)
        'none'
    """
    if expected_count <= 0:
        # No expected evidence defined — cannot assess
        return GapSeverity.NONE

    if found_count <= 0:
        return GapSeverity.MISSING

    if found_count < expected_count:
        return GapSeverity.INCOMPLETE

    # All evidence found — check quality
    if has_inadequate:
        return GapSeverity.INADEQUATE

    if has_outdated:
        return GapSeverity.OUTDATED

    return GapSeverity.NONE


def assess_clause(
    audit_impact: str,
    expected_count: int,
    found_count: int,
    has_inadequate: bool = False,
    has_outdated: bool = False,
) -> dict:
    """Full assessment for a single clause — convenience function.

    Combines determine_gap_severity → assess_risk → risk_to_verdict
    into a single call.

    Args:
        audit_impact: From compliance_rules.py ("critical", "major", "minor")
        expected_count: Total expected evidence items
        found_count: Found evidence items
        has_inadequate: Any evidence flagged as inadequate
        has_outdated: Any evidence from outdated documents

    Returns:
        dict with keys: gap_severity, risk_level, verdict, risk_display, verdict_display
    """
    gap_severity = determine_gap_severity(
        expected_count, found_count, has_inadequate, has_outdated
    )
    risk_level = assess_risk(audit_impact, gap_severity)
    verdict = risk_to_verdict(risk_level)

    return {
        "gap_severity": gap_severity,
        "risk_level": risk_level,
        "verdict": verdict,
        "risk_display": RISK_LEVEL_DISPLAY.get(risk_level, {}),
        "verdict_display": VERDICT_DISPLAY.get(verdict, {}),
    }
