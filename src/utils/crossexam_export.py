"""
AI-QMS — Cross-Examination & Deep Report Export
=================================================

Export utilities for:
1. Individual cross-exam records (Word/Excel)
2. Deep analysis report with ALL LLM interactions (Word/Excel)

Follows the export pattern from doclist_export.py / regulatory_export.py:
  - Uses python-docx for Word
  - Uses openpyxl for Excel
  - Returns file paths
  - Thread-safe via safe_io
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.safe_io import safe_save_binary

logger = logging.getLogger(__name__)

__all__ = [
    "export_crossexam_record_word",
    "export_crossexam_record_excel",
    "export_deep_report_word",
    "export_deep_report_excel",
]

EXPORT_DIR = Path("data/exports")


# ============================================================
# Shared: AI Roles Legend
# ============================================================


def _add_ai_roles_legend(doc) -> None:
    """Insert the AI roles and scoring legend into any Word document."""
    doc.add_heading("AI 角色說明 / AI Role Definitions & Scoring", level=2)
    doc.add_paragraph(
        "本系統採用三角色辯論架構進行 QMS 合規性審查。\n"
        "This system uses a three-role debate architecture for QMS compliance review."
    )

    p = doc.add_paragraph()
    p.add_run("🔍 分析者 / 辯護方（Analyzer / Defender）").bold = True
    doc.add_paragraph(
        "  角色定位：針對每個法規條款，分析 QMS 文件是否提供充分書面證據，採取明確立場（符合/不符合）並加以辯護。\n"
        "  Role: Analyzes QMS documents against each regulatory clause, takes a clear position\n"
        "        (compliant / non-compliant) and defends it with evidence.\n"
        "  輸出欄位：\n"
        "    • position（立場）：compliant / non-compliant / partially_compliant\n"
        "    • confidence（信心度）：high / medium / low\n"
        "    • key_evidence（關鍵證據）：文件中支持立場的引用段落\n"
        "    • regulatory_references（法規引用）：引用的條款編號與條文\n"
        "  評分方式：QA Auditor 評估其法規引用準確性，計入 Dim A（0–100）\n"
        "    90–100 引用精確，完全符合 | 70–89 輕微遺漏 | 50–69 部分符合 | 30–49 表面符合 | 0–29 完全不符"
    )

    p = doc.add_paragraph()
    p.add_run("⚖️ 驗證者 / 質疑方（Verifier / Reviewer）").bold = True
    doc.add_paragraph(
        "  角色定位：以魔鬼代言人角色質疑 Analyzer 的論點，指出未引用的法規要求、矛盾或證據漏洞，\n"
        "            迫使 Analyzer 進行更深入論證，最終給出同意程度結論。\n"
        "  Role: Challenges the Analyzer's argument as devil's advocate, identifies uncited\n"
        "        regulatory requirements, contradictions, or evidence gaps.\n"
        "  輸出欄位：\n"
        "    • agreement_level（同意程度）：agree / partial / disagree\n"
        "    • challenges（質疑點）：具體指出 Analyzer 論點的弱點或漏洞\n"
        "    • overall_assessment（整體評語）：對整場辯論品質的文字總結\n"
        "    • remaining_concerns（未解疑慮）：最終仍存在的爭議點\n"
        "  評分方式：QA Auditor 評估其詰問品質與深度，計入 Dim B（0–100）\n"
        "    90–100 深度均衡可操作 | 70–89 輕微缺失 | 50–69 明顯缺失 | 30–49 流於形式 | 0–29 嚴重不足"
    )

    p = doc.add_paragraph()
    p.add_run("🔎 品質稽核員 / 審查者（QA Auditor）").bold = True
    doc.add_paragraph(
        "  角色定位：模擬獨立第三方稽核員，不參與辯論，對整場 Analyzer↔Verifier 辯論進行客觀品質評核。\n"
        "  Role: Independent third-party auditor — does not debate, only evaluates debate quality.\n"
        "  輸出欄位：\n"
        "    • overall_score（整體分數）：0–100，綜合辯論品質評分\n"
        "    • score_rationale（評分依據）：說明落在哪個分數區間及具體原因\n"
        "    • question_quality（問題品質）：good / acceptable / poor — 評估稽核問題是否聚焦可查\n"
        "    • answer_accuracy（回答準確性）：accurate / partially_accurate / inaccurate\n"
        "    • logic_consistency（邏輯一致性）：consistent / minor_issues / inconsistent\n"
        "    • hallucination_detected（幻覺偵測）：true / false — AI 是否引用了不存在的法規內容\n"
        "    • issues（問題清單）：具體列出辯論中發現的品質問題\n"
        "  審核流程：\n"
        "    1. 評估稽核問題是否針對該條款的核心要求（question_quality）\n"
        "    2. 核查 Analyzer 引用的法規條文是否存在且準確（answer_accuracy）\n"
        "    3. 評估 Verifier 的質疑是否有根據且具建設性（Dim B）\n"
        "    4. 檢查雙方推理鏈是否完整、無內部矛盾（logic_consistency）\n"
        "    5. 偵測是否存在虛構條款、錯誤引用等幻覺現象（hallucination_detected）"
    )


# ============================================================
# Cross-Exam Record Export (individual records)
# ============================================================


def export_crossexam_record_word(record_dict: dict) -> Path:
    """Export a single cross-exam record as a Word document.

    Args:
        record_dict: CrossExamRecord.to_dict() output

    Returns:
        Path to the generated .docx file
    """
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"crossexam_{record_dict.get('record_id', 'unknown')}.docx"

    doc = Document()
    title = doc.add_heading("AI-QMS 交叉詰問記錄", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Metadata
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = meta.add_run(
        f"記錄 ID: {record_dict.get('record_id', '')}  |  "
        f"分析 ID: {record_dict.get('run_id', '')}  |  "
        f"時間: {record_dict.get('timestamp', '')}"
    )
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    # ── 角色說明 ──
    _add_ai_roles_legend(doc)

    doc.add_heading("作用原理 / How Cross-Examination Works", level=2)
    doc.add_paragraph(
        "Phase 5 交叉詰問採用辯論式 AI 稽核架構：\n\n"
        "1. 依 ISO 13485 稽核清單（71 條款）抽取當次問題（以日期為 seed 輪替，全 71 條各有至少 2 個版本）\n"
        "2. Analyzer（辯護方）分析各 QMS 文件，輸出：立場、信心度、關鍵證據\n"
        "3. Verifier（質疑方）逐條質疑 Analyzer 論點，挑戰未引用的法規要求或證據漏洞\n"
        "4. 雙方進行最多 3 輪辯論，達成 agree / partial / disagree 結論\n"
        "5. QA Auditor（審查者）對整場辯論獨立評分（0–100）\n"
        "6. 最終判定（verdict）依辯論結論與 gap_severity 由風險矩陣自動計算\n\n"
        "縮寫對照：verdict — compliant / improvement_plan / deadline_correction / immediate_correction\n"
        "         gap_severity — none / minor / major / critical\n"
        "         flagged_for_ra — 需 RA 法規事務人員進一步審查"
    )

    # Summary
    doc.add_heading("摘要", level=2)
    regs = ", ".join(record_dict.get("selected_regulations", [])) or "無"
    countries = ", ".join(record_dict.get("countries", [])) or "無"
    doc.add_paragraph(
        f"法規: {regs}\n"
        f"國家: {countries}\n"
        f"條款數: {record_dict.get('total_clauses', 0)}  |  "
        f"同意: {record_dict.get('total_agreed', 0)}  |  "
        f"標記 RA: {record_dict.get('total_flagged', 0)}  |  "
        f"總輪次: {record_dict.get('total_rounds', 0)}\n"
        f"模型: {record_dict.get('llm_model', '')}  |  "
        f"耗時: {record_dict.get('duration_seconds', 0):.1f}s"
    )

    # Load ISO checklist for expected_evidence lookup
    try:
        from src.analysis.compliance_rules import ISO_13485_CHECKLIST as _ISO_CL
    except Exception:
        _ISO_CL = {}

    # Clause details
    doc.add_heading("條款交叉詰問詳情", level=2)
    for clause in record_dict.get("clauses", []):
        cid = clause.get('clause_id', '')
        doc.add_heading(
            f"{cid} — {clause.get('clause_title', '')}",
            level=3,
        )
        doc.add_paragraph(
            f"文件: {clause.get('doc_id', '')} {clause.get('doc_title', '')}\n"
            f"判定: {clause.get('verdict', '')}  |  差距: {clause.get('gap_severity', '')}\n"
            f"同意: {'✅ 是' if clause.get('agreed') else '❌ 否'}  |  "
            f"RA 標記: {'⚠️ 是' if clause.get('flagged_for_ra') else '否'}"
        )

        # Audit question source label (A/B hybrid)
        _cl_def = _ISO_CL.get(cid, {})
        _q_source = clause.get("question_source", "")
        if _q_source == "B":
            _src_label = doc.add_paragraph(
                "🤖 [LLM 動態生成問題 / AI-Generated Question (Side B)]",
                style="Quote",
            )
            _focus = clause.get("focus_area", "")
            if _focus:
                doc.add_paragraph(f"  聚焦面向: {_focus}")
            _verifiable = clause.get("verifiable_by", "")
            if _verifiable:
                doc.add_paragraph(f"  驗證方式: {_verifiable}")
        elif _q_source == "A":
            doc.add_paragraph(
                "📋 [靜態題庫問題 / Static Question Pool (Side A)]",
                style="Quote",
            )

        # Audit question
        _aq = clause.get("audit_question") or _cl_def.get("audit_question", "")
        if _aq:
            doc.add_paragraph(f"稽核問題: {_aq}")

        # Expected evidence (static checklist)
        _exp_ev = _cl_def.get("expected_evidence", [])
        if _exp_ev:
            doc.add_paragraph(
                "預期書面證據（靜態清單）/ Expected Evidence (Static):\n"
                + "\n".join(f"  • {e}" for e in _exp_ev),
                style="Quote",
            )

        for rd in clause.get("rounds", []):
            doc.add_heading(f"Round {rd.get('round', '?')}", level=4)

            analyzer = rd.get("analyzer", {})
            p = doc.add_paragraph()
            r = p.add_run("🔍 分析者（實際看到）: ")
            r.bold = True
            _render_role_content(p, analyzer)

            verifier = rd.get("verifier", {})
            p = doc.add_paragraph()
            r = p.add_run("⚖️ 驗證者（期望看到）: ")
            r.bold = True
            _render_role_content(p, verifier)

            agreement = verifier.get("agreement_level", "")
            doc.add_paragraph(f"Agreement: {agreement}")

        qa = clause.get("qa_audit", {})
        if qa:
            doc.add_heading("🔎 第三方稽核", level=4)
            doc.add_paragraph(
                f"分數: {qa.get('score', 0)}/100  |  "
                f"問題品質: {qa.get('question_quality', '')}  |  "
                f"回答準確: {qa.get('answer_accuracy', '')}\n"
                f"幻覺偵測: {'⚠️ 是' if qa.get('hallucination_detected') else '否'}"
            )
            issues = qa.get("issues", [])
            if issues:
                for iss in issues:
                    doc.add_paragraph(f"  • {iss}")

    safe_save_binary(filepath, doc.save)
    return filepath


def export_crossexam_record_excel(record_dict: dict) -> Path:
    """Export a single cross-exam record as an Excel file.

    Args:
        record_dict: CrossExamRecord.to_dict() output

    Returns:
        Path to the generated .xlsx file
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"crossexam_{record_dict.get('record_id', 'unknown')}.xlsx"

    wb = Workbook()

    # Sheet 1: Summary
    ws_sum = wb.active
    ws_sum.title = "摘要"
    summary_data = [
        ("記錄 ID", record_dict.get("record_id", "")),
        ("分析 ID", record_dict.get("run_id", "")),
        ("時間", record_dict.get("timestamp", "")),
        ("法規", ", ".join(record_dict.get("selected_regulations", []))),
        ("國家", ", ".join(record_dict.get("countries", []))),
        ("條款數", record_dict.get("total_clauses", 0)),
        ("同意數", record_dict.get("total_agreed", 0)),
        ("RA 標記", record_dict.get("total_flagged", 0)),
        ("總輪次", record_dict.get("total_rounds", 0)),
        ("模型", record_dict.get("llm_model", "")),
        ("耗時 (秒)", record_dict.get("duration_seconds", 0)),
    ]
    header_fill = PatternFill(
        start_color="4472C4", end_color="4472C4", fill_type="solid"
    )
    header_font = Font(bold=True, color="FFFFFF")
    for ri, (label, value) in enumerate(summary_data, 1):
        c1 = ws_sum.cell(row=ri, column=1, value=label)
        c1.fill = header_fill
        c1.font = header_font
        ws_sum.cell(row=ri, column=2, value=str(value))
    ws_sum.column_dimensions["A"].width = 15
    ws_sum.column_dimensions["B"].width = 50

    # Sheet 2: Clause Details
    ws_detail = wb.create_sheet("條款詳情")
    headers = [
        "條款 ID",          # 1
        "條款名稱",          # 2
        "文件 ID",           # 3
        "判定",              # 4
        "差距",              # 5
        "同意",              # 6
        "RA 標記",           # 7
        "問題來源(A/B)",     # 8  ← new
        "輪次數",            # 9
        "R1 分析者立場",     # 10
        "R1 分析者信心",     # 11
        "R1 實際看到(證據)", # 12  ← new
        "R1 驗證者評估",     # 13
        "R1 Agreement",      # 14
        "R1 期望看到(證據)", # 15  ← new
        "QA 分數",           # 16
        "問題品質",          # 17
        "回答準確",          # 18
        "幻覺偵測",          # 19
    ]
    for ci, h in enumerate(headers, 1):
        c = ws_detail.cell(row=1, column=ci, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    for ri, clause in enumerate(record_dict.get("clauses", []), 2):
        ws_detail.cell(row=ri, column=1, value=clause.get("clause_id", ""))
        ws_detail.cell(row=ri, column=2, value=clause.get("clause_title", ""))
        ws_detail.cell(row=ri, column=3, value=clause.get("doc_id", ""))
        ws_detail.cell(row=ri, column=4, value=clause.get("verdict", ""))
        ws_detail.cell(row=ri, column=5, value=clause.get("gap_severity", ""))
        ws_detail.cell(row=ri, column=6, value="Y" if clause.get("agreed") else "N")
        ws_detail.cell(
            row=ri, column=7, value="Y" if clause.get("flagged_for_ra") else ""
        )
        ws_detail.cell(row=ri, column=8, value=clause.get("question_source", ""))
        rounds = clause.get("rounds", [])
        ws_detail.cell(row=ri, column=9, value=len(rounds))
        if rounds:
            r1 = rounds[0]
            a = r1.get("analyzer", {})
            v = r1.get("verifier", {})
            ws_detail.cell(
                row=ri,
                column=10,
                value=_flatten_role_text(a, "position")[:500],
            )
            ws_detail.cell(
                row=ri,
                column=11,
                value=str(a.get("confidence", a.get("confidence_score", ""))),
            )
            # R1 實際看到：Analyzer key_evidence
            _actual_ev = a.get("key_evidence", [])
            if isinstance(_actual_ev, list):
                _actual_ev = "; ".join(str(x) for x in _actual_ev)
            ws_detail.cell(row=ri, column=12, value=str(_actual_ev)[:500])
            ws_detail.cell(
                row=ri,
                column=13,
                value=_flatten_role_text(v, "assessment")[:500],
            )
            ws_detail.cell(
                row=ri,
                column=14,
                value=v.get("agreement_level", ""),
            )
            # R1 期望看到：Verifier challenges[*].expected_evidence
            _challenges = v.get("challenges", [])
            _exp_parts = []
            for _ch in (_challenges if isinstance(_challenges, list) else []):
                if isinstance(_ch, dict) and _ch.get("expected_evidence"):
                    _exp_parts.append(_ch["expected_evidence"])
            ws_detail.cell(row=ri, column=15, value="; ".join(_exp_parts)[:500])
        qa = clause.get("qa_audit", {})
        ws_detail.cell(row=ri, column=16, value=qa.get("score", "") if qa else "")
        ws_detail.cell(
            row=ri, column=17, value=qa.get("question_quality", "") if qa else ""
        )
        ws_detail.cell(
            row=ri, column=18, value=qa.get("answer_accuracy", "") if qa else ""
        )
        ws_detail.cell(
            row=ri,
            column=19,
            value="Yes"
            if qa and qa.get("hallucination_detected")
            else ("No" if qa else ""),
        )

    # Auto-width
    for col in ws_detail.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=8)
        ws_detail.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)

    safe_save_binary(filepath, wb.save)
    return filepath


# ============================================================
# Deep Analysis Report Export
# ============================================================


def export_deep_report_word(
    run_id: str,
    flat_rows: list[dict],
    summary: dict,
    interactions: list[dict] | None = None,
    crossexam_record: dict | None = None,
    meta_analysis: dict | None = None,
    qa_audit_summary: dict | None = None,
) -> Path:
    """Export a deep analysis report as Word document.

    Includes ALL LLM interactions, GAP analysis, verification, remediation.

    Args:
        run_id: Pipeline run ID
        flat_rows: ComparisonTable.to_flat_rows() output
        summary: ComparisonTable.summary() output
        interactions: InteractionLog interactions list
        crossexam_record: CrossExamRecord.to_dict() (optional)
        meta_analysis: Meta-analysis QA results (optional)

    Returns:
        Path to generated .docx
    """
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"deep_report_{run_id}.docx"

    doc = Document()

    # ── Title ──
    title = doc.add_heading("AI-QMS 深度合規性分析報告", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = meta_p.add_run(
        f"分析 ID: {run_id}  |  "
        f"匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    # ── AI Roles Legend ──
    _add_ai_roles_legend(doc)

    # ── Section 1: Executive Summary ──
    doc.add_heading("第一章 執行摘要", level=2)
    verdict_dist = summary.get("verdict_distribution", {})
    risk_dist = summary.get("risk_distribution", {})
    total = summary.get("total_rows", len(flat_rows))
    flagged = summary.get("flagged_for_ra", 0)

    summary_text = (
        f"本次合規性分析共評估 {total} 個條款-文件對照項目。\n\n判定結果分布:\n"
    )
    for v, count in verdict_dist.items():
        summary_text += f"  • {v}: {count} 項\n"
    summary_text += f"\n風險等級分布:\n"
    for r, count in risk_dist.items():
        summary_text += f"  • {r}: {count} 項\n"
    if flagged:
        summary_text += f"\n⚠️ 需 RA 審查: {flagged} 項\n"

    doc.add_paragraph(summary_text)

    # ── Section 2: GAP Analysis Details ──
    doc.add_heading("第二章 GAP 分析詳情 (Phase 1)", level=2)
    if interactions:
        gap_interactions = [i for i in interactions if i.get("phase") == "gap_scan"]
        if gap_interactions:
            for gi in gap_interactions:
                doc.add_heading(
                    f"文件: {gi.get('doc_id', '')} — {gi.get('doc_title', '')}",
                    level=3,
                )
                # Evidence summary
                extra = gi.get("extra", {})
                ev_sum = extra.get("evidence_summary", {})
                if ev_sum:
                    doc.add_paragraph(
                        f"找到: {ev_sum.get('found', 0)}  |  "
                        f"未找到: {ev_sum.get('not_found', 0)}  |  "
                        f"不足: {ev_sum.get('inadequate', 0)}"
                    )
                # LLM Response (truncated for readability)
                resp = gi.get("llm_response", "")
                if resp:
                    doc.add_heading("LLM 回應", level=4)
                    # Split into manageable paragraphs
                    for chunk in _split_text(resp, 3000):
                        doc.add_paragraph(chunk)
                usage = gi.get("usage", {})
                if usage:
                    doc.add_paragraph(
                        f"Token 用量: {usage.get('total_tokens', 0):,}  |  "
                        f"模型: {gi.get('model', '')}"
                    )
        else:
            doc.add_paragraph("（本次分析無 Phase 1 LLM 互動記錄）")
    else:
        doc.add_paragraph("（無 LLM 互動記錄可用）")

    # ── Section 3: Verification Details ──
    doc.add_heading("第三章 驗證詳情 (Phase 2)", level=2)
    if interactions:
        verify_interactions = [
            i for i in interactions if i.get("phase") == "checklist_verify"
        ]
        if verify_interactions:
            for vi in verify_interactions:
                doc.add_heading(
                    f"文件: {vi.get('doc_id', '')} — {vi.get('doc_title', '')}",
                    level=3,
                )
                resp = vi.get("llm_response", "")
                if resp:
                    for chunk in _split_text(resp, 3000):
                        doc.add_paragraph(chunk)
                usage = vi.get("usage", {})
                if usage:
                    doc.add_paragraph(f"Token 用量: {usage.get('total_tokens', 0):,}")
        else:
            doc.add_paragraph("（本次分析無 Phase 2 LLM 互動記錄）")
    else:
        doc.add_paragraph("（無 LLM 互動記錄可用）")

    # ── Section 4: Remediation ──
    doc.add_heading("第四章 改善建議 (Phase 4)", level=2)
    if interactions:
        remed_interactions = [
            i for i in interactions if i.get("phase") == "remediation"
        ]
        if remed_interactions:
            for ri in remed_interactions:
                doc.add_heading(
                    f"文件: {ri.get('doc_id', '')} — {ri.get('doc_title', '')}",
                    level=3,
                )
                resp = ri.get("llm_response", "")
                if resp:
                    for chunk in _split_text(resp, 3000):
                        doc.add_paragraph(chunk)
        else:
            doc.add_paragraph("（本次分析無 Phase 4 LLM 互動記錄）")
    else:
        doc.add_paragraph("（無 LLM 互動記錄可用）")

    # ── Section 5: Cross-Examination ──
    doc.add_heading("第五章 交叉詰問 (Phase 5)", level=2)
    if interactions:
        xexam_interactions = [
            i for i in interactions if i.get("phase") == "verification"
        ]
        if xexam_interactions:
            # Group by clause_id
            clause_groups: dict[str, list[dict]] = {}
            for xi in xexam_interactions:
                cid = xi.get("clause_id", "unknown")
                clause_groups.setdefault(cid, []).append(xi)

            for cid, group in clause_groups.items():
                clause_title = group[0].get("clause_title", "")
                doc.add_heading(f"{cid} — {clause_title}", level=3)
                doc_id = group[0].get("doc_id", "")
                if doc_id:
                    doc.add_paragraph(f"文件: {doc_id}")

                # Sort by round_number and role
                group.sort(key=lambda x: (x.get("round_number", 0), x.get("role", "")))

                current_round = 0
                for xi in group:
                    rd_num = xi.get("round_number", 0)
                    if rd_num != current_round:
                        current_round = rd_num
                        doc.add_heading(f"Round {rd_num}", level=4)

                    role = xi.get("role", "")
                    role_label = "🔍 分析者" if role == "analyzer" else "⚖️ 驗證者"

                    p = doc.add_paragraph()
                    r = p.add_run(f"{role_label}: ")
                    r.bold = True

                    parsed = xi.get("parsed_response")
                    if parsed and isinstance(parsed, dict):
                        _render_role_content(p, parsed)
                    else:
                        resp = xi.get("llm_response", "")
                        p.add_run(resp[:3000])

                    extra = xi.get("extra", {})
                    agreement = extra.get("agreement_level", "")
                    if agreement:
                        doc.add_paragraph(f"Agreement: {agreement}")
        else:
            doc.add_paragraph("（本次分析無 Phase 5 LLM 互動記錄）")
    elif crossexam_record:
        for clause in crossexam_record.get("clauses", []):
            doc.add_heading(
                f"{clause.get('clause_id', '')} — {clause.get('clause_title', '')}",
                level=3,
            )
            for rd in clause.get("rounds", []):
                doc.add_heading(f"Round {rd.get('round', '?')}", level=4)
                p = doc.add_paragraph()
                r = p.add_run("🔍 分析者: ")
                r.bold = True
                _render_role_content(p, rd.get("analyzer", {}))

                p = doc.add_paragraph()
                r = p.add_run("⚖️ 驗證者: ")
                r.bold = True
                _render_role_content(p, rd.get("verifier", {}))

                agreement = rd.get("verifier", {}).get("agreement_level", "")
                if agreement:
                    doc.add_paragraph(f"Agreement: {agreement}")

            qa = clause.get("qa_audit", {})
            if qa:
                doc.add_heading("🔎 第三方稽核", level=4)
                doc.add_paragraph(
                    f"分數: {qa.get('score', 0)}/100  |  "
                    f"問題品質: {qa.get('question_quality', '')}  |  "
                    f"回答準確: {qa.get('answer_accuracy', '')}\n"
                    f"幻覺偵測: {'⚠️ 是' if qa.get('hallucination_detected') else '否'}"
                )
                issues = qa.get("issues", [])
                if issues:
                    for iss in issues:
                        doc.add_paragraph(f"  • {iss}")
    else:
        doc.add_paragraph("（無交叉詰問記錄可用）")

    # ── Section 5.5: Third-Party QA Audit ──
    doc.add_heading("第五章之二 第三方品質稽核 (Phase 5 Step 2)", level=2)
    _qa_sum = qa_audit_summary
    if not _qa_sum and crossexam_record:
        _qa_sum = crossexam_record.get("qa_audit_summary")
    if _qa_sum and not _qa_sum.get("skipped"):
        score = _qa_sum.get("overall_score", 0)
        doc.add_paragraph(
            f"整體品質分數: {score}/100\n"
            f"稽核條款數: {_qa_sum.get('clause_count', 0)}\n"
            f"模型: {_qa_sum.get('llm_model', '')}"
        )
        qa_summary_text = _qa_sum.get("summary", "")
        if qa_summary_text:
            doc.add_heading("稽核摘要", level=3)
            for chunk in _split_text(qa_summary_text, 3000):
                doc.add_paragraph(chunk)
        qa_recs = _qa_sum.get("recommendations", [])
        if qa_recs:
            doc.add_heading("稽核建議", level=3)
            for rec in qa_recs:
                doc.add_paragraph(f"• {rec}")
        clause_audits = _qa_sum.get("clause_audits", [])
        if clause_audits:
            doc.add_heading("逐條稽核結果", level=3)
            qa_tbl = doc.add_table(rows=1 + len(clause_audits), cols=6)
            qa_tbl.style = "Table Grid"
            qa_headers = ["條款", "分數", "問題品質", "回答準確", "幻覺偵測", "問題"]
            for i, h in enumerate(qa_headers):
                qa_tbl.rows[0].cells[i].text = h
            for qi, ca in enumerate(clause_audits, 1):
                qa_tbl.rows[qi].cells[0].text = ca.get("clause_id", "")
                qa_tbl.rows[qi].cells[1].text = str(ca.get("score", 0))
                qa_tbl.rows[qi].cells[2].text = ca.get("question_quality", "")
                qa_tbl.rows[qi].cells[3].text = ca.get("answer_accuracy", "")
                qa_tbl.rows[qi].cells[4].text = (
                    "⚠️ 是" if ca.get("hallucination_detected") else "否"
                )
                issues = ca.get("issues", [])
                qa_tbl.rows[qi].cells[5].text = "; ".join(issues) if issues else "無"
    elif _qa_sum and _qa_sum.get("skipped"):
        doc.add_paragraph(f"（已跳過：{_qa_sum.get('summary', '')}）")
    else:
        doc.add_paragraph("（無第三方品質稽核記錄）")

    # ── Section 6: Compliance Table ──
    doc.add_heading("第六章 合規性分析結果表", level=2)
    if flat_rows:
        headers = ["條款", "文件", "稽核影響", "判定", "風險", "差距", "RA 標記"]
        tbl = doc.add_table(rows=1 + len(flat_rows), cols=len(headers))
        tbl.style = "Table Grid"
        for i, h in enumerate(headers):
            tbl.rows[0].cells[i].text = h
        for ri, row in enumerate(flat_rows, 1):
            tbl.rows[ri].cells[
                0
            ].text = f"{row.get('clause_id', '')} {row.get('clause_title', '')}"
            tbl.rows[ri].cells[1].text = f"{row.get('doc_id', '')}"
            tbl.rows[ri].cells[2].text = row.get("audit_impact", "")
            tbl.rows[ri].cells[
                3
            ].text = f"{row.get('verdict_icon', '')} {row.get('verdict_label', '')}"
            tbl.rows[ri].cells[
                4
            ].text = f"{row.get('risk_icon', '')} {row.get('risk_label', '')}"
            tbl.rows[ri].cells[5].text = row.get("gap_severity", "") or ""
            tbl.rows[ri].cells[6].text = "⚠️" if row.get("flagged_for_ra") else ""

    # ── Section 7: Meta-Analysis (if available) ──
    if meta_analysis:
        doc.add_heading("第七章 交叉詰問品質分析", level=2)
        doc.add_paragraph(meta_analysis.get("summary", "（無分析摘要）"))

        findings = meta_analysis.get("findings", [])
        if findings:
            doc.add_heading("發現事項", level=3)
            for f in findings:
                doc.add_paragraph(
                    f"• [{f.get('severity', '')}] {f.get('description', '')}",
                )

        recommendations = meta_analysis.get("recommendations", [])
        if recommendations:
            doc.add_heading("建議", level=3)
            for rec in recommendations:
                doc.add_paragraph(f"• {rec}")

        tuning = meta_analysis.get("prompt_tuning", {})
        if tuning:
            doc.add_heading("Prompt 調整記錄", level=3)
            for key, val in tuning.items():
                doc.add_paragraph(f"• {key}: {val}")

    # ── Section 8: LLM Usage Statistics ──
    doc.add_heading("附錄 LLM 使用統計", level=2)
    if interactions:
        phase_counts: dict[str, dict] = {}
        for i in interactions:
            phase = i.get("phase_label", i.get("phase", "unknown"))
            if phase not in phase_counts:
                phase_counts[phase] = {"count": 0, "tokens": 0}
            phase_counts[phase]["count"] += 1
            phase_counts[phase]["tokens"] += i.get("usage", {}).get("total_tokens", 0)

        for phase, stats in phase_counts.items():
            doc.add_paragraph(
                f"• {phase}: {stats['count']} 次呼叫, {stats['tokens']:,} tokens"
            )

    safe_save_binary(filepath, doc.save)
    return filepath


def export_deep_report_excel(
    run_id: str,
    flat_rows: list[dict],
    summary: dict,
    interactions: list[dict] | None = None,
    crossexam_record: dict | None = None,
    meta_analysis: dict | None = None,
    qa_audit_summary: dict | None = None,
) -> Path:
    """Export a deep analysis report as Excel workbook.

    Multiple sheets: Summary, Compliance Table, LLM Interactions, Cross-Exam, Meta-Analysis.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"deep_report_{run_id}.xlsx"

    wb = Workbook()
    header_fill = PatternFill(
        start_color="4472C4", end_color="4472C4", fill_type="solid"
    )
    header_font = Font(bold=True, color="FFFFFF", size=10)

    # ── Sheet 1: Summary ──
    ws_sum = wb.active
    ws_sum.title = "摘要"
    summary_data = [
        ("分析 ID", run_id),
        ("匯出時間", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("總分析項目", summary.get("total_rows", len(flat_rows))),
        ("需 RA 審查", summary.get("flagged_for_ra", 0)),
    ]
    verdict_dist = summary.get("verdict_distribution", {})
    for v, count in verdict_dist.items():
        summary_data.append((f"判定 - {v}", count))
    risk_dist = summary.get("risk_distribution", {})
    for r, count in risk_dist.items():
        summary_data.append((f"風險 - {r}", count))

    for ri, (label, value) in enumerate(summary_data, 1):
        c1 = ws_sum.cell(row=ri, column=1, value=label)
        c1.fill = header_fill
        c1.font = header_font
        ws_sum.cell(row=ri, column=2, value=str(value))
    ws_sum.column_dimensions["A"].width = 20
    ws_sum.column_dimensions["B"].width = 40

    # ── Sheet 2: Compliance Table ──
    ws_comp = wb.create_sheet("合規分析")
    comp_headers = [
        "條款 ID",
        "條款名稱",
        "文件 ID",
        "文件標題",
        "稽核影響",
        "稽核問題",
        "判定",
        "風險等級",
        "差距嚴重度",
        "證據 (找到/總計)",
        "RA 標記",
        "RA 覆寫",
        "RA 備註",
    ]
    for ci, h in enumerate(comp_headers, 1):
        c = ws_comp.cell(row=1, column=ci, value=h)
        c.fill = header_fill
        c.font = header_font
    for ri, row in enumerate(flat_rows, 2):
        ws_comp.cell(row=ri, column=1, value=row.get("clause_id", ""))
        ws_comp.cell(row=ri, column=2, value=row.get("clause_title", ""))
        ws_comp.cell(row=ri, column=3, value=row.get("doc_id", ""))
        ws_comp.cell(row=ri, column=4, value=row.get("doc_title", ""))
        ws_comp.cell(row=ri, column=5, value=row.get("audit_impact", ""))
        ws_comp.cell(row=ri, column=6, value=row.get("audit_question", ""))
        ws_comp.cell(
            row=ri,
            column=7,
            value=f"{row.get('verdict_icon', '')} {row.get('verdict_label', '')}",
        )
        ws_comp.cell(
            row=ri,
            column=8,
            value=f"{row.get('risk_icon', '')} {row.get('risk_label', '')}",
        )
        ws_comp.cell(row=ri, column=9, value=row.get("gap_severity", "") or "")
        ws_comp.cell(
            row=ri,
            column=10,
            value=f"{row.get('evidence_found', 0)}/{row.get('evidence_total', 0)}",
        )
        ws_comp.cell(row=ri, column=11, value="Y" if row.get("flagged_for_ra") else "")
        override = row.get("ra_override")
        ws_comp.cell(
            row=ri,
            column=12,
            value=override.get("reason", "") if isinstance(override, dict) else "",
        )
        ws_comp.cell(row=ri, column=13, value=row.get("ra_notes", "") or "")

    # ── Sheet 3: LLM Interactions ──
    if interactions:
        ws_llm = wb.create_sheet("LLM 互動記錄")
        llm_headers = [
            "Phase",
            "文件 ID",
            "條款 ID",
            "角色",
            "Round",
            "LLM 回應 (摘要)",
            "Token 用量",
            "模型",
            "時間",
        ]
        for ci, h in enumerate(llm_headers, 1):
            c = ws_llm.cell(row=1, column=ci, value=h)
            c.fill = header_fill
            c.font = header_font
        for ri, interaction in enumerate(interactions, 2):
            ws_llm.cell(row=ri, column=1, value=interaction.get("phase_label", ""))
            ws_llm.cell(row=ri, column=2, value=interaction.get("doc_id", ""))
            ws_llm.cell(row=ri, column=3, value=interaction.get("clause_id", ""))
            ws_llm.cell(row=ri, column=4, value=interaction.get("role", ""))
            ws_llm.cell(row=ri, column=5, value=interaction.get("round_number", 0))
            resp = interaction.get("llm_response", "")
            ws_llm.cell(row=ri, column=6, value=resp[:500])
            ws_llm.cell(
                row=ri,
                column=7,
                value=interaction.get("usage", {}).get("total_tokens", 0),
            )
            ws_llm.cell(row=ri, column=8, value=interaction.get("model", ""))
            ws_llm.cell(row=ri, column=9, value=interaction.get("timestamp", ""))

        for col in ws_llm.columns:
            max_len = max((len(str(c.value or "")) for c in col), default=8)
            ws_llm.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)

    # ── Sheet 4: Cross-Exam Details ──
    if crossexam_record:
        ws_xe = wb.create_sheet("交叉詰問")
        xe_headers = [
            "條款 ID",
            "條款名稱",
            "文件 ID",
            "判定",
            "同意",
            "RA 標記",
            "輪次數",
            "R1 分析者立場",
            "R1 分析者信心",
            "R1 驗證者評估",
            "R1 Agreement",
            "QA 分數",
            "問題品質",
            "回答準確",
            "幻覺偵測",
        ]
        for ci, h in enumerate(xe_headers, 1):
            c = ws_xe.cell(row=1, column=ci, value=h)
            c.fill = header_fill
            c.font = header_font
        for ri, clause in enumerate(crossexam_record.get("clauses", []), 2):
            ws_xe.cell(row=ri, column=1, value=clause.get("clause_id", ""))
            ws_xe.cell(row=ri, column=2, value=clause.get("clause_title", ""))
            ws_xe.cell(row=ri, column=3, value=clause.get("doc_id", ""))
            ws_xe.cell(row=ri, column=4, value=clause.get("verdict", ""))
            ws_xe.cell(row=ri, column=5, value="Y" if clause.get("agreed") else "N")
            ws_xe.cell(
                row=ri, column=6, value="Y" if clause.get("flagged_for_ra") else ""
            )
            rounds = clause.get("rounds", [])
            ws_xe.cell(row=ri, column=7, value=len(rounds))
            if rounds:
                r1_a = rounds[0].get("analyzer", {})
                r1_v = rounds[0].get("verifier", {})
                ws_xe.cell(
                    row=ri,
                    column=8,
                    value=_flatten_role_text(r1_a, "position")[:500],
                )
                ws_xe.cell(
                    row=ri,
                    column=9,
                    value=str(r1_a.get("confidence", r1_a.get("confidence_score", ""))),
                )
                ws_xe.cell(
                    row=ri,
                    column=10,
                    value=_flatten_role_text(r1_v, "assessment")[:500],
                )
                ws_xe.cell(
                    row=ri,
                    column=11,
                    value=r1_v.get("agreement_level", ""),
                )
            qa = clause.get("qa_audit", {})
            ws_xe.cell(row=ri, column=12, value=qa.get("score", "") if qa else "")
            ws_xe.cell(
                row=ri, column=13, value=qa.get("question_quality", "") if qa else ""
            )
            ws_xe.cell(
                row=ri, column=14, value=qa.get("answer_accuracy", "") if qa else ""
            )
            ws_xe.cell(
                row=ri,
                column=15,
                value="Yes"
                if qa and qa.get("hallucination_detected")
                else ("No" if qa else ""),
            )

    _qa_sum_xl = qa_audit_summary
    if not _qa_sum_xl and crossexam_record:
        _qa_sum_xl = crossexam_record.get("qa_audit_summary")
    if _qa_sum_xl and not _qa_sum_xl.get("skipped"):
        ws_qa = wb.create_sheet("第三方稽核")
        qa_xl_headers = ["條款 ID", "分數", "問題品質", "回答準確", "幻覺偵測", "問題"]
        for ci, h in enumerate(qa_xl_headers, 1):
            c = ws_qa.cell(row=1, column=ci, value=h)
            c.fill = header_fill
            c.font = header_font
        for qi, ca in enumerate(_qa_sum_xl.get("clause_audits", []), 2):
            ws_qa.cell(row=qi, column=1, value=ca.get("clause_id", ""))
            ws_qa.cell(row=qi, column=2, value=ca.get("score", 0))
            ws_qa.cell(row=qi, column=3, value=ca.get("question_quality", ""))
            ws_qa.cell(row=qi, column=4, value=ca.get("answer_accuracy", ""))
            ws_qa.cell(
                row=qi,
                column=5,
                value="Yes" if ca.get("hallucination_detected") else "No",
            )
            issues = ca.get("issues", [])
            ws_qa.cell(row=qi, column=6, value="; ".join(issues) if issues else "")

    # ── Sheet 5: Meta-Analysis ──
    if meta_analysis:
        ws_ma = wb.create_sheet("品質分析")
        ws_ma.cell(row=1, column=1, value="交叉詰問品質分析結果").font = Font(
            bold=True, size=14
        )
        ws_ma.cell(row=3, column=1, value="摘要").font = Font(bold=True)
        ws_ma.cell(row=4, column=1, value=meta_analysis.get("summary", ""))

        findings = meta_analysis.get("findings", [])
        if findings:
            row_offset = 6
            ws_ma.cell(row=row_offset, column=1, value="發現事項").font = Font(
                bold=True
            )
            for fi, f in enumerate(findings, row_offset + 1):
                ws_ma.cell(row=fi, column=1, value=f.get("severity", ""))
                ws_ma.cell(row=fi, column=2, value=f.get("description", ""))

    # Auto-width for compliance sheet
    for col in ws_comp.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=8)
        ws_comp.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    safe_save_binary(filepath, wb.save)
    return filepath


# ============================================================
# Helpers
# ============================================================


def _split_text(text: str, max_len: int = 3000) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks


def _render_role_content(paragraph, data: dict) -> None:
    """Render Analyzer/Verifier structured data as readable text in a Word paragraph.

    Includes structured display of Verifier challenges with:
      - 質疑要點 (point)
      - 法規依據 (regulation_basis)
      - ▸ 期望看到 (expected_evidence)   ← "expected" side
      - ⚠ 風險影響 (worst_case_impact)
    Analyzer key_evidence renders as "▸ 實際看到" for the "actual" side.
    """
    if not data or not isinstance(data, dict):
        paragraph.add_run("（無資料）")
        return

    parts = []
    for key in (
        "position",
        "assessment",
        "confidence",
        "confidence_score",
        "evidence",
        "evidence_cited",
        "key_evidence",
        "reasoning",
        "analysis",
        "agreement_level",
        "concerns",
        "recommendation",
    ):
        val = data.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            label = "▸ 實際看到" if key == "key_evidence" else key
            parts.append(f"{label}:")
            for item in val:
                parts.append(f"    • {item}")
        elif isinstance(val, dict):
            parts.append(f"{key}: {json.dumps(val, ensure_ascii=False)}")
        else:
            parts.append(f"{key}: {val}")

    # Render Verifier challenges in structured "期望 vs 實際" format
    challenges = data.get("challenges", [])
    if challenges and isinstance(challenges, list):
        parts.append("─── 驗證者質疑 / Verifier Challenges ───")
        for i, ch in enumerate(challenges, 1):
            if isinstance(ch, dict):
                parts.append(f"  [{i}] {ch.get('point', '')}")
                reg_basis = ch.get("regulation_basis", "")
                if reg_basis:
                    parts.append(f"      法規依據: {reg_basis}")
                exp_ev = ch.get("expected_evidence", "")
                if exp_ev:
                    parts.append(f"      ▸ 期望看到: {exp_ev}")
                wci = ch.get("worst_case_impact", "")
                if wci:
                    parts.append(f"      ⚠ 風險影響: {wci}")
            else:
                parts.append(f"  [{i}] {ch}")

    remaining = data.get("remaining_concerns", [])
    if remaining and isinstance(remaining, list):
        parts.append("─── 未解疑慮 / Remaining Concerns ───")
        for c in remaining:
            parts.append(f"  • {c}")

    if parts:
        paragraph.add_run("\n".join(parts)[:4000])
    else:
        paragraph.add_run(json.dumps(data, ensure_ascii=False, indent=2)[:3000])


def _flatten_role_text(data: dict, primary_key: str) -> str:
    """Extract primary field from Analyzer/Verifier data as a readable string."""
    if not data or not isinstance(data, dict):
        return ""
    val = data.get(primary_key, "")
    if isinstance(val, list):
        return "; ".join(str(v) for v in val)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val) if val else json.dumps(data, ensure_ascii=False)
