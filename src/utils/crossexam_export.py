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

EXPORT_DIR = (Path(__file__).resolve().parent.parent.parent / "data" / "exports")


# ============================================================
# Language helpers (bilingual section headers)
# ============================================================

from src.chainlit_app.lang_config import lang_key as _lang_key  # noqa: E402


_EXPORT_HEADERS: dict[str, dict[str, str]] = {
    "zh": {
        "title_crossexam": "AI-QMS 交叉詰問記錄",
        "title_deep": "AI-QMS 完整分析報告",
        "summary": "摘要",
        "clause_details": "條款交叉詰問詳情",
        "record_id": "記錄 ID",
        "analysis_id": "分析 ID",
        "time": "時間",
        "regulations": "法規",
        "countries": "國家",
        "clause_count": "條款數",
        "agreed": "同意",
        "flagged_ra": "標記 RA",
        "total_rounds": "總輪次",
        "model": "模型",
        "duration": "耗時",
        "none": "無",
        "doc": "文件",
        "verdict": "判定",
        "gap": "差距",
        "yes": "是",
        "no": "否",
        # Word body labels
        "how_it_works_heading": "作用原理 / How Cross-Examination Works",
        "how_it_works_body": (
            "Phase 5 交叉詰問採用辯論式 AI 稽核架構：\n\n"
            "1. 依 ISO 13485 稽核清單（71 條款）抽取當次問題（以日期為 seed 輪替，各條款至少 7 個版本）\n"
            "2. Analyzer（辯護方）分析各 QMS 文件，輸出：立場、信心度、關鍵證據\n"
            "3. Verifier（質疑方）逐條質疑 Analyzer 論點，挑戰未引用的法規要求或證據漏洞\n"
            "4. 雙方進行最多 3 輪辯論，達成 agree / partial / disagree 結論\n"
            "5. QA Auditor（審查者）對整場辯論獨立評分（0–100）\n"
            "6. 最終判定（verdict）依辯論結論與 gap_severity 由風險矩陣自動計算\n\n"
            "縮寫對照：verdict — compliant / improvement_plan / deadline_correction / immediate_correction\n"
            "         gap_severity — none / minor / major / critical\n"
            "         flagged_for_ra — 需 RA 法規事務人員進一步審查"
        ),
        "audit_question": "稽核問題",
        "expected_evidence": "預期書面證據（靜態清單）/ Expected Evidence (Static)",
        "source_b_label": "🤖 [LLM 動態生成問題 (Side B)]",
        "source_a_label": "📋 [靜態題庫問題 (Side A)]",
        "focus_area_label": "聚焦面向",
        "verifiable_by_label": "驗證方式",
        "analyzer_label": "🔍 分析者（實際看到）",
        "verifier_label": "⚖️ 驗證者（期望看到）",
        "qa_audit_heading": "🔎 第三方稽核",
        "score_label": "分數",
        "question_quality_label": "問題品質",
        "answer_accuracy_label": "回答準確",
        "hallucination_label": "幻覺偵測",
        "hallucination_yes": "⚠️ 是",
        "hallucination_no": "否",
        "ra_flag_yes": "⚠️ 是",
        "ra_flag_no": "否",
        "agreed_yes": "✅ 是",
        "agreed_no": "❌ 否",
        "meta_label": "記錄 ID: {rid}  |  分析 ID: {aid}  |  時間: {ts}",
        "summary_body": "法規: {regs}\n國家: {countries}\n條款數: {clauses}  |  同意: {agreed}  |  標記 RA: {flagged}  |  總輪次: {rounds}\n模型: {model}  |  耗時: {duration:.1f}s",
        # Deep report section headings
        "deep_title": "AI-QMS 深度合規性分析報告",
        "deep_meta": "分析 ID: {run_id}  |  匯出時間: {ts}",
        "deep_s1": "第一章 執行摘要",
        "deep_s1_intro": "本次合規性分析共評估 {total} 個條款-文件對照項目。\n\n判定結果分布:\n",
        "deep_s1_risk": "\n風險等級分布:\n",
        "deep_s1_ra": "\n⚠️ 需 RA 審查: {flagged} 項\n",
        "deep_s2": "第二章 GAP 分析詳情 (Phase 1)",
        "deep_s2_doc": "文件",
        "deep_s2_found": "找到",
        "deep_s2_not_found": "未找到",
        "deep_s2_inadequate": "不足",
        "deep_llm_response": "LLM 回應",
        "deep_token_usage": "Token 用量: {tokens:,}  |  模型: {model}",
        "deep_no_p1": "（本次分析無 Phase 1 LLM 互動記錄）",
        "deep_no_record": "（無 LLM 互動記錄可用）",
        "deep_s3": "第三章 驗證詳情 (Phase 2)",
        "deep_no_p2": "（本次分析無 Phase 2 LLM 互動記錄）",
        "deep_s4": "第四章 改善建議 (Phase 4)",
        "deep_no_p4": "（本次分析無 Phase 4 LLM 互動記錄）",
        "deep_s5": "第五章 交叉詰問 (Phase 5)",
        "deep_no_p5": "（本次分析無 Phase 5 LLM 互動記錄）",
        "deep_no_xexam": "（無交叉詰問記錄可用）",
        "deep_s55": "第五章之二 第三方品質稽核 (Phase 5 Step 2)",
        "deep_qa_score": "整體品質分數: {score}/100\n稽核條款數: {count}\n模型: {model}",
        "deep_qa_summary": "稽核摘要",
        "deep_qa_recs": "稽核建議",
        "deep_qa_clause_results": "逐條稽核結果",
        "deep_qa_tbl_headers": ["條款", "分數", "問題品質", "回答準確", "幻覺偵測", "問題"],
        "deep_doc_label": "文件",
        "deep_analyzer_label": "🔍 分析者",
        "deep_verifier_label": "⚖️ 驗證者",
        "deep_s6": "第六章 合規性分析結果表",
        "deep_s6_headers": ["條款", "文件", "稽核影響", "判定", "風險", "差距", "RA 標記"],
        "deep_s7": "第七章 交叉詰問品質分析",
        "deep_s7_findings": "發現事項",
        "deep_s7_recs": "建議",
        "deep_s7_prompt": "Prompt 調整記錄",
        "deep_s7_no_summary": "（無分析摘要）",
        "deep_s8": "附錄 LLM 使用統計",
        "deep_s8_calls": "次呼叫",
        "deep_no_issues": "無",
        "deep_qa_skipped": "（已跳過：{summary}）",
        "deep_no_qa_record": "（無第三方品質稽核記錄）",
        "xl_sheet_summary": "摘要",
        "xl_sheet_compliance": "合規分析",
        "xl_sheet_llm": "LLM 互動記錄",
        "xl_sheet_crossexam": "交叉詰問",
        "xl_sheet_meta": "品質分析",
        "xl_run_id": "分析 ID",
        "xl_export_time": "匯出時間",
        "xl_total_rows": "總分析項目",
        "xl_flagged_ra": "需 RA 審查",
        "xl_verdict_prefix": "判定 - ",
        "xl_risk_prefix": "風險 - ",
        "xl_comp_headers": ["條款 ID","條款名稱","文件 ID","文件標題","稽核影響","稽核問題","判定","風險等級","差距嚴重度","證據 (找到/總計)","RA 標記","RA 覆寫","RA 備註","改善建議 (LLM P4)","法規引用 (LLM P4)","分析者立場 (LLM P5)","驗證者評語 (LLM P5)"],
        "xl_llm_headers": ["Phase","文件 ID","條款 ID","角色","Round","LLM 回應 (摘要)","Token 用量","模型","時間"],
        "xl_xe_headers": ["條款 ID","條款名稱","文件 ID","判定","同意","RA 標記","輪次數","R1 分析者立場","R1 分析者信心","R1 驗證者評估","R1 Agreement","QA 分數","問題品質","回答準確","幻覺偵測"],
    },
    "en": {
        "title_crossexam": "AI-QMS Cross-Examination Record",
        "title_deep": "AI-QMS Full Analysis Report",
        "summary": "Summary",
        "clause_details": "Clause Cross-Examination Details",
        "record_id": "Record ID",
        "analysis_id": "Run ID",
        "time": "Time",
        "regulations": "Regulations",
        "countries": "Countries",
        "clause_count": "Clause count",
        "agreed": "Agreed",
        "flagged_ra": "Flagged for RA",
        "total_rounds": "Total rounds",
        "model": "Model",
        "duration": "Duration",
        "none": "None",
        "doc": "Document",
        "verdict": "Verdict",
        "gap": "Gap",
        "yes": "Yes",
        "no": "No",
        # Word body labels
        "how_it_works_heading": "How Cross-Examination Works",
        "how_it_works_body": (
            "Phase 5 cross-examination uses a debate-based AI audit architecture:\n\n"
            "1. Questions are drawn from the ISO 13485 audit checklist (71 clauses) with date-seeded rotation — at least 7 versions per clause\n"
            "2. Analyzer (defender) analyzes each QMS document and outputs: position, confidence, key evidence\n"
            "3. Verifier (challenger) challenges the Analyzer's arguments clause by clause, targeting uncited regulatory requirements or evidence gaps\n"
            "4. Up to 3 debate rounds, reaching agree / partial / disagree conclusion\n"
            "5. QA Auditor independently scores the entire debate (0–100)\n"
            "6. Final verdict is auto-calculated from debate conclusion and gap_severity via the risk matrix\n\n"
            "Abbreviations: verdict — compliant / improvement_plan / deadline_correction / immediate_correction\n"
            "               gap_severity — none / minor / major / critical\n"
            "               flagged_for_ra — requires further review by RA regulatory affairs personnel"
        ),
        "audit_question": "Audit Question",
        "expected_evidence": "Expected Evidence (Static Checklist)",
        "source_b_label": "🤖 [AI-Generated Question (Side B)]",
        "source_a_label": "📋 [Static Question Pool (Side A)]",
        "focus_area_label": "Focus area",
        "verifiable_by_label": "Verifiable by",
        "analyzer_label": "🔍 Analyzer (Actual Evidence Found)",
        "verifier_label": "⚖️ Verifier (Expected to See)",
        "qa_audit_heading": "🔎 Third-Party Audit",
        "score_label": "Score",
        "question_quality_label": "Question quality",
        "answer_accuracy_label": "Answer accuracy",
        "hallucination_label": "Hallucination detected",
        "hallucination_yes": "⚠️ Yes",
        "hallucination_no": "No",
        "ra_flag_yes": "⚠️ Yes",
        "ra_flag_no": "No",
        "agreed_yes": "✅ Yes",
        "agreed_no": "❌ No",
        "meta_label": "Record ID: {rid}  |  Run ID: {aid}  |  Time: {ts}",
        "summary_body": "Regulations: {regs}\nCountries: {countries}\nClauses: {clauses}  |  Agreed: {agreed}  |  Flagged RA: {flagged}  |  Total rounds: {rounds}\nModel: {model}  |  Duration: {duration:.1f}s",
        # Deep report section headings
        "deep_title": "AI-QMS Deep Compliance Analysis Report",
        "deep_meta": "Run ID: {run_id}  |  Export time: {ts}",
        "deep_s1": "Chapter 1: Executive Summary",
        "deep_s1_intro": "This compliance analysis evaluated {total} clause-document pairs.\n\nVerdict distribution:\n",
        "deep_s1_risk": "\nRisk level distribution:\n",
        "deep_s1_ra": "\n⚠️ Requires RA review: {flagged} items\n",
        "deep_s2": "Chapter 2: GAP Analysis Details (Phase 1)",
        "deep_s2_doc": "Document",
        "deep_s2_found": "Found",
        "deep_s2_not_found": "Not found",
        "deep_s2_inadequate": "Inadequate",
        "deep_llm_response": "LLM Response",
        "deep_token_usage": "Token usage: {tokens:,}  |  Model: {model}",
        "deep_no_p1": "(No Phase 1 LLM interaction records for this analysis)",
        "deep_no_record": "(No LLM interaction records available)",
        "deep_s3": "Chapter 3: Verification Details (Phase 2)",
        "deep_no_p2": "(No Phase 2 LLM interaction records for this analysis)",
        "deep_s4": "Chapter 4: Improvement Suggestions (Phase 4)",
        "deep_no_p4": "(No Phase 4 LLM interaction records for this analysis)",
        "deep_s5": "Chapter 5: Cross-Examination (Phase 5)",
        "deep_no_p5": "(No Phase 5 LLM interaction records for this analysis)",
        "deep_no_xexam": "(No cross-examination records available)",
        "deep_s55": "Chapter 5b: Third-Party QA Audit (Phase 5 Step 2)",
        "deep_qa_score": "Overall quality score: {score}/100\nClauses audited: {count}\nModel: {model}",
        "deep_qa_summary": "Audit Summary",
        "deep_qa_recs": "Audit Recommendations",
        "deep_qa_clause_results": "Per-Clause Audit Results",
        "deep_qa_tbl_headers": ["Clause", "Score", "Question Quality", "Answer Accuracy", "Hallucination", "Issues"],
        "deep_doc_label": "Document",
        "deep_analyzer_label": "🔍 Analyzer",
        "deep_verifier_label": "⚖️ Verifier",
        "deep_s6": "Chapter 6: Compliance Analysis Results",
        "deep_s6_headers": ["Clause", "Document", "Audit Impact", "Verdict", "Risk", "Gap", "RA Flag"],
        "deep_s7": "Chapter 7: Cross-Examination Quality Analysis",
        "deep_s7_findings": "Findings",
        "deep_s7_recs": "Recommendations",
        "deep_s7_prompt": "Prompt Tuning Log",
        "deep_s7_no_summary": "(No analysis summary)",
        "deep_s8": "Appendix: LLM Usage Statistics",
        "deep_s8_calls": "calls",
        "deep_no_issues": "None",
        "deep_qa_skipped": "(Skipped: {summary})",
        "deep_no_qa_record": "(No third-party QA audit records)",
        "xl_sheet_summary": "Summary",
        "xl_sheet_compliance": "Compliance",
        "xl_sheet_llm": "LLM Interactions",
        "xl_sheet_crossexam": "Cross-Exam",
        "xl_sheet_meta": "Quality Analysis",
        "xl_run_id": "Run ID",
        "xl_export_time": "Export Time",
        "xl_total_rows": "Total Items",
        "xl_flagged_ra": "Flagged for RA",
        "xl_verdict_prefix": "Verdict - ",
        "xl_risk_prefix": "Risk - ",
        "xl_comp_headers": ["Clause ID","Clause Title","Doc ID","Doc Title","Audit Impact","Audit Question","Verdict","Risk Level","Gap Severity","Evidence (Found/Total)","RA Flag","RA Override","RA Notes","Improvement Suggestion (P4)","Regulation Cite (P4)","Analyzer Position (P5)","Verifier Assessment (P5)"],
        "xl_llm_headers": ["Phase","Doc ID","Clause ID","Role","Round","LLM Response (excerpt)","Token Usage","Model","Timestamp"],
        "xl_xe_headers": ["Clause ID","Clause Title","Doc ID","Verdict","Agreed","RA Flag","Rounds","R1 Analyzer Position","R1 Analyzer Confidence","R1 Verifier Assessment","R1 Agreement","QA Score","Question Quality","Answer Accuracy","Hallucination"],
    },
    "ja": {
        "title_crossexam": "AI-QMS 相互尋問記録",
        "title_deep": "AI-QMS 完全分析レポート",
        "summary": "サマリー",
        "clause_details": "条項相互尋問詳細",
        "record_id": "記録ID",
        "analysis_id": "実行ID",
        "time": "時刻",
        "regulations": "規制",
        "countries": "国",
        "clause_count": "条項数",
        "agreed": "同意",
        "flagged_ra": "RA要確認",
        "total_rounds": "総ラウンド数",
        "model": "モデル",
        "duration": "所要時間",
        "none": "なし",
        "doc": "文書",
        "verdict": "判定",
        "gap": "ギャップ",
        "yes": "はい",
        "no": "いいえ",
        # Word body labels
        "how_it_works_heading": "相互尋問の仕組み / How Cross-Examination Works",
        "how_it_works_body": (
            "フェーズ5の相互尋問は、ディベート型AI監査アーキテクチャを使用します：\n\n"
            "1. ISO 13485監査チェックリスト（71条項）から日付シードによる輪替での質問抽出 — 各条項最低7バージョン\n"
            "2. 分析者（弁護側）が各QMS文書を分析し出力：立場、信頼度、主要証拠\n"
            "3. 検証者（質疑側）が分析者の論点を条項ごとに質疑し、未引用の規制要件または証拠の欠落を指摘\n"
            "4. 最大3ラウンドのディベートを経てagree / partial / disagreeの結論に達する\n"
            "5. QA監査員が議論全体を独立採点（0〜100）\n"
            "6. 最終判定はリスクマトリクスにより議論結論とgap_severityから自動算出\n\n"
            "略語：verdict — compliant / improvement_plan / deadline_correction / immediate_correction\n"
            "      gap_severity — none / minor / major / critical\n"
            "      flagged_for_ra — RA規制担当者による追加審査が必要"
        ),
        "audit_question": "監査質問",
        "expected_evidence": "期待される書面証拠（静的チェックリスト）",
        "source_b_label": "🤖 [AI生成質問 (Side B)]",
        "source_a_label": "📋 [静的質問プール (Side A)]",
        "focus_area_label": "焦点領域",
        "verifiable_by_label": "検証方法",
        "analyzer_label": "🔍 分析者（実際に確認した証拠）",
        "verifier_label": "⚖️ 検証者（期待される証拠）",
        "qa_audit_heading": "🔎 第三者監査",
        "score_label": "スコア",
        "question_quality_label": "質問品質",
        "answer_accuracy_label": "回答精度",
        "hallucination_label": "ハルシネーション検出",
        "hallucination_yes": "⚠️ あり",
        "hallucination_no": "なし",
        "ra_flag_yes": "⚠️ あり",
        "ra_flag_no": "なし",
        "agreed_yes": "✅ はい",
        "agreed_no": "❌ いいえ",
        "meta_label": "記録ID: {rid}  |  実行ID: {aid}  |  時刻: {ts}",
        "summary_body": "規制: {regs}\n国: {countries}\n条項数: {clauses}  |  同意: {agreed}  |  RAフラグ: {flagged}  |  総ラウンド: {rounds}\nモデル: {model}  |  所要時間: {duration:.1f}s",
        # Deep report section headings
        "deep_title": "AI-QMS 詳細コンプライアンス分析レポート",
        "deep_meta": "実行ID: {run_id}  |  エクスポート時刻: {ts}",
        "deep_s1": "第1章 エグゼクティブサマリー",
        "deep_s1_intro": "このコンプライアンス分析では {total} 件の条項-文書ペアを評価しました。\n\n判定結果の分布:\n",
        "deep_s1_risk": "\nリスクレベルの分布:\n",
        "deep_s1_ra": "\n⚠️ RA審査が必要: {flagged} 件\n",
        "deep_s2": "第2章 GAP分析詳細 (Phase 1)",
        "deep_s2_doc": "文書",
        "deep_s2_found": "確認済み",
        "deep_s2_not_found": "未確認",
        "deep_s2_inadequate": "不十分",
        "deep_llm_response": "LLM回答",
        "deep_token_usage": "トークン使用量: {tokens:,}  |  モデル: {model}",
        "deep_no_p1": "（この分析ではPhase 1のLLMインタラクション記録はありません）",
        "deep_no_record": "（利用可能なLLMインタラクション記録はありません）",
        "deep_s3": "第3章 検証詳細 (Phase 2)",
        "deep_no_p2": "（この分析ではPhase 2のLLMインタラクション記録はありません）",
        "deep_s4": "第4章 改善提案 (Phase 4)",
        "deep_no_p4": "（この分析ではPhase 4のLLMインタラクション記録はありません）",
        "deep_s5": "第5章 相互尋問 (Phase 5)",
        "deep_no_p5": "（この分析ではPhase 5のLLMインタラクション記録はありません）",
        "deep_no_xexam": "（利用可能な相互尋問記録はありません）",
        "deep_s55": "第5章b 第三者QA監査 (Phase 5 Step 2)",
        "deep_qa_score": "全体品質スコア: {score}/100\n監査条項数: {count}\nモデル: {model}",
        "deep_qa_summary": "監査サマリー",
        "deep_qa_recs": "監査推奨事項",
        "deep_qa_clause_results": "条項別監査結果",
        "deep_qa_tbl_headers": ["条項", "スコア", "質問品質", "回答精度", "ハルシネーション", "問題点"],
        "deep_doc_label": "文書",
        "deep_analyzer_label": "🔍 分析者",
        "deep_verifier_label": "⚖️ 検証者",
        "deep_s6": "第6章 コンプライアンス分析結果表",
        "deep_s6_headers": ["条項", "文書", "監査影響", "判定", "リスク", "ギャップ", "RAフラグ"],
        "deep_s7": "第7章 相互尋問品質分析",
        "deep_s7_findings": "発見事項",
        "deep_s7_recs": "推奨事項",
        "deep_s7_prompt": "プロンプト調整記録",
        "deep_s7_no_summary": "（分析サマリーなし）",
        "deep_s8": "付録 LLM使用統計",
        "deep_s8_calls": "回の呼び出し",
        "deep_no_issues": "なし",
        "deep_qa_skipped": "（スキップ：{summary}）",
        "deep_no_qa_record": "（第三者QA監査記録なし）",
        "xl_sheet_summary": "サマリー",
        "xl_sheet_compliance": "コンプライアンス",
        "xl_sheet_llm": "LLMインタラクション",
        "xl_sheet_crossexam": "相互尋問",
        "xl_sheet_meta": "品質分析",
        "xl_run_id": "実行ID",
        "xl_export_time": "エクスポート時刻",
        "xl_total_rows": "総分析項目",
        "xl_flagged_ra": "RA要確認",
        "xl_verdict_prefix": "判定 - ",
        "xl_risk_prefix": "リスク - ",
        "xl_comp_headers": ["条項ID","条項名","文書ID","文書タイトル","監査影響","監査質問","判定","リスクレベル","ギャップ重大度","証拠（確認/合計）","RAフラグ","RAオーバーライド","RAメモ","改善提案 (P4)","規制引用 (P4)","分析者立場 (P5)","検証者評価 (P5)"],
        "xl_llm_headers": ["Phase","文書ID","条項ID","役割","Round","LLM回答（抜粋）","トークン使用量","モデル","タイムスタンプ"],
        "xl_xe_headers": ["条項ID","条項名","文書ID","判定","同意","RAフラグ","ラウンド数","R1分析者立場","R1分析者信頼度","R1検証者評価","R1 Agreement","QAスコア","質問品質","回答精度","ハルシネーション"],
    },
}


# ============================================================
# Shared: AI Roles Legend
# ============================================================


def _add_ai_roles_legend(doc, lang: str = "zh-TW") -> None:
    """Insert the AI roles and scoring legend into any Word document."""
    _lk = _lang_key(lang)

    if _lk == "en":
        doc.add_heading("AI Role Definitions & Scoring", level=2)
        doc.add_paragraph(
            "This system uses a three-role debate architecture for QMS compliance review."
        )
        p = doc.add_paragraph()
        p.add_run("🔍 Analyzer / Defender").bold = True
        doc.add_paragraph(
            "  Role: Analyzes QMS documents against each regulatory clause, takes a clear position\n"
            "        (compliant / non-compliant) and defends it with evidence.\n"
            "  Output fields:\n"
            "    • position: compliant / non-compliant / partially_compliant\n"
            "    • confidence: high / medium / low\n"
            "    • key_evidence: quoted passages supporting the position\n"
            "    • regulatory_references: cited clause numbers and text\n"
            "  Scoring: QA Auditor evaluates citation accuracy → Dim A (0–100)\n"
            "    90–100 Precise | 70–89 Minor gaps | 50–69 Partial | 30–49 Superficial | 0–29 Inadequate"
        )
        p = doc.add_paragraph()
        p.add_run("⚖️ Verifier / Reviewer").bold = True
        doc.add_paragraph(
            "  Role: Challenges the Analyzer's argument as devil's advocate, identifies uncited\n"
            "        regulatory requirements, contradictions, or evidence gaps.\n"
            "  Output fields:\n"
            "    • agreement_level: agree / partial / disagree\n"
            "    • challenges: specific weaknesses or gaps in the Analyzer's argument\n"
            "    • overall_assessment: summary evaluation of the debate quality\n"
            "    • remaining_concerns: unresolved issues after debate\n"
            "  Scoring: QA Auditor evaluates challenge quality and depth → Dim B (0–100)\n"
            "    90–100 Deep & balanced | 70–89 Minor gaps | 50–69 Notable gaps | 30–49 Superficial | 0–29 Inadequate"
        )
        p = doc.add_paragraph()
        p.add_run("🔎 QA Auditor").bold = True
        doc.add_paragraph(
            "  Role: Independent third-party auditor — does not debate, only evaluates debate quality.\n"
            "  Output fields:\n"
            "    • overall_score: 0–100 composite debate quality score\n"
            "    • score_rationale: explanation of the score band and specific reasons\n"
            "    • question_quality: good / acceptable / poor\n"
            "    • answer_accuracy: accurate / partially_accurate / inaccurate\n"
            "    • logic_consistency: consistent / minor_issues / inconsistent\n"
            "    • hallucination_detected: true / false — whether AI cited non-existent regulations\n"
            "    • issues: list of specific quality problems found in the debate\n"
            "  Review steps:\n"
            "    1. Assess whether audit questions target the core requirement (question_quality)\n"
            "    2. Verify that cited regulations exist and are accurately quoted (answer_accuracy)\n"
            "    3. Evaluate whether Verifier challenges are grounded and constructive (Dim B)\n"
            "    4. Check that both reasoning chains are complete and internally consistent (logic_consistency)\n"
            "    5. Detect fabricated clauses or erroneous citations (hallucination_detected)"
        )

    elif _lk == "ja":
        doc.add_heading("AIロール定義とスコアリング", level=2)
        doc.add_paragraph(
            "本システムはQMSコンプライアンス審査のために三役割討論アーキテクチャを採用しています。"
        )
        p = doc.add_paragraph()
        p.add_run("🔍 分析者 / 弁護方（Analyzer / Defender）").bold = True
        doc.add_paragraph(
            "  役割：各規制条項に対してQMS文書を分析し、明確な立場（適合／非適合）を取り、証拠で弁護します。\n"
            "  出力フィールド：\n"
            "    • position（立場）：compliant / non-compliant / partially_compliant\n"
            "    • confidence（確信度）：high / medium / low\n"
            "    • key_evidence（主要証拠）：立場を支持する文書引用箇所\n"
            "    • regulatory_references（規制引用）：引用した条項番号と条文\n"
            "  採点方法：QA Auditor が規制引用の正確性を評価 → Dim A（0–100）\n"
            "    90–100 引用精確 | 70–89 軽微な漏れ | 50–69 部分的 | 30–49 表面的 | 0–29 不十分"
        )
        p = doc.add_paragraph()
        p.add_run("⚖️ 検証者 / 質問方（Verifier / Reviewer）").bold = True
        doc.add_paragraph(
            "  役割：悪魔の代弁者として Analyzer の論拠に異議を唱え、未引用の規制要件・矛盾・証拠の欠落を指摘します。\n"
            "  出力フィールド：\n"
            "    • agreement_level（同意度）：agree / partial / disagree\n"
            "    • challenges（質問点）：Analyzer の論拠の弱点や欠落を具体的に指摘\n"
            "    • overall_assessment（総合評価）：討論品質の文章サマリー\n"
            "    • remaining_concerns（未解決懸念）：討論後も残る争点\n"
            "  採点方法：QA Auditor が質問の質と深さを評価 → Dim B（0–100）\n"
            "    90–100 深く均衡的 | 70–89 軽微な欠落 | 50–69 顕著な欠落 | 30–49 形式的 | 0–29 不十分"
        )
        p = doc.add_paragraph()
        p.add_run("🔎 品質監査員（QA Auditor）").bold = True
        doc.add_paragraph(
            "  役割：独立した第三者監査員として討論には参加せず、討論品質のみを客観的に評価します。\n"
            "  出力フィールド：\n"
            "    • overall_score（総合スコア）：0–100、討論品質の総合評点\n"
            "    • score_rationale（採点根拠）：スコア帯と具体的理由の説明\n"
            "    • question_quality（質問品質）：good / acceptable / poor\n"
            "    • answer_accuracy（回答精度）：accurate / partially_accurate / inaccurate\n"
            "    • logic_consistency（論理一貫性）：consistent / minor_issues / inconsistent\n"
            "    • hallucination_detected（幻覚検出）：true / false — AIが存在しない規制を引用したか\n"
            "    • issues（問題リスト）：討論中に発見された品質上の問題を具体的に列挙\n"
            "  審査手順：\n"
            "    1. 監査質問が当該条項の核心要件を対象としているか評価（question_quality）\n"
            "    2. Analyzer が引用した規制条文が存在し正確かを確認（answer_accuracy）\n"
            "    3. Verifier の質問が根拠のある建設的なものかを評価（Dim B）\n"
            "    4. 双方の推論チェーンが完整で内部矛盾がないか確認（logic_consistency）\n"
            "    5. 架空条項や誤引用などの幻覚現象を検出（hallucination_detected）"
        )

    else:
        doc.add_heading("AI 角色說明 / AI Role Definitions & Scoring", level=2)
        doc.add_paragraph(
            "本系統採用三角色辩論架構進行 QMS 合規性審查。\n"
            "This system uses a three-role debate architecture for QMS compliance review."
        )
        p = doc.add_paragraph()
        p.add_run("🔍 分析者 / 辩護方（Analyzer / Defender）").bold = True
        doc.add_paragraph(
            "  角色定位：針對每個法規条款，分析 QMS 文件是否提供充分書面證據，採取明確立場（符合/不符合）並加以辩護。\n"
            "  Role: Analyzes QMS documents against each regulatory clause, takes a clear position\n"
            "        (compliant / non-compliant) and defends it with evidence.\n"
            "  輸出欄位：\n"
            "    • position（立場）：compliant / non-compliant / partially_compliant\n"
            "    • confidence（信心度）：high / medium / low\n"
            "    • key_evidence（關鍵證據）：文件中支持立場的引用段落\n"
            "    • regulatory_references（法規引用）：引用的条款編號與条文\n"
            "  評分方式：QA Auditor 評估其法規引用準確性，計入 Dim A（0–100）\n"
            "    90–100 引用精確，完全符合 | 70–89 輕微遗漏 | 50–69 部分符合 | 30–49 表面符合 | 0–29 完全不符"
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
            "    • overall_assessment（整體評語）：對整場辩論品質的文字總結\n"
            "    • remaining_concerns（未解疑慮）：最終仍存在的爭議點\n"
            "  評分方式：QA Auditor 評估其詰問品質與深度，計入 Dim B（0–100）\n"
            "    90–100 深度均衡可操作 | 70–89 輕微缺失 | 50–69 明顯缺失 | 30–49 流於形式 | 0–29 嚴重不足"
        )
        p = doc.add_paragraph()
        p.add_run("🔎 品質稽核員 / 審查者（QA Auditor）").bold = True
        doc.add_paragraph(
            "  角色定位：模擬獨立第三方稽核員，不參與辩論，對整場 Analyzer↔Verifier 辩論進行客觀品質評核。\n"
            "  Role: Independent third-party auditor — does not debate, only evaluates debate quality.\n"
            "  輸出欄位：\n"
            "    • overall_score（整體分數）：0–100，綜合辩論品質評分\n"
            "    • score_rationale（評分依據）：說明落在哪個分數區間及具體原因\n"
            "    • question_quality（問題品質）：good / acceptable / poor — 評估稽核問題是否聰焦可查\n"
            "    • answer_accuracy（回答準確性）：accurate / partially_accurate / inaccurate\n"
            "    • logic_consistency（邏輯一致性）：consistent / minor_issues / inconsistent\n"
            "    • hallucination_detected（幻覺偉測）：true / false — AI 是否引用了不存在的法規內容\n"
            "    • issues（問題清單）：具體列出辩論中發現的品質問題\n"
            "  審核流程：\n"
            "    1. 評估稽核問題是否針對該条款的核心要求（question_quality）\n"
            "    2. 核查 Analyzer 引用的法規条文是否存在且準確（answer_accuracy）\n"
            "    3. 評估 Verifier 的質疑是否有根據且具建設性（Dim B）\n"
            "    4. 檢查雙方推理鏈是否完整、無內部矛盾（logic_consistency）\n"
            "    5. 偵測是否存在虛構条款、錯誤引用等幻覺現象（hallucination_detected）"
        )



# ============================================================
# Cross-Exam Record Export (individual records)
# ============================================================


def export_crossexam_record_word(record_dict: dict, lang: str = "zh-TW") -> Path:
    """Export a single cross-exam record as a Word document.

    Args:
        record_dict: CrossExamRecord.to_dict() output
        lang: UI language code (e.g., 'zh-TW', 'en', 'ja') — controls section headers

    Returns:
        Path to the generated .docx file
    """
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    lk = _lang_key(lang)
    h = _EXPORT_HEADERS[lk]

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"crossexam_{record_dict.get('record_id', 'unknown')}.docx"

    doc = Document()
    title = doc.add_heading(h["title_crossexam"], level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Metadata
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = meta.add_run(
        h["meta_label"].format(
            rid=record_dict.get("record_id", ""),
            aid=record_dict.get("run_id", ""),
            ts=record_dict.get("timestamp", ""),
        )
    )
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    # ── AI roles legend ──
    _add_ai_roles_legend(doc, lang)

    doc.add_heading(h["how_it_works_heading"], level=2)
    doc.add_paragraph(h["how_it_works_body"])

    # Summary
    doc.add_heading(h["summary"], level=2)
    regs = ", ".join(record_dict.get("selected_regulations", [])) or h["none"]
    countries = ", ".join(record_dict.get("countries", [])) or h["none"]
    doc.add_paragraph(
        h["summary_body"].format(
            regs=regs,
            countries=countries,
            clauses=record_dict.get("total_clauses", 0),
            agreed=record_dict.get("total_agreed", 0),
            flagged=record_dict.get("total_flagged", 0),
            rounds=record_dict.get("total_rounds", 0),
            model=record_dict.get("llm_model", ""),
            duration=record_dict.get("duration_seconds", 0),
        )
    )

    # Load ISO checklist for expected_evidence lookup
    try:
        from src.analysis.compliance_rules import ISO_13485_CHECKLIST as _ISO_CL
    except Exception:
        _ISO_CL = {}

    # Clause details
    doc.add_heading(h["clause_details"], level=2)
    for clause in record_dict.get("clauses", []):
        cid = clause.get("clause_id", "")
        doc.add_heading(
            f"{cid} — {clause.get('clause_title', '')}",
            level=3,
        )
        doc.add_paragraph(
            f"{h['doc']}: {clause.get('doc_id', '')} {clause.get('doc_title', '')}\n"
            f"{h['verdict']}: {clause.get('verdict', '')}  |  {h['gap']}: {clause.get('gap_severity', '')}\n"
            f"{h['agreed']}: {h['agreed_yes'] if clause.get('agreed') else h['agreed_no']}  |  "
            f"{h['flagged_ra']}: {h['ra_flag_yes'] if clause.get('flagged_for_ra') else h['ra_flag_no']}"
        )

        # Audit question source label (A/B hybrid)
        _cl_def = _ISO_CL.get(cid, {})
        _q_source = clause.get("question_source", "")
        if _q_source == "B":
            doc.add_paragraph(h["source_b_label"], style="Quote")
            _focus = clause.get("focus_area", "")
            if _focus:
                doc.add_paragraph(f"  {h['focus_area_label']}: {_focus}")
            _verifiable = clause.get("verifiable_by", "")
            if _verifiable:
                doc.add_paragraph(f"  {h['verifiable_by_label']}: {_verifiable}")
        elif _q_source == "A":
            doc.add_paragraph(h["source_a_label"], style="Quote")

        # Audit question
        _aq = clause.get("audit_question") or _cl_def.get("audit_question", "")
        if _aq:
            doc.add_paragraph(f"{h['audit_question']}: {_aq}")

        # Expected evidence (static checklist)
        _exp_ev = _cl_def.get("expected_evidence", [])
        if _exp_ev:
            doc.add_paragraph(
                f"{h['expected_evidence']}:\n"
                + "\n".join(f"  • {e}" for e in _exp_ev),
                style="Quote",
            )

        for rd in clause.get("rounds", []):
            doc.add_heading(f"Round {rd.get('round', '?')}", level=4)

            analyzer = rd.get("analyzer", {})
            p = doc.add_paragraph()
            r = p.add_run(f"{h['analyzer_label']}: ")
            r.bold = True
            _render_role_content(p, analyzer)

            verifier = rd.get("verifier", {})
            p = doc.add_paragraph()
            r = p.add_run(f"{h['verifier_label']}: ")
            r.bold = True
            _render_role_content(p, verifier)

            agreement = verifier.get("agreement_level", "")
            doc.add_paragraph(f"Agreement: {agreement}")

        qa = clause.get("qa_audit", {})
        if qa:
            doc.add_heading(h["qa_audit_heading"], level=4)
            doc.add_paragraph(
                f"{h['score_label']}: {qa.get('score', 0)}/100  |  "
                f"{h['question_quality_label']}: {qa.get('question_quality', '')}  |  "
                f"{h['answer_accuracy_label']}: {qa.get('answer_accuracy', '')}\n"
                f"{h['hallucination_label']}: "
                f"{h['hallucination_yes'] if qa.get('hallucination_detected') else h['hallucination_no']}"
            )
            issues = qa.get("issues", [])
            if issues:
                for iss in issues:
                    doc.add_paragraph(f"  • {iss}")

    safe_save_binary(filepath, doc.save)
    return filepath


def export_crossexam_record_excel(record_dict: dict, lang: str = "zh-TW") -> Path:
    """Export a single cross-exam record as an Excel file.

    Args:
        record_dict: CrossExamRecord.to_dict() output
        lang: UI language code (e.g., 'zh-TW', 'en', 'ja')

    Returns:
        Path to the generated .xlsx file
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    # lang reserved for future localization of sheet/section names
    _lk = _lang_key(lang)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"crossexam_{record_dict.get('record_id', 'unknown')}.xlsx"

    wb = Workbook()

    eh = _EXPORT_HEADERS[_lk]
    _duration_label = {"zh": "耗時 (秒)", "en": "Duration (s)", "ja": "所要時間 (秒)"}[_lk]
    _agreed_count_label = {"zh": "同意數", "en": "Agreed count", "ja": "同意数"}[_lk]

    # Sheet 1: Summary
    ws_sum = wb.active
    ws_sum.title = eh["summary"]
    summary_data = [
        (eh["record_id"], record_dict.get("record_id", "")),
        (eh["analysis_id"], record_dict.get("run_id", "")),
        (eh["time"], record_dict.get("timestamp", "")),
        (eh["regulations"], ", ".join(record_dict.get("selected_regulations", []))),
        (eh["countries"], ", ".join(record_dict.get("countries", []))),
        (eh["clause_count"], record_dict.get("total_clauses", 0)),
        (_agreed_count_label, record_dict.get("total_agreed", 0)),
        (eh["flagged_ra"], record_dict.get("total_flagged", 0)),
        (eh["total_rounds"], record_dict.get("total_rounds", 0)),
        (eh["model"], record_dict.get("llm_model", "")),
        (_duration_label, record_dict.get("duration_seconds", 0)),
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

    _sheet2_headers: dict[str, list] = {
        "zh": [
            "條款 ID", "條款名稱", "文件 ID", "判定", "差距", "同意", "RA 標記",
            "問題來源(A/B)", "輪次數", "R1 分析者立場", "R1 分析者信心",
            "R1 實際看到(證據)", "R1 驗證者評估", "R1 Agreement",
            "R1 期望看到(證據)", "QA 分數", "問題品質", "回答準確", "幻覺偵測",
        ],
        "en": [
            "Clause ID", "Clause Name", "Doc ID", "Verdict", "Gap", "Agreed", "RA Flag",
            "Question Source(A/B)", "Rounds", "R1 Analyzer Position", "R1 Analyzer Confidence",
            "R1 Actual Evidence", "R1 Verifier Assessment", "R1 Agreement",
            "R1 Expected Evidence", "QA Score", "Question Quality", "Answer Accuracy", "Hallucination",
        ],
        "ja": [
            "条項ID", "条項名", "文書ID", "判定", "ギャップ", "同意", "RAフラグ",
            "質問ソース(A/B)", "ラウンド数", "R1 分析者立場", "R1 分析者信頼度",
            "R1 実際の証拠", "R1 検証者評価", "R1 Agreement",
            "R1 期待される証拠", "QAスコア", "質問品質", "回答精度", "ハルシネーション",
        ],
    }
    _sheet2_title: dict[str, str] = {
        "zh": "條款詳情", "en": "Clause Details", "ja": "条項詳細"
    }
    ws_detail = wb.create_sheet(_sheet2_title[_lk])
    headers = _sheet2_headers[_lk]
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
    lang: str = "zh-TW",
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
        qa_audit_summary: QA-audit summary (optional)
        lang: UI language code (e.g., 'zh-TW', 'en', 'ja')

    Returns:
        Path to generated .docx
    """
    _lk = _lang_key(lang)
    dh = _EXPORT_HEADERS[_lk]
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"deep_report_{run_id}.docx"

    doc = Document()

    # ── Title ──
    title = doc.add_heading(dh["deep_title"], level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = meta_p.add_run(
        dh["deep_meta"].format(
            run_id=run_id,
            ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    )
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    # ── AI Roles Legend ──
    _add_ai_roles_legend(doc, lang)

    # ── Section 1: Executive Summary ──
    doc.add_heading(dh["deep_s1"], level=2)
    verdict_dist = summary.get("verdict_distribution", {})
    risk_dist = summary.get("risk_distribution", {})
    total = summary.get("total_rows", len(flat_rows))
    flagged = summary.get("flagged_for_ra", 0)

    from src.analysis.risk_matrix import VERDICT_DISPLAY, RISK_LEVEL_DISPLAY
    _label_key = "label_en" if _lk == "en" else "label_ja" if _lk == "ja" else "label_zh"
    summary_text = dh["deep_s1_intro"].format(total=total)
    for v, count in verdict_dist.items():
        _vlabel = VERDICT_DISPLAY.get(v, {}).get(_label_key, v)
        summary_text += f"  • {_vlabel}: {count}\n"
    summary_text += dh["deep_s1_risk"]
    for r, count in risk_dist.items():
        _rlabel = RISK_LEVEL_DISPLAY.get(r, {}).get(_label_key, r)
        summary_text += f"  • {_rlabel}: {count}\n"
    if flagged:
        summary_text += dh["deep_s1_ra"].format(flagged=flagged)

    doc.add_paragraph(summary_text)

    # ── Section 2: GAP Analysis Details ──
    doc.add_heading(dh["deep_s2"], level=2)
    if interactions:
        gap_interactions = [i for i in interactions if i.get("phase") == "gap_scan"]
        if gap_interactions:
            for gi in gap_interactions:
                doc.add_heading(
                    f"{dh['deep_s2_doc']}: {gi.get('doc_id', '')} — {gi.get('doc_title', '')}",
                    level=3,
                )
                extra = gi.get("extra", {})
                ev_sum = extra.get("evidence_summary", {})
                if ev_sum:
                    doc.add_paragraph(
                        f"{dh['deep_s2_found']}: {ev_sum.get('found', 0)}  |  "
                        f"{dh['deep_s2_not_found']}: {ev_sum.get('not_found', 0)}  |  "
                        f"{dh['deep_s2_inadequate']}: {ev_sum.get('inadequate', 0)}"
                    )
                resp = gi.get("llm_response", "")
                if resp:
                    doc.add_heading(dh["deep_llm_response"], level=4)
                    for chunk in _split_text(resp, 3000):
                        doc.add_paragraph(chunk)
                usage = gi.get("usage", {})
                if usage:
                    doc.add_paragraph(
                        dh["deep_token_usage"].format(
                            tokens=usage.get("total_tokens", 0),
                            model=gi.get("model", ""),
                        )
                    )
        else:
            doc.add_paragraph(dh["deep_no_p1"])
    else:
        doc.add_paragraph(dh["deep_no_record"])

    # ── Section 3: Verification Details ──
    doc.add_heading(dh["deep_s3"], level=2)
    if interactions:
        verify_interactions = [
            i for i in interactions if i.get("phase") == "checklist_verify"
        ]
        if verify_interactions:
            for vi in verify_interactions:
                doc.add_heading(
                    f"{dh['deep_s2_doc']}: {vi.get('doc_id', '')} — {vi.get('doc_title', '')}",
                    level=3,
                )
                resp = vi.get("llm_response", "")
                if resp:
                    for chunk in _split_text(resp, 3000):
                        doc.add_paragraph(chunk)
                usage = vi.get("usage", {})
                if usage:
                    doc.add_paragraph(
                        dh["deep_token_usage"].format(
                            tokens=usage.get("total_tokens", 0),
                            model=vi.get("model", ""),
                        )
                    )
        else:
            doc.add_paragraph(dh["deep_no_p2"])
    else:
        doc.add_paragraph(dh["deep_no_record"])

    # ── Section 4: Remediation ──
    doc.add_heading(dh["deep_s4"], level=2)
    if interactions:
        remed_interactions = [
            i for i in interactions if i.get("phase") == "remediation"
        ]
        if remed_interactions:
            for ri in remed_interactions:
                doc.add_heading(
                    f"{dh['deep_s2_doc']}: {ri.get('doc_id', '')} — {ri.get('doc_title', '')}",
                    level=3,
                )
                resp = ri.get("llm_response", "")
                if resp:
                    for chunk in _split_text(resp, 3000):
                        doc.add_paragraph(chunk)
        else:
            doc.add_paragraph(dh["deep_no_p4"])
    else:
        doc.add_paragraph(dh["deep_no_record"])

    # ── Section 5: Cross-Examination ──
    doc.add_heading(dh["deep_s5"], level=2)
    if interactions:
        xexam_interactions = [
            i for i in interactions if i.get("phase") == "verification"
        ]
        if xexam_interactions:
            clause_groups: dict[str, list[dict]] = {}
            for xi in xexam_interactions:
                cid = xi.get("clause_id", "unknown")
                clause_groups.setdefault(cid, []).append(xi)

            for cid, group in clause_groups.items():
                clause_title = group[0].get("clause_title", "")
                doc.add_heading(f"{cid} — {clause_title}", level=3)
                doc_id = group[0].get("doc_id", "")
                if doc_id:
                    doc.add_paragraph(f"{dh['deep_doc_label']}: {doc_id}")

                group.sort(key=lambda x: (x.get("round_number", 0), x.get("role", "")))

                current_round = 0
                for xi in group:
                    rd_num = xi.get("round_number", 0)
                    if rd_num != current_round:
                        current_round = rd_num
                        doc.add_heading(f"Round {rd_num}", level=4)

                    role = xi.get("role", "")
                    role_label = (
                        dh["deep_analyzer_label"]
                        if role == "analyzer"
                        else dh["deep_verifier_label"]
                    )

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
            doc.add_paragraph(dh["deep_no_p5"])
    elif crossexam_record:
        for clause in crossexam_record.get("clauses", []):
            doc.add_heading(
                f"{clause.get('clause_id', '')} — {clause.get('clause_title', '')}",
                level=3,
            )
            for rd in clause.get("rounds", []):
                doc.add_heading(f"Round {rd.get('round', '?')}", level=4)
                p = doc.add_paragraph()
                r = p.add_run(f"{dh['deep_analyzer_label']}: ")
                r.bold = True
                _render_role_content(p, rd.get("analyzer", {}))

                p = doc.add_paragraph()
                r = p.add_run(f"{dh['deep_verifier_label']}: ")
                r.bold = True
                _render_role_content(p, rd.get("verifier", {}))

                agreement = rd.get("verifier", {}).get("agreement_level", "")
                if agreement:
                    doc.add_paragraph(f"Agreement: {agreement}")

            qa = clause.get("qa_audit", {})
            if qa:
                doc.add_heading(dh["qa_audit_heading"], level=4)
                doc.add_paragraph(
                    f"{dh['score_label']}: {qa.get('score', 0)}/100  |  "
                    f"{dh['question_quality_label']}: {qa.get('question_quality', '')}  |  "
                    f"{dh['answer_accuracy_label']}: {qa.get('answer_accuracy', '')}\n"
                    f"{dh['hallucination_label']}: "
                    f"{dh['hallucination_yes'] if qa.get('hallucination_detected') else dh['hallucination_no']}"
                )
                issues = qa.get("issues", [])
                if issues:
                    for iss in issues:
                        doc.add_paragraph(f"  • {iss}")
    else:
        doc.add_paragraph(dh["deep_no_xexam"])

    # ── Section 5.5: Third-Party QA Audit ──
    doc.add_heading(dh["deep_s55"], level=2)
    _qa_sum = qa_audit_summary
    if not _qa_sum and crossexam_record:
        _qa_sum = crossexam_record.get("qa_audit_summary")
    if _qa_sum and not _qa_sum.get("skipped"):
        score = _qa_sum.get("overall_score", 0)
        doc.add_paragraph(
            dh["deep_qa_score"].format(
                score=score,
                count=_qa_sum.get("clause_count", 0),
                model=_qa_sum.get("llm_model", ""),
            )
        )
        qa_summary_text = _qa_sum.get("summary", "")
        if qa_summary_text:
            doc.add_heading(dh["deep_qa_summary"], level=3)
            for chunk in _split_text(qa_summary_text, 3000):
                doc.add_paragraph(chunk)
        qa_recs = _qa_sum.get("recommendations", [])
        if qa_recs:
            doc.add_heading(dh["deep_qa_recs"], level=3)
            for rec in qa_recs:
                doc.add_paragraph(f"• {rec}")
        clause_audits = _qa_sum.get("clause_audits", [])
        if clause_audits:
            doc.add_heading(dh["deep_qa_clause_results"], level=3)
            qa_tbl = doc.add_table(rows=1 + len(clause_audits), cols=6)
            qa_tbl.style = "Table Grid"
            qa_headers = dh["deep_qa_tbl_headers"]
            for i, h in enumerate(qa_headers):
                qa_tbl.rows[0].cells[i].text = h
            for qi, ca in enumerate(clause_audits, 1):
                qa_tbl.rows[qi].cells[0].text = ca.get("clause_id", "")
                qa_tbl.rows[qi].cells[1].text = str(ca.get("score", 0))
                qa_tbl.rows[qi].cells[2].text = ca.get("question_quality", "")
                qa_tbl.rows[qi].cells[3].text = ca.get("answer_accuracy", "")
                qa_tbl.rows[qi].cells[4].text = (
                    dh["hallucination_yes"] if ca.get("hallucination_detected") else dh["hallucination_no"]
                )
                issues = ca.get("issues", [])
                qa_tbl.rows[qi].cells[5].text = "; ".join(issues) if issues else dh["deep_no_issues"]
    elif _qa_sum and _qa_sum.get("skipped"):
        doc.add_paragraph(dh["deep_qa_skipped"].format(summary=_qa_sum.get("summary", "")))
    else:
        doc.add_paragraph(dh["deep_no_qa_record"])

    # ── Section 6: Compliance Table ──
    doc.add_heading(dh["deep_s6"], level=2)
    if flat_rows:
        headers = dh["deep_s6_headers"]
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
        doc.add_heading(dh["deep_s7"], level=2)
        doc.add_paragraph(meta_analysis.get("summary", dh["deep_s7_no_summary"]))

        findings = meta_analysis.get("findings", [])
        if findings:
            doc.add_heading(dh["deep_s7_findings"], level=3)
            for f in findings:
                doc.add_paragraph(
                    f"• [{f.get('severity', '')}] {f.get('description', '')}",
                )

        recommendations = meta_analysis.get("recommendations", [])
        if recommendations:
            doc.add_heading(dh["deep_s7_recs"], level=3)
            for rec in recommendations:
                doc.add_paragraph(f"• {rec}")

        tuning = meta_analysis.get("prompt_tuning", {})
        if tuning:
            doc.add_heading(dh["deep_s7_prompt"], level=3)
            for key, val in tuning.items():
                doc.add_paragraph(f"• {key}: {val}")

    # ── Section 8: LLM Usage Statistics ──
    doc.add_heading(dh["deep_s8"], level=2)
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
                f"• {phase}: {stats['count']} {dh['deep_s8_calls']}, {stats['tokens']:,} tokens"
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
    lang: str = "zh-TW",
) -> Path:
    """Export a deep analysis report as Excel workbook.

    Multiple sheets: Summary, Compliance Table, LLM Interactions, Cross-Exam, Meta-Analysis.

    Args:
        lang: UI language code (e.g., 'zh-TW', 'en', 'ja') — reserved for
            future localization of sheet/section names.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from src.analysis.risk_matrix import VERDICT_DISPLAY, RISK_LEVEL_DISPLAY

    _lk = _lang_key(lang)
    dh = _EXPORT_HEADERS[_lk]
    _label_key = "label_en" if _lk == "en" else "label_ja" if _lk == "ja" else "label_zh"

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"deep_report_{run_id}.xlsx"

    wb = Workbook()
    header_fill = PatternFill(
        start_color="4472C4", end_color="4472C4", fill_type="solid"
    )
    header_font = Font(bold=True, color="FFFFFF", size=10)

    # ── Sheet 1: Summary ──
    ws_sum = wb.active
    ws_sum.title = dh["xl_sheet_summary"]
    summary_data = [
        (dh["xl_run_id"], run_id),
        (dh["xl_export_time"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        (dh["xl_total_rows"], summary.get("total_rows", len(flat_rows))),
        (dh["xl_flagged_ra"], summary.get("flagged_for_ra", 0)),
    ]
    verdict_dist = summary.get("verdict_distribution", {})
    for v, count in verdict_dist.items():
        _vlabel = VERDICT_DISPLAY.get(v, {}).get(_label_key, v)
        summary_data.append((f"{dh['xl_verdict_prefix']}{_vlabel}", count))
    risk_dist = summary.get("risk_distribution", {})
    for r, count in risk_dist.items():
        _rlabel = RISK_LEVEL_DISPLAY.get(r, {}).get(_label_key, r)
        summary_data.append((f"{dh['xl_risk_prefix']}{_rlabel}", count))

    for ri, (label, value) in enumerate(summary_data, 1):
        c1 = ws_sum.cell(row=ri, column=1, value=label)
        c1.fill = header_fill
        c1.font = header_font
        ws_sum.cell(row=ri, column=2, value=str(value))
    ws_sum.column_dimensions["A"].width = 20
    ws_sum.column_dimensions["B"].width = 40

    # ── Sheet 2: Compliance Table ──
    ws_comp = wb.create_sheet(dh["xl_sheet_compliance"])
    comp_headers = dh["xl_comp_headers"]
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
        ws_comp.cell(row=ri, column=14, value=row.get("remediation_suggestion", "") or "")
        ws_comp.cell(row=ri, column=15, value=row.get("remediation_regulation_cite", "") or "")
        ws_comp.cell(row=ri, column=16, value=row.get("analyzer_position", "") or "")
        ws_comp.cell(row=ri, column=17, value=row.get("verifier_position", "") or "")

    # ── Sheet 3: LLM Interactions ──
    if interactions:
        ws_llm = wb.create_sheet(dh["xl_sheet_llm"])
        llm_headers = dh["xl_llm_headers"]
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
        ws_xe = wb.create_sheet(dh["xl_sheet_crossexam"])
        xe_headers = dh["xl_xe_headers"]
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
        _qa_sheet_name = {"zh": "第三方稽核", "en": "Third-Party QA", "ja": "第三者QA"}[_lk]
        ws_qa = wb.create_sheet(_qa_sheet_name)
        qa_xl_headers = dh["deep_qa_tbl_headers"]
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
        _meta_title = {"zh": "交叉詰問品質分析結果", "en": "Cross-Examination Quality Analysis", "ja": "相互尋問品質分析結果"}[_lk]
        ws_ma = wb.create_sheet(dh["xl_sheet_meta"])
        ws_ma.cell(row=1, column=1, value=_meta_title).font = Font(
            bold=True, size=14
        )
        ws_ma.cell(row=3, column=1, value=dh["summary"]).font = Font(bold=True)
        ws_ma.cell(row=4, column=1, value=meta_analysis.get("summary", ""))

        findings = meta_analysis.get("findings", [])
        if findings:
            row_offset = 6
            ws_ma.cell(row=row_offset, column=1, value=dh["deep_s7_findings"]).font = Font(
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
