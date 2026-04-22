"""
AI-QMS — Compliance Rules (Multi-Regulation Cross-Reference)
=============================================================

Multi-regulation compliance baseline for medical device QMS analysis.

Architecture (3 layers):
  Layer 1: ISO 13485:2016 base checklist (71 clauses) — the universal baseline
  Layer 2: Country-specific regulation profiles (predefined + crawlable)
           Each profile contains:
             - iso_mapped: which ISO 13485 clauses this regulation covers
             - unique_requirements: country-specific delta (not in ISO 13485)
  Layer 3: Dynamic cross-examination question generator
           Given a quality document + selected countries →
           generates tailored questions (delta items = highest priority)

Predefined regulations: US FDA QMSR, EU MDR 2017/745, Taiwan TFDA
Dynamic regulations: any country via crawler + LLM analysis
All regulations use the same data format (RegulationProfile).

Downstream usage:
  - Cross-examination engine uses these questions to debate
  - Rule engine uses overlap/delta to determine compliance verdict
  - Risk matrix uses audit_impact to calculate risk level
  - Human watches cross-examination live, intervenes when needed

Currently supported standards:
  - ISO 13485:2016 (Medical devices — Quality management systems)
"""

from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from datetime import datetime

__all__ = [
    # Existing API
    "ISO_13485_CHECKLIST",
    "get_checklist",
    "get_clause",
    "list_clauses",
    "SUPPORTED_STANDARDS",
    # Multi-regulation API
    "MappingStatus",
    "UniqueRequirement",
    "RegulationProfile",
    "PREDEFINED_REGULATIONS",
    "get_regulation",
    "get_all_regulations",
    "get_overlap_analysis",
    "generate_cross_exam_questions",
    "load_crawled_regulation",
    "save_crawled_regulation",
    "map_unique_to_iso_clause",
    "get_profile_id_for_region",
    "get_region_for_profile",
    "get_profile_ids_for_regions",
    "get_regions_without_profile",
    "generate_profile_id_from_region",
    "cleanup_non_selected_crawled_profiles",
    "WithinClauseDelta",
    # Supplemental Standards API
    "StandardCategory",
    "SupplementalStandardProfile",
    "ProductProfile",
    "PREDEFINED_STANDARDS",
    "get_standard",
    "get_all_standards",
    "get_applicable_standards",
    "adjust_standard_clause_mapping",
    "get_audit_question",
]


# ============================================================
# Question rotation helper
# ============================================================

from datetime import date as _date


def get_audit_question(
    clause: dict,
    seed: int | None = None,
    doc_id: str = "",
    lang: str = "zh-TW",
) -> str:
    """Return an audit question from the clause using date-based rotation.

    Language-aware selection:
      - ``lang`` starts with ``"zh"`` (or is empty/unknown) → Chinese pool
        (``audit_questions`` / ``audit_question``)
      - ``lang`` starts with ``"ja"`` → Japanese pool
        (``audit_questions_ja`` / ``audit_question_ja``) with graceful
        fallback to the English pool if no Japanese version is available.
      - Any other language (``"en"``, ``"de"``, ...) → English pool
        (``audit_questions_en`` / ``audit_question_en``) with graceful
        fallback to the Chinese pool if no English version is available
        (e.g., crawled regulation delta questions).

    If the selected-language pool has multiple entries, rotates through them
    deterministically using *seed* (default: today's date as YYYYMMDD int).
    If *doc_id* is provided, its hash is mixed into the seed so that
    different documents on the same day receive different questions.

    Args:
        clause: A single entry from ISO_13485_CHECKLIST or a delta-question dict.
        seed:   Integer seed for rotation. Defaults to today's date (YYYYMMDD).
        doc_id: Optional document ID to mix into seed for per-doc variation.
        lang:   UI language code. Defaults to ``"zh-TW"`` for backwards
                compatibility.

    Returns:
        The selected audit question string.

    Example:
        >>> clause = ISO_13485_CHECKLIST["4.1"]
        >>> q = get_audit_question(clause)                           # Chinese, today
        >>> q = get_audit_question(clause, lang="en")                # English, today
        >>> q = get_audit_question(clause, lang="ja")                # Japanese, today
        >>> q = get_audit_question(clause, seed=0, lang="en")        # always first (EN)
        >>> q = get_audit_question(clause, doc_id="QP-001")          # per-doc variation
    """
    use_chinese = (not lang) or lang.startswith("zh")
    use_japanese = bool(lang) and lang.startswith("ja")

    if use_chinese:
        questions = clause.get("audit_questions") or []
        single = clause.get("audit_question", "")
    elif use_japanese:
        questions = clause.get("audit_questions_ja") or []
        single = clause.get("audit_question_ja", "")
        # Fallback to English, then Chinese if no Japanese version exists
        if not questions and not single:
            questions = clause.get("audit_questions_en") or []
            single = clause.get("audit_question_en", "")
        if not questions and not single:
            questions = clause.get("audit_questions") or []
            single = clause.get("audit_question", "")
    else:
        questions = clause.get("audit_questions_en") or []
        single = clause.get("audit_question_en", "")
        # Fallback to Chinese if no English version exists (e.g., delta dicts)
        if not questions and not single:
            questions = clause.get("audit_questions") or []
            single = clause.get("audit_question", "")

    if len(questions) > 1:
        if seed is None:
            seed = int(_date.today().strftime("%Y%m%d"))
        if doc_id:
            seed = seed + abs(hash(doc_id)) % 1000
        return questions[seed % len(questions)]
    if questions:
        return questions[0]
    return single


# ============================================================
# ISO 13485:2016 — Complete Audit Checklist
# ============================================================

ISO_13485_CHECKLIST: dict[str, dict] = {
    # --------------------------------------------------------
    # Section 4: 品質管理系統
    # --------------------------------------------------------
    "4.1": {
        "title": "品質管理系統 — 一般要求",
        "title_en": "Quality Management System — General Requirements",
        "title_ja": "品質マネジメントシステム — 一般要求事項",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立、文件化、實施及維持品質管理系統，並維持其有效性？"
            "是否鑑別品質管理系統所需的過程及其在整個組織的應用？"
            "是否對外包過程實施管制？"
        ),
        "audit_questions": [
            (
                "組織是否建立、文件化、實施及維持品質管理系統，並維持其有效性？"
                "是否鑑別品質管理系統所需的過程及其在整個組織的應用？"
                "是否對外包過程實施管制？"
            ),
            "品質管理系統的範圍邊界如何定義？是否涵蓋所有影響產品品質的過程？外包過程的風險管控措施為何？",
            "品質管理系統的過程順序與交互作用圖是否定期更新？上次更新是何時、由誰核准？",
            "依 ISO 13485:2016 §4.1(f)，外包過程的管控措施是否文件化？請提供最近一次外包商評鑑記錄。",
            "品質管理系統的有效性如何衡量？是否設有可量測的 KPI，且定期向管理階層報告？",
            "依 ISO 13485:2016 §4.1，品質管理系統是否涵蓋組織內所有影響產品安全性與有效性的過程？哪些過程曾被排除在外？理由為何？",
            "當外包過程的品質績效不符合要求時，組織採取了哪些具體的矯正措施？請提供相關紀錄。",
        ],
        "expected_evidence": [
            "品質手冊",
            "品質管理系統過程圖或過程清單",
            "外包過程管制紀錄（如適用）",
        ],
        "audit_question_en": "Has the organization established, documented, implemented, and maintained a quality management system, and maintained its effectiveness? Are the processes needed for the QMS and their application throughout the organization identified? Are outsourced processes controlled?",
        "audit_question_ja": "組織は品質マネジメントシステムを確立し、文書化し、実施し、維持し、その有効性を維持しているか？品質マネジメントシステムに必要なプロセス及び組織全体への適用を特定しているか？外部委託したプロセスに対して管理を行っているか？",
        "audit_questions_en": [
            "Has the organization established, documented, implemented, and maintained a quality management system, and maintained its effectiveness? Are the processes needed for the QMS and their application throughout the organization identified? Are outsourced processes controlled?",
            "How is the scope boundary of the QMS defined? Does it cover all processes affecting product quality? What are the risk control measures for outsourced processes?",
            "Is the process sequence and interaction diagram of the QMS updated regularly? When was the last update and who approved it?",
            "Per ISO 13485:2016 §4.1(f), are the controls for outsourced processes documented? Please provide the most recent supplier evaluation records.",
            "How is the effectiveness of the QMS measured? Are there quantifiable KPIs that are regularly reported to top management?",
            "Per ISO 13485:2016 §4.1, does the QMS cover all organizational processes affecting product safety and effectiveness? Which processes have been excluded, and why?",
            "When the quality performance of an outsourced process does not meet requirements, what specific corrective actions has the organization taken? Please provide related records.",
        ],
        "audit_questions_ja": [
            "組織は品質マネジメントシステムを確立し、文書化し、実施し、維持し、その有効性を維持しているか？品質マネジメントシステムに必要なプロセス及び組織全体への適用を特定しているか？外部委託したプロセスに対して管理を行っているか？",
            "品質マネジメントシステムの適用範囲の境界はどのように定義されているか？製品品質に影響するすべてのプロセスを網羅しているか？外部委託プロセスのリスク管理策は何か？",
            "品質マネジメントシステムのプロセス順序と相互作用図は定期的に更新されているか？最終更新はいつで、誰が承認したか？",
            "ISO 13485:2016 §4.1(f)に従い、外部委託プロセスの管理策は文書化されているか？直近の外部委託先評価記録を提示すること。",
            "品質マネジメントシステムの有効性はどのように測定されているか？定量的なKPIが設定され、経営層に定期的に報告されているか？",
            "ISO 13485:2016 §4.1に従い、品質マネジメントシステムは組織内で製品の安全性及び有効性に影響するすべてのプロセスを網羅しているか？除外されたプロセスはあるか？その理由は？",
            "外部委託プロセスの品質パフォーマンスが要求事項に適合しない場合、組織はどのような具体的な是正処置を行ったか？関連記録を提示すること。",
        ],
        "expected_evidence_en": [
            "Quality Manual",
            "QMS process map or process list",
            "Outsourced process control records (if applicable)",
        ],
        "expected_evidence_ja": [
            "品質マニュアル",
            "品質マネジメントシステムのプロセスマップ又はプロセス一覧",
            "外部委託プロセス管理記録（該当する場合）",
        ],
    },
    "4.2.1": {
        "title": "文件化要求 — 一般",
        "title_en": "Documentation Requirements — General",
        "title_ja": "文書化の要求事項 — 一般",
        "audit_impact": "major",
        "audit_question": (
            "品質管理系統文件是否包含品質政策與品質目標的聲明、品質手冊、"
            "本國際標準所要求的程序與紀錄、以及組織確定為確保過程有效策劃、"
            "運作及管制所需的文件？"
        ),
        "audit_questions": [
            (
                "品質管理系統文件是否包含品質政策與品質目標的聲明、品質手冊、"
                "本國際標準所要求的程序與紀錄、以及組織確定為確保過程有效策劃、"
                "運作及管制所需的文件？"
            ),
            "品質管理系統文件是否定期審查更新？各層級文件的控制責任是否明確指派給特定人員？",
            "品質管理系統文件的版本管制機制為何？是否能追溯任何文件的修訂歷史？",
            "依 ISO 13485:2016 §4.2.1，程序書清單是否完整？是否有任何法規要求的程序書尚未建立？",
            "品質目標是否以文件化形式呈現？各部門是否有各自的品質目標且與公司層級目標對齊？",
            "組織確定為過程有效運作所需的文件，其識別標準為何？誰有權決定哪些文件需要納入 QMS？",
            "依 ISO 13485:2016 §4.2.1(d)，組織是否建立並維持醫療器材相關的技術文件？最近一次文件完整性審查是何時？",
        ],
        "expected_evidence": [
            "品質政策聲明",
            "品質目標",
            "品質手冊",
            "程序書清單",
        ],
        "audit_question_en": "Does the QMS documentation include statements of a quality policy and quality objectives, a quality manual, the procedures and records required by this International Standard, and the documents determined by the organization to be necessary to ensure effective planning, operation, and control of its processes?",
        "audit_question_ja": "品質マネジメントシステムの文書には、品質方針及び品質目標の表明、品質マニュアル、本国際規格が要求する手順及び記録、並びにプロセスの効果的な計画、運用及び管理を確実にするために組織が必要と判断した文書が含まれているか？",
        "audit_questions_en": [
            "Does the QMS documentation include statements of a quality policy and quality objectives, a quality manual, the procedures and records required by this International Standard, and the documents determined by the organization to be necessary to ensure effective planning, operation, and control of its processes?",
            "Is the QMS documentation periodically reviewed and updated? Is the control responsibility for documents at each level clearly assigned to specific personnel?",
            "What is the version control mechanism for QMS documentation? Can the revision history of any document be traced?",
            "Per ISO 13485:2016 §4.2.1, is the procedure list complete? Are there any regulatory-required procedures that have not yet been established?",
            "Are quality objectives presented in documented form? Do each department have their own quality objectives aligned with company-level objectives?",
            "What are the criteria for identifying documents determined by the organization as necessary for effective process operation? Who has authority to decide which documents should be included in the QMS?",
            "Per ISO 13485:2016 §4.2.1(d), has the organization established and maintained technical documentation related to medical devices? When was the last document completeness review?",
        ],
        "audit_questions_ja": [
            "品質マネジメントシステムの文書には、品質方針及び品質目標の表明、品質マニュアル、本国際規格が要求する手順及び記録、並びにプロセスの効果的な計画、運用及び管理を確実にするために組織が必要と判断した文書が含まれているか？",
            "品質マネジメントシステム文書は定期的にレビューされ更新されているか？各階層の文書管理責任は特定の担当者に明確に割り当てられているか？",
            "品質マネジメントシステム文書のバージョン管理メカニズムは何か？あらゆる文書の改訂履歴を追跡できるか？",
            "ISO 13485:2016 §4.2.1に従い、手順書一覧は完全か？法規制で要求されながらまだ確立されていない手順書はあるか？",
            "品質目標は文書化された形で示されているか？各部門は会社レベルの目標と整合した独自の品質目標を持っているか？",
            "プロセスの効果的な運用に必要と組織が判断する文書の識別基準は何か？どの文書を品質マネジメントシステムに含めるかを決定する権限を持つのは誰か？",
            "ISO 13485:2016 §4.2.1(d)に従い、組織は医療機器に関する技術文書を確立し維持しているか？直近の文書完全性レビューはいつ実施されたか？",
        ],
        "expected_evidence_en": [
            "Quality policy statement",
            "Quality objectives",
            "Quality manual",
            "Procedure list",
        ],
        "expected_evidence_ja": [
            "品質方針表明書",
            "品質目標",
            "品質マニュアル",
            "手順書一覧",
        ],
    },
    "4.2.2": {
        "title": "品質手冊",
        "title_en": "Quality Manual",
        "title_ja": "品質マニュアル",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立並維持品質手冊，包含品質管理系統的範圍（含排除的理由）、"
            "文件化程序或其引用、以及品質管理系統過程之間的交互作用描述？"
        ),
        "audit_questions": [
            (
                "組織是否建立並維持品質手冊，包含品質管理系統的範圍（含排除的理由）、"
                "文件化程序或其引用、以及品質管理系統過程之間的交互作用描述？"
            ),
            "品質手冊是否反映組織實際運作？上次審查日期與版次為何？排除條款的理由是否充分說明？",
            "依 ISO 13485:2016 §4.2.2，品質手冊是否明確說明哪些條款被排除及其理由？排除理由是否有書面依據且可供稽核員核實？",
            "品質手冊所描述的過程交互作用圖是否與組織實際運作一致？是否因組織架構或業務範圍變更而定期更新？",
            "品質手冊的核准流程是否文件化？修訂歷程是否完整保存，且每次修訂均載明變更摘要與核准人？",
            "品質手冊中引用的文件化程序清單是否與現行受控文件清單一致？是否有引用但未建立的程序？",
            "品質手冊的發行管制方式為何？如何確保所有相關人員取得的是最新版本，且作廢版本已被回收或標示？",
        ],
        "expected_evidence": [
            "品質手冊",
            "品質管理系統範圍說明",
            "排除條款理由說明（如適用）",
            "過程交互作用描述",
        ],
        "audit_question_en": "Has the organization established and maintained a quality manual that includes the scope of the QMS (with details of and justification for any exclusion), the documented procedures or references to them, and a description of the interaction between the processes of the QMS?",
        "audit_question_ja": "組織は、品質マネジメントシステムの適用範囲（除外の詳細及び正当化を含む）、文書化された手順又はそれらの参照、並びに品質マネジメントシステムのプロセス間の相互作用の記述を含む品質マニュアルを確立し維持しているか？",
        "audit_questions_en": [
            "Has the organization established and maintained a quality manual that includes the scope of the QMS (with details of and justification for any exclusion), the documented procedures or references to them, and a description of the interaction between the processes of the QMS?",
            "Does the quality manual reflect the organization's actual operations? What are the last review date and revision? Are the justifications for exclusion clauses fully explained?",
            "Per ISO 13485:2016 §4.2.2, does the quality manual clearly state which clauses are excluded and the reasons? Are exclusion justifications documented and verifiable by auditors?",
            "Is the process interaction diagram described in the quality manual consistent with actual operations? Is it updated regularly in response to organizational or business scope changes?",
            "Is the quality manual approval process documented? Is the revision history completely preserved with change summaries and approver names for each revision?",
            "Is the documented procedure list referenced in the quality manual consistent with the current controlled document list? Are there any referenced but unestablished procedures?",
            "What is the release control method for the quality manual? How is it ensured that all relevant personnel have access to the latest version and obsolete versions are recovered or marked?",
        ],
        "audit_questions_ja": [
            "組織は、品質マネジメントシステムの適用範囲（除外の詳細及び正当化を含む）、文書化された手順又はそれらの参照、並びに品質マネジメントシステムのプロセス間の相互作用の記述を含む品質マニュアルを確立し維持しているか？",
            "品質マニュアルは組織の実際の運用を反映しているか？最終レビュー日及び改訂は？除外条項の正当化は十分に説明されているか？",
            "ISO 13485:2016 §4.2.2に従い、品質マニュアルはどの条項が除外されるか及びその理由を明確に述べているか？除外の正当化は文書化され、監査員による検証が可能か？",
            "品質マニュアルに記述されたプロセス相互作用図は実際の運用と一致しているか？組織又は事業範囲の変更に応じて定期的に更新されているか？",
            "品質マニュアルの承認プロセスは文書化されているか？改訂履歴は各改訂の変更要約及び承認者名とともに完全に保存されているか？",
            "品質マニュアルで参照されている文書化手順一覧は、現行の管理文書一覧と一致しているか？参照されているが未確立の手順はあるか？",
            "品質マニュアルの発行管理方法は何か？すべての関連要員が最新版にアクセスでき、廃止版が回収又は表示されることをどのように確実にしているか？",
        ],
        "expected_evidence_en": [
            "Quality Manual",
            "QMS scope statement",
            "Exclusion clause justification (if applicable)",
            "Process interaction description",
        ],
        "expected_evidence_ja": [
            "品質マニュアル",
            "品質マネジメントシステムの適用範囲説明書",
            "除外条項の正当化説明書（該当する場合）",
            "プロセス相互作用の記述",
        ],
    },
    "4.2.3": {
        "title": "文件管制",
        "title_en": "Document Control",
        "title_ja": "文書管理",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立文件管制程序，涵蓋審查、核准、發行、變更、"
            "版本識別、外來文件管制及作廢文件管制？"
        ),
        "audit_questions": [
            (
                "組織是否建立文件管制程序，涵蓋審查、核准、發行、變更、"
                "版本識別、外來文件管制及作廢文件管制？"
            ),
            "文件變更管制程序是否有效防止使用作廢版本？請舉例說明最近一次文件變更的完整管制流程。",
            "依 ISO 13485:2016 §4.2.4，作廢文件如何管制？是否有機制確保作廢文件不被誤用？",
            "外來文件（如法規、客戶規範）如何識別、受控並分發？請舉一個外來文件管制的實例。",
            "文件核准流程需要幾個層級的簽核？跨部門文件的核准責任如何界定？",
            "依 ISO 13485:2016 §4.2.3(g)，當文件發行至現場使用時，如何確保使用者取得的是最新版本？",
            "電子文件管理系統（如有）是否經過驗證？其存取權限控制機制為何？",
        ],
        "expected_evidence": [
            "文件管制程序書",
            "文件發行/變更紀錄",
            "文件清單 (Master List)",
        ],
        "audit_question_en": "Has the organization established document control procedures covering review, approval, issue, change, version identification, control of external documents, and control of obsolete documents?",
        "audit_question_ja": "組織は、レビュー、承認、発行、変更、版の識別、外部文書の管理、廃止文書の管理を含む文書管理手順を確立しているか？",
        "audit_questions_en": [
            "Has the organization established document control procedures covering review, approval, issue, change, version identification, control of external documents, and control of obsolete documents?",
            "Does the document change control procedure effectively prevent the use of obsolete versions? Please illustrate the complete control process of a recent document change.",
            "Per ISO 13485:2016 §4.2.4, how are obsolete documents controlled? Is there a mechanism to ensure obsolete documents are not inadvertently used?",
            "How are external documents (e.g., regulations, customer specifications) identified, controlled, and distributed? Please provide an example of external document control.",
            "How many levels of approval are required in the document approval process? How is approval responsibility defined for cross-departmental documents?",
            "Per ISO 13485:2016 §4.2.3(g), when documents are issued for on-site use, how is it ensured that users obtain the latest version?",
            "Is the electronic document management system (if any) validated? What is its access permission control mechanism?",
        ],
        "audit_questions_ja": [
            "組織は、レビュー、承認、発行、変更、版の識別、外部文書の管理、廃止文書の管理を含む文書管理手順を確立しているか？",
            "文書変更管理手順は廃止版の使用を効果的に防止しているか？直近の文書変更の完全な管理プロセスを例示すること。",
            "ISO 13485:2016 §4.2.4に従い、廃止文書はどのように管理されているか？廃止文書が誤用されないことを確実にする仕組みはあるか？",
            "外部文書（法規制、顧客仕様等）はどのように識別、管理、配布されているか？外部文書管理の実例を提示すること。",
            "文書承認プロセスには何段階の決裁が必要か？部門横断文書の承認責任はどのように規定されているか？",
            "ISO 13485:2016 §4.2.3(g)に従い、文書が現場使用のために発行される際、利用者が最新版を入手することをどのように確実にしているか？",
            "電子文書管理システム（存在する場合）はバリデーションされているか？そのアクセス権限管理メカニズムは何か？",
        ],
        "expected_evidence_en": [
            "Document Control Procedure",
            "Document issue/change records",
            "Master Document List",
        ],
        "expected_evidence_ja": [
            "文書管理手順書",
            "文書発行／変更記録",
            "文書一覧（マスターリスト）",
        ],
    },
    "4.2.4": {
        "title": "紀錄管制",
        "title_en": "Record Control",
        "title_ja": "記録の管理",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立紀錄管制程序，確保紀錄的識別、儲存、保護、"
            "檢索、保存期限及處置？"
        ),
        "audit_questions": [
            (
                "組織是否建立紀錄管制程序，確保紀錄的識別、儲存、保護、"
                "檢索、保存期限及處置？"
            ),
            "紀錄保存期限的依據為何？是否符合各適用法規（MDSAP/TFDA/EU MDR）的最低要求？電子紀錄是否有備份機制？",
            "紀錄的保存期限如何決定？是否考量產品的預期壽命加上法規規定的最低保存期限？",
            "依 ISO 13485:2016 §4.2.5，紀錄是否清晰、易讀且可識別？是否有因存放不當而損毀的案例？",
            "電子紀錄（如掃描文件、電子簽名）是否符合法規要求（如 21 CFR Part 11，如適用）？",
            "當紀錄需要移轉（如系統更換）時，移轉的完整性如何驗證？是否有移轉驗證程序？",
            "依 ISO 13485:2016 §4.2.5，所有法規要求的紀錄類型是否都已建立並受控？是否有紀錄清單？",
        ],
        "expected_evidence": [
            "紀錄管制程序書",
            "紀錄保存期限清單",
        ],
        "audit_question_en": "Has the organization established record control procedures to ensure the identification, storage, protection, retrieval, retention time, and disposition of records?",
        "audit_question_ja": "組織は、記録の識別、保管、保護、検索、保管期間及び処分を確実にする記録管理手順を確立しているか？",
        "audit_questions_en": [
            "Has the organization established record control procedures to ensure the identification, storage, protection, retrieval, retention time, and disposition of records?",
            "What is the basis for record retention periods? Do they meet the minimum requirements of each applicable regulation (MDSAP/TFDA/EU MDR)? Are electronic records backed up?",
            "How are record retention periods determined? Are the expected product lifetime plus regulatory minimum retention periods considered?",
            "Per ISO 13485:2016 §4.2.5, are records clear, legible, and identifiable? Are there any cases of damage due to improper storage?",
            "Do electronic records (e.g., scanned documents, electronic signatures) comply with regulatory requirements (such as 21 CFR Part 11, if applicable)?",
            "When records need to be transferred (e.g., system replacement), how is transfer integrity verified? Is there a transfer verification procedure?",
            "Per ISO 13485:2016 §4.2.5, have all regulatory-required record types been established and controlled? Is there a record list?",
        ],
        "audit_questions_ja": [
            "組織は、記録の識別、保管、保護、検索、保管期間及び処分を確実にする記録管理手順を確立しているか？",
            "記録保管期間の根拠は何か？各適用法規制（MDSAP／TFDA／EU MDR）の最低要求事項を満たしているか？電子記録のバックアップ機構はあるか？",
            "記録の保管期間はどのように決定されているか？製品の予想耐用年数に法規制で定められた最低保管期間を加算したものを考慮しているか？",
            "ISO 13485:2016 §4.2.5に従い、記録は明確かつ判読可能で識別可能か？不適切な保管による破損事例はあるか？",
            "電子記録（スキャン文書、電子署名等）は法規制要求事項（21 CFR Part 11等、該当する場合）に適合しているか？",
            "記録の移行（システム更新等）が必要な場合、移行の完全性はどのように検証されるか？移行バリデーション手順はあるか？",
            "ISO 13485:2016 §4.2.5に従い、すべての法規制要求記録種別は確立され管理されているか？記録一覧は存在するか？",
        ],
        "expected_evidence_en": [
            "Record Control Procedure",
            "Record retention period list",
        ],
        "expected_evidence_ja": [
            "記録管理手順書",
            "記録保管期間一覧",
        ],
    },
    "4.2.5": {
        "title": "醫療器材檔案",
        "title_en": "Medical Device File",
        "title_ja": "医療機器ファイル",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否為每一醫療器材類型或醫療器材族建立並維持醫療器材檔案，"
            "包含或引用產生的文件以展示符合本標準要求及適用法規要求？"
        ),
        "audit_questions": [
            (
                "組織是否為每一醫療器材類型或醫療器材族建立並維持醫療器材檔案，"
                "包含或引用產生的文件以展示符合本標準要求及適用法規要求？"
            ),
            "醫療器材檔案的完整性如何定期確認？若發現文件缺失，其偵測與補救機制為何？",
            "依 ISO 13485:2016 §4.2.5，醫療器材檔案是否涵蓋每一器材類型或族，且包含或引用所有必要文件以展示法規符合性？",
            "醫療器材檔案的索引目錄是否維持最新狀態？是否有定期完整性審查（如年度）的紀錄？",
            "當產品發生設計變更時，醫療器材檔案的更新責任人與更新時限如何界定？是否有相關追蹤機制？",
            "醫療器材檔案中的技術文件是否足以使主管機關進行符合性評估？曾被外部查廠機構指出的文件缺失為何？",
            "電子化醫療器材檔案的存取控制與版本管理機制為何？離職人員的存取權限如何及時撤銷？",
        ],
        "expected_evidence": [
            "醫療器材檔案 (Device Master Record / Technical File)",
            "產品規格書",
            "適用法規要求清單",
        ],
        "audit_question_en": "Has the organization established and maintained a medical device file for each type or family of medical device, containing or referencing documents generated to demonstrate conformity to the requirements of this standard and compliance with applicable regulatory requirements?",
        "audit_question_ja": "組織は、医療機器の種類又はファミリごとに、本規格の要求事項への適合及び適用される規制要求事項への適合を実証するために作成された文書を含む又は参照する医療機器ファイルを確立し維持しているか？",
        "audit_questions_en": [
            "Has the organization established and maintained a medical device file for each type or family of medical device, containing or referencing documents generated to demonstrate conformity to the requirements of this standard and compliance with applicable regulatory requirements?",
            "How is the completeness of the medical device file periodically confirmed? What are the detection and remediation mechanisms if document gaps are found?",
            "Per ISO 13485:2016 §4.2.5, does the medical device file cover each device type or family, and include or reference all necessary documents to demonstrate regulatory compliance?",
            "Is the index table of the medical device file kept up to date? Are there records of periodic completeness reviews (e.g., annual)?",
            "When a product design change occurs, how are the person responsible for updating the medical device file and the update deadline defined? Is there a related tracking mechanism?",
            "Are the technical documents in the medical device file sufficient for regulatory authorities to conduct conformity assessment? What document gaps have been identified by external audit agencies?",
            "What is the access control and version management mechanism for electronic medical device files? How is access permission of departed personnel revoked promptly?",
        ],
        "audit_questions_ja": [
            "組織は、医療機器の種類又はファミリごとに、本規格の要求事項への適合及び適用される規制要求事項への適合を実証するために作成された文書を含む又は参照する医療機器ファイルを確立し維持しているか？",
            "医療機器ファイルの完全性はどのように定期的に確認されているか？文書の欠落が発見された場合の検出及び是正機構は何か？",
            "ISO 13485:2016 §4.2.5に従い、医療機器ファイルは各機器種別又はファミリを網羅し、規制適合性を実証するために必要なすべての文書を含む又は参照しているか？",
            "医療機器ファイルの索引目録は最新状態に維持されているか？定期的な完全性レビュー（年次等）の記録はあるか？",
            "製品の設計変更が発生した場合、医療機器ファイルの更新責任者及び更新期限はどのように規定されているか？関連する追跡機構はあるか？",
            "医療機器ファイル内の技術文書は、規制当局による適合性評価の実施に十分か？外部監査機関から指摘された文書不備はあるか？",
            "電子化医療機器ファイルのアクセス制御及びバージョン管理機構は何か？離任者のアクセス権限は速やかに取り消されているか？",
        ],
        "expected_evidence_en": [
            "Medical Device File (Device Master Record / Technical File)",
            "Product specification",
            "Applicable regulatory requirements list",
        ],
        "expected_evidence_ja": [
            "医療機器ファイル（Device Master Record／技術文書）",
            "製品仕様書",
            "適用法規制要求事項一覧",
        ],
    },
    # --------------------------------------------------------
    # Section 5: 管理責任
    # --------------------------------------------------------
    "5.1": {
        "title": "管理階層承諾",
        "title_en": "Management Commitment",
        "title_ja": "経営者のコミットメント",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否提供其對品質管理系統之開發與實施、"
            "以及維持其有效性之承諾的證據？"
        ),
        "audit_questions": [
            (
                "最高管理階層是否提供其對品質管理系統之開發與實施、"
                "以及維持其有效性之承諾的證據？"
            ),
            "最高管理階層對品質管理系統的承諾如何量化展示？品質目標達成率是否定期向管理階層報告？",
            "依 ISO 13485:2016 §5.1，最高管理階層是否透過建立品質政策、設定品質目標、進行管理審查等具體行動展示其對 QMS 的承諾？請提供最近一次管理審查的出席紀錄。",
            "最高管理階層是否確保組織的各層級了解滿足顧客及法規要求的重要性？溝通方式與頻率為何？",
            "品質政策是否由最高管理階層親自制定並公開承諾？品質政策的審查頻率與上次審查結論為何？",
            "當品質管理系統的資源需求與商業目標衝突時，最高管理階層如何做出決策？請提供一個具體案例。",
            "最高管理階層是否定期審視品質目標達成情況並採取行動？最近一次目標未達成的應對措施為何？",
        ],
        "expected_evidence": [
            "品質政策聲明",
            "管理審查會議紀錄",
            "資源配置紀錄",
        ],
        "audit_question_en": "Does top management provide evidence of its commitment to the development and implementation of the quality management system and maintenance of its effectiveness?",
        "audit_question_ja": "トップマネジメントは、品質マネジメントシステムの開発及び実施並びにその有効性の維持に対するコミットメントの証拠を提供しているか？",
        "audit_questions_en": [
            "Does top management provide evidence of its commitment to the development and implementation of the quality management system and maintenance of its effectiveness?",
            "How is top management's commitment to the QMS quantifiably demonstrated? Is the achievement rate of quality objectives regularly reported to top management?",
            "Per ISO 13485:2016 §5.1, does top management demonstrate its commitment to the QMS through concrete actions such as establishing the quality policy, setting quality objectives, and conducting management reviews? Please provide the attendance record of the most recent management review.",
            "Does top management ensure that the importance of meeting customer and regulatory requirements is understood at all levels of the organization? What is the communication method and frequency?",
            "Is the quality policy personally established and publicly committed by top management? What is the review frequency of the quality policy and the conclusion of the last review?",
            "When QMS resource requirements conflict with business objectives, how does top management make decisions? Please provide a specific case.",
            "Does top management periodically review quality objective achievement and take action? What are the countermeasures for the most recent objective non-achievement?",
        ],
        "audit_questions_ja": [
            "トップマネジメントは、品質マネジメントシステムの開発及び実施並びにその有効性の維持に対するコミットメントの証拠を提供しているか？",
            "トップマネジメントの品質マネジメントシステムへのコミットメントはどのように定量的に示されているか？品質目標の達成率はトップマネジメントに定期報告されているか？",
            "ISO 13485:2016 §5.1に従い、トップマネジメントは品質方針の確立、品質目標の設定、マネジメントレビューの実施等の具体的行動を通じて品質マネジメントシステムへのコミットメントを示しているか？直近のマネジメントレビューの出席記録を提示すること。",
            "トップマネジメントは、顧客要求事項及び法規制要求事項を満たすことの重要性が組織の各階層で理解されることを確実にしているか？コミュニケーション方法及び頻度は？",
            "品質方針はトップマネジメントにより自ら策定され、公に表明されているか？品質方針のレビュー頻度及び直近のレビュー結論は？",
            "品質マネジメントシステムの資源ニーズが事業目標と相反する場合、トップマネジメントはどのように意思決定するか？具体事例を提示すること。",
            "トップマネジメントは定期的に品質目標の達成状況をレビューし処置を取っているか？直近の目標未達時の対応策は何か？",
        ],
        "expected_evidence_en": [
            "Quality policy statement",
            "Management review meeting minutes",
            "Resource allocation records",
        ],
        "expected_evidence_ja": [
            "品質方針表明書",
            "マネジメントレビュー議事録",
            "資源配分記録",
        ],
    },
    "5.2": {
        "title": "以顧客為重",
        "title_en": "Customer Focus",
        "title_ja": "顧客重視",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保顧客要求與適用法規要求已被確定並予以滿足？"
        ),
        "audit_questions": [
            "最高管理階層是否確保顧客要求與適用法規要求已被確定並予以滿足？",
            "顧客要求如何被系統性地識別並轉化為內部品質要求？是否有追溯機制確保每項顧客要求都被落實？",
            "依 ISO 13485:2016 §5.2，最高管理階層如何確保顧客要求與適用法規要求被系統性地識別並持續滿足？",
            "顧客滿意度的量測指標為何？量測結果如何用於改善品質管理系統或產品？",
            "當顧客要求與法規要求存在差異時，組織的優先處理原則為何？是否有相關決策紀錄？",
            "顧客對產品效能或安全性的回饋如何被納入持續改善過程？最近一個具體改善案例為何？",
            "法規要求的變更（如新法規發布）如何被及時識別並確保顧客要求的更新？責任人為誰？",
        ],
        "expected_evidence": [
            "顧客要求確認紀錄",
            "顧客滿意度調查（如適用）",
            "適用法規要求清單",
        ],
        "audit_question_en": "Does top management ensure that customer requirements and applicable regulatory requirements are determined and met?",
        "audit_question_ja": "トップマネジメントは、顧客要求事項及び適用される規制要求事項が決定され満たされることを確実にしているか？",
        "audit_questions_en": [
            "Does top management ensure that customer requirements and applicable regulatory requirements are determined and met?",
            "How are customer requirements systematically identified and translated into internal quality requirements? Is there a traceability mechanism to ensure each customer requirement is implemented?",
            "Per ISO 13485:2016 §5.2, how does top management ensure that customer requirements and applicable regulatory requirements are systematically identified and continually met?",
            "What are the measurement indicators for customer satisfaction? How are measurement results used to improve the QMS or products?",
            "When customer requirements and regulatory requirements differ, what is the organization's priority principle? Are there related decision records?",
            "How are customer feedback on product performance or safety incorporated into continual improvement processes? What is the most recent specific improvement case?",
            "How are changes in regulatory requirements (e.g., new regulation release) identified in a timely manner and customer requirement updates ensured? Who is the responsible person?",
        ],
        "audit_questions_ja": [
            "トップマネジメントは、顧客要求事項及び適用される規制要求事項が決定され満たされることを確実にしているか？",
            "顧客要求事項はどのように体系的に識別され、社内品質要求事項に展開されているか？各顧客要求事項が確実に反映される追跡機構はあるか？",
            "ISO 13485:2016 §5.2に従い、トップマネジメントはどのように顧客要求事項及び適用法規制要求事項が体系的に識別され継続的に満たされることを確実にしているか？",
            "顧客満足度の測定指標は何か？測定結果は品質マネジメントシステム又は製品の改善にどのように活用されているか？",
            "顧客要求事項と法規制要求事項の間に相違がある場合、組織の優先処理原則は何か？関連する意思決定記録はあるか？",
            "製品性能又は安全性に関する顧客フィードバックは、継続的改善プロセスにどのように組み込まれているか？直近の具体的改善事例は？",
            "法規制要求事項の変更（新規法規制の公布等）はどのように適時に識別され、顧客要求事項の更新が確実に行われるか？責任者は誰か？",
        ],
        "expected_evidence_en": [
            "Customer requirements confirmation records",
            "Customer satisfaction survey (if applicable)",
            "Applicable regulatory requirements list",
        ],
        "expected_evidence_ja": [
            "顧客要求事項確認記録",
            "顧客満足度調査（該当する場合）",
            "適用法規制要求事項一覧",
        ],
    },
    "5.3": {
        "title": "品質政策",
        "title_en": "Quality Policy",
        "title_ja": "品質方針",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保品質政策適合組織的目的、包含對滿足要求及維持"
            "品質管理系統有效性的承諾、提供建立及審查品質目標的架構、"
            "在組織內被溝通與理解、並被審查以持續適切？"
        ),
        "audit_questions": [
            (
                "最高管理階層是否確保品質政策適合組織的目的、包含對滿足要求及維持"
                "品質管理系統有效性的承諾、提供建立及審查品質目標的架構、"
                "在組織內被溝通與理解、並被審查以持續適切？"
            ),
            "品質政策是否被所有相關人員理解？如何驗證員工對品質政策的理解程度？上次政策審查的時間與結論為何？",
            "依 ISO 13485:2016 §5.3，品質政策是否包含對滿足要求及維持 QMS 有效性的承諾，並提供建立品質目標的架構？",
            "品質政策如何在組織內進行溝通？是否包含新進員工培訓中的品質政策教育？",
            "品質政策是否定期被審查以確保其持續適切性？審查的觸發條件（如業務方向變更）是否文件化？",
            "品質政策與組織的業務策略如何連結？是否有機制確保品質政策與業務目標保持一致？",
            "品質政策的傳達方式（如張貼、電子郵件、培訓）是否能確保所有層級的員工均能取得並理解？",
        ],
        "expected_evidence": [
            "品質政策文件",
            "品質政策溝通紀錄",
        ],
        "audit_question_en": "Does top management ensure that the quality policy is appropriate to the purpose of the organization, includes a commitment to comply with requirements and to maintain the effectiveness of the QMS, provides a framework for establishing and reviewing quality objectives, is communicated and understood within the organization, and is reviewed for continuing suitability?",
        "audit_question_ja": "トップマネジメントは、品質方針が組織の目的に対して適切であること、要求事項への適合及び品質マネジメントシステムの有効性の維持に対するコミットメントを含むこと、品質目標の設定及びレビューのための枠組みを提供すること、組織内で伝達され理解されること、継続的な適切性のためにレビューされることを確実にしているか？",
        "audit_questions_en": [
            "Does top management ensure that the quality policy is appropriate to the purpose of the organization, includes a commitment to comply with requirements and to maintain the effectiveness of the QMS, provides a framework for establishing and reviewing quality objectives, is communicated and understood within the organization, and is reviewed for continuing suitability?",
            "Is the quality policy understood by all relevant personnel? How is employees' understanding of the quality policy verified? What are the time and conclusion of the last policy review?",
            "Per ISO 13485:2016 §5.3, does the quality policy include a commitment to comply with requirements and maintain QMS effectiveness, and provide a framework for establishing quality objectives?",
            "How is the quality policy communicated within the organization? Does it include quality policy education for new employee training?",
            "Is the quality policy periodically reviewed to ensure its continuing suitability? Are the review triggering conditions (e.g., business direction change) documented?",
            "How is the quality policy connected to the organization's business strategy? Is there a mechanism to ensure that the quality policy and business objectives remain aligned?",
            "Does the quality policy dissemination method (e.g., posting, email, training) ensure that employees at all levels can obtain and understand it?",
        ],
        "audit_questions_ja": [
            "トップマネジメントは、品質方針が組織の目的に対して適切であること、要求事項への適合及び品質マネジメントシステムの有効性の維持に対するコミットメントを含むこと、品質目標の設定及びレビューのための枠組みを提供すること、組織内で伝達され理解されること、継続的な適切性のためにレビューされることを確実にしているか？",
            "品質方針はすべての関連要員により理解されているか？従業員の品質方針理解度はどのように検証されているか？直近の方針レビューの時期及び結論は？",
            "ISO 13485:2016 §5.3に従い、品質方針は要求事項への適合及び品質マネジメントシステムの有効性の維持に対するコミットメントを含み、品質目標設定の枠組みを提供しているか？",
            "品質方針は組織内でどのように伝達されているか？新入社員研修に品質方針の教育が含まれているか？",
            "品質方針は継続的な適切性を確実にするために定期的にレビューされているか？レビューのトリガー条件（事業方向の変更等）は文書化されているか？",
            "品質方針は組織の事業戦略とどのように結び付いているか？品質方針と事業目標の整合性を保持する機構はあるか？",
            "品質方針の伝達方法（掲示、電子メール、研修等）は、すべての階層の従業員が入手し理解できることを確実にしているか？",
        ],
        "expected_evidence_en": [
            "Quality policy statement",
            "Quality policy review records",
        ],
        "expected_evidence_ja": [
            "品質方針表明書",
            "品質方針レビュー記録",
        ],
    },
    "5.4.1": {
        "title": "品質目標",
        "title_en": "Quality Objectives",
        "title_ja": "品質目標",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保在組織內相關職能與層級建立品質目標？"
            "品質目標是否可量測且與品質政策一致？"
        ),
        "audit_questions": [
            (
                "最高管理階層是否確保在組織內相關職能與層級建立品質目標？"
                "品質目標是否可量測且與品質政策一致？"
            ),
            "品質目標是否為 SMART 目標（具體、可量測、可達成、相關、有時限）？目標未達成時有何應對措施與改善計畫？",
            "依 ISO 13485:2016 §5.4.1，品質目標是否在組織內相關職能與層級建立，且每個目標均可量測並與品質政策一致？",
            "各部門/層級的品質目標如何與公司整體品質目標對齊？目標分解（Cascade）的方法為何？",
            "品質目標的追蹤頻率為何？誰負責定期審視並報告目標達成情況？審視紀錄是否保存？",
            "若品質目標連續未達成，升級機制與根本原因分析流程為何？是否曾因此修訂目標或過程？",
            "品質目標是否定期（如年度）重新評估其適切性？目標設定的依據（如歷史績效、行業基準）為何？",
        ],
        "expected_evidence": [
            "品質目標清單",
            "品質目標達成率追蹤紀錄",
        ],
        "audit_question_en": "Does top management ensure that quality objectives, including those needed to meet applicable regulatory requirements and requirements for product, are established at relevant functions and levels within the organization, and that the quality objectives are measurable and consistent with the quality policy?",
        "audit_question_ja": "トップマネジメントは、適用される規制要求事項及び製品に対する要求事項を満たすために必要なものを含む品質目標を、組織内の関連する機能及び階層で確立し、品質目標が測定可能で品質方針と整合していることを確実にしているか？",
        "audit_questions_en": [
            "Does top management ensure that quality objectives, including those needed to meet applicable regulatory requirements and requirements for product, are established at relevant functions and levels within the organization, and that the quality objectives are measurable and consistent with the quality policy?",
            "How is the quantifiability of quality objectives designed? Are measurement methods and target values defined at the time of objective establishment?",
            "Per ISO 13485:2016 §5.4.1, are quality objectives established at each function and level, and are they measurable and consistent with the quality policy?",
            "When quality objectives are not achieved, what is the escalation mechanism? Which management level is responsible for approving countermeasures?",
            "Are quality objectives cascaded to individual employee performance indicators? Are employee performance evaluations linked to quality objective achievement?",
            "Are quality objectives related to product requirements aligned with the requirements of applicable regulations (such as EU MDR, FDA QMSR)?",
            "Is the quality objective review cycle consistent with management reviews? What is the triggering mechanism for objective adjustment when circumstances change?",
        ],
        "audit_questions_ja": [
            "トップマネジメントは、適用される規制要求事項及び製品に対する要求事項を満たすために必要なものを含む品質目標を、組織内の関連する機能及び階層で確立し、品質目標が測定可能で品質方針と整合していることを確実にしているか？",
            "品質目標の定量化可能性はどのように設計されているか？目標設定時に測定方法及び目標値が定義されているか？",
            "ISO 13485:2016 §5.4.1に従い、品質目標は各機能及び階層で設定され、測定可能で品質方針と整合しているか？",
            "品質目標未達時のエスカレーション機構は何か？対策承認の責任はどの管理階層にあるか？",
            "品質目標は個人の業績指標にまで展開されているか？従業員の業績評価は品質目標の達成と連動しているか？",
            "製品要求事項に関する品質目標は、適用法規制（EU MDR、FDA QMSR等）の要求事項と整合しているか？",
            "品質目標のレビュー周期はマネジメントレビューと整合しているか？状況変化時の目標調整のトリガー機構は何か？",
        ],
        "expected_evidence_en": [
            "Quality objectives statement",
            "Quality objective achievement tracking records",
        ],
        "expected_evidence_ja": [
            "品質目標書",
            "品質目標達成状況追跡記録",
        ],
    },
    "5.4.2": {
        "title": "品質管理系統規劃",
        "title_en": "Quality Management System Planning",
        "title_ja": "品質マネジメントシステムの計画",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保品質管理系統的規劃已執行以滿足一般要求及品質目標？"
            "當規劃和實施品質管理系統的變更時，是否維持其完整性？"
        ),
        "audit_questions": [
            (
                "最高管理階層是否確保品質管理系統的規劃已執行以滿足一般要求及品質目標？"
                "當規劃和實施品質管理系統的變更時，是否維持其完整性？"
            ),
            "品質管理系統規劃的輸出文件包含哪些要素？當品質管理系統發生重大變更時，如何確保所有相關過程的完整性不受影響？",
            "依 ISO 13485:2016 §5.4.2，品質管理系統規劃是否確保在實施變更期間維持 QMS 的完整性？",
            "QMS 規劃如何與組織的年度經營計劃整合？資源規劃是否作為 QMS 規劃的一部分？",
            "當組織擴張或縮減業務範圍時，QMS 規劃的調整程序為何？調整的核准層級是誰？",
            "QMS 規劃的輸出如何被追蹤執行？規劃活動的進度如何在管理審查中報告？",
            "組織是否有長期（如 3 年）QMS 路線圖？短期規劃如何與長期目標保持一致？",
        ],
        "expected_evidence": [
            "品質管理系統規劃文件",
            "變更管理紀錄",
        ],
        "audit_question_en": "Does top management ensure that the planning of the QMS is carried out in order to meet the requirements of 4.1 as well as the quality objectives, and the integrity of the QMS is maintained when changes to the QMS are planned and implemented?",
        "audit_question_ja": "トップマネジメントは、4.1の要求事項及び品質目標を満たすために品質マネジメントシステムの計画が実施され、品質マネジメントシステムへの変更が計画され実施される際に品質マネジメントシステムの完全性が維持されることを確実にしているか？",
        "audit_questions_en": [
            "Does top management ensure that the planning of the QMS is carried out in order to meet the requirements of 4.1 as well as the quality objectives, and the integrity of the QMS is maintained when changes to the QMS are planned and implemented?",
            "How is QMS change planning controlled to ensure system integrity? What are the impact assessment procedures for major changes (e.g., organizational restructuring, ERP system replacement)?",
            "Per ISO 13485:2016 §5.4.2, does the organization have a planning mechanism to ensure the continued integrity of the QMS when changes are planned and implemented?",
            "Is the QMS planning formally documented (e.g., QMS roadmap)? Does it cover short-term, medium-term, and long-term objectives?",
            "When the QMS change impacts multiple departments or processes, how is the coordination mechanism designed? Is there a cross-functional change management team?",
            "Is the risk assessment for QMS change management linked to product risk management? When a QMS change may affect product safety, what is the escalation path?",
            "Is the change validation mechanism defined? Are post-change QMS effectiveness measurement indicators and verification timelines defined in the change plan?",
        ],
        "audit_questions_ja": [
            "トップマネジメントは、4.1の要求事項及び品質目標を満たすために品質マネジメントシステムの計画が実施され、品質マネジメントシステムへの変更が計画され実施される際に品質マネジメントシステムの完全性が維持されることを確実にしているか？",
            "品質マネジメントシステムの変更計画はシステムの完全性を確実にするためどのように管理されているか？大規模変更（組織再編、ERPシステム更新等）の影響評価手順は？",
            "ISO 13485:2016 §5.4.2に従い、変更が計画され実施される際に品質マネジメントシステムの継続的完全性を確実にする計画機構はあるか？",
            "品質マネジメントシステムの計画は正式に文書化されているか（品質マネジメントシステムロードマップ等）？短期・中期・長期の目標を網羅しているか？",
            "品質マネジメントシステムの変更が複数の部門又はプロセスに影響する場合、調整機構はどのように設計されているか？部門横断変更管理チームはあるか？",
            "品質マネジメントシステム変更管理のリスク評価は製品リスクマネジメントと連携しているか？品質マネジメントシステム変更が製品安全性に影響し得る場合のエスカレーション経路は？",
            "変更バリデーション機構は規定されているか？変更後の品質マネジメントシステム有効性の測定指標及び検証期限は変更計画で定義されているか？",
        ],
        "expected_evidence_en": [
            "QMS planning documents",
            "Change management records",
        ],
        "expected_evidence_ja": [
            "品質マネジメントシステム計画書",
            "変更管理記録",
        ],
    },
    "5.5.1": {
        "title": "責任與權限",
        "title_en": "Responsibility and Authority",
        "title_ja": "責任及び権限",
        "audit_impact": "major",
        "audit_question": (
            "最高管理階層是否確保組織內的責任與權限已被界定、文件化及溝通？"
            "是否建立互有關係人員之間的交互作用關係？"
        ),
        "audit_questions": [
            (
                "最高管理階層是否確保組織內的責任與權限已被界定、文件化及溝通？"
                "是否建立互有關係人員之間的交互作用關係？"
            ),
            "如何確認所有相關人員知悉其職責與權限？跨部門職責的衝突如何解決，是否有升級程序？",
            "依 ISO 13485:2016 §5.5.1，組織內所有影響產品品質的職位是否均有文件化的職責與權限說明？",
            "職務說明書（或權責矩陣）的更新頻率為何？當人員異動或組織重組時，如何確保職責更新的及時性？",
            "臨時代理職責的授權機制為何？代理期間的決策紀錄如何保存與追蹤？",
            "品質相關的決策授權層級是否明確？哪些決策需要升至最高管理階層核准？",
            "新員工如何被告知其職責與權限？是否有職責簽收或培訓確認紀錄？",
        ],
        "expected_evidence": [
            "組織架構圖",
            "職務說明書或權責矩陣",
        ],
        "audit_question_en": "Does top management ensure that responsibilities and authorities are defined, documented, and communicated within the organization?",
        "audit_question_ja": "トップマネジメントは、責任及び権限が組織内で定義され、文書化され、伝達されることを確実にしているか？",
        "audit_questions_en": [
            "Does top management ensure that responsibilities and authorities are defined, documented, and communicated within the organization?",
            "Are responsibilities and authorities at all levels clearly documented? How are duty transitions (e.g., personnel change) handled?",
            "Per ISO 13485:2016 §5.5.1, are the responsibilities and authorities of all personnel at all levels of the organization clearly defined and documented (e.g., organizational chart, job descriptions)?",
            "How are the responsibilities and authorities of new hires clearly communicated? Does onboarding training include explanation of QMS responsibilities?",
            "Are the responsibility boundaries of cross-departmental tasks clearly defined? Are there procedures to resolve responsibility ambiguity?",
            "When responsibilities and authorities change (e.g., promotion, transfer), is the update mechanism for related documents documented?",
            "Is the responsibility-authority-accountability relationship clearly established in QMS documents? Is the accountability system consistent with the responsibility framework?",
        ],
        "audit_questions_ja": [
            "トップマネジメントは、責任及び権限が組織内で定義され、文書化され、伝達されることを確実にしているか？",
            "各階層の責任及び権限は明確に文書化されているか？職務引継ぎ（人事異動等）はどのように処理されているか？",
            "ISO 13485:2016 §5.5.1に従い、組織の全階層のすべての要員の責任及び権限は明確に定義され文書化されているか（組織図、職務記述書等）？",
            "新規採用者の責任及び権限はどのように明確に伝達されているか？入社研修に品質マネジメントシステム責任の説明が含まれているか？",
            "部門横断業務の責任境界は明確に定義されているか？責任の不明確性を解決する手順はあるか？",
            "責任及び権限の変更（昇進、異動等）が発生した場合、関連文書の更新機構は文書化されているか？",
            "責任・権限・説明責任の関係は品質マネジメントシステム文書で明確に確立されているか？説明責任体系は責任枠組みと整合しているか？",
        ],
        "expected_evidence_en": [
            "Organizational chart",
            "Job descriptions",
        ],
        "expected_evidence_ja": [
            "組織図",
            "職務記述書",
        ],
    },
    "5.5.2": {
        "title": "管理代表",
        "title_en": "Management Representative",
        "title_ja": "管理責任者",
        "audit_impact": "major",
        "audit_question": (
            "最高管理階層是否指定管理階層中的一員作為管理代表，"
            "負責確保品質管理系統過程的建立與維持、向管理階層報告績效、"
            "以及確保在整個組織中促進對法規要求及品質管理系統要求的認知？"
        ),
        "audit_questions": [
            (
                "最高管理階層是否指定管理階層中的一員作為管理代表，"
                "負責確保品質管理系統過程的建立與維持、向管理階層報告績效、"
                "以及確保在整個組織中促進對法規要求及品質管理系統要求的認知？"
            ),
            "管理代表如何向管理階層報告品質管理系統績效？報告頻率與格式為何？管理代表是否獲得足夠授權以推動品質改善？",
            "依 ISO 13485:2016 §5.5.2，管理代表是否屬於管理階層成員，且其 QMS 相關職責是否以文件化方式指派？",
            "管理代表是否有足夠的時間與資源履行其職責？是否兼任其他職位，若有，是否存在利益衝突？",
            "管理代表如何確保 QMS 要求在整個組織中被有效溝通與理解？是否有相關計劃或紀錄？",
            "管理代表的後備方案為何？若管理代表缺席，QMS 的監督職責如何延續？",
            "管理代表與法規主管機關的溝通職責如何界定？是否有相關通報或聯絡的紀錄？",
        ],
        "expected_evidence": [
            "管理代表任命書",
            "管理代表職責說明",
        ],
        "audit_question_en": "Has top management appointed a member of the organization's management who, irrespective of other responsibilities, has responsibility and authority for ensuring that QMS processes are documented, and reporting to top management on the effectiveness of the QMS and any need for improvement, and ensuring the promotion of awareness of applicable regulatory requirements and QMS requirements throughout the organization?",
        "audit_question_ja": "トップマネジメントは、他の責任に関わらず、品質マネジメントシステムプロセスが文書化されていること、品質マネジメントシステムの有効性及び改善の必要性についてトップマネジメントに報告すること、並びに適用される規制要求事項及び品質マネジメントシステム要求事項の認識を組織全体に促進することを確実にする責任及び権限を有する組織の管理層の一員を任命しているか？",
        "audit_questions_en": [
            "Has top management appointed a member of the organization's management who, irrespective of other responsibilities, has responsibility and authority for ensuring that QMS processes are documented, and reporting to top management on the effectiveness of the QMS and any need for improvement, and ensuring the promotion of awareness of applicable regulatory requirements and QMS requirements throughout the organization?",
            "Is the appointment of the management representative formally documented? Does the scope of authorization include all QMS-related matters?",
            "Per ISO 13485:2016 §5.5.2, does the management representative have documented authority to ensure that QMS processes are established and reported to top management?",
            "Does the management representative have sufficient authority and resources to execute duties? When QMS issues require cross-departmental coordination, what is their authority?",
            "What are the reporting frequency and content of the management representative to top management? Does it include QMS effectiveness indicators, non-conformity trends, and corrective action status?",
            "How does the management representative promote awareness of regulatory requirements and QMS requirements throughout the organization? Are there specific communication plans and records?",
            "Is there a clear alternate when the management representative is absent or his/her role changes? How is the continuity of authority transfer ensured?",
        ],
        "audit_questions_ja": [
            "トップマネジメントは、他の責任に関わらず、品質マネジメントシステムプロセスが文書化されていること、品質マネジメントシステムの有効性及び改善の必要性についてトップマネジメントに報告すること、並びに適用される規制要求事項及び品質マネジメントシステム要求事項の認識を組織全体に促進することを確実にする責任及び権限を有する組織の管理層の一員を任命しているか？",
            "管理責任者の任命は正式に文書化されているか？権限付与範囲は品質マネジメントシステムに関するすべての事項を網羅しているか？",
            "ISO 13485:2016 §5.5.2に従い、管理責任者は品質マネジメントシステムプロセスの確立及びトップマネジメントへの報告を確実にする文書化された権限を有しているか？",
            "管理責任者は職務遂行のため十分な権限及び資源を有しているか？品質マネジメントシステムの問題が部門横断調整を要する場合の権限は？",
            "管理責任者のトップマネジメントへの報告頻度及び内容は？品質マネジメントシステム有効性指標、不適合傾向、是正処置状況を含むか？",
            "管理責任者は組織全体に対し、規制要求事項及び品質マネジメントシステム要求事項の認識をどのように促進しているか？具体的なコミュニケーション計画及び記録はあるか？",
            "管理責任者の不在時又は役割変更時の明確な代理者はいるか？権限移行の連続性はどのように確実にされているか？",
        ],
        "expected_evidence_en": [
            "Management representative appointment letter",
            "Management representative reports",
        ],
        "expected_evidence_ja": [
            "管理責任者任命書",
            "管理責任者報告書",
        ],
    },
    "5.5.3": {
        "title": "內部溝通",
        "title_en": "Internal Communication",
        "title_ja": "内部コミュニケーション",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保組織內建立適當的溝通過程，"
            "且針對品質管理系統的有效性進行溝通？"
        ),
        "audit_questions": [
            (
                "最高管理階層是否確保組織內建立適當的溝通過程，"
                "且針對品質管理系統的有效性進行溝通？"
            ),
            "組織如何確保品質管理系統的重要資訊有效傳達至相關人員？請舉例說明最近一次內部品質溝通的機制與效果。",
            "依 ISO 13485:2016 §5.5.3，組織是否建立適當的內部溝通過程，確保 QMS 有效性相關資訊在組織內部流通？",
            "品質相關的溝通管道有哪些（如內部電子報、例會、公告欄）？各管道的覆蓋率與有效性如何評估？",
            "當品質政策、程序或目標發生變更時，如何確保相關人員及時知悉？是否有確認機制？",
            "員工是否有管道向管理階層反映品質疑慮或改善建議？此機制的實際使用頻率與效果如何？",
            "重要品質事件（如重大客訴、法規通報）的內部溝通程序為何？溝通的時效要求是否文件化？",
        ],
        "expected_evidence": [
            "內部溝通程序或紀錄",
            "會議紀錄",
        ],
        "audit_question_en": "Does top management ensure that appropriate communication processes are established within the organization and that communication takes place regarding the effectiveness of the QMS?",
        "audit_question_ja": "トップマネジメントは、組織内に適切なコミュニケーションプロセスが確立され、品質マネジメントシステムの有効性に関するコミュニケーションが行われることを確実にしているか？",
        "audit_questions_en": [
            "Does top management ensure that appropriate communication processes are established within the organization and that communication takes place regarding the effectiveness of the QMS?",
            "Is the internal communication of QMS effectiveness structured? Are the communication frequency, content format, and target audiences defined?",
            "Per ISO 13485:2016 §5.5.3, has top management established appropriate communication processes to ensure communication regarding QMS effectiveness?",
            "What communication channels (meetings, emails, bulletin boards, intranet) are used to deliver QMS-related information to employees? How is the information reach verified?",
            "When QMS effectiveness issues are identified, how is upward communication conducted? Is an anonymous reporting channel provided?",
            "How is the effectiveness of internal communication evaluated? Is an employee understanding survey conducted regularly?",
            "Is cross-departmental communication effective? When an issue affects multiple departments, is there a unified communication mechanism to ensure information consistency?",
        ],
        "audit_questions_ja": [
            "トップマネジメントは、組織内に適切なコミュニケーションプロセスが確立され、品質マネジメントシステムの有効性に関するコミュニケーションが行われることを確実にしているか？",
            "品質マネジメントシステム有効性の社内コミュニケーションは体系化されているか？コミュニケーションの頻度、内容形式、対象者は定義されているか？",
            "ISO 13485:2016 §5.5.3に従い、トップマネジメントは品質マネジメントシステム有効性に関するコミュニケーションを確実にする適切なコミュニケーションプロセスを確立しているか？",
            "品質マネジメントシステム関連情報を従業員に伝えるために、どのコミュニケーションチャネル（会議、電子メール、掲示板、イントラネット）が使用されているか？情報到達性はどのように検証されているか？",
            "品質マネジメントシステム有効性の問題が識別された場合、上方向のコミュニケーションはどのように行われるか？匿名報告チャネルは提供されているか？",
            "社内コミュニケーションの有効性はどのように評価されているか？従業員の理解度調査は定期的に実施されているか？",
            "部門横断コミュニケーションは有効か？問題が複数部門に影響する場合、情報の一貫性を確実にする統一コミュニケーション機構はあるか？",
        ],
        "expected_evidence_en": [
            "Internal communication records",
            "QMS effectiveness report",
        ],
        "expected_evidence_ja": [
            "社内コミュニケーション記録",
            "品質マネジメントシステム有効性報告書",
        ],
    },
    "5.6.1": {
        "title": "管理審查 — 一般",
        "title_en": "Management Review — General",
        "title_ja": "マネジメントレビュー — 一般",
        "audit_impact": "major",
        "audit_question": (
            "最高管理階層是否依規劃的時間間隔審查品質管理系統，以確保其持續的"
            "適切性、充分性及有效性？審查是否包含評估改善的機會及品質管理系統"
            "變更的需要？管理審查紀錄是否予以維持？"
        ),
        "audit_questions": [
            (
                "最高管理階層是否依規劃的時間間隔審查品質管理系統，以確保其持續的"
                "適切性、充分性及有效性？審查是否包含評估改善的機會及品質管理系統"
                "變更的需要？管理審查紀錄是否予以維持？"
            ),
            "管理審查的頻率如何決定？是否有觸發條件（如重大不符合、法規變更）要求提前進行臨時管理審查？",
            "管理審查的頻率是否依規定執行？最近兩次審查的間隔是否符合規定？",
            "依 ISO 13485:2016 §5.6.2，管理審查輸入是否包含適用的新的或修訂的法規要求？最近哪些法規更新被納入審查？",
            "管理審查輸出的決議事項是否有明確的負責人與完成期限？追蹤機制為何？",
            "管理審查記錄是否包含出席人員名單、討論摘要、決議事項，並由最高管理階層核准？",
            "依 ISO 13485:2016 §5.6.3，上次管理審查所提出的改善措施，目前完成狀況如何？",
        ],
        "expected_evidence": [
            "管理審查程序書",
            "管理審查會議紀錄",
            "管理審查排程計畫",
        ],
        "audit_question_en": "Does the organization document procedures for management review, and does top management review the QMS at planned intervals to ensure its continuing suitability, adequacy, and effectiveness?",
        "audit_question_ja": "組織はマネジメントレビューの手順を文書化し、トップマネジメントは、品質マネジメントシステムの継続的な適切性、妥当性、有効性を確実にするため、計画された間隔で品質マネジメントシステムをレビューしているか？",
        "audit_questions_en": [
            "Does the organization document procedures for management review, and does top management review the QMS at planned intervals to ensure its continuing suitability, adequacy, and effectiveness?",
            "Is the management review frequency sufficient (e.g., at least annually)? When abnormal events occur (major recall, regulatory audit), is there a triggering mechanism for ad-hoc review?",
            "Per ISO 13485:2016 §5.6.1, does the organization have a documented management review procedure, and does top management review the QMS at planned intervals?",
            "Who are the attendees of the management review? Are all department heads and the management representative required to attend? Is the attendance record complete?",
            "Are the inputs of the management review prepared in advance (at least 1-2 weeks before the meeting) to allow participants sufficient time to review?",
            "Is the management review record complete? Does it include discussion content, decision items, action plans, and responsible persons?",
            "Are the action items of the management review tracked to completion? What is the follow-up mechanism to ensure decisions are implemented?",
        ],
        "audit_questions_ja": [
            "組織はマネジメントレビューの手順を文書化し、トップマネジメントは、品質マネジメントシステムの継続的な適切性、妥当性、有効性を確実にするため、計画された間隔で品質マネジメントシステムをレビューしているか？",
            "マネジメントレビューの頻度は十分か（少なくとも年1回等）？異常事象発生時（重大回収、規制監査等）の臨時レビューのトリガー機構はあるか？",
            "ISO 13485:2016 §5.6.1に従い、組織は文書化されたマネジメントレビュー手順を有し、トップマネジメントは計画された間隔で品質マネジメントシステムをレビューしているか？",
            "マネジメントレビューの出席者は誰か？全部門長及び管理責任者の出席が要求されているか？出席記録は完全か？",
            "マネジメントレビューのインプットは事前に準備されているか（会議の少なくとも1～2週間前）、参加者が十分なレビュー時間を持てるか？",
            "マネジメントレビュー記録は完全か？議論内容、決定事項、処置計画、責任者を含むか？",
            "マネジメントレビューの処置事項は完了まで追跡されているか？決定事項の実施を確実にするフォロー機構は何か？",
        ],
        "expected_evidence_en": [
            "Management review procedure",
            "Management review meeting minutes",
            "Management review action item tracking records",
        ],
        "expected_evidence_ja": [
            "マネジメントレビュー手順書",
            "マネジメントレビュー議事録",
            "マネジメントレビュー処置事項追跡記録",
        ],
    },
    "5.6.2": {
        "title": "管理審查 — 輸入",
        "title_en": "Management Review — Input",
        "title_ja": "マネジメントレビューへのインプット",
        "audit_impact": "major",
        "audit_question": (
            "管理審查的輸入是否包含稽核結果、顧客回饋、過程績效與產品符合性、"
            "預防及矯正措施狀況、先前管理審查之追蹤措施、可能影響品質管理系統的"
            "變更、改善建議、以及適用的新的或修訂的法規要求？"
        ),
        "audit_questions": [
            (
                "管理審查的輸入是否包含稽核結果、顧客回饋、過程績效與產品符合性、"
                "預防及矯正措施狀況、先前管理審查之追蹤措施、可能影響品質管理系統的"
                "變更、改善建議、以及適用的新的或修訂的法規要求？"
            ),
            "管理審查輸入資料如何被彙整與分析？各輸入來源的負責人是否明確指派？數據品質如何確保？",
            "依 ISO 13485:2016 §5.6.2，管理審查輸入是否包含所有規定項目：稽核結果、顧客回饋、過程績效、產品符合性、CAPA 狀態、先前審查追蹤、可能影響 QMS 的變更、改善建議及適用法規要求？",
            "管理審查輸入資料的截止日期與報告格式是否標準化？各部門的提交責任與期限如何管理？",
            "管理審查輸入中，哪些數據顯示過去一年 QMS 績效改善或退步的趨勢？趨勢分析是否系統化進行？",
            "當某項輸入數據無法獲取或不完整時，如何處理？是否有替代數據或例外說明的機制？",
            "法規變更資訊如何被納入管理審查輸入？負責追蹤法規更新的人員或部門為何？",
        ],
        "expected_evidence": [
            "管理審查輸入資料",
            "稽核報告摘要",
            "顧客回饋彙整",
            "CAPA 狀態報告",
        ],
        "audit_question_en": "Do the inputs to management review include feedback, complaint handling, reporting to regulatory authorities, audits, monitoring and measurement of processes, monitoring and measurement of product, corrective action, preventive action, follow-up actions from previous management reviews, changes that could affect the QMS, recommendations for improvement, and applicable new or revised regulatory requirements?",
        "audit_question_ja": "マネジメントレビューへのインプットには、フィードバック、苦情処理、規制当局への報告、監査、プロセスの監視及び測定、製品の監視及び測定、是正処置、予防処置、前回のマネジメントレビューからのフォローアップ処置、品質マネジメントシステムに影響し得る変更、改善の提案、及び適用される新規又は改訂された規制要求事項が含まれているか？",
        "audit_questions_en": [
            "Do the inputs to management review include feedback, complaint handling, reporting to regulatory authorities, audits, monitoring and measurement of processes, monitoring and measurement of product, corrective action, preventive action, follow-up actions from previous management reviews, changes that could affect the QMS, recommendations for improvement, and applicable new or revised regulatory requirements?",
            "Are the inputs of the management review comprehensive? Do they cover all 12 items required by standard §5.6.2 (a-l)?",
            "Per ISO 13485:2016 §5.6.2, do the management review inputs include feedback, complaint handling, regulatory reporting, audits, process monitoring, product monitoring, CAPA, follow-up actions, changes, improvement recommendations, and new/revised regulatory requirements?",
            "Are the management review inputs prepared by data or subjective reports? What is the reliability assurance mechanism for input data?",
            "How are customer complaint data quantified and trended in the management review? Is the discussion of complaint root causes systematic?",
            "Are the results of internal audits, external audits, and regulatory audits included in the management review inputs? How are the trends and common themes of these audits analyzed?",
            "Are the impact assessments of new or revised regulatory requirements (EU MDR amendments, FDA guidance updates, etc.) systematically presented in the management review?",
        ],
        "audit_questions_ja": [
            "マネジメントレビューへのインプットには、フィードバック、苦情処理、規制当局への報告、監査、プロセスの監視及び測定、製品の監視及び測定、是正処置、予防処置、前回のマネジメントレビューからのフォローアップ処置、品質マネジメントシステムに影響し得る変更、改善の提案、及び適用される新規又は改訂された規制要求事項が含まれているか？",
            "マネジメントレビューのインプットは包括的か？規格§5.6.2(a-l)が要求する12項目すべてを網羅しているか？",
            "ISO 13485:2016 §5.6.2に従い、マネジメントレビューのインプットには、フィードバック、苦情処理、規制当局への報告、監査、プロセス監視、製品監視、是正予防処置、フォローアップ処置、変更、改善提案、新規／改訂規制要求事項が含まれているか？",
            "マネジメントレビューのインプットはデータにより整備されているか、それとも主観的報告か？インプットデータの信頼性保証機構は何か？",
            "顧客苦情データはマネジメントレビューでどのように定量化されトレンド化されているか？苦情の根本原因に関する議論は体系的か？",
            "内部監査、外部監査、規制監査の結果はマネジメントレビューのインプットに含まれているか？これらの監査の傾向及び共通テーマはどのように分析されているか？",
            "新規又は改訂規制要求事項（EU MDR改訂、FDAガイダンス更新等）の影響評価は、マネジメントレビューで体系的に提示されているか？",
        ],
        "expected_evidence_en": [
            "Management review input checklist",
            "Audit reports",
            "Customer complaint analysis",
            "Regulatory requirements update log",
        ],
        "expected_evidence_ja": [
            "マネジメントレビューインプットチェックリスト",
            "監査報告書",
            "顧客苦情分析",
            "規制要求事項更新ログ",
        ],
    },
    "5.6.3": {
        "title": "管理審查 — 輸出",
        "title_en": "Management Review — Output",
        "title_ja": "マネジメントレビューからのアウトプット",
        "audit_impact": "major",
        "audit_question": (
            "管理審查的輸出是否包含品質管理系統及其過程有效性的改善、"
            "與顧客要求有關的產品改善、以及資源需求等相關決定及措施？"
        ),
        "audit_questions": [
            (
                "管理審查的輸出是否包含品質管理系統及其過程有效性的改善、"
                "與顧客要求有關的產品改善、以及資源需求等相關決定及措施？"
            ),
            "管理審查的決議如何被追蹤執行？是否設定完成期限與責任人？未能按時完成的措施如何升級處理？",
            "依 ISO 13485:2016 §5.6.3，管理審查輸出是否包含 QMS 有效性改善、產品改善及資源需求等決定與措施？",
            "管理審查輸出的行動項目追蹤系統為何？如何確保在下次管理審查前驗證前次決議的執行情況？",
            "管理審查輸出中涉及資源配置的決定如何被轉化為預算或採購計畫？執行時間框架為何？",
            "管理審查的結論與決議是否以書面形式記錄，並由最高管理階層核准後發行？紀錄保存期限為何？",
            "歷次管理審查輸出的趨勢是否被分析？是否有重複出現的改善項目未被根本解決的情形？",
        ],
        "expected_evidence": [
            "管理審查輸出/決議事項",
            "改善行動計畫",
            "資源配置決議",
        ],
        "audit_question_en": "Do the records from management reviews include the outputs as inputs for improvement of the effectiveness of the QMS and its processes, improvement of product related to customer requirements, changes needed to respond to applicable new or revised regulatory requirements, and resource needs?",
        "audit_question_ja": "マネジメントレビューからの記録には、品質マネジメントシステム及びそのプロセスの有効性の改善、顧客要求事項に関連する製品の改善、適用される新規又は改訂された規制要求事項に対応するために必要な変更、及び資源ニーズに対するインプットとしてのアウトプットが含まれているか？",
        "audit_questions_en": [
            "Do the records from management reviews include the outputs as inputs for improvement of the effectiveness of the QMS and its processes, improvement of product related to customer requirements, changes needed to respond to applicable new or revised regulatory requirements, and resource needs?",
            "Are the outputs of management reviews specific and actionable? Are all 4 output categories (a-d) required by standard §5.6.3 addressed?",
            "Per ISO 13485:2016 §5.6.3, do the outputs of management reviews include decisions related to improvement of QMS effectiveness, product improvement, response to new/revised regulatory requirements, and resource needs?",
            "Are the action items of management reviews assigned with owners, deadlines, and completion criteria? How is progress tracked?",
            "Is the approval of resource needs implemented in budget planning? What is the mechanism to ensure approved resources are actually allocated?",
            "Are the product improvement outputs of the management review linked to the design change control or CAPA system?",
            "Are changes required to respond to new or revised regulatory requirements translated into specific implementation plans with deadlines? What is the follow-up mechanism?",
        ],
        "audit_questions_ja": [
            "マネジメントレビューからの記録には、品質マネジメントシステム及びそのプロセスの有効性の改善、顧客要求事項に関連する製品の改善、適用される新規又は改訂された規制要求事項に対応するために必要な変更、及び資源ニーズに対するインプットとしてのアウトプットが含まれているか？",
            "マネジメントレビューのアウトプットは具体的かつ実行可能か？規格§5.6.3が要求する4つのアウトプットカテゴリ（a-d）はすべて対応されているか？",
            "ISO 13485:2016 §5.6.3に従い、マネジメントレビューのアウトプットには、品質マネジメントシステム有効性の改善、製品改善、新規／改訂規制要求事項への対応、資源ニーズに関連する決定が含まれているか？",
            "マネジメントレビューの処置事項には担当者、期限、完了基準が割り当てられているか？進捗はどのように追跡されているか？",
            "資源ニーズの承認は予算計画に実装されているか？承認された資源が実際に配分されることを確実にする機構は何か？",
            "マネジメントレビューの製品改善アウトプットは設計変更管理又は是正予防処置システムと連携しているか？",
            "新規又は改訂規制要求事項への対応に必要な変更は、期限付きの具体的な実施計画に展開されているか？フォロー機構は何か？",
        ],
        "expected_evidence_en": [
            "Management review output record",
            "Action plan tracking",
            "Resource allocation approval record",
        ],
        "expected_evidence_ja": [
            "マネジメントレビューアウトプット記録",
            "処置計画追跡記録",
            "資源配分承認記録",
        ],
    },
    # --------------------------------------------------------
    # Section 6: 資源管理
    # --------------------------------------------------------
    "6.1": {
        "title": "資源提供",
        "title_en": "Provision of Resources",
        "title_ja": "資源の提供",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否決定並提供所需的資源，以實施品質管理系統並維持其有效性，"
            "以及滿足適用的法規要求及顧客要求？"
        ),
        "audit_questions": [
            (
                "組織是否決定並提供所需的資源，以實施品質管理系統並維持其有效性，"
                "以及滿足適用的法規要求及顧客要求？"
            ),
            "資源需求如何被識別與預算化？當實際資源無法滿足計畫時，有何優先排序機制？",
            "資源需求的識別過程是否文件化？當業務量增加時，資源重新評估的觸發條件為何？",
            "依 ISO 13485:2016 §6.1，資源供應的決策是否包含基礎設施老化與設備汰換的規劃？",
            "人力資源的能力要求如何識別？是否有能力評估機制，且評估結果被記錄？",
            "當關鍵人員離職時，其職位的能力要求如何確保繼任者能迅速符合？是否有知識移轉計劃？",
            "依 ISO 13485:2016 §6.1，資源供應是否包含法規合規所需的資源（如法規人員、測試設備）？如何確保？",
        ],
        "expected_evidence": [
            "資源規劃紀錄",
            "預算分配紀錄",
        ],
        "audit_question_en": "Does the organization determine and provide the resources needed to implement and maintain the QMS and maintain its effectiveness, and to meet applicable regulatory and customer requirements?",
        "audit_question_ja": "組織は、品質マネジメントシステムを実施し維持し、その有効性を維持するために、並びに適用される規制要求事項及び顧客要求事項を満たすために必要な資源を決定し提供しているか？",
        "audit_questions_en": [
            "Does the organization determine and provide the resources needed to implement and maintain the QMS and maintain its effectiveness, and to meet applicable regulatory and customer requirements?",
            "How are resource needs identified and applied for? Is there a formal resource planning mechanism (annual budget, medium-term plan)?",
            "Per ISO 13485:2016 §6.1, does the organization determine and provide the resources needed to maintain the QMS and meet regulatory requirements?",
            "When business grows or regulatory requirements increase, how are resource gaps identified? Is there a trigger mechanism for dynamic resource adjustment?",
            "Are the resources to implement QMS effectiveness covered in the annual budget? Are human, financial, infrastructure, and technology resources all included?",
            "When resource shortages affect QMS effectiveness, what is the escalation procedure? Who has authority to approve urgent resource allocation?",
            "Are the outcomes of resource allocation effectively monitored? How is the rationality and effectiveness of resource allocation evaluated?",
        ],
        "audit_questions_ja": [
            "組織は、品質マネジメントシステムを実施し維持し、その有効性を維持するために、並びに適用される規制要求事項及び顧客要求事項を満たすために必要な資源を決定し提供しているか？",
            "資源ニーズはどのように識別され申請されているか？正式な資源計画機構（年次予算、中期計画）はあるか？",
            "ISO 13485:2016 §6.1に従い、組織は品質マネジメントシステムを維持し規制要求事項を満たすために必要な資源を決定し提供しているか？",
            "事業拡大又は規制要求の増加時、資源ギャップはどのように識別されるか？動的な資源調整のトリガー機構はあるか？",
            "品質マネジメントシステム有効性を実施する資源は年次予算に含まれているか？人的、財務、インフラ、技術資源はすべて含まれているか？",
            "資源不足が品質マネジメントシステム有効性に影響する場合、エスカレーション手順は何か？緊急資源配分の承認権限は誰にあるか？",
            "資源配分の成果は有効に監視されているか？資源配分の妥当性及び有効性はどのように評価されているか？",
        ],
        "expected_evidence_en": [
            "Resource planning documents",
            "Annual budget (QMS-related portion)",
        ],
        "expected_evidence_ja": [
            "資源計画書",
            "年次予算（品質マネジメントシステム関連部分）",
        ],
    },
    "6.2": {
        "title": "人力資源",
        "title_en": "Human Resources",
        "title_ja": "人的資源",
        "audit_impact": "major",
        "audit_question": (
            "執行影響產品品質工作的人員是否基於適當的教育、訓練、技能及經驗而能勝任？"
            "組織是否建立訓練需求的過程、提供訓練或採取其他措施以達成能力、"
            "並維持適當的紀錄？"
        ),
        "audit_questions": [
            (
                "執行影響產品品質工作的人員是否基於適當的教育、訓練、技能及經驗而能勝任？"
                "組織是否建立訓練需求的過程、提供訓練或採取其他措施以達成能力、"
                "並維持適當的紀錄？"
            ),
            "如何確認訓練的有效性？訓練有效性評估方法是什麼？若訓練未達預期效果，後續措施為何？",
            "依 ISO 13485:2016 §6.2，執行影響產品品質工作的人員是否基於適當的教育、訓練、技能及經驗而能勝任？資格認定準則如何界定？",
            "年度訓練計畫的制定依據為何（如職能差距分析、新法規要求）？計畫如何因應組織變化而動態調整？",
            "關鍵崗位的繼任計劃是否存在？關鍵技術知識如何文件化以防止知識流失？",
            "外包或臨時人員的能力要求與管理方式為何？其訓練記錄如何維持？",
            "績效評估結果如何與訓練需求識別掛鉤？最近一次因績效評估而觸發的訓練活動為何？",
        ],
        "expected_evidence": [
            "教育訓練程序書",
            "員工訓練紀錄",
            "職能資格矩陣",
            "訓練有效性評估紀錄",
        ],
        "audit_question_en": "Does the organization ensure that personnel performing work affecting product quality are competent on the basis of appropriate education, training, skills, and experience; document the process for establishing competence, providing needed training, and ensuring awareness of personnel; ensure that personnel are aware of the relevance and importance of their activities; and maintain appropriate records?",
        "audit_question_ja": "組織は、製品品質に影響する業務を遂行する要員が、適切な教育、訓練、技能及び経験に基づいて力量を有することを確実にし、力量の確立、必要な訓練の提供、要員の認識の確実化のためのプロセスを文書化し、要員がその活動の関連性及び重要性を認識することを確実にし、適切な記録を維持しているか？",
        "audit_questions_en": [
            "Does the organization ensure that personnel performing work affecting product quality are competent on the basis of appropriate education, training, skills, and experience; document the process for establishing competence, providing needed training, and ensuring awareness of personnel; ensure that personnel are aware of the relevance and importance of their activities; and maintain appropriate records?",
            "How is competence assessment for each position defined? Does it include education, experience, training, and skill dimensions? How is the effectiveness of training evaluated?",
            "Per ISO 13485:2016 §6.2, is the competence requirement for each position defined and documented? How is the competence of personnel performing work affecting product quality assessed?",
            "Is the training plan established based on competence gap analysis? How are training topics prioritized?",
            "Are training records complete? Do they include training content, participants, trainers, dates, and assessment results?",
            "How is the effectiveness of training evaluated? Is it limited to training attendance, or is it followed up by on-the-job performance?",
            "How is the awareness of personnel about the relevance and importance of their activities confirmed? Is there a mechanism for quality awareness surveys?",
        ],
        "audit_questions_ja": [
            "組織は、製品品質に影響する業務を遂行する要員が、適切な教育、訓練、技能及び経験に基づいて力量を有することを確実にし、力量の確立、必要な訓練の提供、要員の認識の確実化のためのプロセスを文書化し、要員がその活動の関連性及び重要性を認識することを確実にし、適切な記録を維持しているか？",
            "各職位の力量評価はどのように規定されているか？教育、経験、訓練、技能の側面を含むか？訓練の有効性はどのように評価されるか？",
            "ISO 13485:2016 §6.2に従い、各職位の力量要求事項は定義され文書化されているか？製品品質に影響する業務を遂行する要員の力量はどのように評価されているか？",
            "訓練計画は力量ギャップ分析に基づいて策定されているか？訓練テーマの優先順位はどのように決定されているか？",
            "訓練記録は完全か？訓練内容、参加者、講師、日付、評価結果を含むか？",
            "訓練の有効性はどのように評価されているか？訓練出席のみか、それとも現場パフォーマンスによる追跡評価か？",
            "要員の活動の関連性及び重要性に関する認識はどのように確認されているか？品質意識調査の機構はあるか？",
        ],
        "expected_evidence_en": [
            "Competence requirements documents",
            "Training plan",
            "Training records",
            "Competence assessment records",
        ],
        "expected_evidence_ja": [
            "力量要求事項文書",
            "訓練計画",
            "訓練記録",
            "力量評価記録",
        ],
    },
    "6.3": {
        "title": "基礎設施",
        "title_en": "Infrastructure",
        "title_ja": "インフラストラクチャ",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定、提供及維持達成產品符合要求所需的基礎設施？"
            "基礎設施是否包含建築物、工作空間、過程設備及支援服務？"
            "是否建立基礎設施維護活動的文件化要求（含間隔）？"
        ),
        "audit_questions": [
            (
                "組織是否決定、提供及維持達成產品符合要求所需的基礎設施？"
                "基礎設施是否包含建築物、工作空間、過程設備及支援服務？"
                "是否建立基礎設施維護活動的文件化要求（含間隔）？"
            ),
            "設備維護保養計畫的制定依據為何？關鍵設備若發生非計畫性停機，緊急備援計畫為何？",
            "依 ISO 13485:2016 §6.3，基礎設施維護活動的要求（包含維護間隔）是否有文件化記錄？維護紀錄保存期限為何？",
            "所有影響產品品質的設備是否均列入維護計畫？設備的危急程度分類標準為何？",
            "設備老化或技術落後的評估機制為何？更換計畫如何納入年度預算規劃？",
            "支援服務（如資訊系統、供水、電力）的維護責任與緊急應變計畫是否文件化？",
            "廠房設施的設計（如動線規劃、防污染隔離）是否符合產品品質要求？最近一次廠房設施審查的結果為何？",
        ],
        "expected_evidence": [
            "設備清單",
            "設備維護保養計畫與紀錄",
            "廠房配置圖",
        ],
        "audit_question_en": "Does the organization document the requirements for the infrastructure needed to achieve conformity to product requirements, prevent product mix-up, and ensure orderly handling of product? Infrastructure includes buildings, workspace and associated utilities; process equipment (both hardware and software); and supporting services (such as transport, communication or information systems).",
        "audit_question_ja": "組織は、製品要求事項への適合の達成、製品の混同の防止、及び製品の秩序正しい取扱いの確実化のために必要なインフラストラクチャの要求事項を文書化しているか？インフラストラクチャには、建物、作業空間及び関連するユーティリティ、プロセス装置（ハードウェア及びソフトウェアの両方）、並びに支援サービス（輸送、通信又は情報システム等）が含まれる。",
        "audit_questions_en": [
            "Does the organization document the requirements for the infrastructure needed to achieve conformity to product requirements, prevent product mix-up, and ensure orderly handling of product? Infrastructure includes buildings, workspace and associated utilities; process equipment (both hardware and software); and supporting services (such as transport, communication or information systems).",
            "Are the infrastructure maintenance procedures documented? Are the maintenance frequency, responsible personnel, and records complete?",
            "Per ISO 13485:2016 §6.3, are the infrastructure requirements (buildings, workspace, utilities, process equipment, supporting services) documented?",
            "Is preventive maintenance implemented according to the plan? When equipment downtime affects product quality, is the impact assessment procedure documented?",
            "Is the infrastructure design considered from the perspectives of preventing product mix-up, contamination, and improper handling? Are relevant risk control measures documented?",
            "How is equipment-related software (e.g., PLC, ERP, MES) validated and maintained? Is there a dedicated software change management procedure?",
            "When infrastructure changes (e.g., workshop expansion, equipment replacement), how is the impact on product quality assessed? Is there a change validation mechanism?",
        ],
        "audit_questions_ja": [
            "組織は、製品要求事項への適合の達成、製品の混同の防止、及び製品の秩序正しい取扱いの確実化のために必要なインフラストラクチャの要求事項を文書化しているか？インフラストラクチャには、建物、作業空間及び関連するユーティリティ、プロセス装置（ハードウェア及びソフトウェアの両方）、並びに支援サービス（輸送、通信又は情報システム等）が含まれる。",
            "インフラストラクチャの保守手順は文書化されているか？保守頻度、責任要員、記録は完全か？",
            "ISO 13485:2016 §6.3に従い、インフラストラクチャ要求事項（建物、作業空間、ユーティリティ、プロセス装置、支援サービス）は文書化されているか？",
            "予防保全は計画通りに実施されているか？装置の停止が製品品質に影響する場合、影響評価手順は文書化されているか？",
            "インフラストラクチャ設計は、製品の混同、汚染、不適切な取扱いの防止の観点から考慮されているか？関連するリスク管理策は文書化されているか？",
            "装置関連ソフトウェア（PLC、ERP、MES等）はどのようにバリデーションされ保守されているか？専用のソフトウェア変更管理手順はあるか？",
            "インフラストラクチャ変更時（工場拡張、装置更新等）、製品品質への影響はどのように評価されているか？変更バリデーション機構はあるか？",
        ],
        "expected_evidence_en": [
            "Infrastructure list",
            "Equipment maintenance plan/records",
            "Workspace plan",
        ],
        "expected_evidence_ja": [
            "インフラストラクチャ一覧",
            "装置保守計画／記録",
            "作業空間計画",
        ],
    },
    "6.4.1": {
        "title": "工作環境",
        "title_en": "Work Environment",
        "title_ja": "作業環境",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定並管理達成產品符合要求所需的工作環境？"
            "如果工作環境條件可能對產品品質產生不利影響，"
            "組織是否建立工作環境要求、監督與管制這些條件的程序？"
        ),
        "audit_questions": [
            (
                "組織是否決定並管理達成產品符合要求所需的工作環境？"
                "如果工作環境條件可能對產品品質產生不利影響，"
                "組織是否建立工作環境要求、監督與管制這些條件的程序？"
            ),
            "工作環境條件超出規格時，產品的處置程序為何？環境監測數據是否定期趨勢分析以預測潛在問題？",
            "依 ISO 13485:2016 §6.4.1，工作環境的管制要求（如溫度、濕度、潔淨度）是否文件化，且定期進行監測與記錄？",
            "工作環境的管制限值如何確定？是否有科學依據或法規要求支持所設定的管制界限？",
            "工作環境監測設備的校正狀態如何確保？監測數據的記錄頻率與留存期限為何？",
            "員工健康與安全要求（如無菌室著裝、個人衛生）如何融入工作環境管制規定？",
            "靜電放電（ESD）防護或其他特殊環境要求（如低濕、無菌）是否被識別並納入管制程序？",
        ],
        "expected_evidence": [
            "工作環境管制程序書",
            "環境監測紀錄（溫濕度、潔淨度等）",
        ],
        "audit_question_en": "Does the organization document the requirements for the work environment needed to achieve conformity to product requirements, and establish documented requirements for health, cleanliness, and clothing of personnel if contact between such personnel and the product or work environment could affect medical device safety or performance?",
        "audit_question_ja": "組織は、製品要求事項への適合の達成のために必要な作業環境の要求事項を文書化し、要員と製品又は作業環境との接触が医療機器の安全性又は性能に影響し得る場合には、要員の健康、清潔さ及び服装に関する文書化された要求事項を確立しているか？",
        "audit_questions_en": [
            "Does the organization document the requirements for the work environment needed to achieve conformity to product requirements, and establish documented requirements for health, cleanliness, and clothing of personnel if contact between such personnel and the product or work environment could affect medical device safety or performance?",
            "Are work environment control requirements defined (e.g., temperature, humidity, cleanliness levels)? Is routine monitoring performed?",
            "Per ISO 13485:2016 §6.4.1, are the work environment requirements necessary to meet product requirements documented, and are health, cleanliness, and clothing requirements for personnel established (if applicable)?",
            "Is employee health monitoring mechanism (e.g., regular health check, symptom reporting) implemented? How is the risk of work assignments for personnel with infectious diseases controlled?",
            "Are clothing and personal protective equipment (PPE) requirements for different operational areas documented? Are the clothing changing procedures and supervision mechanisms clear?",
            "Is the cleanliness control procedure for production environments (cleaning, disinfection, biological monitoring) risk-based? What are the procedures for handling abnormal monitoring results?",
            "When subcontractors or visitors enter controlled work environments, what are the entry conditions? How is compliance with environmental requirements ensured?",
        ],
        "audit_questions_ja": [
            "組織は、製品要求事項への適合の達成のために必要な作業環境の要求事項を文書化し、要員と製品又は作業環境との接触が医療機器の安全性又は性能に影響し得る場合には、要員の健康、清潔さ及び服装に関する文書化された要求事項を確立しているか？",
            "作業環境管理要求事項は定義されているか（温度、湿度、清浄度等級等）？日常監視は実施されているか？",
            "ISO 13485:2016 §6.4.1に従い、製品要求事項を満たすために必要な作業環境要求事項は文書化され、要員の健康、清潔さ、服装要求事項が確立されているか（該当する場合）？",
            "従業員の健康監視機構（定期健康診断、症状報告等）は実施されているか？感染症に罹患した要員の業務割当てリスクはどのように管理されているか？",
            "異なる作業エリアの服装及び個人用保護具（PPE）要求事項は文書化されているか？更衣手順及び監督機構は明確か？",
            "製造環境の清浄度管理手順（清掃、消毒、生物学的モニタリング）はリスクに基づいているか？監視結果異常時の処理手順は？",
            "外部委託先又は訪問者が管理された作業環境に入る場合、入室条件は何か？環境要求事項への適合はどのように確実にされているか？",
        ],
        "expected_evidence_en": [
            "Work environment requirements documents",
            "Personnel health/clothing requirements (if applicable)",
        ],
        "expected_evidence_ja": [
            "作業環境要求事項文書",
            "要員の健康／服装要求事項（該当する場合）",
        ],
    },
    "6.4.2": {
        "title": "污染管制",
        "title_en": "Contamination Control",
        "title_ja": "汚染管理",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否依適當情況規劃並文件化污染或潛在污染產品的管制安排，"
            "以防止工作環境對產品造成污染？"
            "對於無菌醫療器材，是否維持組裝或包裝過程中微生物污染管制的要求？"
        ),
        "audit_questions": [
            (
                "組織是否依適當情況規劃並文件化污染或潛在污染產品的管制安排，"
                "以防止工作環境對產品造成污染？"
                "對於無菌醫療器材，是否維持組裝或包裝過程中微生物污染管制的要求？"
            ),
            "污染事件的偵測與處置流程為何？如何驗證清潔或污染管制措施的持續有效性？",
            "依 ISO 13485:2016 §6.4.2，組織是否已規劃並文件化污染管制安排，適用於無菌器材的組裝或包裝過程？",
            "微生物監測（環境監測程序）的取樣計畫依據為何？取樣頻率、位置與警戒/行動限值如何設定？",
            "人員進出潔淨區的管控程序為何？違規行為（如著裝不符）的矯正措施如何執行？",
            "清潔劑與消毒劑的選擇依據為何？是否進行過輪換以避免微生物抗性？相關驗證紀錄是否維持？",
            "污染物料的隔離與處置程序是否文件化？污染事件的根本原因分析是否列入 CAPA 系統管理？",
        ],
        "expected_evidence": [
            "污染管制程序書",
            "潔淨室管制紀錄（如適用）",
            "微生物監測紀錄（如適用）",
        ],
        "audit_question_en": "Does the organization plan, document, and control arrangements for the control of contamination of product by any substance or contamination, including control measures for sterile devices?",
        "audit_question_ja": "組織は、滅菌機器の管理策を含め、あらゆる物質又は汚染による製品の汚染管理のための取決めを計画し、文書化し、管理しているか？",
        "audit_questions_en": [
            "Does the organization plan, document, and control arrangements for the control of contamination of product by any substance or contamination, including control measures for sterile devices?",
            "Is the contamination control plan comprehensive? Does it cover microbial, particulate, and chemical contamination risks?",
            "Per ISO 13485:2016 §6.4.2, does the organization plan, document, and control arrangements for contamination control of products by substances or contamination?",
            "For sterile products, is the cleanroom environment (ISO 14644 class) monitoring continuous? Are the procedures for handling abnormal data documented?",
            "Is the contamination control program implemented with personnel (clothing, health), facility (HVAC), and process (cleaning, disinfection) dimensions covered?",
            "Are the contamination risks of incoming raw materials assessed? Are there microbial or chemical contamination testing requirements for key materials?",
            "When contamination events occur (e.g., cleanroom excursion), what is the investigation procedure? How is the corrective action effectiveness verified?",
        ],
        "audit_questions_ja": [
            "組織は、滅菌機器の管理策を含め、あらゆる物質又は汚染による製品の汚染管理のための取決めを計画し、文書化し、管理しているか？",
            "汚染管理計画は包括的か？微生物、粒子、化学汚染リスクを網羅しているか？",
            "ISO 13485:2016 §6.4.2に従い、組織は物質又は汚染による製品の汚染管理のための取決めを計画し、文書化し、管理しているか？",
            "滅菌製品について、クリーンルーム環境（ISO 14644等級）の監視は継続的か？データ異常時の処理手順は文書化されているか？",
            "汚染管理プログラムは、要員（服装、健康）、施設（HVAC）、プロセス（清掃、消毒）の側面で実施されているか？",
            "受入原材料の汚染リスクは評価されているか？重要資材の微生物又は化学汚染試験要求事項はあるか？",
            "汚染事象発生時（クリーンルーム逸脱等）、調査手順は何か？是正処置の有効性はどのように検証されているか？",
        ],
        "expected_evidence_en": [
            "Contamination control plan",
            "Cleanroom environmental monitoring records (if applicable)",
            "Contamination control procedures",
        ],
        "expected_evidence_ja": [
            "汚染管理計画",
            "クリーンルーム環境モニタリング記録（該当する場合）",
            "汚染管理手順書",
        ],
    },
    # --------------------------------------------------------
    # Section 7: 產品實現
    # --------------------------------------------------------
    "7.1": {
        "title": "產品實現之規劃",
        "title_en": "Planning of Product Realization",
        "title_ja": "製品実現の計画",
        "audit_impact": "major",
        "audit_question": (
            "組織是否規劃並開發產品實現所需的過程？"
            "規劃是否與品質管理系統其他過程的要求一致？"
            "是否建立風險管理的文件化要求？"
        ),
        "audit_questions": [
            (
                "組織是否規劃並開發產品實現所需的過程？"
                "規劃是否與品質管理系統其他過程的要求一致？"
                "是否建立風險管理的文件化要求？"
            ),
            "產品實現規劃如何確保風險管理貫穿整個產品生命週期？風險管理活動的輸出如何與設計、採購、生產等過程整合？",
            "依 ISO 13485:2016 §7.1，產品實現規劃是否確立品質目標與要求、過程文件化需求、資源需求、驗證/確認/監控/量測需求以及可接受準則？",
            "產品實現規劃的輸出形式為何（如品質計畫、專案計劃）？每個新產品/專案是否都建立個別的規劃文件？",
            "如何確保產品實現規劃在產品開發過程中保持最新狀態？計畫變更的審批與紀錄程序為何？",
            "風險管理計畫是否作為產品實現規劃的組成部分？風險管理活動的責任人如何指派？",
            "當產品實現過程中發現之前規劃未能滿足要求時，如何啟動規劃修訂程序？",
        ],
        "expected_evidence": [
            "產品實現規劃文件",
            "風險管理計畫",
            "品質計畫（如適用）",
        ],
        "audit_question_en": "Does the organization plan and develop the processes needed for product realization, consistent with the requirements of other processes of the QMS? In planning product realization, does the organization determine quality objectives and requirements for the product; the need to establish processes and documents and to provide resources specific to the product; required verification, validation, monitoring, measurement, inspection and test, handling, storage, distribution, and traceability activities; and records needed to provide evidence that the realization processes and resulting product meet requirements?",
        "audit_question_ja": "組織は、品質マネジメントシステムの他のプロセスの要求事項と整合する、製品実現に必要なプロセスを計画し開発しているか？製品実現の計画において、組織は、製品に対する品質目標及び要求事項、製品に固有のプロセス及び文書を確立し、資源を提供することの必要性、要求される検証、妥当性確認、監視、測定、検査及び試験、取扱い、保管、流通、並びにトレーサビリティの活動、並びに実現プロセス及び結果として得られる製品が要求事項を満たすことの証拠を提供するために必要な記録を決定しているか？",
        "audit_questions_en": [
            "Does the organization plan and develop the processes needed for product realization, consistent with the requirements of other processes of the QMS? In planning product realization, does the organization determine quality objectives and requirements for the product; the need to establish processes and documents and to provide resources specific to the product; required verification, validation, monitoring, measurement, inspection and test, handling, storage, distribution, and traceability activities; and records needed to provide evidence that the realization processes and resulting product meet requirements?",
            "Is the product realization planning documented? Is it coordinated with the design and development plan, production plan, and QC plan?",
            "Per ISO 13485:2016 §7.1, is product realization planning consistent with QMS process requirements? Does it cover quality objectives, process and document needs, verification, validation, handling, storage, distribution, and traceability requirements?",
            "How is the risk management plan integrated with product realization planning? Is the risk management output used as an input to product realization planning?",
            "Is the traceability plan established at the product realization planning stage? Does it cover all critical components and process steps?",
            "Are the quality planning documents periodically reviewed? How is it ensured that the plan is up to date and reflects changes?",
            "How are the records needed for product realization processes identified at the planning stage? How is it ensured that records are consistent with regulatory traceability requirements?",
        ],
        "audit_questions_ja": [
            "組織は、品質マネジメントシステムの他のプロセスの要求事項と整合する、製品実現に必要なプロセスを計画し開発しているか？製品実現の計画において、組織は、製品に対する品質目標及び要求事項、製品に固有のプロセス及び文書を確立し、資源を提供することの必要性、要求される検証、妥当性確認、監視、測定、検査及び試験、取扱い、保管、流通、並びにトレーサビリティの活動、並びに実現プロセス及び結果として得られる製品が要求事項を満たすことの証拠を提供するために必要な記録を決定しているか？",
            "製品実現計画は文書化されているか？設計開発計画、生産計画、QC計画と調整されているか？",
            "ISO 13485:2016 §7.1に従い、製品実現計画は品質マネジメントシステムプロセス要求事項と整合しているか？品質目標、プロセス及び文書のニーズ、検証、妥当性確認、取扱い、保管、流通、トレーサビリティ要求事項を網羅しているか？",
            "リスクマネジメント計画は製品実現計画とどのように統合されているか？リスクマネジメントアウトプットは製品実現計画のインプットとして使用されているか？",
            "トレーサビリティ計画は製品実現計画段階で確立されているか？すべての重要部品及びプロセスステップを網羅しているか？",
            "品質計画文書は定期的にレビューされているか？計画が最新で変更を反映していることをどのように確実にしているか？",
            "製品実現プロセスに必要な記録は、計画段階でどのように識別されているか？記録が規制当局のトレーサビリティ要求事項と整合することをどのように確実にしているか？",
        ],
        "expected_evidence_en": [
            "Product realization plan",
            "Risk management plan",
            "Traceability plan",
        ],
        "expected_evidence_ja": [
            "製品実現計画書",
            "リスクマネジメント計画書",
            "トレーサビリティ計画書",
        ],
    },
    "7.2.1": {
        "title": "與產品有關的要求之決定",
        "title_en": "Determination of Requirements Related to Product",
        "title_ja": "製品に関連する要求事項の明確化",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定顧客規定的要求（含交付及交付後活動的要求）、"
            "顧客未陳述但已知預期用途所必要的要求、與產品有關的適用法規要求、"
            "以及任何附加要求？"
        ),
        "audit_questions": [
            (
                "組織是否決定顧客規定的要求（含交付及交付後活動的要求）、"
                "顧客未陳述但已知預期用途所必要的要求、與產品有關的適用法規要求、"
                "以及任何附加要求？"
            ),
            "顧客要求的優先順序如何確定？當顧客要求與法規要求衝突時，如何處理？",
            "依 ISO 13485:2016 §7.2.1，組織是否系統性地確定顧客明示要求、隱含要求、交付後活動要求及適用法規要求？",
            "交付後活動（如維護、技術支援、產品退役）的要求如何被識別並納入產品開發或採購規劃？",
            "組織如何識別顧客未明確陳述但對預期用途所必要的要求？識別的方法與紀錄為何？",
            "適用法規要求的識別責任人為誰？法規要求清單的更新機制與頻率為何？",
            "市場上若有新興的使用情境或技術標準更新，如何觸發對產品要求的重新評估？",
        ],
        "expected_evidence": [
            "產品需求規格書",
            "顧客要求紀錄",
            "適用法規要求清單",
        ],
        "audit_question_en": "Does the organization determine requirements specified by the customer, including the requirements for delivery and post-delivery activities; requirements not stated by the customer but necessary for specified or intended use, as known; applicable regulatory requirements related to the product; any user training needed to ensure specified performance and safe use of the medical device; and any additional requirements determined by the organization?",
        "audit_question_ja": "組織は、引渡し及び引渡し後の活動に関する要求事項を含む顧客によって規定された要求事項、顧客によって規定されていないが知られている規定された使用又は意図された使用に必要な要求事項、製品に関連する適用規制要求事項、医療機器の規定された性能及び安全な使用を確実にするために必要な利用者訓練、並びに組織が決定したその他の要求事項を決定しているか？",
        "audit_questions_en": [
            "Does the organization determine requirements specified by the customer, including the requirements for delivery and post-delivery activities; requirements not stated by the customer but necessary for specified or intended use, as known; applicable regulatory requirements related to the product; any user training needed to ensure specified performance and safe use of the medical device; and any additional requirements determined by the organization?",
            "Is the customer requirement identification process complete? Does it cover explicit requirements, implicit requirements, regulatory requirements, and user training requirements?",
            "Per ISO 13485:2016 §7.2.1, does the organization identify all customer requirements, delivery and post-delivery activity requirements, implicit use requirements, applicable regulatory requirements, user training needs, and other organization-determined requirements?",
            "Are the regulatory requirements for the product destination country/region identified? How are changes in regulations tracked and impact assessments performed?",
            "How are implicit user needs (e.g., usability, biocompatibility, use environment) identified and documented? Is the human factors engineering process integrated?",
            "How is user training needed for safe use determined? Is training material development aligned with product design and regulatory requirements?",
            "Are the requirements for delivery (packaging, transportation, installation) and post-delivery activities (maintenance, service) included in the requirement identification?",
        ],
        "audit_questions_ja": [
            "組織は、引渡し及び引渡し後の活動に関する要求事項を含む顧客によって規定された要求事項、顧客によって規定されていないが知られている規定された使用又は意図された使用に必要な要求事項、製品に関連する適用規制要求事項、医療機器の規定された性能及び安全な使用を確実にするために必要な利用者訓練、並びに組織が決定したその他の要求事項を決定しているか？",
            "顧客要求事項の識別プロセスは完全か？明示的要求事項、暗黙的要求事項、規制要求事項、利用者訓練要求事項を網羅しているか？",
            "ISO 13485:2016 §7.2.1に従い、組織はすべての顧客要求事項、引渡し及び引渡し後活動の要求事項、暗黙的使用要求事項、適用規制要求事項、利用者訓練ニーズ、組織が決定したその他の要求事項を識別しているか？",
            "製品の仕向国／地域の規制要求事項は識別されているか？規制変更の追跡及び影響評価はどのように実施されているか？",
            "暗黙的な利用者ニーズ（使いやすさ、生体適合性、使用環境等）はどのように識別され文書化されているか？ヒューマンファクタズエンジニアリングプロセスは統合されているか？",
            "安全な使用に必要な利用者訓練はどのように決定されているか？訓練資料の開発は製品設計及び規制要求事項と整合しているか？",
            "引渡し（包装、輸送、据付）及び引渡し後活動（保守、サービス）に関する要求事項は要求事項識別に含まれているか？",
        ],
        "expected_evidence_en": [
            "Customer requirements document",
            "Applicable regulatory requirements list",
            "User training material (if applicable)",
        ],
        "expected_evidence_ja": [
            "顧客要求事項文書",
            "適用法規制要求事項一覧",
            "利用者訓練資料（該当する場合）",
        ],
    },
    "7.2.2": {
        "title": "與產品有關的要求之審查",
        "title_en": "Review of Requirements Related to Product",
        "title_ja": "製品に関連する要求事項のレビュー",
        "audit_impact": "major",
        "audit_question": (
            "組織是否在承諾供應產品予顧客之前審查與產品有關的要求？"
            "審查是否確保產品要求已被界定、合約或訂單要求的差異已解決、"
            "以及組織有能力滿足已界定的要求？"
        ),
        "audit_questions": [
            (
                "組織是否在承諾供應產品予顧客之前審查與產品有關的要求？"
                "審查是否確保產品要求已被界定、合約或訂單要求的差異已解決、"
                "以及組織有能力滿足已界定的要求？"
            ),
            "合約審查的觸發時機與完成標準為何？若審查後發現組織能力不足以滿足要求，決策流程為何？",
            "依 ISO 13485:2016 §7.2.2，在承諾供應產品前，組織是否確認：產品要求已界定、合約差異已解決、且有能力滿足要求？",
            "口頭訂單或緊急訂單的審查流程是否有簡化版本？如何確保即使走快速通道仍完成必要審查？",
            "合約審查的紀錄保存期限及存放位置為何？是否能快速調出任一訂單的審查紀錄？",
            "當顧客要求在合約執行中途發生變更時，重新審查的啟動條件與完成期限為何？",
            "合約審查是否涵蓋法規符合性的確認？法規主管機關要求的特殊文件（如上市許可）是否納入審查？",
        ],
        "expected_evidence": [
            "合約審查紀錄",
            "訂單確認紀錄",
        ],
        "audit_question_en": "Does the organization review the requirements related to product prior to commitment to supply product to the customer, and ensure that product requirements are defined and documented; contract or order requirements differing from those previously expressed are resolved; applicable regulatory requirements are met; user training identified in accordance with 7.2.1 is available or planned to be available; and the organization has the ability to meet the defined requirements?",
        "audit_question_ja": "組織は、顧客への製品供給のコミットメント前に、製品に関連する要求事項をレビューし、製品要求事項が定義され文書化されていること、以前に表明されたものと異なる契約又は注文の要求事項が解決されていること、適用規制要求事項が満たされること、7.2.1に従って識別された利用者訓練が利用可能又は利用可能になるよう計画されていること、並びに組織が定義された要求事項を満たす能力を有することを確実にしているか？",
        "audit_questions_en": [
            "Does the organization review the requirements related to product prior to commitment to supply product to the customer, and ensure that product requirements are defined and documented; contract or order requirements differing from those previously expressed are resolved; applicable regulatory requirements are met; user training identified in accordance with 7.2.1 is available or planned to be available; and the organization has the ability to meet the defined requirements?",
            "Is the contract review procedure documented? Does it cover requirement definition, differential clarification, regulatory compliance, user training readiness, and capability assessment?",
            "Per ISO 13485:2016 §7.2.2, does the organization review product-related requirements prior to commitment to supply product? Are review records maintained?",
            "When there is a deviation between contract and original requirement, how is the difference resolution mechanism? Are all differences documented and approved?",
            "How is the ability to meet customer requirements assessed? Do capability assessments include manufacturing capability, regulatory capability, and supply chain capability?",
            "When the contract review identifies unachievable customer requirements, what is the feedback mechanism? How is the customer negotiation managed?",
            "Is the contract review conducted before each order, or only for major contracts? How are small/repeat orders reviewed?",
        ],
        "audit_questions_ja": [
            "組織は、顧客への製品供給のコミットメント前に、製品に関連する要求事項をレビューし、製品要求事項が定義され文書化されていること、以前に表明されたものと異なる契約又は注文の要求事項が解決されていること、適用規制要求事項が満たされること、7.2.1に従って識別された利用者訓練が利用可能又は利用可能になるよう計画されていること、並びに組織が定義された要求事項を満たす能力を有することを確実にしているか？",
            "契約レビュー手順は文書化されているか？要求事項定義、差異明確化、規制適合、利用者訓練準備、能力評価を網羅しているか？",
            "ISO 13485:2016 §7.2.2に従い、組織は製品供給のコミットメント前に製品関連要求事項をレビューしているか？レビュー記録は維持されているか？",
            "契約と当初要求事項の間にずれがある場合、差異解決機構は何か？すべての差異は文書化され承認されているか？",
            "顧客要求事項を満たす能力はどのように評価されているか？能力評価は製造能力、規制能力、サプライチェーン能力を含むか？",
            "契約レビューで達成不可能な顧客要求事項が識別された場合、フィードバック機構は何か？顧客交渉はどのように管理されているか？",
            "契約レビューは各注文前に実施されるか、それとも主要契約のみか？少量／繰返し注文はどのようにレビューされるか？",
        ],
        "expected_evidence_en": [
            "Contract review records",
            "Difference resolution records (if applicable)",
        ],
        "expected_evidence_ja": [
            "契約レビュー記録",
            "差異解決記録（該当する場合）",
        ],
    },
    "7.2.3": {
        "title": "溝通",
        "title_en": "Communication",
        "title_ja": "コミュニケーション",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否對以下事項規劃並文件化與顧客溝通的安排："
            "產品資訊、詢問/合約或訂單處理（含修訂）、顧客回饋（含抱怨）、"
            "以及諮詢通知？"
        ),
        "audit_questions": [
            (
                "組織是否對以下事項規劃並文件化與顧客溝通的安排："
                "產品資訊、詢問/合約或訂單處理（含修訂）、顧客回饋（含抱怨）、"
                "以及諮詢通知？"
            ),
            "顧客溝通的記錄保存期限為何？當顧客提出口頭要求或修改時，如何確保書面化與追蹤？",
            "依 ISO 13485:2016 §7.2.3，組織是否建立並文件化與顧客溝通的安排，涵蓋產品資訊、詢問/合約/訂單處理（含修訂）、顧客回饋（含抱怨）及諮詢通知？",
            "諮詢通知（Advisory Notice）的發佈程序是否文件化？從決定發佈到實際送達顧客的時間流程為何？",
            "顧客投訴的初始響應時間要求為何？超時響應的升級機制為何？",
            "顧客溝通紀錄（如郵件、服務報告、電話記錄）如何系統化存管以支持後續查詢和法規審查？",
            "如何確保顧客收到最新的產品安全資訊（如使用說明、警示標籤更新）？溝通後的確認機制為何？",
        ],
        "expected_evidence": [
            "顧客溝通程序書",
            "顧客抱怨處理紀錄",
            "諮詢通知程序（如適用）",
        ],
        "audit_question_en": "Does the organization plan and document arrangements for communicating with customers in relation to product information; enquiries, contracts or order handling, including amendments; customer feedback, including customer complaints; and advisory notices?",
        "audit_question_ja": "組織は、製品情報、問合せ、契約又は注文処理（変更を含む）、顧客フィードバック（顧客苦情を含む）、並びに勧告通知に関して顧客とコミュニケーションを行うための取決めを計画し文書化しているか？",
        "audit_questions_en": [
            "Does the organization plan and document arrangements for communicating with customers in relation to product information; enquiries, contracts or order handling, including amendments; customer feedback, including customer complaints; and advisory notices?",
            "Is the customer communication mechanism comprehensive? Does it cover product information, enquiries, complaints, feedback, and advisory notices?",
            "Per ISO 13485:2016 §7.2.3, does the organization plan and document arrangements for customer communication, covering product information, enquiry/contract/order handling, customer feedback, and advisory notices?",
            "How are advisory notices issued to customers? Does it include product safety-related advisory notices, recall notices, etc.?",
            "How are customer complaints received, documented, acknowledged, and followed up? Is the complaint handling timeline tracked?",
            "How does the product information provided to customers (e.g., instructions for use, training materials) match the current product version? Does it meet regulatory requirements?",
            "When product changes impact customer use (e.g., specification changes, recalls), how is the customer notification mechanism? What is the response timeline requirement?",
        ],
        "audit_questions_ja": [
            "組織は、製品情報、問合せ、契約又は注文処理（変更を含む）、顧客フィードバック（顧客苦情を含む）、並びに勧告通知に関して顧客とコミュニケーションを行うための取決めを計画し文書化しているか？",
            "顧客コミュニケーション機構は包括的か？製品情報、問合せ、苦情、フィードバック、勧告通知を網羅しているか？",
            "ISO 13485:2016 §7.2.3に従い、組織は顧客コミュニケーションの取決めを計画し文書化しており、製品情報、問合せ／契約／注文処理、顧客フィードバック、勧告通知を網羅しているか？",
            "勧告通知は顧客にどのように発行されるか？製品安全関連の勧告通知、リコール通知等を含むか？",
            "顧客苦情はどのように受付、文書化、確認応答、フォローアップされているか？苦情処理期限は追跡されているか？",
            "顧客に提供される製品情報（使用説明書、訓練資料等）は現行製品バージョンとどのように整合しているか？規制要求事項を満たしているか？",
            "製品変更が顧客使用に影響する場合（仕様変更、リコール等）、顧客通知機構は？対応期限要求は？",
        ],
        "expected_evidence_en": [
            "Customer communication procedures",
            "Customer feedback records",
            "Advisory notice records (if applicable)",
        ],
        "expected_evidence_ja": [
            "顧客コミュニケーション手順書",
            "顧客フィードバック記録",
            "勧告通知記録（該当する場合）",
        ],
    },
    "7.3.1": {
        "title": "設計與開發規劃",
        "title_en": "Design and Development Planning",
        "title_ja": "設計・開発の計画",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否規劃並管制產品的設計與開發？"
            "設計開發規劃是否涵蓋階段、審查/驗證/確認活動、"
            "責任與權限、以及設計開發輸入輸出之間的追溯方法？"
        ),
        "audit_questions": [
            (
                "組織是否規劃並管制產品的設計與開發？"
                "設計開發規劃是否涵蓋階段、審查/驗證/確認活動、"
                "責任與權限、以及設計開發輸入輸出之間的追溯方法？"
            ),
            "設計開發規劃在執行過程中是否定期更新？計畫變更的審批流程為何？",
            "設計開發計劃中，各階段的驗收標準（Entry/Exit Criteria）是否明確定義？請提供最近一個產品的設計計劃。",
            "依 ISO 13485:2016 §7.3.1，設計與開發的職責分工是否文件化？設計輸入與輸出的追溯矩陣是否維持最新狀態？",
            "設計階段審查（Design Review）的參與者是否包含與審查階段無直接責任的人員？最近一次 Design Review 的參與紀錄為何？",
            "當設計開發時程或人員變更時，設計開發計劃如何更新？是否有版本控制？",
            "依 ISO 13485:2016 §7.3.1(c)，設計與開發各階段的責任與權限如何界定？是否以 RACI 或類似矩陣文件化？",
        ],
        "expected_evidence": [
            "設計開發計畫書",
            "設計開發階段定義",
            "設計開發團隊權責",
        ],
        "audit_question_en": "Does the organization plan and control the design and development of product, and as design and development progresses, maintain design and development plans, and update them, as appropriate?",
        "audit_question_ja": "組織は製品の設計・開発を計画し管理し、設計・開発の進捗に応じて、設計・開発計画を維持し、適切に更新しているか？",
        "audit_questions_en": [
            "Does the organization plan and control the design and development of product, and as design and development progresses, maintain design and development plans, and update them, as appropriate?",
            "Is the design and development plan complete? Does it cover stage division, responsibility assignment, review/verification/validation points, and risk management activities?",
            "Per ISO 13485:2016 §7.3.2, does the design plan include stages, review/verification/validation activities, responsibilities and authorities, resource requirements, and traceability?",
            "Is the design plan updated with design progress? How is it ensured that the plan keeps up with actual progress?",
            "Is the interface management of the design plan documented? Is cross-disciplinary (e.g., hardware, software, usability, biocompatibility) interface management defined?",
            "How is the design plan coordinated with the project schedule management? Does it use formal project management tools?",
            "When the design plan changes, how is the change management procedure? How are the impacts on subsequent stages assessed?",
        ],
        "audit_questions_ja": [
            "組織は製品の設計・開発を計画し管理し、設計・開発の進捗に応じて、設計・開発計画を維持し、適切に更新しているか？",
            "設計開発計画は完全か？段階区分、責任割当、レビュー／検証／妥当性確認ポイント、リスクマネジメント活動を網羅しているか？",
            "ISO 13485:2016 §7.3.2に従い、設計計画は段階、レビュー／検証／妥当性確認活動、責任及び権限、資源要求事項、トレーサビリティを含むか？",
            "設計計画は設計進捗とともに更新されているか？計画が実際の進捗に追随することをどのように確実にしているか？",
            "設計計画のインタフェース管理は文書化されているか？部門横断（ハードウェア、ソフトウェア、使いやすさ、生体適合性等）のインタフェース管理は定義されているか？",
            "設計計画とプロジェクトスケジュール管理はどのように調整されているか？正式なプロジェクト管理ツールは使用されているか？",
            "設計計画が変更される場合、変更管理手順は？後続段階への影響はどのように評価されているか？",
        ],
        "expected_evidence_en": [
            "Design and development plan",
            "Plan revision records",
            "Design responsibility matrix",
        ],
        "expected_evidence_ja": [
            "設計開発計画書",
            "計画改訂記録",
            "設計責任マトリクス",
        ],
    },
    "7.3.2": {
        "title": "設計與開發輸入",
        "title_en": "Design and Development Inputs",
        "title_ja": "設計・開発へのインプット",
        "audit_impact": "critical",
        "audit_question": (
            "設計輸入是否包含功能與性能要求、適用的法規要求、"
            "風險管理輸出、及適用的先前類似設計資訊？"
            "輸入是否被審查其充分性並經核准？"
        ),
        "audit_questions": [
            (
                "設計輸入是否包含功能與性能要求、適用的法規要求、"
                "風險管理輸出、及適用的先前類似設計資訊？"
                "輸入是否被審查其充分性並經核准？"
            ),
            "設計輸入的完整性如何驗證？若設計輸入在開發過程中發現缺失或矛盾，變更管理程序為何？",
            "設計輸入是否包含使用者需求（User Needs）並轉化為可驗證的設計要求？轉化過程的追溯性如何確保？",
            "依 ISO 13485:2016 §7.3.2，設計輸入是否包含來自先前類似設計的資訊？風險管理資訊是否作為設計輸入的一部分？",
            "當法規要求變更時（如 EU MDR 更新），設計輸入如何相應更新？是否有變更通知機制？",
            "設計輸入的核准流程為何？核准前是否進行充分性審查（包含完整性、模糊性的檢查）？",
            "如何確保所有適用的法規要求都已被識別並納入設計輸入？是否有法規查核清單？",
        ],
        "expected_evidence": [
            "設計輸入文件/規格書",
            "風險管理計畫",
            "法規要求清單",
        ],
        "audit_question_en": "Does the organization determine inputs relating to product requirements and maintain records? Do these inputs include functional, performance, usability and safety requirements; applicable regulatory requirements and standards; applicable output(s) of risk management; other information essential for design and development; and requirements for new designs or improvements?",
        "audit_question_ja": "組織は製品要求事項に関連するインプットを決定し記録を維持しているか？これらのインプットには、機能、性能、使いやすさ及び安全性の要求事項、適用される規制要求事項及び規格、リスクマネジメントの適用可能なアウトプット、設計・開発に不可欠なその他の情報、並びに新規設計又は改善の要求事項が含まれているか？",
        "audit_questions_en": [
            "Does the organization determine inputs relating to product requirements and maintain records? Do these inputs include functional, performance, usability and safety requirements; applicable regulatory requirements and standards; applicable output(s) of risk management; other information essential for design and development; and requirements for new designs or improvements?",
            "Is the design input completeness evaluation mechanism documented? Are functional, performance, usability, safety, regulatory, and risk management outputs all included?",
            "Per ISO 13485:2016 §7.3.3, do design inputs include functional, performance, usability, safety, regulatory, risk management output, and other essential information?",
            "How is the traceability between design inputs and clinical needs / user needs established? Is the traceability matrix maintained?",
            "Do the design inputs include specific requirements of applicable regulations (e.g., EU MDR Annex I, FDA 21 CFR Part 820)? How is regulatory gap analysis performed?",
            "How is the risk management output integrated into design inputs? Are the initial risk assessment results used as design input requirements?",
            "Are the design inputs reviewed and approved? How are incomplete, ambiguous, or conflicting requirements handled?",
        ],
        "audit_questions_ja": [
            "組織は製品要求事項に関連するインプットを決定し記録を維持しているか？これらのインプットには、機能、性能、使いやすさ及び安全性の要求事項、適用される規制要求事項及び規格、リスクマネジメントの適用可能なアウトプット、設計・開発に不可欠なその他の情報、並びに新規設計又は改善の要求事項が含まれているか？",
            "設計インプットの完全性評価機構は文書化されているか？機能、性能、使いやすさ、安全性、規制、リスクマネジメントアウトプットはすべて含まれているか？",
            "ISO 13485:2016 §7.3.3に従い、設計インプットには機能、性能、使いやすさ、安全性、規制、リスクマネジメントアウトプット、その他不可欠な情報が含まれているか？",
            "設計インプットと臨床ニーズ／利用者ニーズとの間のトレーサビリティはどのように確立されているか？トレーサビリティマトリクスは維持されているか？",
            "設計インプットには、適用法規制の具体的要求事項（EU MDR附属書I、FDA 21 CFR Part 820等）が含まれているか？規制ギャップ分析はどのように実施されているか？",
            "リスクマネジメントアウトプットはどのように設計インプットに統合されているか？初期リスク評価結果は設計インプット要求事項として使用されているか？",
            "設計インプットはレビューされ承認されているか？不完全、曖昧、又は相反する要求事項はどのように処理されているか？",
        ],
        "expected_evidence_en": [
            "Design input document",
            "Regulatory requirements/standards analysis",
            "Risk management plan/output",
        ],
        "expected_evidence_ja": [
            "設計インプット文書",
            "規制要求事項／規格分析",
            "リスクマネジメント計画／アウトプット",
        ],
    },
    "7.3.3": {
        "title": "設計與開發輸出",
        "title_en": "Design and Development Outputs",
        "title_ja": "設計・開発からのアウトプット",
        "audit_impact": "critical",
        "audit_question": (
            "設計輸出是否以能夠對照設計輸入進行驗證的形式提供？"
            "是否在發行前經核准？設計輸出是否滿足輸入要求、提供採購/生產/服務"
            "的適當資訊、包含或引用產品驗收準則、以及規定對安全和正常使用"
            "所必需的產品特性？"
        ),
        "audit_questions": [
            (
                "設計輸出是否以能夠對照設計輸入進行驗證的形式提供？"
                "是否在發行前經核准？設計輸出是否滿足輸入要求、提供採購/生產/服務"
                "的適當資訊、包含或引用產品驗收準則、以及規定對安全和正常使用"
                "所必需的產品特性？"
            ),
            "設計輸出與設計輸入的可追溯性如何建立與維持？設計輸出的發行管制程序為何？",
            "依 ISO 13485:2016 §7.3.3，設計輸出是否在發行前經核准，並提供採購、生產及服務的充分資訊？",
            "設計輸出文件（如圖面、規格書）的編號與版本管控規則為何？如何防止使用過期版本？",
            "設計輸出是否明確包含產品驗收準則以及對安全和正常使用必需的產品特性？如何驗證其完整性？",
            "設計輸出與製造文件（如作業指導書、BOM）的一致性如何確保？兩者不一致時的解決程序為何？",
            "軟體設計輸出（如韌體、應用程式）的版本控制與發行管理如何進行？是否與硬體設計輸出聯動？",
        ],
        "expected_evidence": [
            "設計輸出文件",
            "設計輸出審查/核准紀錄",
            "產品規格書",
        ],
        "audit_question_en": "Are the outputs of design and development documented and provided in a form suitable for verification against the design and development inputs? Do design and development outputs meet the input requirements; provide appropriate information for purchasing, production and service provision; contain or reference product acceptance criteria; and specify the characteristics of the product that are essential for its safe and proper use?",
        "audit_question_ja": "設計・開発のアウトプットは、設計・開発インプットに対する検証に適した形式で文書化され提供されているか？設計・開発アウトプットは、インプット要求事項を満たし、購買、生産及びサービス提供のための適切な情報を提供し、製品の合否判定基準を含む又は参照し、並びにその安全で適切な使用に不可欠な製品の特性を規定しているか？",
        "audit_questions_en": [
            "Are the outputs of design and development documented and provided in a form suitable for verification against the design and development inputs? Do design and development outputs meet the input requirements; provide appropriate information for purchasing, production and service provision; contain or reference product acceptance criteria; and specify the characteristics of the product that are essential for its safe and proper use?",
            "Is the design output completeness standard clear? Does it cover design specifications, manufacturing drawings, purchase specifications, test procedures, and acceptance criteria?",
            "Per ISO 13485:2016 §7.3.4, do design outputs meet design input requirements, and provide appropriate information for purchasing, production, and service provision?",
            "Do design outputs contain or reference product acceptance criteria? Are the acceptance criteria measurable and quantified?",
            "Do design outputs specify product characteristics essential for safe use? Are critical safety features clearly marked in design outputs?",
            "Are design outputs reviewed before approval? Does the approval include multi-disciplinary experts (quality, regulatory, manufacturing, clinical)?",
            "How is the version control of design outputs? When design outputs are updated, how is the downstream use (manufacturing, purchasing) notified?",
        ],
        "audit_questions_ja": [
            "設計・開発のアウトプットは、設計・開発インプットに対する検証に適した形式で文書化され提供されているか？設計・開発アウトプットは、インプット要求事項を満たし、購買、生産及びサービス提供のための適切な情報を提供し、製品の合否判定基準を含む又は参照し、並びにその安全で適切な使用に不可欠な製品の特性を規定しているか？",
            "設計アウトプットの完全性基準は明確か？設計仕様、製造図面、購買仕様、試験手順、合否判定基準を網羅しているか？",
            "ISO 13485:2016 §7.3.4に従い、設計アウトプットは設計インプット要求事項を満たし、購買、生産、サービス提供のための適切な情報を提供しているか？",
            "設計アウトプットは製品合否判定基準を含む又は参照しているか？合否判定基準は測定可能で定量化されているか？",
            "設計アウトプットは安全使用に不可欠な製品特性を規定しているか？重要安全特性は設計アウトプットで明確にマークされているか？",
            "設計アウトプットは承認前にレビューされているか？承認には多分野の専門家（品質、規制、製造、臨床）が含まれるか？",
            "設計アウトプットのバージョン管理は？設計アウトプット更新時、下流の使用部門（製造、購買）にはどのように通知されるか？",
        ],
        "expected_evidence_en": [
            "Design output document",
            "Product specification",
            "Acceptance criteria",
        ],
        "expected_evidence_ja": [
            "設計アウトプット文書",
            "製品仕様書",
            "合否判定基準",
        ],
    },
    "7.3.4": {
        "title": "設計與開發審查",
        "title_en": "Design and Development Review",
        "title_ja": "設計・開発のレビュー",
        "audit_impact": "critical",
        "audit_question": (
            "是否在適當階段依規劃安排對設計與開發進行系統化審查？"
            "審查是否評估設計結果滿足要求的能力、識別問題並提出必要措施？"
            "審查紀錄是否予以維持？"
        ),
        "audit_questions": [
            (
                "是否在適當階段依規劃安排對設計與開發進行系統化審查？"
                "審查是否評估設計結果滿足要求的能力、識別問題並提出必要措施？"
                "審查紀錄是否予以維持？"
            ),
            "設計審查的準入與完成準則為何？外部專家如何被納入設計審查過程？",
            "依 ISO 13485:2016 §7.3.4，設計與開發審查是否在適當階段依規劃安排進行，且包含與審查階段無直接責任的人員？",
            "設計審查發現的問題如何被追蹤至關閉？是否有開放項目清單（Open Action Items）的管理機制？",
            "每次設計審查的議程、出席名單與決議是否有完整紀錄？紀錄的核准流程為何？",
            "是否有設計審查檢查表（Checklist）以確保覆蓋所有關鍵審查點？清單的版本與適用範圍如何管理？",
            "設計審查的獨立審查人員（非直接開發團隊成員）資格要求為何？如何確保審查的客觀性？",
        ],
        "expected_evidence": [
            "設計審查會議紀錄",
            "設計審查檢查表",
            "設計審查行動項目追蹤",
        ],
        "audit_question_en": "Are design and development reviews conducted at suitable stages in accordance with planned arrangements to evaluate the ability of the results to meet requirements and to identify any problems and propose necessary actions? Do participants in such reviews include representatives of functions concerned with the design and development stage being reviewed, as well as other specialist personnel? Are records maintained?",
        "audit_question_ja": "設計・開発レビューは、結果が要求事項を満たす能力を評価し、いかなる問題も特定し必要な処置を提案するため、計画された取決めに従って適切な段階で実施されているか？そのようなレビューの参加者には、レビューされている設計・開発段階に関わる機能の代表者及びその他の専門要員が含まれているか？記録は維持されているか？",
        "audit_questions_en": [
            "Are design and development reviews conducted at suitable stages in accordance with planned arrangements to evaluate the ability of the results to meet requirements and to identify any problems and propose necessary actions? Do participants in such reviews include representatives of functions concerned with the design and development stage being reviewed, as well as other specialist personnel? Are records maintained?",
            "Are design review stage points clearly defined (concept, design, verification, validation, launch)? Is each review independent from daily design meetings?",
            "Per ISO 13485:2016 §7.3.5, are design reviews conducted at appropriate stages of the design? Does it include representatives from relevant functions and specialists?",
            "Do the design review participants include independent experts (i.e., not directly involved in the design)? What is the scope of independent expert opinions?",
            "Are the design review records complete? Do they include review inputs, discussion items, decisions, action items, participants, and review timeline?",
            "How are the results of design reviews fed back to subsequent stages? Is the closure of action items tracked?",
            "What are the criteria for passing a design review? When review issues are not resolved, are there clear procedures to prohibit proceeding to the next stage?",
        ],
        "audit_questions_ja": [
            "設計・開発レビューは、結果が要求事項を満たす能力を評価し、いかなる問題も特定し必要な処置を提案するため、計画された取決めに従って適切な段階で実施されているか？そのようなレビューの参加者には、レビューされている設計・開発段階に関わる機能の代表者及びその他の専門要員が含まれているか？記録は維持されているか？",
            "設計レビュー段階ポイントは明確に定義されているか（コンセプト、設計、検証、妥当性確認、市場投入）？各レビューは日常の設計会議と独立しているか？",
            "ISO 13485:2016 §7.3.5に従い、設計レビューは設計の適切な段階で実施されているか？関連機能の代表者及び専門要員を含むか？",
            "設計レビュー参加者には独立した専門家（すなわち設計に直接関与していない者）が含まれているか？独立専門家意見の範囲は何か？",
            "設計レビュー記録は完全か？レビューインプット、討議項目、決定事項、処置事項、参加者、レビュー期限を含むか？",
            "設計レビュー結果は後続段階にどのようにフィードバックされるか？処置事項の完結は追跡されているか？",
            "設計レビュー合格の基準は何か？レビュー問題が解決されない場合、次段階への移行を禁止する明確な手順はあるか？",
        ],
        "expected_evidence_en": [
            "Design review records",
            "Review participant list",
            "Action item tracking",
        ],
        "expected_evidence_ja": [
            "設計レビュー記録",
            "レビュー参加者一覧",
            "処置事項追跡記録",
        ],
    },
    "7.3.5": {
        "title": "設計與開發驗證",
        "title_en": "Design and Development Verification",
        "title_ja": "設計・開発の検証",
        "audit_impact": "critical",
        "audit_question": (
            "是否依規劃安排執行設計與開發驗證，以確保設計輸出滿足設計輸入要求？"
            "驗證結果及必要措施的紀錄是否予以維持？"
        ),
        "audit_questions": [
            (
                "是否依規劃安排執行設計與開發驗證，以確保設計輸出滿足設計輸入要求？"
                "驗證結果及必要措施的紀錄是否予以維持？"
            ),
            "設計驗證失敗時的處置流程為何？驗證方法的選擇依據是什麼？驗證結果是否充分覆蓋所有設計輸入要求？",
            "依 ISO 13485:2016 §7.3.5，設計驗證是否依規劃安排執行，確保設計輸出滿足設計輸入要求，且維持驗證結果及必要措施的紀錄？",
            "設計驗證計畫中，每項設計輸入要求是否有對應的驗證方法和驗收準則？追溯矩陣是否維持最新狀態？",
            "驗證測試所使用的設備是否經過校正，且測試環境是否符合規範要求？相關記錄如何保存？",
            "設計驗證報告是否在設計凍結前完成核准？未完成驗證時，是否有風險評估支持的例外處理流程？",
            "部分驗證測試（如加速老化測試）的預測模型依據為何？模型的合理性如何被評估和核准？",
        ],
        "expected_evidence": [
            "設計驗證計畫",
            "設計驗證報告/紀錄",
            "測試數據",
        ],
        "audit_question_en": "Is design and development verification performed in accordance with planned and documented arrangements to ensure that the design and development outputs have met the design and development input requirements? Does the organization document verification plans that include methods, acceptance criteria, and appropriate statistical techniques with rationale for sample size, when appropriate? Are records maintained?",
        "audit_question_ja": "設計・開発検証は、設計・開発アウトプットが設計・開発インプット要求事項を満たしていることを確実にするため、計画され文書化された取決めに従って実施されているか？組織は、方法、合否判定基準、並びに適切な場合にはサンプルサイズの根拠とともに統計的手法を含む検証計画を文書化しているか？記録は維持されているか？",
        "audit_questions_en": [
            "Is design and development verification performed in accordance with planned and documented arrangements to ensure that the design and development outputs have met the design and development input requirements? Does the organization document verification plans that include methods, acceptance criteria, and appropriate statistical techniques with rationale for sample size, when appropriate? Are records maintained?",
            "Is the design verification plan complete? Does it cover methods, acceptance criteria, sample size statistical basis, and qualifications of testing personnel?",
            "Per ISO 13485:2016 §7.3.6, does the design verification plan include methods, acceptance criteria, and sample size statistical rationale (when applicable)?",
            "How is the sample size of the verification determined? Are statistical techniques applied to ensure adequacy of the sample?",
            "How does design verification prove that each design output meets its design input? Is the traceability matrix updated?",
            "When verification fails, how is the failure investigated, recorded, and resolved? How are the impacts of failure on the subsequent design assessed?",
            "What are the qualifications and independence of the verification personnel? Do they include external laboratory testing, and if so, what are the qualifications of the external laboratory?",
        ],
        "audit_questions_ja": [
            "設計・開発検証は、設計・開発アウトプットが設計・開発インプット要求事項を満たしていることを確実にするため、計画され文書化された取決めに従って実施されているか？組織は、方法、合否判定基準、並びに適切な場合にはサンプルサイズの根拠とともに統計的手法を含む検証計画を文書化しているか？記録は維持されているか？",
            "設計検証計画は完全か？方法、合否判定基準、サンプルサイズの統計的根拠、試験要員の適格性を網羅しているか？",
            "ISO 13485:2016 §7.3.6に従い、設計検証計画には方法、合否判定基準、サンプルサイズの統計的根拠（該当する場合）が含まれているか？",
            "検証のサンプルサイズはどのように決定されているか？サンプルの妥当性を確実にするために統計的手法が適用されているか？",
            "設計検証は、各設計アウトプットがその設計インプットを満たすことをどのように証明しているか？トレーサビリティマトリクスは更新されているか？",
            "検証が失敗した場合、失敗はどのように調査、記録、解決されているか？失敗の後続設計への影響はどのように評価されているか？",
            "検証要員の適格性及び独立性は何か？外部試験所試験を含むか、その場合の外部試験所の資格は？",
        ],
        "expected_evidence_en": [
            "Design verification plan",
            "Verification test reports",
            "Statistical basis description",
        ],
        "expected_evidence_ja": [
            "設計検証計画書",
            "検証試験報告書",
            "統計的根拠説明書",
        ],
    },
    "7.3.6": {
        "title": "設計與開發確認",
        "title_en": "Design and Development Validation",
        "title_ja": "設計・開発のバリデーション",
        "audit_impact": "critical",
        "audit_question": (
            "是否依規劃安排執行設計與開發確認？"
            "確認是否在產品交付或實施之前完成（如可行）？"
            "確認是否包含臨床評估或效能評估（如適用法規要求）？"
        ),
        "audit_questions": [
            (
                "是否依規劃安排執行設計與開發確認？"
                "確認是否在產品交付或實施之前完成（如可行）？"
                "確認是否包含臨床評估或效能評估（如適用法規要求）？"
            ),
            "設計確認的樣本選取策略為何？若確認結果不符合要求，如何決定是否需要重新設計？",
            "依 ISO 13485:2016 §7.3.6，設計確認是否在首批量產或代表性樣品上執行，且在產品交付前完成（如可行）？",
            "臨床評估或效能評估（如適用）是否作為設計確認的一部分？評估計畫與報告是否符合法規要求？",
            "使用者需求測試（Usability/Human Factors Testing）是否包含在設計確認範圍內？測試方法與標準為何？",
            "設計確認的樣品是否代表量產條件？若使用工程樣品，差異性評估文件是否存在？",
            "設計確認的結論如何與設計輸入的使用者需求直接對應？確認報告的核准層級與流程為何？",
        ],
        "expected_evidence": [
            "設計確認計畫",
            "設計確認報告",
            "臨床評估報告（如適用）",
        ],
        "audit_question_en": "Is design and development validation performed in accordance with planned and documented arrangements to ensure that the resulting product is capable of meeting the requirements for the specified application or intended use? Does validation consider clinical evaluation or performance evaluation of the medical device, and include performance of validation activities on representative product? Are records maintained?",
        "audit_question_ja": "設計・開発の妥当性確認は、結果として得られる製品が規定された用途又は意図された使用に対する要求事項を満たす能力を有することを確実にするため、計画され文書化された取決めに従って実施されているか？妥当性確認は医療機器の臨床評価又は性能評価を考慮し、代表的な製品に対する妥当性確認活動の実施を含んでいるか？記録は維持されているか？",
        "audit_questions_en": [
            "Is design and development validation performed in accordance with planned and documented arrangements to ensure that the resulting product is capable of meeting the requirements for the specified application or intended use? Does validation consider clinical evaluation or performance evaluation of the medical device, and include performance of validation activities on representative product? Are records maintained?",
            "Does design validation include clinical evaluation / performance evaluation? How is the representative product sample for validation selected? Does it include final manufacturing condition samples?",
            "Per ISO 13485:2016 §7.3.7, does design validation demonstrate that the final product meets the specified application/intended use? Does it use representative product and include clinical evaluation?",
            "Is the clinical evaluation plan documented? Does it follow ISO 14155 (clinical investigation) or MEDDEV 2.7/1 rev4 (EU clinical evaluation)?",
            "Does the user interface / usability validation follow IEC 62366-1 (usability engineering for medical devices)?",
            "How is validation conducted before product release? What is the authorization procedure that validation must pass before release?",
            "Are the design validation records traceable to the design inputs and design outputs? Does the validation fully cover all intended uses?",
        ],
        "audit_questions_ja": [
            "設計・開発の妥当性確認は、結果として得られる製品が規定された用途又は意図された使用に対する要求事項を満たす能力を有することを確実にするため、計画され文書化された取決めに従って実施されているか？妥当性確認は医療機器の臨床評価又は性能評価を考慮し、代表的な製品に対する妥当性確認活動の実施を含んでいるか？記録は維持されているか？",
            "設計妥当性確認には臨床評価／性能評価が含まれているか？妥当性確認のための代表製品サンプルはどのように選定されているか？最終製造条件サンプルを含むか？",
            "ISO 13485:2016 §7.3.7に従い、設計妥当性確認は最終製品が規定された用途／意図された使用を満たすことを実証しているか？代表製品を使用し臨床評価を含んでいるか？",
            "臨床評価計画は文書化されているか？ISO 14155（臨床試験）又はMEDDEV 2.7/1 rev4（EU臨床評価）に準拠しているか？",
            "ユーザインタフェース／ユーザビリティ妥当性確認はIEC 62366-1（医療機器のユーザビリティエンジニアリング）に準拠しているか？",
            "製品出荷前の妥当性確認はどのように実施されているか？出荷前に妥当性確認が合格しなければならない承認手順は何か？",
            "設計妥当性確認記録は設計インプット及び設計アウトプットまで追跡可能か？妥当性確認はすべての意図された使用を完全に網羅しているか？",
        ],
        "expected_evidence_en": [
            "Design validation plan",
            "Clinical evaluation / performance evaluation report",
            "Usability validation report",
        ],
        "expected_evidence_ja": [
            "設計妥当性確認計画書",
            "臨床評価／性能評価報告書",
            "ユーザビリティ妥当性確認報告書",
        ],
    },
    "7.3.7": {
        "title": "設計與開發轉移",
        "title_en": "Design and Development Transfer",
        "title_ja": "設計・開発の移管",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立設計開發輸出轉移至製造的程序？"
            "轉移過程是否確保設計開發輸出在成為最終生產規格之前被驗證為適合製造？"
        ),
        "audit_questions": [
            (
                "組織是否建立設計開發輸出轉移至製造的程序？"
                "轉移過程是否確保設計開發輸出在成為最終生產規格之前被驗證為適合製造？"
            ),
            "設計轉移的完成準則如何定義？生產線首批量產後是否有正式的轉移完成確認？",
            "依 ISO 13485:2016 §7.3.7，設計開發輸出在成為最終生產規格前，是否驗證為適合製造且能重現地生產出符合要求的產品？",
            "設計轉移計畫中，設計端與製造端的職責如何界定？轉移過程中的問題如何記錄與解決？",
            "首批量產（First Article Inspection）的驗收準則是否與設計輸出一致？不一致的偏差如何處理？",
            "作業指導書（WI）和製造流程文件（Process Flow）是否在設計轉移過程中由工程師正式移交並驗證？",
            "設計轉移後，如有過程變更需求，其變更管制流程是否與設計開發變更管制流程有所區分？",
        ],
        "expected_evidence": [
            "設計轉移程序書",
            "設計轉移驗證紀錄",
        ],
        "audit_question_en": "Before transferring design and development outputs to manufacturing, does the organization document procedures for transferring design and development outputs, ensuring that design and development outputs are verified as suitable for manufacturing before becoming final production specifications, and that production capability can meet product requirements? Are records maintained?",
        "audit_question_ja": "設計・開発アウトプットを製造に移管する前に、組織は設計・開発アウトプットの移管手順を文書化し、設計・開発アウトプットが最終生産仕様となる前に製造に適していることが検証されており、生産能力が製品要求事項を満たすことができることを確実にしているか？記録は維持されているか？",
        "audit_questions_en": [
            "Before transferring design and development outputs to manufacturing, does the organization document procedures for transferring design and development outputs, ensuring that design and development outputs are verified as suitable for manufacturing before becoming final production specifications, and that production capability can meet product requirements? Are records maintained?",
            "Is the design transfer procedure documented? What is the specific mechanism to ensure manufacturing capability can meet product requirements?",
            "Per ISO 13485:2016 §7.3.8, before design output is transferred to manufacturing, is it verified as suitable for manufacturing, and is the manufacturing capability assessed?",
            "How is the manufacturing capability assessed (e.g., process Cp/Cpk, yield)? Are the assessment criteria documented?",
            "Does the design transfer include equipment/tools/fixtures design specifications? What is the equipment/tools preparation status check procedure?",
            "Does the design transfer include manufacturing operators' training completion? How is the operator skill sufficiency assessed?",
            "When design transfer-related issues occur, what is the escalation procedure? How is design-manufacturing interface alignment ensured?",
        ],
        "audit_questions_ja": [
            "設計・開発アウトプットを製造に移管する前に、組織は設計・開発アウトプットの移管手順を文書化し、設計・開発アウトプットが最終生産仕様となる前に製造に適していることが検証されており、生産能力が製品要求事項を満たすことができることを確実にしているか？記録は維持されているか？",
            "設計移管手順は文書化されているか？製造能力が製品要求事項を満たせることを確実にする具体的機構は何か？",
            "ISO 13485:2016 §7.3.8に従い、設計アウトプットが製造に移管される前に、製造適合性が検証され、製造能力が評価されているか？",
            "製造能力はどのように評価されているか（プロセスCp/Cpk、歩留り等）？評価基準は文書化されているか？",
            "設計移管には装置／治具／冶具の設計仕様は含まれるか？装置／治具準備状況チェック手順は何か？",
            "設計移管には製造作業者の訓練完了が含まれるか？作業者技能充足性はどのように評価されているか？",
            "設計移管関連の問題発生時、エスカレーション手順は？設計―製造インタフェースの整合性はどのように確実にされているか？",
        ],
        "expected_evidence_en": [
            "Design transfer procedure",
            "Manufacturing capability assessment records",
        ],
        "expected_evidence_ja": [
            "設計移管手順書",
            "製造能力評価記録",
        ],
    },
    "7.3.8": {
        "title": "設計與開發變更管制",
        "title_en": "Design and Development Changes Control",
        "title_ja": "設計・開発の変更管理",
        "audit_impact": "critical",
        "audit_question": (
            "設計與開發變更是否被識別？變更在實施前是否經審查、驗證、確認（適當時）"
            "及核准？變更審查是否包含評估變更對組成零件、已交付產品、"
            "風險管理輸出及產品實現過程的影響？"
        ),
        "audit_questions": [
            (
                "設計與開發變更是否被識別？變更在實施前是否經審查、驗證、確認（適當時）"
                "及核准？變更審查是否包含評估變更對組成零件、已交付產品、"
                "風險管理輸出及產品實現過程的影響？"
            ),
            "設計變更如何評估其對已上市產品的影響？是否有機制確保現場已安裝設備的設計變更資訊能及時傳達？",
            "依 ISO 13485:2016 §7.3.8，設計與開發變更在實施前是否識別、審查、驗證、確認（適當時）及核准，且評估對組成零件、已交付產品、風險管理及產品實現過程的影響？",
            "設計變更的分類（如重大/次要）標準為何？不同分類的審查流程和核准層級有何差異？",
            "設計變更是否觸發法規通報義務的評估（如補充申請或通知主管機關）？評估的決策流程為何？",
            "設計變更後的再驗證或再確認範疇如何決定？是否有評估矩陣（如影響評估表）輔助決策？",
            "所有設計變更記錄是否納入設計開發歷史檔案（DHF）？紀錄中是否包含變更原因、影響評估及核准人？",
        ],
        "expected_evidence": [
            "設計變更管制程序書",
            "設計變更申請/核准紀錄",
            "變更影響評估紀錄",
        ],
        "audit_question_en": "Does the organization document procedures to control design and development changes? Does the organization determine the significance of the change to function, performance, usability, safety, and applicable regulatory requirements for the medical device and its intended use? Are design and development changes identified? Before implementation, are the changes reviewed, verified, validated as appropriate, and approved? Does the review of design and development changes include evaluation of the effect of the changes on constituent parts and product in process or already delivered, inputs or outputs of risk management, and product realization processes? Are records maintained?",
        "audit_question_ja": "組織は設計・開発変更を管理する手順を文書化しているか？組織は、医療機器及びその意図された使用に対する機能、性能、使いやすさ、安全性、並びに適用規制要求事項への変更の重要性を決定しているか？設計・開発変更は識別されているか？実施前に、変更は適切にレビュー、検証、妥当性確認され承認されているか？設計・開発変更のレビューは、変更の構成部品及び仕掛中又は既に引渡された製品、リスクマネジメントのインプット又はアウトプット、並びに製品実現プロセスへの影響の評価を含んでいるか？記録は維持されているか？",
        "audit_questions_en": [
            "Does the organization document procedures to control design and development changes? Does the organization determine the significance of the change to function, performance, usability, safety, and applicable regulatory requirements for the medical device and its intended use? Are design and development changes identified? Before implementation, are the changes reviewed, verified, validated as appropriate, and approved? Does the review of design and development changes include evaluation of the effect of the changes on constituent parts and product in process or already delivered, inputs or outputs of risk management, and product realization processes? Are records maintained?",
            "Is the design change control procedure documented? Does the change significance assessment include function, performance, usability, safety, and regulatory requirements?",
            "Per ISO 13485:2016 §7.3.9, does the organization assess the significance of design changes and review, verify, validate, and approve changes before implementation?",
            "Does the design change review include assessment of impacts on components in manufacturing or already delivered products? How are retrospective actions implemented?",
            "Does the design change review include assessment of impacts on risk management input/output? Is the risk management file updated as required?",
            "Is the design change notification process to regulatory authorities (e.g., FDA 510(k), EU MDR Annex X) documented? What is the decision procedure for regulatory notification needs?",
            "Is the revision control of design change records traceable? How is the version management of the changed design outputs?",
        ],
        "audit_questions_ja": [
            "組織は設計・開発変更を管理する手順を文書化しているか？組織は、医療機器及びその意図された使用に対する機能、性能、使いやすさ、安全性、並びに適用規制要求事項への変更の重要性を決定しているか？設計・開発変更は識別されているか？実施前に、変更は適切にレビュー、検証、妥当性確認され承認されているか？設計・開発変更のレビューは、変更の構成部品及び仕掛中又は既に引渡された製品、リスクマネジメントのインプット又はアウトプット、並びに製品実現プロセスへの影響の評価を含んでいるか？記録は維持されているか？",
            "設計変更管理手順は文書化されているか？変更重要性評価には機能、性能、使いやすさ、安全性、規制要求事項が含まれているか？",
            "ISO 13485:2016 §7.3.9に従い、組織は設計変更の重要性を評価し、実施前に変更をレビュー、検証、妥当性確認、承認しているか？",
            "設計変更レビューには仕掛中部品又は既に引渡された製品への影響評価が含まれているか？遡及的処置はどのように実施されているか？",
            "設計変更レビューにはリスクマネジメントインプット／アウトプットへの影響評価が含まれているか？リスクマネジメントファイルは必要に応じて更新されているか？",
            "規制当局への設計変更通知プロセス（FDA 510(k)、EU MDR附属書X等）は文書化されているか？規制通知必要性の決定手順は何か？",
            "設計変更記録の版管理は追跡可能か？変更された設計アウトプットのバージョン管理はどのように行われているか？",
        ],
        "expected_evidence_en": [
            "Design change control procedure",
            "Design change request/approval records",
            "Change impact assessment records",
        ],
        "expected_evidence_ja": [
            "設計変更管理手順書",
            "設計変更申請／承認記録",
            "変更影響評価記録",
        ],
    },
    "7.3.9": {
        "title": "設計與開發檔案",
        "title_en": "Design History File",
        "title_ja": "設計履歴ファイル",
        "audit_impact": "major",
        "audit_question": (
            "組織是否為每一醫療器材類型或族維持設計與開發檔案？"
            "檔案是否包含或引用展示設計開發符合要求的紀錄，"
            "以及設計開發變更的紀錄？"
        ),
        "audit_questions": [
            (
                "組織是否為每一醫療器材類型或族維持設計與開發檔案？"
                "檔案是否包含或引用展示設計開發符合要求的紀錄，"
                "以及設計開發變更的紀錄？"
            ),
            "設計歷史檔案如何管理版本控制？外部設計夥伴的文件如何納入 DHF 管理？",
            "依 ISO 13485:2016 §7.3.9，組織是否為每一醫療器材類型或族維持設計開發檔案，包含或引用展示符合要求的紀錄及設計開發變更的紀錄？",
            "設計開發歷史檔案（DHF）的目錄索引是否完整且定期更新？如何確保所有相關文件均被正確引用？",
            "DHF 的存取控制與保護措施為何？如何防止未授權修改或刪除？",
            "DHF 的存放方式（電子或紙本）及備份策略為何？如何確保長期可讀性（如 20 年後仍可取得）？",
            "當產品停產或組織轉讓時，DHF 的移交或封存程序為何？是否有相關書面協議？",
        ],
        "expected_evidence": [
            "設計開發歷史檔案 (DHF)",
            "設計開發索引或目錄",
        ],
        "audit_question_en": "Does the organization maintain a design and development file for each medical device type or medical device family? Does the file include or reference records generated to demonstrate conformity to the requirements for design and development and records for design and development changes?",
        "audit_question_ja": "組織は医療機器の種類又は医療機器ファミリごとに設計・開発ファイルを維持しているか？ファイルは、設計・開発の要求事項への適合を実証するために作成された記録及び設計・開発変更の記録を含む又は参照しているか？",
        "audit_questions_en": [
            "Does the organization maintain a design and development file for each medical device type or medical device family? Does the file include or reference records generated to demonstrate conformity to the requirements for design and development and records for design and development changes?",
            "Is the design and development file maintained per device type/family? Is its completeness periodically reviewed?",
            "Per ISO 13485:2016 §7.3.10, does the design file include or reference records to demonstrate conformity to design and development requirements, including change records?",
            "Is the design file structure standardized (e.g., index table)? Is the relative position of each document clear?",
            "Is the design file access control implemented? Who has permission to view/edit? How is access for departed personnel revoked?",
            "How is the electronic design file management? Is there a complete backup and version history?",
            "How does the design file provide evidence of regulatory compliance? Can it be easily rearranged into a submission package for regulatory authorities?",
        ],
        "audit_questions_ja": [
            "組織は医療機器の種類又は医療機器ファミリごとに設計・開発ファイルを維持しているか？ファイルは、設計・開発の要求事項への適合を実証するために作成された記録及び設計・開発変更の記録を含む又は参照しているか？",
            "設計開発ファイルは機器種別／ファミリごとに維持されているか？その完全性は定期的にレビューされているか？",
            "ISO 13485:2016 §7.3.10に従い、設計ファイルには、変更記録を含む設計開発要求事項への適合を実証する記録が含まれる又は参照されているか？",
            "設計ファイルの構成は標準化されているか（索引表等）？各文書の相対位置は明確か？",
            "設計ファイルのアクセス制御は実施されているか？閲覧／編集の権限を持つのは誰か？離任者のアクセスはどのように取り消されているか？",
            "電子化された設計ファイルの管理はどのように行われているか？完全なバックアップ及び版履歴はあるか？",
            "設計ファイルは規制適合の証拠をどのように提供しているか？規制当局への提出パッケージに容易に再編できるか？",
        ],
        "expected_evidence_en": [
            "Design and development file index",
            "Design file completeness check records",
        ],
        "expected_evidence_ja": [
            "設計開発ファイル索引",
            "設計ファイル完全性確認記録",
        ],
    },
    "7.3.10": {
        "title": "設計與開發文件",
        "title_en": "Design and Development Documentation",
        "title_ja": "設計・開発の文書",
        "audit_impact": "major",
        "audit_question": ("組織是否維持每一醫療器材的設計規格文件？"),
        "audit_questions": [
            (
                "組織是否維持每一醫療器材的設計規格文件？"
            ),
            "設計規格文件的更新如何觸發相關生產文件的同步更新？設備主檔案的完整性審查頻率為何？",
            "依 ISO 13485:2016 §7.3.9，每一醫療器材是否維持完整的設計規格文件（Device Master Record），且包含所有必要的生產和品質保證資訊？",
            "設計規格文件（如 BOM、圖面）的核准流程是否有效防止非授權變更？文件發行前需要哪些部門會簽？",
            "設計規格文件的版本控制如何確保生產現場使用的永遠是最新版本？作廢版本的回收程序為何？",
            "設計規格文件與製造程序文件（如 SOP、作業指導書）之間的連結是否清晰？如何追蹤其一致性？",
            "設計規格文件的審查週期如何設定？定期審查的目的與觸發條件（如客訴、不合格趨勢）為何？",
        ],
        "expected_evidence": [
            "設計規格文件",
            "設備主檔案 (DMR)",
        ],
        "audit_question_en": "Does the organization maintain design specification documents (Device Master Record / DMR) for each medical device, containing all design outputs, manufacturing specifications, BOMs, drawings, and quality assurance requirements necessary for production?",
        "audit_question_ja": "組織は医療機器ごとに設計仕様文書（Device Master Record／DMR）を維持し、生産に必要なすべての設計アウトプット、製造仕様、BOM、図面、品質保証要求事項を含めているか？",
        "audit_questions_en": [
            "Does the organization maintain design specification documents (Device Master Record / DMR) for each medical device, containing all design outputs, manufacturing specifications, BOMs, drawings, and quality assurance requirements necessary for production?",
            "How are updates of the design specification documents (DMR) triggered to synchronize related production documents? What is the frequency of DMR completeness review?",
            "Per ISO 13485:2016 §7.3.10, does each medical device maintain a complete Device Master Record containing all necessary production and quality assurance information?",
            "Does the approval process of design specification documents (BOM, drawings) effectively prevent unauthorized changes? Which departments need to countersign before document release?",
            "How does version control of design specifications ensure that production lines always use the latest version? What is the recovery procedure for obsolete versions?",
            "Is the link between design specification documents and manufacturing process documents (SOP, work instructions) clear? How is their consistency tracked?",
            "How is the review cycle of design specification documents set? What is the purpose and trigger conditions (customer complaints, non-conformity trends, etc.) for periodic review?",
        ],
        "audit_questions_ja": [
            "組織は医療機器ごとに設計仕様文書（Device Master Record／DMR）を維持し、生産に必要なすべての設計アウトプット、製造仕様、BOM、図面、品質保証要求事項を含めているか？",
            "設計仕様文書（DMR）の更新は関連生産文書の同期更新をどのようにトリガーしているか？DMRの完全性レビュー頻度は？",
            "ISO 13485:2016 §7.3.10に従い、各医療機器は生産及び品質保証に必要なすべての情報を含む完全なDevice Master Recordを維持しているか？",
            "設計仕様文書（BOM、図面等）の承認プロセスは非認可変更を有効に防止しているか？文書発行前に会議決裁が必要な部門はどれか？",
            "設計仕様書の版管理は、生産現場が常に最新版を使用することをどのように確実にしているか？廃止版の回収手順は？",
            "設計仕様文書と製造プロセス文書（SOP、作業指示書）との連結は明確か？一貫性はどのように追跡されているか？",
            "設計仕様文書のレビュー周期はどのように設定されているか？定期レビューの目的及びトリガー条件（顧客苦情、不適合傾向等）は？",
        ],
        "expected_evidence_en": [
            "Design specification document",
            "Device Master Record (DMR)",
        ],
        "expected_evidence_ja": [
            "設計仕様文書",
            "Device Master Record（DMR）",
        ],
    },
    "7.4.1": {
        "title": "採購過程",
        "title_en": "Purchasing Process",
        "title_ja": "購買プロセス",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立採購產品符合規定要求的程序？"
            "是否建立供應商評估與選擇準則？"
            "是否基於供應商提供符合要求產品的能力進行評估？"
            "評估結果及任何必要措施的紀錄是否予以維持？"
        ),
        "audit_questions": [
            (
                "組織是否建立採購產品符合規定要求的程序？"
                "是否建立供應商評估與選擇準則？"
                "是否基於供應商提供符合要求產品的能力進行評估？"
                "評估結果及任何必要措施的紀錄是否予以維持？"
            ),
            "供應商分類（關鍵或非關鍵）的標準為何？不同類別供應商的管理強度差異為何？",
            "依 ISO 13485:2016 §7.4.1，組織是否根據供應商滿足採購要求的能力評估並選擇供應商，且維持評估結果及必要措施的紀錄？",
            "合格供應商清單（ASL）的維護責任人為誰？供應商的重新評估頻率與觸發條件（如品質問題）為何？",
            "新供應商導入的評估程序包含哪些要素（如問卷、現場稽核、樣品測試）？評估結果如何核准？",
            "供應商績效數據（如進料合格率、交貨準時率）如何定期彙整分析？績效不佳的供應商如何管理？",
            "當關鍵供應商無法繼續供貨時，備用供應商計畫是否存在？備用供應商的資格狀態如何維持？",
        ],
        "expected_evidence": [
            "採購管制程序書",
            "合格供應商清單 (ASL)",
            "供應商評估/稽核紀錄",
        ],
        "audit_question_en": "Does the organization document procedures to ensure that purchased product conforms to specified purchasing information? Does the organization establish criteria for the evaluation and selection of suppliers, which shall be proportionate to the risk associated with the medical device and based on the supplier's ability to meet purchasing requirements; the performance of the supplier; the effect of the purchased product on the quality of the medical device; and the risk associated with the medical device? Does the organization plan the monitoring and re-evaluation of suppliers?",
        "audit_question_ja": "組織は、購入製品が規定された購買情報に適合することを確実にする手順を文書化しているか？組織は、供給者の評価及び選定の基準を確立しているか。これは医療機器に関連するリスクに比例するものであり、購買要求事項を満たす供給者の能力、供給者の実績、購入製品が医療機器の品質に与える影響、及び医療機器に関連するリスクに基づくべきものである。組織は供給者の監視及び再評価を計画しているか？",
        "audit_questions_en": [
            "Does the organization document procedures to ensure that purchased product conforms to specified purchasing information? Does the organization establish criteria for the evaluation and selection of suppliers, which shall be proportionate to the risk associated with the medical device and based on the supplier's ability to meet purchasing requirements; the performance of the supplier; the effect of the purchased product on the quality of the medical device; and the risk associated with the medical device? Does the organization plan the monitoring and re-evaluation of suppliers?",
            "Is the supplier evaluation criteria risk-based? Does it cover the 4 dimensions of capability, performance, product impact, and device risk?",
            "Per ISO 13485:2016 §7.4.1, are supplier evaluation/selection criteria proportionate to medical device risk, and does it cover supplier capability, performance, product impact, and device risk?",
            "Is the supplier monitoring and re-evaluation cycle defined? Is the re-evaluation frequency for critical suppliers higher than that for ordinary suppliers?",
            "When a supplier fails to meet requirements, what are the disqualification and alternative supplier procedures? How is the impact on ongoing manufacturing operations controlled?",
            "Is the supplier quality agreement (Quality Agreement) established? Does it cover quality requirements, change notification, and audit rights?",
            "Are supplier audit records complete? Does the audit frequency match the risk classification? Are audit findings tracked to closure?",
        ],
        "audit_questions_ja": [
            "組織は、購入製品が規定された購買情報に適合することを確実にする手順を文書化しているか？組織は、供給者の評価及び選定の基準を確立しているか。これは医療機器に関連するリスクに比例するものであり、購買要求事項を満たす供給者の能力、供給者の実績、購入製品が医療機器の品質に与える影響、及び医療機器に関連するリスクに基づくべきものである。組織は供給者の監視及び再評価を計画しているか？",
            "供給者評価基準はリスクに基づいているか？能力、実績、製品影響、機器リスクの4つの側面を網羅しているか？",
            "ISO 13485:2016 §7.4.1に従い、供給者評価／選定基準は医療機器リスクに比例し、供給者能力、実績、製品影響、機器リスクを網羅しているか？",
            "供給者監視及び再評価周期は定義されているか？重要供給者の再評価頻度は一般供給者より高いか？",
            "供給者が要求事項を満たせない場合、資格取消及び代替供給者の手順は？進行中の製造業務への影響はどのように管理されているか？",
            "供給者品質協定書（Quality Agreement）は締結されているか？品質要求事項、変更通知、監査権を網羅しているか？",
            "供給者監査記録は完全か？監査頻度はリスク分類と整合しているか？監査所見は完結まで追跡されているか？",
        ],
        "expected_evidence_en": [
            "Supplier management procedure",
            "Qualified supplier list",
            "Supplier evaluation records",
        ],
        "expected_evidence_ja": [
            "供給者管理手順書",
            "認定供給者一覧",
            "供給者評価記録",
        ],
    },
    "7.4.2": {
        "title": "採購資訊",
        "title_en": "Purchasing Information",
        "title_ja": "購買情報",
        "audit_impact": "major",
        "audit_question": (
            "採購文件是否描述所採購的產品，適當時包含產品規格、"
            "驗收要求、供應商品質系統要求、以及書面協議中有關採購產品變更的通知？"
        ),
        "audit_questions": [
            (
                "採購文件是否描述所採購的產品，適當時包含產品規格、"
                "驗收要求、供應商品質系統要求、以及書面協議中有關採購產品變更的通知？"
            ),
            "採購文件的發行與變更管制程序為何？如何確保供應商收到最新版採購規格？",
            "依 ISO 13485:2016 §7.4.2，採購文件是否充分描述所採購的產品，包含規格、驗收要求及供應商品質系統要求？",
            "品質協議（Quality Agreement）的談判與更新程序為何？協議中是否涵蓋供應商變更通知義務？",
            "採購規格書的核准層級為何？技術規格與商務條款的核准是否分開進行？",
            "外來文件（如供應商提供的材料規格書）如何納入受控文件管理？版本更新時如何確保與採購規格的一致性？",
            "採購文件是否包含對採購產品的可追溯性要求？若有，供應商提供追溯資訊的格式和方式如何規定？",
        ],
        "expected_evidence": [
            "採購規格書/訂單",
            "品質協議 (Quality Agreement)",
        ],
        "audit_question_en": "Does purchasing information describe or reference the product to be purchased, including product specifications; requirements for product acceptance, procedures, processes, and equipment; requirements for qualification of supplier personnel; and quality management system requirements? Does the organization ensure the adequacy of specified purchasing requirements prior to their communication to the supplier?",
        "audit_question_ja": "購買情報は、購入される製品を、製品仕様、製品の受入要求事項、手順、プロセス、装置、供給者要員の適格性の要求事項、及び品質マネジメントシステムの要求事項を含めて記述又は参照しているか？組織は、供給者への伝達前に規定された購買要求事項の適切性を確実にしているか？",
        "audit_questions_en": [
            "Does purchasing information describe or reference the product to be purchased, including product specifications; requirements for product acceptance, procedures, processes, and equipment; requirements for qualification of supplier personnel; and quality management system requirements? Does the organization ensure the adequacy of specified purchasing requirements prior to their communication to the supplier?",
            "Are purchasing requirements explicitly documented? Does the purchase order specify product specifications, acceptance criteria, and regulatory/QMS requirements?",
            "Per ISO 13485:2016 §7.4.2, are purchasing requirements complete, including product specifications, acceptance requirements, procedure/process/equipment requirements, personnel qualifications, and QMS requirements?",
            "How are purchasing requirements approved and verified for adequacy before being communicated to suppliers?",
            "Are the traceability requirements in purchasing information (e.g., material batch traceability) documented? How is it verified?",
            "How are the purchasing requirements communicated for product/process changes? What is the supplier change notification procedure?",
            "Are the purchasing requirements for supplier personnel (e.g., special process operator qualifications) documented? Does the supplier need to submit qualification evidence?",
        ],
        "audit_questions_ja": [
            "購買情報は、購入される製品を、製品仕様、製品の受入要求事項、手順、プロセス、装置、供給者要員の適格性の要求事項、及び品質マネジメントシステムの要求事項を含めて記述又は参照しているか？組織は、供給者への伝達前に規定された購買要求事項の適切性を確実にしているか？",
            "購買要求事項は明示的に文書化されているか？注文書には製品仕様、合否判定基準、規制／品質マネジメントシステム要求事項が規定されているか？",
            "ISO 13485:2016 §7.4.2に従い、購買要求事項は完全で、製品仕様、受入要求事項、手順／プロセス／装置要求事項、要員適格性、品質マネジメントシステム要求事項を含むか？",
            "購買要求事項は供給者への伝達前にどのように承認され、適切性が検証されているか？",
            "購買情報におけるトレーサビリティ要求事項（資材ロットトレーサビリティ等）は文書化されているか？どのように検証されているか？",
            "製品／プロセス変更時の購買要求事項はどのように伝達されているか？供給者の変更通知手順は？",
            "供給者要員（特殊プロセス作業者資格等）の購買要求事項は文書化されているか？供給者は資格証拠の提出を要求されているか？",
        ],
        "expected_evidence_en": [
            "Purchase order/contract",
            "Purchase requirements specification",
        ],
        "expected_evidence_ja": [
            "注文書／契約書",
            "購買要求事項仕様書",
        ],
    },
    "7.4.3": {
        "title": "採購產品之驗證",
        "title_en": "Verification of Purchased Products",
        "title_ja": "購買製品の検証",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立並實施所需的檢驗或其他活動，以確保採購產品滿足規定的採購要求？"
        ),
        "audit_questions": [
            (
                "組織是否建立並實施所需的檢驗或其他活動，以確保採購產品滿足規定的採購要求？"
            ),
            "進料檢驗豁免的條件與管控措施為何？進料不合格率的趨勢如何監測與應對？",
            "依 ISO 13485:2016 §7.4.3，組織是否建立並實施進料檢驗或其他活動，確保採購產品滿足規定要求？",
            "進料檢驗計畫（包含抽樣方式、頻率和驗收準則）的依據為何？抽樣計畫是否符合統計原理？",
            "當進料不合格品無法及時處理時，其隔離、標示和後續評估程序為何？是否有緊急豁免使用的管制流程？",
            "組織是否在供應商現場進行驗證活動（如供應商稽核或現場監督）？相關計畫和紀錄是否維持？",
            "進料不合格的根本原因分析結果是否回饋給供應商？供應商的 CAPA 如何追蹤和驗證有效性？",
        ],
        "expected_evidence": [
            "進料檢驗程序書",
            "進料檢驗紀錄",
        ],
        "audit_question_en": "Does the organization establish and implement the inspection or other activities necessary for ensuring that purchased product meets specified purchasing requirements? The extent of verification activities shall be based on the supplier evaluation results and proportionate to the risks associated with the purchased product. When the organization becomes aware of any changes to the purchased product, does the organization determine whether these changes affect the product realization process or the medical device? Are records maintained?",
        "audit_question_ja": "組織は、購入製品が規定された購買要求事項を満たすことを確実にするために必要な検査又はその他の活動を確立し実施しているか？検証活動の程度は、供給者の評価結果に基づき、購入製品に関連するリスクに比例するものとする。組織が購入製品への何らかの変更を知った場合、組織はこれらの変更が製品実現プロセス又は医療機器に影響するかどうかを決定しているか？記録は維持されているか？",
        "audit_questions_en": [
            "Does the organization establish and implement the inspection or other activities necessary for ensuring that purchased product meets specified purchasing requirements? The extent of verification activities shall be based on the supplier evaluation results and proportionate to the risks associated with the purchased product. When the organization becomes aware of any changes to the purchased product, does the organization determine whether these changes affect the product realization process or the medical device? Are records maintained?",
            "Is the extent of incoming inspection based on supplier evaluation results and product risk? How are the items and sampling plan for inspection determined?",
            "Per ISO 13485:2016 §7.4.3, is the incoming inspection extent proportionate to supplier evaluation results and purchase product risk?",
            "When the supplier notifies a change to the purchased product, how is the change impact assessed? Are records of such assessments maintained?",
            "Are the incoming inspection records complete? Do they include inspection items, methods, results, acceptance/rejection decisions, and inspector names?",
            "When the incoming inspection rejects material, how is the handling procedure? How is the process to return, request rework, or conditionally accept?",
            "Is there a reduced-inspection or skip-lot procedure for certified suppliers? Are the conditions for skip-lot strictly controlled?",
        ],
        "audit_questions_ja": [
            "組織は、購入製品が規定された購買要求事項を満たすことを確実にするために必要な検査又はその他の活動を確立し実施しているか？検証活動の程度は、供給者の評価結果に基づき、購入製品に関連するリスクに比例するものとする。組織が購入製品への何らかの変更を知った場合、組織はこれらの変更が製品実現プロセス又は医療機器に影響するかどうかを決定しているか？記録は維持されているか？",
            "受入検査の程度は供給者評価結果及び製品リスクに基づいているか？検査項目及びサンプリング計画はどのように決定されているか？",
            "ISO 13485:2016 §7.4.3に従い、受入検査の程度は供給者評価結果及び購入製品リスクに比例しているか？",
            "供給者が購入製品の変更を通知した場合、変更影響はどのように評価されているか？そのような評価の記録は維持されているか？",
            "受入検査記録は完全か？検査項目、方法、結果、合否判定、検査員名を含むか？",
            "受入検査で不合格となった資材の場合、処理手順は？返品、手直し依頼、又は条件付き受入のプロセスは？",
            "認定供給者に対する検査軽減又はロット抜取省略手順はあるか？ロット抜取省略の条件は厳密に管理されているか？",
        ],
        "expected_evidence_en": [
            "Incoming inspection records",
            "Supplier change notification records (if applicable)",
        ],
        "expected_evidence_ja": [
            "受入検査記録",
            "供給者変更通知記録（該当する場合）",
        ],
    },
    "7.5.1": {
        "title": "生產與服務提供之管制",
        "title_en": "Control of Production and Service Provision",
        "title_ja": "製造及びサービス提供の管理",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否在管制條件下規劃並執行生產與服務提供？"
            "管制條件是否包含產品特性描述的文件化程序與要求、"
            "監督與量測設備、適當的生產基礎設施與工作環境、"
            "以及已界定的標示與包裝作業？"
        ),
        "audit_questions": [
            (
                "組織是否在管制條件下規劃並執行生產與服務提供？"
                "管制條件是否包含產品特性描述的文件化程序與要求、"
                "監督與量測設備、適當的生產基礎設施與工作環境、"
                "以及已界定的標示與包裝作業？"
            ),
            "生產記錄的完整性如何在生產過程中即時確保？當生產偏離 SOP 時，偏差報告與處理程序為何？",
            "關鍵製造過程是否進行過製程驗證（Process Validation）？最近一次驗證是何時？結果如何？",
            "依 ISO 13485:2016 §7.5.1，過程中的監督與量測活動是否文件化？不合格品如何在線上被識別與隔離？",
            "生產批次記錄（Batch Record）是否完整追溯每個批次的人員、設備、材料、環境？最近一次稽核發現哪些批次記錄缺失？",
            "機器設備的預防保養計劃是否存在且按期執行？保養紀錄是否維持？",
            "依 ISO 13485:2016 §7.5.1(f)，產品放行的核准標準是否文件化？誰有最終放行權限？",
        ],
        "expected_evidence": [
            "生產管制程序書",
            "作業指導書 (SOP/WI)",
            "批次紀錄 (Batch Record)",
        ],
        "audit_question_en": "Does the organization plan and carry out production and service provision under controlled conditions? As appropriate, such conditions include documented procedures and methods for the control of production; qualification of infrastructure; implementation of monitoring and measurement; the availability and use of monitoring and measuring equipment; implementation of defined operations for labelling and packaging; and implementation of product release, delivery, and post-delivery activities?",
        "audit_question_ja": "組織は管理された条件の下で生産及びサービス提供を計画し実施しているか？適切な場合には、そのような条件には、生産管理のための文書化された手順及び方法、インフラストラクチャの適格性確認、監視及び測定の実施、監視及び測定装置の利用可能性及び使用、ラベル及び包装に関する定義された操作の実施、並びに製品の出荷、引渡し、及び引渡し後の活動の実施が含まれる。",
        "audit_questions_en": [
            "Does the organization plan and carry out production and service provision under controlled conditions? As appropriate, such conditions include documented procedures and methods for the control of production; qualification of infrastructure; implementation of monitoring and measurement; the availability and use of monitoring and measuring equipment; implementation of defined operations for labelling and packaging; and implementation of product release, delivery, and post-delivery activities?",
            "Are production operating procedures (SOPs) complete? Are operating procedures at all critical process stages documented?",
            "Per ISO 13485:2016 §7.5.1, is production conducted under controlled conditions? Are the 6 essential elements (procedures, infrastructure, monitoring, equipment, labelling/packaging, release) implemented?",
            "Is the in-process monitoring plan documented? Are monitoring points/frequency based on product risk?",
            "Are production records preserved according to the medical device file requirements? Can they be traced back to specific batches/units?",
            "What is the calibration status monitoring of production equipment (e.g., test instruments)? What is the handling when out-of-calibration is detected?",
            "How are labelling/packaging operations controlled? How is the labelling correctness confirmed to prevent product mix-up?",
        ],
        "audit_questions_ja": [
            "組織は管理された条件の下で生産及びサービス提供を計画し実施しているか？適切な場合には、そのような条件には、生産管理のための文書化された手順及び方法、インフラストラクチャの適格性確認、監視及び測定の実施、監視及び測定装置の利用可能性及び使用、ラベル及び包装に関する定義された操作の実施、並びに製品の出荷、引渡し、及び引渡し後の活動の実施が含まれる。",
            "生産標準作業手順書（SOP）は完全か？すべての重要プロセス段階の作業手順は文書化されているか？",
            "ISO 13485:2016 §7.5.1に従い、生産は管理された条件下で実施されているか？6つの必須要素（手順、インフラストラクチャ、監視、装置、ラベル／包装、出荷）は実施されているか？",
            "工程内監視計画は文書化されているか？監視ポイント／頻度は製品リスクに基づいているか？",
            "生産記録は医療機器ファイル要求事項に従って保存されているか？特定のロット／ユニットまで追跡可能か？",
            "製造装置（試験機器等）の校正状態監視はどのように行われているか？校正外検出時の処理は？",
            "ラベル／包装操作はどのように管理されているか？ラベリングの正確性はどのように確認され、製品混同を防いでいるか？",
        ],
        "expected_evidence_en": [
            "Production operating procedures (SOPs)",
            "In-process monitoring records",
            "Production batch record",
        ],
        "expected_evidence_ja": [
            "生産標準作業手順書（SOP）",
            "工程内監視記録",
            "生産バッチ記録",
        ],
    },
    "7.5.2": {
        "title": "產品之潔淨",
        "title_en": "Cleanliness of Product",
        "title_ja": "製品の清潔性",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否將產品清潔或污染管制的要求文件化？"
            "如果產品在滅菌前或使用前需要清潔，或是清潔劑的殘留可能影響產品效能，"
            "是否有適當的清潔驗證？"
        ),
        "audit_questions": [
            (
                "組織是否將產品清潔或污染管制的要求文件化？"
                "如果產品在滅菌前或使用前需要清潔，或是清潔劑的殘留可能影響產品效能，"
                "是否有適當的清潔驗證？"
            ),
            "清潔驗證的有效期限如何確定？何種情況下需要重新進行清潔驗證？",
            "依 ISO 13485:2016 §7.5.2，組織是否依適當情況將產品清潔要求文件化，並確保清潔劑殘留不影響產品安全性或效能？",
            "清潔程序的關鍵參數（如清潔劑濃度、時間、溫度）是否被識別，且監測方式是否文件化？",
            "清潔驗證的方法（如 TOC、目視檢查、生物指示劑）如何選定？驗收準則的科學依據為何？",
            "產品清潔作業人員的訓練內容與資格要求為何？訓練記錄如何維持？",
            "清潔劑或清潔方法更換時，是否需要重新進行驗證？評估和核准程序為何？",
        ],
        "expected_evidence": [
            "產品清潔程序書",
            "清潔驗證紀錄（如適用）",
        ],
        "audit_question_en": "Does the organization establish documented requirements for cleanliness of product or contamination control of product where product is cleaned by the organization prior to sterilization or its use; is supplied non-sterile to be subjected to a cleaning process prior to sterilization or its use; is supplied to be used non-sterile and its cleanliness is of significance in use; is to have process agents removed from it during manufacture?",
        "audit_question_ja": "組織は、製品が滅菌又は使用前に組織によって洗浄される場合、非滅菌で供給され滅菌又は使用前に洗浄プロセスを受ける場合、非滅菌で供給され使用時に清浄度が重要である場合、又は製造中にプロセス剤が製品から除去される場合、製品の清浄度又は製品の汚染管理に関する文書化された要求事項を確立しているか？",
        "audit_questions_en": [
            "Does the organization establish documented requirements for cleanliness of product or contamination control of product where product is cleaned by the organization prior to sterilization or its use; is supplied non-sterile to be subjected to a cleaning process prior to sterilization or its use; is supplied to be used non-sterile and its cleanliness is of significance in use; is to have process agents removed from it during manufacture?",
            "Are cleanliness / contamination control requirements documented? Are cleanliness testing methods and acceptance criteria defined?",
            "Per ISO 13485:2016 §7.5.2, are cleanliness requirements established? Do they cover the 4 scenarios (cleaned before sterilization/use, cleaned prior to use, cleanliness significant in use, process agent removal)?",
            "Are cleaning validation records complete? Is the cleaning validation periodically reviewed and updated for changes in products or processes?",
            "Is the monitoring of residue removal (e.g., process agents) validated? What is the acceptance criteria for residue levels?",
            "If cleaning operations are outsourced, how is the supplier's cleaning capability assessed? Is the outsourced cleaning validation kept on file?",
            "How is the cleanliness testing result of each batch recorded? When cleanliness fails, how is the handling procedure?",
        ],
        "audit_questions_ja": [
            "組織は、製品が滅菌又は使用前に組織によって洗浄される場合、非滅菌で供給され滅菌又は使用前に洗浄プロセスを受ける場合、非滅菌で供給され使用時に清浄度が重要である場合、又は製造中にプロセス剤が製品から除去される場合、製品の清浄度又は製品の汚染管理に関する文書化された要求事項を確立しているか？",
            "清浄度／汚染管理要求事項は文書化されているか？清浄度試験方法及び合否判定基準は定義されているか？",
            "ISO 13485:2016 §7.5.2に従い、清浄度要求事項は確立されているか？4つのシナリオ（滅菌／使用前洗浄、使用前洗浄、使用時清浄度が重要、プロセス剤除去）を網羅しているか？",
            "洗浄バリデーション記録は完全か？洗浄バリデーションは製品又はプロセスの変更に対して定期的にレビュー・更新されているか？",
            "残留物除去（プロセス剤等）の監視はバリデーションされているか？残留物水準の合否判定基準は？",
            "洗浄操作が外部委託されている場合、供給者の洗浄能力はどのように評価されているか？外部委託洗浄バリデーションはファイルに保管されているか？",
            "各ロットの清浄度試験結果はどのように記録されているか？清浄度が不合格の場合、処理手順は？",
        ],
        "expected_evidence_en": [
            "Cleanliness requirements documents",
            "Cleaning validation records (if applicable)",
        ],
        "expected_evidence_ja": [
            "清浄度要求事項文書",
            "洗浄バリデーション記録（該当する場合）",
        ],
    },
    "7.5.3": {
        "title": "安裝活動",
        "title_en": "Installation Activities",
        "title_ja": "据付活動",
        "audit_impact": "major",
        "audit_question": (
            "如適用，組織是否將醫療器材安裝與安裝驗證的驗收準則文件化？"
            "如果安裝由組織或其授權代理以外的人員執行，"
            "是否提供安裝與驗證要求的文件？"
        ),
        "audit_questions": [
            (
                "如適用，組織是否將醫療器材安裝與安裝驗證的驗收準則文件化？"
                "如果安裝由組織或其授權代理以外的人員執行，"
                "是否提供安裝與驗證要求的文件？"
            ),
            "安裝服務人員的資格認定程序為何？遠端或第三方安裝的品質管制措施為何？",
            "依 ISO 13485:2016 §7.5.3，組織是否將醫療器材的安裝要求及安裝驗收準則文件化，並確保安裝人員取得所需文件？",
            "安裝驗證（Installation Qualification, IQ）的檢查清單是否涵蓋所有關鍵安裝參數？未通過 IQ 時的處置程序為何？",
            "客戶自行安裝時，組織如何確保安裝品質？是否有遠端技術支援或安裝驗證確認機制？",
            "安裝完成後，設備是否需要進行性能測試（OQ/PQ）才能正式使用？相關程序和紀錄如何管理？",
            "安裝紀錄的保存位置與期限為何？如何快速調取特定設備的安裝歷史記錄以支持故障分析？",
        ],
        "expected_evidence": [
            "安裝程序書（如適用）",
            "安裝驗證紀錄（如適用）",
        ],
        "audit_question_en": "Does the organization document requirements for installation of the medical device and acceptance criteria for verification of installation, as appropriate? If the agreed customer requirements allow installation of the medical device to be performed other than by the organization or its authorized supplier, does the organization provide documented requirements for installation and verification? Are records of installation performed by the organization or its authorized supplier including acceptance criteria maintained?",
        "audit_question_ja": "組織は、適切な場合、医療機器の据付の要求事項及び据付検証の合否判定基準を文書化しているか？合意された顧客要求事項が、医療機器の据付を組織又はその認定供給者以外の者が行うことを認めている場合、組織は据付及び検証のための文書化された要求事項を提供しているか？組織又はその認定供給者によって実施された据付の記録（合否判定基準を含む）は維持されているか？",
        "audit_questions_en": [
            "Does the organization document requirements for installation of the medical device and acceptance criteria for verification of installation, as appropriate? If the agreed customer requirements allow installation of the medical device to be performed other than by the organization or its authorized supplier, does the organization provide documented requirements for installation and verification? Are records of installation performed by the organization or its authorized supplier including acceptance criteria maintained?",
            "Are installation requirements and verification acceptance criteria documented? Are the completeness of records for installation performed by the organization or authorized supplier ensured?",
            "Per ISO 13485:2016 §7.5.3, are installation requirements and verification acceptance criteria documented (if applicable)?",
            "Are the installation SOPs/checklists available for customer-performed installation? Are they in a format understandable by the customer?",
            "How is the qualification of installation personnel confirmed? Does the organization or its authorized supplier have training/certification mechanisms for installation personnel?",
            "How are the installation verification records submitted back to the organization? Are the records traceable to specific installation locations and units?",
            "How is the adequacy of installation verification demonstrated in cases where customers install the device themselves? Are there customer-installation verification records?",
        ],
        "audit_questions_ja": [
            "組織は、適切な場合、医療機器の据付の要求事項及び据付検証の合否判定基準を文書化しているか？合意された顧客要求事項が、医療機器の据付を組織又はその認定供給者以外の者が行うことを認めている場合、組織は据付及び検証のための文書化された要求事項を提供しているか？組織又はその認定供給者によって実施された据付の記録（合否判定基準を含む）は維持されているか？",
            "据付要求事項及び検証合否判定基準は文書化されているか？組織又は認定供給者が実施した据付記録の完全性は確実にされているか？",
            "ISO 13485:2016 §7.5.3に従い、据付要求事項及び検証合否判定基準は文書化されているか（該当する場合）？",
            "顧客が実施する据付のための据付SOP／チェックリストは提供されているか？顧客が理解可能な形式か？",
            "据付要員の適格性はどのように確認されているか？組織又は認定供給者は据付要員の訓練／認定機構を有しているか？",
            "据付検証記録はどのように組織に返送されているか？記録は特定の据付場所及びユニットまで追跡可能か？",
            "顧客が自ら機器を据え付ける場合、据付検証の適切性はどのように実証されているか？顧客据付検証記録はあるか？",
        ],
        "expected_evidence_en": [
            "Installation requirements documents",
            "Installation records/verification records (if applicable)",
        ],
        "expected_evidence_ja": [
            "据付要求事項文書",
            "据付記録／検証記録（該当する場合）",
        ],
    },
    "7.5.4": {
        "title": "服務活動",
        "title_en": "Servicing Activities",
        "title_ja": "サービス活動",
        "audit_impact": "major",
        "audit_question": (
            "如果服務是規定的要求，組織是否將服務活動的執行與驗證程序、"
            "參考量測程序、以及服務報告的分析文件化？"
        ),
        "audit_questions": [
            (
                "如果服務是規定的要求，組織是否將服務活動的執行與驗證程序、"
                "參考量測程序、以及服務報告的分析文件化？"
            ),
            "服務報告的分析結果如何回饋至設計改善或預防措施系統？服務紀錄的保存期限是否符合法規要求？",
            "依 ISO 13485:2016 §7.5.4，組織是否將服務活動的程序文件化，包含服務紀錄的分析以確定服務活動是否構成客訴或應通報的不良事件？",
            "服務工程師如何被培訓識別潛在的安全問題或法規通報義務？識別後的上報程序為何？",
            "服務備品的管理方式為何？備品是否具有品質狀態標識，且其品質紀錄如何維持？",
            "服務活動的服務參考量測程序（如性能驗收測試）是否文件化，且使用的量測設備是否已校正？",
            "客戶端的服務完成後，服務報告是否由客戶簽認？服務報告的數據如何彙整分析以識別系統性問題？",
        ],
        "expected_evidence": [
            "服務程序書（如適用）",
            "服務紀錄/報告（如適用）",
        ],
        "audit_question_en": "Does the organization document requirements for servicing of the medical device and its acceptance criteria for verification of servicing, as appropriate? Does the organization analyse records of servicing activities carried out by the organization or its authorized supplier to determine if the information is to be handled as a complaint, and as input to the improvement process? Are records of servicing activities carried out by the organization or its authorized supplier maintained?",
        "audit_question_ja": "組織は、適切な場合、医療機器のサービスの要求事項及びサービス検証のための合否判定基準を文書化しているか？組織は、組織又はその認定供給者により実施されたサービス活動の記録を分析し、情報を苦情として扱うべきか、また改善プロセスへのインプットとして扱うべきかを決定しているか？組織又はその認定供給者により実施されたサービス活動の記録は維持されているか？",
        "audit_questions_en": [
            "Does the organization document requirements for servicing of the medical device and its acceptance criteria for verification of servicing, as appropriate? Does the organization analyse records of servicing activities carried out by the organization or its authorized supplier to determine if the information is to be handled as a complaint, and as input to the improvement process? Are records of servicing activities carried out by the organization or its authorized supplier maintained?",
            "Are servicing procedures and verification criteria documented? Are servicing records analyzed to determine whether they should be handled as complaints?",
            "Per ISO 13485:2016 §7.5.4, does the organization document the servicing requirements and servicing verification acceptance criteria (if applicable)?",
            "What is the criteria for determining that servicing records should be handled as complaints? Is the determination procedure documented?",
            "How is the qualification of servicing personnel confirmed? Does the servicing training include medical device safety, regulatory requirements, and documentation?",
            "How are servicing records submitted back to the organization? What is the retention period of the records?",
            "How are the outputs of servicing record analysis fed back into the product improvement process? Can they drive design improvements or CAPA?",
        ],
        "audit_questions_ja": [
            "組織は、適切な場合、医療機器のサービスの要求事項及びサービス検証のための合否判定基準を文書化しているか？組織は、組織又はその認定供給者により実施されたサービス活動の記録を分析し、情報を苦情として扱うべきか、また改善プロセスへのインプットとして扱うべきかを決定しているか？組織又はその認定供給者により実施されたサービス活動の記録は維持されているか？",
            "サービス手順及び検証基準は文書化されているか？サービス記録は苦情として扱うべきかを決定するために分析されているか？",
            "ISO 13485:2016 §7.5.4に従い、組織はサービス要求事項及びサービス検証合否判定基準を文書化しているか（該当する場合）？",
            "サービス記録を苦情として扱うべきかを決定する基準は何か？決定手順は文書化されているか？",
            "サービス要員の適格性はどのように確認されているか？サービス訓練には医療機器の安全性、規制要求事項、文書化が含まれているか？",
            "サービス記録はどのように組織に返送されているか？記録の保管期間は？",
            "サービス記録分析のアウトプットはどのように製品改善プロセスにフィードバックされているか？設計改善又はCAPAを推進できるか？",
        ],
        "expected_evidence_en": [
            "Servicing requirements documents",
            "Servicing records (if applicable)",
        ],
        "expected_evidence_ja": [
            "サービス要求事項文書",
            "サービス記録（該当する場合）",
        ],
    },
    "7.5.5": {
        "title": "無菌醫療器材之特殊要求",
        "title_en": "Particular Requirements for Sterile Medical Devices",
        "title_ja": "滅菌医療機器の特別要求事項",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否記錄每一滅菌批次所使用的滅菌過程參數？"
            "滅菌紀錄是否可追溯至每一生產批次？"
        ),
        "audit_questions": [
            (
                "組織是否記錄每一滅菌批次所使用的滅菌過程參數？"
                "滅菌紀錄是否可追溯至每一生產批次？"
            ),
            "當滅菌批次參數超出規格時，產品的隔離與評估程序為何？滅菌過程的再確認觸發條件為何？",
            "依 ISO 13485:2016 §7.5.5，每一滅菌批次的過程參數是否被記錄，且滅菌紀錄可追溯至每一生產批次？",
            "滅菌驗證（包含 IQ/OQ/PQ）的執行週期與觸發再驗證的條件為何？最近一次再驗證的結論為何？",
            "滅菌設備的預防性維護計畫是否涵蓋所有關鍵零件？維護後是否需要進行確認測試才能恢復生產？",
            "無菌包裝系統（無菌屏障系統）的完整性測試方法是否文件化？測試失敗時的批次處理程序為何？",
            "用於評估無菌保證水平（SAL）的生物負載測試是否按規定頻率執行？結果超標時的應對流程為何？",
        ],
        "expected_evidence": [
            "滅菌程序書",
            "滅菌批次紀錄",
            "滅菌驗證報告",
        ],
        "audit_question_en": "If the medical device is sterile, does the organization document requirements for control of particulate matter? Does the organization maintain records of the sterilization process parameters used for each sterilization batch?",
        "audit_question_ja": "医療機器が滅菌される場合、組織は粒子状物質の管理に関する要求事項を文書化しているか？組織は、各滅菌バッチに対して使用された滅菌プロセスパラメータの記録を維持しているか？",
        "audit_questions_en": [
            "If the medical device is sterile, does the organization document requirements for control of particulate matter? Does the organization maintain records of the sterilization process parameters used for each sterilization batch?",
            "Are sterilization process parameters recorded for each batch? Is the sterilization process validation periodically requalified (e.g., annually)?",
            "Per ISO 13485:2016 §7.5.5, are sterilization process parameters recorded for each sterilization batch and linked to the product batch?",
            "Is the sterilization process validation performed per ISO 11135 (EO), ISO 11137 (irradiation), or ISO 17665 (moist heat) applicable standard?",
            "Are the sterilization parameters (e.g., temperature, pressure, time, humidity, gas concentration) measured with calibrated instruments? What is the handling for out-of-range data?",
            "How is the sterility assurance level (SAL) demonstrated for each batch? Is the bioburden of incoming product monitored?",
            "Is the traceability between sterilization batch and finished product batch complete? Can each sterile product unit be traced back to the sterilization cycle record?",
        ],
        "audit_questions_ja": [
            "医療機器が滅菌される場合、組織は粒子状物質の管理に関する要求事項を文書化しているか？組織は、各滅菌バッチに対して使用された滅菌プロセスパラメータの記録を維持しているか？",
            "滅菌プロセスパラメータは各バッチについて記録されているか？滅菌プロセスバリデーションは定期的に再適格性評価されているか（年次等）？",
            "ISO 13485:2016 §7.5.5に従い、滅菌プロセスパラメータは各滅菌バッチについて記録され、製品バッチと紐付けられているか？",
            "滅菌プロセスバリデーションはISO 11135（EO）、ISO 11137（放射線）、又はISO 17665（湿熱）の該当規格に準じて実施されているか？",
            "滅菌パラメータ（温度、圧力、時間、湿度、ガス濃度等）は校正済計器で測定されているか？範囲外データの処理は？",
            "各バッチの無菌性保証水準（SAL）はどのように実証されているか？入荷製品のバイオバーデンは監視されているか？",
            "滅菌バッチと完成品バッチのトレーサビリティは完全か？各滅菌製品ユニットを滅菌サイクル記録まで追跡できるか？",
        ],
        "expected_evidence_en": [
            "Sterilization process validation records",
            "Sterilization batch records",
            "Sterilization parameter records",
        ],
        "expected_evidence_ja": [
            "滅菌プロセスバリデーション記録",
            "滅菌バッチ記録",
            "滅菌パラメータ記録",
        ],
    },
    "7.5.6": {
        "title": "生產與服務提供過程之確認",
        "title_en": "Validation of Processes for Production and Service Provision",
        "title_ja": "製造及びサービス提供プロセスのバリデーション",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否確認生產和服務提供過程中，其輸出無法由後續的監督或量測加以驗證的過程？"
            "確認是否展示這些過程達成規劃結果的能力？"
            "是否建立確認安排，包含準則、方法、統計技術、"
            "設備資格鑑定以及人員資格？"
        ),
        "audit_questions": [
            (
                "組織是否確認生產和服務提供過程中，其輸出無法由後續的監督或量測加以驗證的過程？"
                "確認是否展示這些過程達成規劃結果的能力？"
                "是否建立確認安排，包含準則、方法、統計技術、"
                "設備資格鑑定以及人員資格？"
            ),
            "過程確認的再確認觸發條件有哪些？如何確保確認報告中的假設在實際生產中持續有效？",
            "依 ISO 13485:2016 §7.5.6，組織是否識別所有輸出無法由後續監測驗證的「特殊過程」，並對這些過程進行確認？",
            "過程確認的範疇是否包含人員（Operator Qualification）、設備（Equipment Qualification）和環境（Environment Qualification）的確認？",
            "過程確認計畫中是否明確定義 IQ、OQ、PQ 各階段的驗收準則？確認失敗時的處理程序為何？",
            "已確認過程的日常監控參數如何設定？當過程參數超出監控界限時的反應計畫為何？",
            "過程確認文件（如確認計畫、協議和報告）是否受文件管制，且保存於產品相關的設計歷史檔案中？",
        ],
        "expected_evidence": [
            "過程確認程序書",
            "過程確認報告（IQ/OQ/PQ）",
            "特殊過程清單",
        ],
        "audit_question_en": "Does the organization validate any processes for production and service provision where the resulting output cannot be or is not verified by subsequent monitoring or measurement and, as a consequence, deficiencies become apparent only after the product is in use or the service has been delivered? Does validation demonstrate the ability of these processes to achieve planned results consistently?",
        "audit_question_ja": "組織は、結果として得られるアウトプットが後続の監視又は測定によって検証できない又はされず、結果として欠陥が製品の使用後又はサービスの提供後にしか明らかにならない生産及びサービス提供のプロセスについて妥当性を確認しているか？妥当性確認は、これらのプロセスが計画された結果を一貫して達成する能力を実証しているか？",
        "audit_questions_en": [
            "Does the organization validate any processes for production and service provision where the resulting output cannot be or is not verified by subsequent monitoring or measurement and, as a consequence, deficiencies become apparent only after the product is in use or the service has been delivered? Does validation demonstrate the ability of these processes to achieve planned results consistently?",
            "Are special processes identified (e.g., sterilization, welding, molding, bonding)? Are validation plans and periodic requalification schedules established for each?",
            "Per ISO 13485:2016 §7.5.6, are processes whose output cannot be verified by subsequent monitoring/measurement identified and validated?",
            "Does the process validation cover IQ (Installation Qualification), OQ (Operational Qualification), and PQ (Performance Qualification)?",
            "Is a periodic requalification cycle defined for special processes? When process changes occur, how is the revalidation procedure?",
            "What are the criteria for the success of process validation? Is statistical sampling used to confirm process consistency?",
            "When process validation fails, how is the handling procedure? How is the impact on related product batches assessed?",
        ],
        "audit_questions_ja": [
            "組織は、結果として得られるアウトプットが後続の監視又は測定によって検証できない又はされず、結果として欠陥が製品の使用後又はサービスの提供後にしか明らかにならない生産及びサービス提供のプロセスについて妥当性を確認しているか？妥当性確認は、これらのプロセスが計画された結果を一貫して達成する能力を実証しているか？",
            "特殊プロセスは識別されているか（滅菌、溶接、成形、接着等）？各々についてバリデーション計画及び定期的再適格性評価スケジュールが確立されているか？",
            "ISO 13485:2016 §7.5.6に従い、後続の監視／測定で検証できないプロセスは識別されバリデーションされているか？",
            "プロセスバリデーションはIQ（据付適格性）、OQ（運転適格性）、PQ（性能適格性）を網羅しているか？",
            "特殊プロセスに対する定期的再適格性評価周期は定義されているか？プロセス変更発生時の再バリデーション手順は？",
            "プロセスバリデーション成功の基準は何か？プロセスの一貫性を確認するために統計的サンプリングは使用されているか？",
            "プロセスバリデーションが失敗した場合、処理手順は？関連製品バッチへの影響はどのように評価されているか？",
        ],
        "expected_evidence_en": [
            "Process validation plan",
            "IQ/OQ/PQ reports",
            "Process requalification records",
        ],
        "expected_evidence_ja": [
            "プロセスバリデーション計画書",
            "IQ／OQ／PQ報告書",
            "プロセス再適格性評価記録",
        ],
    },
    "7.5.7": {
        "title": "滅菌與無菌屏障系統過程之確認",
        "title_en": "Validation of Processes for Sterilization and Sterile Barrier Systems",
        "title_ja": "滅菌及び滅菌バリアシステムのプロセスのバリデーション",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否確認滅菌過程與無菌屏障系統的過程？"
            "確認是否在首次使用前進行，且適當時在產品或過程變更後重新確認？"
        ),
        "audit_questions": [
            (
                "組織是否確認滅菌過程與無菌屏障系統的過程？"
                "確認是否在首次使用前進行，且適當時在產品或過程變更後重新確認？"
            ),
            "滅菌確認後，批次放行的授權流程為何？滅菌設備校正狀態如何確保在確認期間的有效性？",
            "依 ISO 13485:2016 §7.5.7，滅菌過程與無菌屏障系統的確認是否在首次使用前進行，且在產品或過程變更後重新確認？",
            "滅菌過程的確認方法（如 ISO 11135、ISO 11137）依據為何？是否符合相關國際標準的要求？",
            "無菌屏障系統（如滅菌袋、托盤封蓋）的確認是否涵蓋密封強度、完整性和老化穩定性測試？",
            "年度驗證（Annual Product Review or Annual Requalification）的執行內容與頻率為何？最近一次結果如何？",
            "滅菌過程確認中使用的生物指示劑（BI）和化學指示劑（CI）的管理程序為何？效期管制如何執行？",
        ],
        "expected_evidence": [
            "滅菌確認計畫與報告",
            "無菌屏障系統確認報告",
            "再確認紀錄",
        ],
        "audit_question_en": "Does the organization document procedures for validation of the application of computer software used in production and service provision? Such software applications shall be validated prior to initial use and, as appropriate, after changes to such software or its application. The specific approach and activities associated with software validation and revalidation shall be proportionate to the risk associated with the use of the software. Are records maintained?",
        "audit_question_ja": "組織は、生産及びサービス提供に使用されるコンピュータソフトウェアの適用の妥当性確認の手順を文書化しているか？そのようなソフトウェアアプリケーションは、初回使用前、及び適切な場合にはそのようなソフトウェア又はその適用の変更後に妥当性確認されるものとする。ソフトウェアの妥当性確認及び再妥当性確認に関連する具体的アプローチ及び活動は、ソフトウェアの使用に関連するリスクに比例するものとする。記録は維持されているか？",
        "audit_questions_en": [
            "Does the organization document procedures for validation of the application of computer software used in production and service provision? Such software applications shall be validated prior to initial use and, as appropriate, after changes to such software or its application. The specific approach and activities associated with software validation and revalidation shall be proportionate to the risk associated with the use of the software. Are records maintained?",
            "Are all applicable computer software (ERP, MES, test software) validated? Is the validation method risk-based?",
            "Per ISO 13485:2016 §7.5.7, are computer software applications used in production and service provision validated before initial use, and after software or application changes?",
            "Is the risk of software applications assessed? Is the depth of software validation proportionate to the software risk?",
            "How is software validation performed (black-box testing, script testing, code review)? Are test records complete?",
            "When software changes occur (e.g., version updates, configuration changes), how is the revalidation procedure triggered?",
            "Is software access control implemented? How are the validation of data integrity (e.g., audit trail) implemented?",
        ],
        "audit_questions_ja": [
            "組織は、生産及びサービス提供に使用されるコンピュータソフトウェアの適用の妥当性確認の手順を文書化しているか？そのようなソフトウェアアプリケーションは、初回使用前、及び適切な場合にはそのようなソフトウェア又はその適用の変更後に妥当性確認されるものとする。ソフトウェアの妥当性確認及び再妥当性確認に関連する具体的アプローチ及び活動は、ソフトウェアの使用に関連するリスクに比例するものとする。記録は維持されているか？",
            "すべての該当コンピュータソフトウェア（ERP、MES、試験ソフトウェア）はバリデーションされているか？バリデーション方法はリスクに基づいているか？",
            "ISO 13485:2016 §7.5.7に従い、生産及びサービス提供に使用されるコンピュータソフトウェアアプリケーションは、初回使用前及びソフトウェア／アプリケーション変更後にバリデーションされているか？",
            "ソフトウェアアプリケーションのリスクは評価されているか？ソフトウェアバリデーションの深さはソフトウェアリスクに比例しているか？",
            "ソフトウェアバリデーションはどのように実施されているか（ブラックボックステスト、スクリプトテスト、コードレビュー等）？試験記録は完全か？",
            "ソフトウェア変更発生時（バージョン更新、構成変更等）、再バリデーション手順はどのようにトリガーされるか？",
            "ソフトウェアアクセス制御は実施されているか？データ完全性（監査証跡等）のバリデーションはどのように実施されているか？",
        ],
        "expected_evidence_en": [
            "Software validation plan",
            "Software validation report",
            "Software change records",
        ],
        "expected_evidence_ja": [
            "ソフトウェアバリデーション計画書",
            "ソフトウェアバリデーション報告書",
            "ソフトウェア変更記録",
        ],
    },
    "7.5.8": {
        "title": "識別",
        "title_en": "Identification",
        "title_ja": "識別",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立識別產品的文件化程序，並在整個產品實現過程中以適當方法識別產品？"
            "是否在退回的醫療器材與產品實現過程中識別產品狀態？"
        ),
        "audit_questions": [
            (
                "組織是否建立識別產品的文件化程序，並在整個產品實現過程中以適當方法識別產品？"
                "是否在退回的醫療器材與產品實現過程中識別產品狀態？"
            ),
            "如何防止產品在生產過程中的標示混淆或錯誤標示？退回品的識別程序是否與新品明確區分？",
            "依 ISO 13485:2016 §7.5.8，組織是否在整個產品實現過程中以適當方法識別產品狀態（如待驗、合格、不合格）？",
            "電子批次記錄或條碼系統在識別管理中的角色為何？系統錯誤或故障時的備用識別程序為何？",
            "部分組裝品或在製品（WIP）的識別方式為何？如何確保識別標示不會在搬運過程中脫落或損毀？",
            "產品識別資訊（如料號、批號、版本）是否貫穿整個供應鏈？如何確保供應商提供的物料也有適當識別？",
            "混料或錯誤識別事件的調查與矯正措施程序為何？如何評估事件對已出貨產品的潛在影響？",
        ],
        "expected_evidence": [
            "產品識別程序書",
            "標示管制紀錄",
        ],
        "audit_question_en": "Does the organization document procedures for identification of product and identify product status with respect to monitoring and measurement requirements throughout product realization? Product identification shall be maintained throughout product realization, storage, installation and servicing of the medical device to prevent mix-up of product.",
        "audit_question_ja": "組織は、製品の識別の手順を文書化し、製品実現全体を通して監視及び測定の要求事項に関して製品の状態を識別しているか？製品識別は、製品の混同を防止するため、医療機器の製品実現、保管、据付及びサービスの全体を通して維持されるものとする。",
        "audit_questions_en": [
            "Does the organization document procedures for identification of product and identify product status with respect to monitoring and measurement requirements throughout product realization? Product identification shall be maintained throughout product realization, storage, installation and servicing of the medical device to prevent mix-up of product.",
            "Are product identification procedures (including batch/serial number) documented? Is product status (pending inspection, accepted, rejected, released) clearly identified?",
            "Per ISO 13485:2016 §7.5.8, does the organization document procedures for product identification and maintain identification throughout product realization, storage, installation, and servicing?",
            "What is the identification method (barcode, QR code, label) of each product? Is it consistent across stages?",
            "How is the identification maintained during production, storage, installation, and servicing to prevent product mix-up?",
            "How is rework of an identified product controlled? When identification is damaged or lost, how is reassignment procedure?",
            "When product is marked for status change (e.g., approval to release), who is authorized to change the status, and how is it recorded?",
        ],
        "audit_questions_ja": [
            "組織は、製品の識別の手順を文書化し、製品実現全体を通して監視及び測定の要求事項に関して製品の状態を識別しているか？製品識別は、製品の混同を防止するため、医療機器の製品実現、保管、据付及びサービスの全体を通して維持されるものとする。",
            "製品識別手順（ロット／シリアル番号を含む）は文書化されているか？製品状態（検査待ち、合格、不合格、出荷可）は明確に識別されているか？",
            "ISO 13485:2016 §7.5.8に従い、組織は製品識別の手順を文書化し、製品実現、保管、据付、サービスの全体を通して識別を維持しているか？",
            "各製品の識別方法（バーコード、QRコード、ラベル等）は何か？各段階で一貫しているか？",
            "生産、保管、据付、サービス中に識別はどのように維持され、製品混同を防止しているか？",
            "識別された製品の手直しはどのように管理されているか？識別が損傷又は紛失した場合、再割当の手順は？",
            "製品状態変更（出荷承認等）のマーキング時、状態変更の権限を持つのは誰で、どのように記録されているか？",
        ],
        "expected_evidence_en": [
            "Product identification procedure",
            "Product status identification records",
        ],
        "expected_evidence_ja": [
            "製品識別手順書",
            "製品状態識別記録",
        ],
    },
    "7.5.9": {
        "title": "追溯性 — 一般",
        "title_en": "Traceability — General",
        "title_ja": "トレーサビリティ — 一般",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立追溯性的文件化程序？程序是否界定追溯的範圍及所需紀錄？"
        ),
        "audit_questions": [
            (
                "組織是否建立追溯性的文件化程序？程序是否界定追溯的範圍及所需紀錄？"
            ),
            "追溯性紀錄的完整性如何在整個供應鏈中確保？在產品召回情境下，追溯系統的實際執行速度是否符合法規要求？",
            "依 ISO 13485:2016 §7.5.9，組織是否建立追溯性的文件化程序，界定追溯範圍及所需紀錄，並考量適用法規要求？",
            "追溯性的範圍是否涵蓋所有原物料、零組件、生產過程、人員及設備到最終產品？最薄弱的追溯環節是哪裡？",
            "追溯性系統的定期演練（模擬召回）是否執行？最近一次演練的結果與發現為何？",
            "電子化追溯系統的資料備份策略為何？如何確保系統故障不會導致追溯能力喪失？",
            "供應商提供的追溯性資訊（如材料批號、CoC）如何被記錄並與內部批次紀錄連結？",
        ],
        "expected_evidence": [
            "追溯性程序書",
            "追溯性紀錄範例",
        ],
        "audit_question_en": "Does the organization document procedures for traceability? Such procedures shall define the extent of traceability in accordance with applicable regulatory requirements and the records to be maintained.",
        "audit_question_ja": "組織はトレーサビリティの手順を文書化しているか？そのような手順は、適用される規制要求事項及び維持されるべき記録に従って、トレーサビリティの範囲を定義するものとする。",
        "audit_questions_en": [
            "Does the organization document procedures for traceability? Such procedures shall define the extent of traceability in accordance with applicable regulatory requirements and the records to be maintained.",
            "Is the traceability procedure complete? Does it cover the full chain from raw materials, in-process, finished goods, distribution, and post-market?",
            "Per ISO 13485:2016 §7.5.9, does the organization have a traceability procedure that defines the scope of traceability based on applicable regulatory requirements?",
            "Does the traceability system allow full bidirectional (upstream and downstream) traceability? Can specific product batches quickly identify the source of raw materials and the distribution destination?",
            "How long are the traceability records retained? Do they comply with the regulatory requirements of the destination country (e.g., EU MDR requires 10-15 years)?",
            "Is the traceability system periodically tested? When does a traceability test (mock recall) last conducted and what were the results?",
            "Is UDI (Unique Device Identification) implemented? Does UDI-DI/PI labeling meet the requirements of the destination country (US FDA, EU MDR)?",
        ],
        "audit_questions_ja": [
            "組織はトレーサビリティの手順を文書化しているか？そのような手順は、適用される規制要求事項及び維持されるべき記録に従って、トレーサビリティの範囲を定義するものとする。",
            "トレーサビリティ手順は完全か？原材料、仕掛品、完成品、流通、市販後の全連鎖を網羅しているか？",
            "ISO 13485:2016 §7.5.9に従い、組織は適用法規制要求事項に基づいてトレーサビリティの範囲を定義したトレーサビリティ手順を有しているか？",
            "トレーサビリティシステムは完全な双方向（上流及び下流）のトレーサビリティを可能にしているか？特定製品バッチから原材料の入手先及び流通先を迅速に特定できるか？",
            "トレーサビリティ記録の保管期間はどれくらいか？仕向国の規制要求事項（EU MDRは10～15年等）に適合しているか？",
            "トレーサビリティシステムは定期的にテストされているか？最後のトレーサビリティテスト（模擬リコール）はいつ実施され、結果はどうであったか？",
            "UDI（機器固有識別）は実施されているか？UDI-DI/PIの表示は仕向国（米国FDA、EU MDR等）の要求事項を満たしているか？",
        ],
        "expected_evidence_en": [
            "Traceability procedure",
            "Traceability test records",
        ],
        "expected_evidence_ja": [
            "トレーサビリティ手順書",
            "トレーサビリティ試験記録",
        ],
    },
    "7.5.9.1": {
        "title": "追溯性 — 植入式醫療器材",
        "title_en": "Traceability — Implantable Medical Devices",
        "title_ja": "トレーサビリティ — 植込み型医療機器",
        "audit_impact": "critical",
        "audit_question": (
            "對於植入式醫療器材，追溯性紀錄是否包含所有可能導致醫療器材不滿足其"
            "規定安全與效能要求的零件、材料及工作環境條件？"
            "組織是否要求供應商維持追溯性紀錄？"
        ),
        "audit_questions": [
            (
                "對於植入式醫療器材，追溯性紀錄是否包含所有可能導致醫療器材不滿足其"
                "規定安全與效能要求的零件、材料及工作環境條件？"
                "組織是否要求供應商維持追溯性紀錄？"
            ),
            "植入物追溯性資料庫的存取控制與備份程序為何？如何確保長達產品使用壽命期間的紀錄可讀性？",
            "依 ISO 13485:2016 §7.5.9.1，對於植入式醫療器材，追溯性紀錄是否包含所有可能導致器材不滿足安全與效能要求的零件、材料及工作環境條件？",
            "植入物的配送（Distribution）紀錄是否足以識別特定批次產品流向的醫院和患者（在法規允許範圍內）？",
            "組織是否要求植入物的分銷商或醫院維持植入記錄？相關要求是否納入合約或品質協議？",
            "當植入物的關鍵零件供應商變更時，追溯性紀錄如何確保不同時期產品的零件來源可清楚區分？",
            "植入物追溯性紀錄的保存期限如何確定（至少應涵蓋器材的預期使用壽命加上法規規定的年限）？",
        ],
        "expected_evidence": [
            "植入物追溯性紀錄",
            "供應商追溯性要求文件（如適用）",
        ],
        "audit_question_en": "Does the organization document the procedures for traceability? In defining traceability records, does the organization include records of the extent of traceability required by applicable regulatory requirements and records to enable identification of the components, materials, and conditions of the work environment used for manufacturing, if these could cause the medical device not to satisfy its specified safety and performance requirements?",
        "audit_question_ja": "組織はトレーサビリティの手順を文書化しているか？トレーサビリティ記録を定義する際、組織は、適用される規制要求事項によって要求されるトレーサビリティの範囲の記録、及び、これらが医療機器の規定された安全性及び性能要求事項を満たさない原因となり得る場合には、製造に使用された構成部品、材料、及び作業環境の状態を識別できる記録を含めているか？",
        "audit_questions_en": [
            "Does the organization document the procedures for traceability? In defining traceability records, does the organization include records of the extent of traceability required by applicable regulatory requirements and records to enable identification of the components, materials, and conditions of the work environment used for manufacturing, if these could cause the medical device not to satisfy its specified safety and performance requirements?",
            "Does traceability identify all critical components and raw materials? Does it include manufacturing environment conditions (temperature, humidity, cleanliness)?",
            "Per ISO 13485:2016 §7.5.9.1, do traceability records include components, materials, and work environment conditions that may affect safety and performance?",
            "Is the traceability of high-risk components (e.g., surgical implants) more stringent than that of general components? How is the identification level defined?",
            "For components/materials supplied by a single supplier, is the traceability sufficient? Can specific batches be quickly identified for recall?",
            "What is the strategy for preserving traceability records for the expected product service life? Are electronic records backed up?",
            "Have there been instances where traceability failed? What were the root causes, and how has the procedure been improved?",
        ],
        "audit_questions_ja": [
            "組織はトレーサビリティの手順を文書化しているか？トレーサビリティ記録を定義する際、組織は、適用される規制要求事項によって要求されるトレーサビリティの範囲の記録、及び、これらが医療機器の規定された安全性及び性能要求事項を満たさない原因となり得る場合には、製造に使用された構成部品、材料、及び作業環境の状態を識別できる記録を含めているか？",
            "トレーサビリティはすべての重要部品及び原材料を識別しているか？製造環境条件（温度、湿度、清浄度）を含むか？",
            "ISO 13485:2016 §7.5.9.1に従い、トレーサビリティ記録には、安全性及び性能に影響する可能性のある部品、材料、作業環境条件が含まれているか？",
            "高リスク部品（手術用インプラント等）のトレーサビリティは一般部品より厳格か？識別水準はどのように定義されているか？",
            "単一供給者から供給される部品／材料について、トレーサビリティは十分か？特定バッチをリコールのため迅速に識別できるか？",
            "製品の想定サービス期間にわたるトレーサビリティ記録の保管戦略は何か？電子記録はバックアップされているか？",
            "トレーサビリティが失敗した事例はあるか？根本原因は何で、手順はどのように改善されたか？",
        ],
        "expected_evidence_en": [
            "Traceability procedure",
            "Batch-component linkage records",
        ],
        "expected_evidence_ja": [
            "トレーサビリティ手順書",
            "バッチ―部品連結記録",
        ],
    },
    "7.5.9.2": {
        "title": "追溯性 — UDI",
        "title_en": "Traceability — UDI",
        "title_ja": "トレーサビリティ — UDI",
        "audit_impact": "critical",
        "audit_question": ("組織是否建立符合適用法規要求的唯一裝置識別 (UDI) 系統？"),
        "audit_questions": [
            (
                "組織是否識別、驗證、保護與保管顧客所提供的財產？"
                "顧客財產發生遺失、損壞或不適用時，是否向顧客報告並維持紀錄？"
            ),
            "UDI 指派的錯誤防呆機制為何？UDI 數據庫的更新程序與責任人是否明確指定？",
            "依 ISO 13485:2016 §7.5.9.2 及適用法規（如 EU MDR Article 27 或 FDA UDI Rule），組織是否建立符合法規要求的唯一裝置識別（UDI）系統？",
            "UDI 的組成（DI + PI）是否符合適用法規及 IMDRF 指引？UDI 數據庫（如 GUDID、EUDAMED）的提交與更新程序為何？",
            "標籤上的 UDI（Human Readable Interpretation + Automatic Identification）格式是否符合規範？最近一次標籤合規審查的結果為何？",
            "UDI 變更（如產品版本更新、包裝變更）的觸發條件和更新程序為何？如何確保 UDI 數據庫同步更新？",
            "如何確保整個供應鏈（包含轉銷商）正確使用 UDI？是否有監控機制確認標籤完整性？",
        ],
        "expected_evidence": [
            "UDI 指派程序與紀錄（如適用）",
        ],
        "audit_question_en": "For implantable medical devices, does the organization document the components, materials and conditions for the work environment used, if these could cause the medical device not to satisfy its specified safety and performance requirements? Does the organization require that its suppliers of distribution services or distributors maintain records of distribution of medical devices to allow traceability and that such records are available for inspection?",
        "audit_question_ja": "植込み可能医療機器について、組織は、使用された構成部品、材料及び作業環境の状態が医療機器の規定された安全性及び性能要求事項を満たさない原因となり得る場合、これらを文書化しているか？組織は、流通サービスの供給者又は流通業者に対し、トレーサビリティを可能にするために医療機器の流通の記録を維持し、そのような記録が検査のために利用可能であることを要求しているか？",
        "audit_questions_en": [
            "For implantable medical devices, does the organization document the components, materials and conditions for the work environment used, if these could cause the medical device not to satisfy its specified safety and performance requirements? Does the organization require that its suppliers of distribution services or distributors maintain records of distribution of medical devices to allow traceability and that such records are available for inspection?",
            "For implantable medical devices, is the traceability extended to patient-level (distribution records)? Are distributor records complete and inspectable?",
            "Per ISO 13485:2016 §7.5.9.2, for implantable medical devices, does the organization require distribution suppliers or distributors to maintain distribution records for traceability?",
            "Are distribution records of implantable devices traceable to specific patients or recipients (e.g., hospitals, surgeons)?",
            "Are all components, materials, and work environment conditions that may cause medical device non-conformity documented for implantable devices?",
            "Do distribution records meet the regulatory requirements of the destination country (e.g., EUDAMED for EU MDR)?",
            "When the implantable device needs recall or correction, are the distribution records able to support rapid identification of all affected units?",
        ],
        "audit_questions_ja": [
            "植込み可能医療機器について、組織は、使用された構成部品、材料及び作業環境の状態が医療機器の規定された安全性及び性能要求事項を満たさない原因となり得る場合、これらを文書化しているか？組織は、流通サービスの供給者又は流通業者に対し、トレーサビリティを可能にするために医療機器の流通の記録を維持し、そのような記録が検査のために利用可能であることを要求しているか？",
            "植込み可能医療機器について、トレーサビリティは患者レベル（流通記録）まで拡張されているか？流通業者記録は完全で検査可能か？",
            "ISO 13485:2016 §7.5.9.2に従い、植込み可能医療機器について、組織は流通供給者又は流通業者にトレーサビリティのために流通記録の維持を要求しているか？",
            "植込み可能機器の流通記録は特定の患者又は受領者（病院、外科医等）まで追跡可能か？",
            "植込み可能機器について、医療機器の不適合の原因となり得るすべての部品、材料、作業環境条件は文書化されているか？",
            "流通記録は仕向国の規制要求事項（EU MDRのEUDAMED等）に適合しているか？",
            "植込み可能機器のリコール又は改修が必要な場合、流通記録は影響を受けるすべてのユニットの迅速な特定を支援できるか？",
        ],
        "expected_evidence_en": [
            "Implantable device distribution records (if applicable)",
        ],
        "expected_evidence_ja": [
            "植込み可能機器流通記録（該当する場合）",
        ],
    },
    "7.5.10": {
        "title": "顧客財產",
        "title_en": "Customer Property",
        "title_ja": "顧客の所有物",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否識別、驗證、保護與保管顧客所提供的財產？"
            "顧客財產發生遺失、損壞或不適用時，是否向顧客報告並維持紀錄？"
        ),
        "audit_questions": [
            (
                "組織是否識別、驗證、保護與保管顧客所提供的財產？"
                "顧客財產發生遺失、損壞或不適用時，是否向顧客報告並維持紀錄？"
            ),
            "顧客提供的知識產權（如設計圖面、軟體）如何進行保護與存取控制？",
            "依 ISO 13485:2016 §7.5.10，組織是否識別、驗證、保護並保管顧客財產，且當財產遺失、損壞或不適用時向顧客報告並維持紀錄？",
            "顧客財產（如來料加工物料、借用工具、模具）的清單是否維持？清單如何定期盤點確認？",
            "組織如何識別入庫的顧客財產並與自有物料區分管理？識別標示與儲存區域的管制措施為何？",
            "顧客財產在生產過程中損毀或遺失的通報時限要求為何？通報後的賠償或補救程序如何規定？",
            "顧客提供的軟體或智慧財產的使用授權與版本管控如何執行？如何確保不超出授權範圍使用？",
        ],
        "expected_evidence": [
            "顧客財產管制程序書（如適用）",
            "顧客財產紀錄（如適用）",
        ],
        "audit_question_en": "Does the organization identify, verify, protect, and safeguard customer property provided for use or incorporation into the product while it is under the organization's control or being used by the organization? If any customer property is lost, damaged or otherwise found to be unsuitable for use, does the organization report this to the customer and maintain records?",
        "audit_question_ja": "組織は、組織の管理下にある間又は組織によって使用されている間、使用のため又は製品への組込みのために提供された顧客の所有物を識別し、検証し、保護し、安全に保管しているか？顧客の所有物が紛失、損傷、又はその他の理由で使用に不適当と判明した場合、組織はこれを顧客に報告し記録を維持しているか？",
        "audit_questions_en": [
            "Does the organization identify, verify, protect, and safeguard customer property provided for use or incorporation into the product while it is under the organization's control or being used by the organization? If any customer property is lost, damaged or otherwise found to be unsuitable for use, does the organization report this to the customer and maintain records?",
            "Is customer-owned property (e.g., OEM components, patient implantable components) clearly identified and managed?",
            "Per ISO 13485:2016 §7.5.10, is customer property identified, verified, protected, and safeguarded? Is the procedure for reporting loss/damage to the customer documented?",
            "What is the criteria for customer property acceptance verification? How is it ensured that the customer property meets the requirements before use?",
            "Is customer property stored separately from the organization's own property? Is the storage location clearly labeled?",
            "When customer property is lost, damaged, or found unsuitable, how is the customer reporting procedure conducted? What is the reporting timeline requirement?",
            "Do customer property records include receipt, use, storage, return, and disposal history? Are the records auditable?",
        ],
        "audit_questions_ja": [
            "組織は、組織の管理下にある間又は組織によって使用されている間、使用のため又は製品への組込みのために提供された顧客の所有物を識別し、検証し、保護し、安全に保管しているか？顧客の所有物が紛失、損傷、又はその他の理由で使用に不適当と判明した場合、組織はこれを顧客に報告し記録を維持しているか？",
            "顧客所有物（OEM部品、患者植込み部品等）は明確に識別され管理されているか？",
            "ISO 13485:2016 §7.5.10に従い、顧客所有物は識別、検証、保護、安全保管されているか？顧客への損失／損傷報告手順は文書化されているか？",
            "顧客所有物の受入検証基準は何か？使用前に顧客所有物が要求事項を満たすことをどのように確実にしているか？",
            "顧客所有物は組織の所有物と分離して保管されているか？保管場所は明確にラベリングされているか？",
            "顧客所有物の紛失、損傷、又は不適合が判明した場合、顧客への報告手順はどのように実施されているか？報告期限要求は？",
            "顧客所有物記録は受入、使用、保管、返却、処分の履歴を含むか？記録は監査可能か？",
        ],
        "expected_evidence_en": [
            "Customer property management records (if applicable)",
            "Customer property incident reports (if applicable)",
        ],
        "expected_evidence_ja": [
            "顧客所有物管理記録（該当する場合）",
            "顧客所有物事象報告書（該当する場合）",
        ],
    },
    "7.5.11": {
        "title": "產品防護",
        "title_en": "Product Preservation",
        "title_ja": "製品の保持",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立在內部處理及交付至預定目的地期間，"
            "防護產品符合性的文件化程序或作業指導書？"
            "防護是否包含識別、搬運、包裝、儲存及保護？"
            "是否對有限壽命或需特殊儲存條件的產品建立管制？"
        ),
        "audit_questions": [
            (
                "組織是否建立在內部處理及交付至預定目的地期間，"
                "防護產品符合性的文件化程序或作業指導書？"
                "防護是否包含識別、搬運、包裝、儲存及保護？"
                "是否對有限壽命或需特殊儲存條件的產品建立管制？"
            ),
            "有效期限接近的庫存如何被系統性識別與處置？特殊儲存條件的失效應急計畫為何？",
            "依 ISO 13485:2016 §7.5.11，組織是否在內部處理及交付過程中建立防護產品符合性的文件化程序或作業指導書？",
            "產品搬運設備（如叉車、輸送帶）的使用是否有規定以防止產品損傷或污染？搬運人員的培訓要求為何？",
            "倉儲管理系統是否支持先進先出（FIFO）或先到期先出（FEFO）原則？如何定期稽核庫存合規性？",
            "包裝材料的採購規格與驗收準則是否文件化？包裝是否進行過運輸測試驗證，確保在預期運輸條件下的完整性？",
            "在出貨前，最終包裝的完整性（如密封完整性、標示清晰度）如何進行最終確認？",
        ],
        "expected_evidence": [
            "產品防護/倉儲管理程序書",
            "儲存環境監測紀錄",
            "有效期限管制紀錄（如適用）",
        ],
        "audit_question_en": "Does the organization preserve the conformity of product to requirements during processing, storage, handling, and distribution? Preservation shall include identification, handling, packaging, storage, and protection. Preservation shall apply to the constituent parts of a medical device.",
        "audit_question_ja": "組織は、処理、保管、取扱い、及び流通の間、製品の要求事項への適合性を保持しているか？保存には、識別、取扱い、包装、保管、及び保護が含まれるものとする。保存は医療機器の構成部品にも適用されるものとする。",
        "audit_questions_en": [
            "Does the organization preserve the conformity of product to requirements during processing, storage, handling, and distribution? Preservation shall include identification, handling, packaging, storage, and protection. Preservation shall apply to the constituent parts of a medical device.",
            "Is product preservation procedure documented? Does it include identification, handling, packaging, storage, and protection?",
            "Per ISO 13485:2016 §7.5.11, is the preservation of product conformity maintained during processing, storage, handling, and distribution (covering identification, handling, packaging, storage, protection)?",
            "How is the preservation implemented for sensitive products (e.g., temperature-sensitive, moisture-sensitive, electrostatic-sensitive)? Is the monitoring of environmental conditions effective?",
            "Is the product packaging validated to ensure that the product is not damaged during transportation? Does the packaging validation follow ISTA or other applicable standards?",
            "Is the first-in-first-out (FIFO) management of warehouse inventory implemented to prevent expired products from reaching customers?",
            "Is the preservation requirement communicated to the distribution/transportation service provider? How is the compliance verified?",
        ],
        "audit_questions_ja": [
            "組織は、処理、保管、取扱い、及び流通の間、製品の要求事項への適合性を保持しているか？保存には、識別、取扱い、包装、保管、及び保護が含まれるものとする。保存は医療機器の構成部品にも適用されるものとする。",
            "製品保存手順は文書化されているか？識別、取扱い、包装、保管、保護を含むか？",
            "ISO 13485:2016 §7.5.11に従い、製品の適合性は処理、保管、取扱い、流通の間で維持されているか（識別、取扱い、包装、保管、保護を網羅）？",
            "温度感受性、湿度感受性、静電気感受性等の敏感な製品に対する保存はどのように実施されているか？環境条件の監視は有効か？",
            "製品包装は輸送中の製品損傷を防ぐためにバリデーションされているか？包装バリデーションはISTA又はその他該当規格に準拠しているか？",
            "倉庫在庫の先入先出（FIFO）管理は実施され、期限切れ製品が顧客に到達しないようにしているか？",
            "保存要求事項は流通／輸送サービス提供者に伝達されているか？適合性はどのように検証されているか？",
        ],
        "expected_evidence_en": [
            "Product preservation procedure",
            "Storage environment monitoring records",
            "Packaging validation records",
        ],
        "expected_evidence_ja": [
            "製品保存手順書",
            "保管環境モニタリング記録",
            "包装バリデーション記録",
        ],
    },
    "7.6": {
        "title": "監督與量測設備之管制",
        "title_en": "Control of Monitoring and Measuring Equipment",
        "title_ja": "監視機器及び測定機器の管理",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定需執行的監督與量測及所需的設備，以提供產品符合已定要求的證據？"
            "設備是否依規劃的時間間隔或使用前校正或驗證？"
            "是否維持校正與驗證結果的紀錄？"
        ),
        "audit_questions": [
            (
                "組織是否決定需執行的監督與量測及所需的設備，以提供產品符合已定要求的證據？"
                "設備是否依規劃的時間間隔或使用前校正或驗證？"
                "是否維持校正與驗證結果的紀錄？"
            ),
            "量測設備校正結果超出允差時，對先前量測結果的追溯評估程序為何？軟體型量測工具的確認方法為何？",
            "量測設備的校正頻率是否基於設備使用頻率與歷史校正結果動態調整？",
            "依 ISO 13485:2016 §7.6，當量測設備發現超出容許誤差時，先前量測結果的有效性如何評估？有無召回或重新評估的記錄？",
            "量測設備的校正是否可追溯至國家或國際標準？校正證書是否保存完整？",
            "對於用於品質決策的軟體工具，是否進行了軟體驗證（Software Validation）？最近一次驗證記錄為何？",
            "依 ISO 13485:2016 §7.6，量測設備的保護措施（防損壞、防未授權調整）是否文件化且有效執行？",
        ],
        "expected_evidence": [
            "量測設備管制程序書",
            "校正計畫與紀錄",
            "量測設備清單",
        ],
        "audit_question_en": "Does the organization determine the monitoring and measurement to be undertaken and the monitoring and measuring equipment needed to provide evidence of conformity of product to determined requirements? Does the organization document procedures to ensure that monitoring and measurement can be carried out and are carried out in a manner that is consistent with the monitoring and measurement requirements? Is measuring equipment calibrated or verified at specified intervals? Are records of calibration and verification maintained?",
        "audit_question_ja": "組織は、決定された要求事項への製品の適合性の証拠を提供するために実施すべき監視及び測定、並びに必要とされる監視及び測定装置を決定しているか？組織は、監視及び測定が実施可能であり、監視及び測定の要求事項と整合する方法で実施されることを確実にする手順を文書化しているか？測定装置は規定された間隔で校正又は検証されているか？校正及び検証の記録は維持されているか？",
        "audit_questions_en": [
            "Does the organization determine the monitoring and measurement to be undertaken and the monitoring and measuring equipment needed to provide evidence of conformity of product to determined requirements? Does the organization document procedures to ensure that monitoring and measurement can be carried out and are carried out in a manner that is consistent with the monitoring and measurement requirements? Is measuring equipment calibrated or verified at specified intervals? Are records of calibration and verification maintained?",
            "Is measuring and monitoring equipment management procedure complete? Is calibration cycle reasonably set based on equipment characteristics and usage frequency?",
            "Per ISO 13485:2016 §7.6, is measuring equipment calibrated or verified at specified intervals? Is it traceable to national or international measurement standards?",
            "How is the handling of out-of-calibration equipment? When out-of-calibration is detected, is the verification of the impact on previously tested products complete?",
            "Is the calibration performed in-house or outsourced? If outsourced, is the calibration service provider qualified (e.g., ISO/IEC 17025 accredited)?",
            "How is the identification of calibration status (e.g., calibration label) effectively prevent the use of uncalibrated/expired equipment?",
            "Do calibration records include calibration results, standards used, calibration personnel, calibration date, and next calibration date?",
        ],
        "audit_questions_ja": [
            "組織は、決定された要求事項への製品の適合性の証拠を提供するために実施すべき監視及び測定、並びに必要とされる監視及び測定装置を決定しているか？組織は、監視及び測定が実施可能であり、監視及び測定の要求事項と整合する方法で実施されることを確実にする手順を文書化しているか？測定装置は規定された間隔で校正又は検証されているか？校正及び検証の記録は維持されているか？",
            "測定監視装置管理手順は完全か？校正周期は装置特性及び使用頻度に基づいて合理的に設定されているか？",
            "ISO 13485:2016 §7.6に従い、測定装置は規定された間隔で校正又は検証されているか？国家又は国際測定標準まで追跡可能か？",
            "校正外装置の処理はどのように行われているか？校正外検出時、以前に試験された製品への影響検証は完全か？",
            "校正は社内実施か外部委託か？外部委託の場合、校正サービス提供者は認定を受けているか（ISO/IEC 17025認定等）？",
            "校正状態の識別（校正ラベル等）は未校正／期限切れ装置の使用をどのように有効に防止しているか？",
            "校正記録は校正結果、使用標準、校正要員、校正日、次回校正日を含むか？",
        ],
        "expected_evidence_en": [
            "Measuring equipment list",
            "Calibration records",
            "Calibration certificate",
        ],
        "expected_evidence_ja": [
            "測定装置一覧",
            "校正記録",
            "校正証明書",
        ],
    },
    # --------------------------------------------------------
    # Section 8: 量測、分析與改善
    # --------------------------------------------------------
    "8.1": {
        "title": "量測、分析與改善 — 一般",
        "title_en": "Measurement, Analysis and Improvement — General",
        "title_ja": "測定、分析及び改善 — 一般",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否規劃並實施所需的監督、量測、分析及改善過程，"
            "以展示產品的符合性、確保品質管理系統的符合性、以及維持其有效性？"
        ),
        "audit_questions": [
            (
                "組織是否規劃並實施所需的監督、量測、分析及改善過程，"
                "以展示產品的符合性、確保品質管理系統的符合性、以及維持其有效性？"
            ),
            "品質數據分析的結果如何驅動管理決策？統計方法的選擇與適用性由誰決定與審查？",
            "依 ISO 13485:2016 §8.1，組織是否規劃並實施所需的監督、量測、分析及改善過程，以展示產品符合性及確保 QMS 的有效性？",
            "組織使用的統計方法（如 SPC、抽樣計畫）是否文件化，且適用性由具備統計能力的人員確認？",
            "量測、分析與改善過程的資源需求（如人員能力、軟體工具）是否在年度規劃中被識別和配置？",
            "量測、分析過程的輸出如何定期整合並向管理階層報告？報告頻率與格式是否標準化？",
            "當量測數據顯示異常趨勢時，緊急反應程序的觸發條件和負責人為何？",
        ],
        "expected_evidence": [
            "監督量測分析改善規劃文件",
            "統計技術應用紀錄（如適用）",
        ],
        "audit_question_en": "Does the organization plan and implement the monitoring, measurement, analysis and improvement processes needed to demonstrate conformity of product, to ensure conformity of the QMS, and to maintain the effectiveness of the QMS? This shall include determination of appropriate methods, including statistical techniques, and the extent of their use.",
        "audit_question_ja": "組織は、製品の適合性を実証し、品質マネジメントシステムの適合性を確実にし、品質マネジメントシステムの有効性を維持するために必要な監視、測定、分析及び改善のプロセスを計画し実施しているか？これには、統計的手法を含む適切な方法及びその使用範囲の決定を含むものとする。",
        "audit_questions_en": [
            "Does the organization plan and implement the monitoring, measurement, analysis and improvement processes needed to demonstrate conformity of product, to ensure conformity of the QMS, and to maintain the effectiveness of the QMS? This shall include determination of appropriate methods, including statistical techniques, and the extent of their use.",
            "Is the monitoring/measurement/analysis/improvement planning complete? Does it cover product conformity, QMS conformity, and QMS effectiveness maintenance?",
            "Per ISO 13485:2016 §8.1, are monitoring, measurement, analysis, and improvement planning covering product conformity, QMS conformity, and QMS effectiveness?",
            "Is statistical technique application documented? What statistical techniques are used (SPC, sampling, hypothesis testing)?",
            "How is the output of data analysis used for decision-making? Are the outputs periodically reviewed in management reviews?",
            "Is statistical technique application training provided to relevant personnel? Is the competence for statistical analysis effectively managed?",
            "How are the monitoring indicators and KPIs of the QMS effectiveness defined? Are the KPIs quantifiable and trend-trackable?",
        ],
        "audit_questions_ja": [
            "組織は、製品の適合性を実証し、品質マネジメントシステムの適合性を確実にし、品質マネジメントシステムの有効性を維持するために必要な監視、測定、分析及び改善のプロセスを計画し実施しているか？これには、統計的手法を含む適切な方法及びその使用範囲の決定を含むものとする。",
            "監視／測定／分析／改善計画は完全か？製品適合性、品質マネジメントシステム適合性、品質マネジメントシステム有効性維持を網羅しているか？",
            "ISO 13485:2016 §8.1に従い、監視、測定、分析、改善の計画は製品適合性、品質マネジメントシステム適合性、品質マネジメントシステム有効性を網羅しているか？",
            "統計的手法の適用は文書化されているか？どの統計的手法（SPC、サンプリング、仮説検定等）が使用されているか？",
            "データ分析のアウトプットは意思決定にどのように使用されているか？アウトプットはマネジメントレビューで定期的にレビューされているか？",
            "統計的手法適用の訓練は関連要員に提供されているか？統計分析の力量は有効に管理されているか？",
            "品質マネジメントシステム有効性の監視指標及びKPIはどのように定義されているか？KPIは定量化可能でトレンド追跡可能か？",
        ],
        "expected_evidence_en": [
            "Monitoring/measurement/analysis planning document",
            "Statistical technique application documents",
        ],
        "expected_evidence_ja": [
            "監視／測定／分析計画書",
            "統計的手法適用文書",
        ],
    },
    "8.2.1": {
        "title": "回饋",
        "title_en": "Feedback",
        "title_ja": "フィードバック",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立收集與監督回饋資訊的文件化程序，作為品質管理系統績效的量測之一？"
            "回饋過程是否包含蒐集生產及生產後活動資料的規定？"
            "回饋過程中收集的資訊是否作為風險管理及產品實現或改善過程的輸入？"
        ),
        "audit_questions": [
            (
                "組織是否建立收集與監督回饋資訊的文件化程序，作為品質管理系統績效的量測之一？"
                "回饋過程是否包含蒐集生產及生產後活動資料的規定？"
                "回饋過程中收集的資訊是否作為風險管理及產品實現或改善過程的輸入？"
            ),
            "回饋數據的收集渠道有哪些？如何確保負面回饋不被過濾或低報？回饋趨勢的法規意涵如何評估？",
            "顧客抱怨的處理時效是否有規定？最近 12 個月內，是否有超時未回覆的案例？",
            "依 ISO 13485:2016 §8.2.1，顧客回饋資料是否被用於管理審查輸入？是否有趨勢分析？",
            "售後服務人員如何識別潛在的法規通報義務（MDR/Vigilance）？識別後的升級流程為何？",
            "顧客回饋的收集管道（電話、Email、現場服務記錄等）是否全部納入統一追蹤系統？",
            "依 ISO 13485:2016 §8.2.1，收集顧客回饋的頻率與方法是否文件化？是否有顧客滿意度調查機制？",
        ],
        "expected_evidence": [
            "顧客回饋管制程序書",
            "顧客回饋/抱怨紀錄",
            "趨勢分析報告",
        ],
        "audit_question_en": "As one of the measurements of the effectiveness of the QMS, does the organization gather and monitor information relating to whether the organization has met customer requirements? Does the organization document procedures for these feedback processes and include provisions for gathering data from production and post-production activities?",
        "audit_question_ja": "品質マネジメントシステムの有効性の測定の一つとして、組織は、組織が顧客要求事項を満たしたかどうかに関連する情報を収集し監視しているか？組織は、これらのフィードバックプロセスの手順を文書化し、生産及び生産後活動からのデータ収集の規定を含めているか？",
        "audit_questions_en": [
            "As one of the measurements of the effectiveness of the QMS, does the organization gather and monitor information relating to whether the organization has met customer requirements? Does the organization document procedures for these feedback processes and include provisions for gathering data from production and post-production activities?",
            "Is the customer feedback collection mechanism comprehensive? Does it cover customer satisfaction survey, complaint, service record, distributor feedback?",
            "Per ISO 13485:2016 §8.2.1, does the organization gather feedback from production and post-production activities, including complaint handling, service records, distributor feedback?",
            "What is the objectivity of customer satisfaction survey? Is the sample selection representative and the response rate adequate?",
            "How are the feedback data used for product improvement and QMS improvement? Is there a process to link feedback to CAPA?",
            "How is feedback information classified and prioritized (e.g., safety-related, quality-related, service-related)? Is the handling procedure documented?",
            "How are the trends of customer feedback (e.g., complaint rate, satisfaction score) reported to management? What are the communication channels?",
        ],
        "audit_questions_ja": [
            "品質マネジメントシステムの有効性の測定の一つとして、組織は、組織が顧客要求事項を満たしたかどうかに関連する情報を収集し監視しているか？組織は、これらのフィードバックプロセスの手順を文書化し、生産及び生産後活動からのデータ収集の規定を含めているか？",
            "顧客フィードバック収集機構は包括的か？顧客満足度調査、苦情、サービス記録、流通業者フィードバックを網羅しているか？",
            "ISO 13485:2016 §8.2.1に従い、組織は生産及び生産後活動からフィードバックを収集しており、苦情処理、サービス記録、流通業者フィードバックを含むか？",
            "顧客満足度調査の客観性は？サンプル選定は代表的で、回答率は十分か？",
            "フィードバックデータは製品改善及び品質マネジメントシステム改善にどのように使用されているか？フィードバックをCAPAに結び付けるプロセスはあるか？",
            "フィードバック情報は分類され優先順位付けされているか（安全関連、品質関連、サービス関連等）？処理手順は文書化されているか？",
            "顧客フィードバックの傾向（苦情率、満足度スコア等）はどのように経営層に報告されているか？コミュニケーションチャネルは？",
        ],
        "expected_evidence_en": [
            "Feedback procedure",
            "Customer satisfaction data",
            "Post-market monitoring records",
        ],
        "expected_evidence_ja": [
            "フィードバック手順書",
            "顧客満足度データ",
            "市販後監視記録",
        ],
    },
    "8.2.2": {
        "title": "客訴處理",
        "title_en": "Complaint Handling",
        "title_ja": "苦情処理",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立客訴處理的文件化程序，符合適用的法規要求？"
            "程序是否包含接收與記錄資訊的要求、評估是否構成客訴、"
            "調查/向法規機關報告/處理的要求？"
            "如果客訴未經調查，是否文件化理由？"
        ),
        "audit_questions": [
            (
                "組織是否建立客訴處理的文件化程序，符合適用的法規要求？"
                "程序是否包含接收與記錄資訊的要求、評估是否構成客訴、"
                "調查/向法規機關報告/處理的要求？"
                "如果客訴未經調查，是否文件化理由？"
            ),
            "客訴調查的完成時限要求為何？如何確保調查深度足以識別系統性問題？是否有客訴趨勢的定期審查？",
            "內部稽核的頻率是否基於過程重要性與先前稽核結果而調整？最近一次如何決定稽核頻率？",
            "依 ISO 13485:2016 §8.2.2，稽核員是否與被稽核區域無直接責任關係（獨立性）？是否有文件記錄此獨立性？",
            "稽核發現（Findings）的追蹤關閉機制為何？是否有系統確保逾期的稽核缺失被升級？",
            "稽核計劃是否涵蓋所有 QMS 過程，包含外包過程和供應商稽核？最近一次供應商稽核是何時？",
            "依 ISO 13485:2016 §8.2.2，稽核記錄保存期限是否符合法規要求？記錄保存在哪裡、如何存取？",
        ],
        "expected_evidence": [
            "客訴處理程序書",
            "客訴紀錄/調查報告",
            "法規通報紀錄（如適用）",
        ],
        "audit_question_en": "Does the organization document procedures for the timely handling of complaints in accordance with applicable regulatory requirements? Do these procedures include receiving and recording information; evaluating information to determine if the feedback constitutes a complaint; investigating complaints; determining the need to report the information to appropriate regulatory authorities; handling complaint-related product; and determining the need to initiate corrections or corrective actions?",
        "audit_question_ja": "組織は、適用される規制要求事項に従って苦情を適時に処理する手順を文書化しているか？これらの手順には、情報の受領及び記録、フィードバックが苦情を構成するかどうかを決定するための情報の評価、苦情の調査、情報を適切な規制当局に報告する必要性の決定、苦情関連製品の処理、並びに是正又は是正処置を開始する必要性の決定が含まれるか？",
        "audit_questions_en": [
            "Does the organization document procedures for the timely handling of complaints in accordance with applicable regulatory requirements? Do these procedures include receiving and recording information; evaluating information to determine if the feedback constitutes a complaint; investigating complaints; determining the need to report the information to appropriate regulatory authorities; handling complaint-related product; and determining the need to initiate corrections or corrective actions?",
            "Is the complaint handling procedure complete? Does it cover receiving, recording, evaluating, investigating, reporting, handling, and corrective action?",
            "Per ISO 13485:2016 §8.2.2, does the organization have documented procedures for timely complaint handling that include the 6 elements (receiving/recording, evaluation, investigation, regulatory reporting, complaint-related product handling, correction/CAPA determination)?",
            "Is the complaint handling timeline defined? Does it meet the regulatory timeline requirements (e.g., FDA MDR, EU MDR Vigilance)?",
            "How are complaints evaluated as reportable events or adverse events? What is the decision criteria for regulatory reporting?",
            "When a complaint is handled and resolved, are the records complete? Is the root cause analysis included?",
            "Is the handling of complaint-related products (e.g., return, quarantine, investigation) effective? How is the product traceability ensured?",
        ],
        "audit_questions_ja": [
            "組織は、適用される規制要求事項に従って苦情を適時に処理する手順を文書化しているか？これらの手順には、情報の受領及び記録、フィードバックが苦情を構成するかどうかを決定するための情報の評価、苦情の調査、情報を適切な規制当局に報告する必要性の決定、苦情関連製品の処理、並びに是正又は是正処置を開始する必要性の決定が含まれるか？",
            "苦情処理手順は完全か？受領、記録、評価、調査、報告、処理、是正処置を網羅しているか？",
            "ISO 13485:2016 §8.2.2に従い、組織は適時の苦情処理のための文書化手順を有しており、6つの要素（受領／記録、評価、調査、規制報告、苦情関連製品処理、是正／CAPA決定）を含むか？",
            "苦情処理期限は定義されているか？法規制期限要求事項（FDA MDR、EU MDR Vigilance等）を満たしているか？",
            "苦情はどのように報告すべき事象又は有害事象として評価されるか？規制報告の決定基準は何か？",
            "苦情が処理され解決された際、記録は完全か？根本原因分析は含まれているか？",
            "苦情関連製品の処理（返品、隔離、調査等）は有効か？製品トレーサビリティはどのように確実にされているか？",
        ],
        "expected_evidence_en": [
            "Complaint handling procedure",
            "Complaint records",
            "Complaint investigation reports",
        ],
        "expected_evidence_ja": [
            "苦情処理手順書",
            "苦情記録",
            "苦情調査報告書",
        ],
    },
    "8.2.3": {
        "title": "法規主管機關報告",
        "title_en": "Reporting to Regulatory Authorities",
        "title_ja": "規制当局への報告",
        "audit_impact": "critical",
        "audit_question": (
            "如果適用法規要求通報符合規定通報準則的客訴或諮詢通知，"
            "組織是否建立向法規主管機關提供通知的文件化程序？"
            "是否維持向法規主管機關報告的紀錄？"
        ),
        "audit_questions": [
            (
                "如果適用法規要求通報符合規定通報準則的客訴或諮詢通知，"
                "組織是否建立向法規主管機關提供通知的文件化程序？"
                "是否維持向法規主管機關報告的紀錄？"
            ),
            "如何判定特定事件是否達到法規通報門檻？錯誤分類（應通報而未通報）的防呆措施為何？",
            "依 ISO 13485:2016 §8.2.3，組織是否建立文件化程序，確保符合法規要求的不良事件及諮詢通知被及時通報至相關法規主管機關？",
            "不良事件的通報時限（如 FDA MDR 30 天、EU MDR 15 天、臺灣 TFDA 相關要求）是否被識別，且達到觸發條件時的記者計時起點如何界定？",
            "通報記錄的格式與保存要求是否符合各目標市場法規要求？如何確保記錄在查廠時可快速調取？",
            "法規通報責任人（如 RA/QA 人員）的備援方案是否存在？當責任人缺席時，通報程序如何延續？",
            "諮詢通知（Advisory Notice / FSCA）的分發追蹤機制為何？如何確認所有目標接收者已收到通知並採取措施？",
        ],
        "expected_evidence": [
            "法規通報程序書",
            "不良事件通報紀錄（如適用）",
            "諮詢通知紀錄（如適用）",
        ],
        "audit_question_en": "Does the organization document procedures for providing notification to the appropriate regulatory authorities in accordance with applicable regulatory requirements? Are records of reporting to regulatory authorities maintained?",
        "audit_question_ja": "組織は、適用される規制要求事項に従って適切な規制当局に通知するための手順を文書化しているか？規制当局への報告の記録は維持されているか？",
        "audit_questions_en": [
            "Does the organization document procedures for providing notification to the appropriate regulatory authorities in accordance with applicable regulatory requirements? Are records of reporting to regulatory authorities maintained?",
            "Is the regulatory reporting procedure complete? Does it cover the reporting requirements of destination countries/regions (FDA MDR, EU MDR Vigilance, TFDA, etc.)?",
            "Per ISO 13485:2016 §8.2.3, does the organization have documented procedures for reporting to regulatory authorities, and are reporting records maintained?",
            "What is the criteria for determining regulatory reporting need? Are the criteria documented and accessible to relevant personnel?",
            "How is the regulatory reporting timeline managed? When the reporting deadline approaches (e.g., FDA 30-day rule), what is the escalation procedure?",
            "Are regulatory reporting records complete? Do they include report content, date, responsible person, regulatory authority response, and follow-up actions?",
            "When regulatory requirements change (e.g., EU MDR implementation), how is the internal reporting procedure updated? Who is responsible for tracking regulatory updates?",
        ],
        "audit_questions_ja": [
            "組織は、適用される規制要求事項に従って適切な規制当局に通知するための手順を文書化しているか？規制当局への報告の記録は維持されているか？",
            "規制報告手順は完全か？仕向国／地域の報告要求事項（FDA MDR、EU MDR Vigilance、TFDA等）を網羅しているか？",
            "ISO 13485:2016 §8.2.3に従い、組織は規制当局への報告のための文書化手順を有し、報告記録は維持されているか？",
            "規制報告必要性の決定基準は何か？基準は文書化され関連要員が入手可能か？",
            "規制報告期限はどのように管理されているか？報告期限が迫った場合（FDA 30日ルール等）のエスカレーション手順は？",
            "規制報告記録は完全か？報告内容、日付、責任者、規制当局の回答、フォロー処置を含むか？",
            "規制要求事項が変更された場合（EU MDR施行等）、社内報告手順はどのように更新されているか？規制更新の追跡責任者は誰か？",
        ],
        "expected_evidence_en": [
            "Regulatory reporting procedure",
            "Reporting records",
            "Regulatory requirements mapping table",
        ],
        "expected_evidence_ja": [
            "規制報告手順書",
            "報告記録",
            "規制要求事項マッピング表",
        ],
    },
    "8.2.4": {
        "title": "內部稽核",
        "title_en": "Internal Audit",
        "title_ja": "内部監査",
        "audit_impact": "major",
        "audit_question": (
            "組織是否依規劃的時間間隔執行內部稽核，以確定品質管理系統是否符合"
            "規劃的安排、本標準的要求、適用法規要求、以及組織所建立的品質管理系統要求？"
            "稽核方案的規劃是否考量過程與領域的狀態及重要性以及先前稽核結果？"
        ),
        "audit_questions": [
            (
                "組織是否依規劃的時間間隔執行內部稽核，以確定品質管理系統是否符合"
                "規劃的安排、本標準的要求、適用法規要求、以及組織所建立的品質管理系統要求？"
                "稽核方案的規劃是否考量過程與領域的狀態及重要性以及先前稽核結果？"
            ),
            "稽核員的訓練與資格維持計畫為何？如何確保稽核問題的追蹤不流於形式？",
            "依 ISO 13485:2016 §8.2.4，年度稽核計畫的規劃是否考量過程重要性、先前稽核結果和法規要求，且覆蓋所有 QMS 過程？",
            "內部稽核計畫是否包含對外包過程和關鍵供應商的稽核？供應商稽核頻率的依據為何？",
            "稽核發現的分級（如主要缺失 Major NC、次要缺失 Minor NC、觀察事項 OFI）標準是否文件化？",
            "稽核後的矯正措施（CAPA）是否在規定時限內完成，且有效性被驗證？關閉標準為何？",
            "依 ISO 13485:2016 §8.2.4，稽核方案的管理（規劃、執行、報告和改善）是否有專責人員負責，且程序文件化？",
        ],
        "expected_evidence": [
            "內部稽核程序書",
            "年度稽核計畫",
            "稽核報告",
            "稽核發現追蹤紀錄",
        ],
        "audit_question_en": "Does the organization conduct internal audits at planned intervals to determine whether the QMS conforms to planned and documented arrangements, requirements of this International Standard, QMS requirements established by the organization, and applicable regulatory requirements, and is effectively implemented and maintained? Does the organization document a procedure to describe the responsibilities and requirements for planning and conducting audits, and recording and reporting audit results?",
        "audit_question_ja": "組織は、品質マネジメントシステムが計画され文書化された取決め、本国際規格の要求事項、組織によって確立された品質マネジメントシステム要求事項、及び適用される規制要求事項に適合しているかどうか、並びに有効に実施され維持されているかどうかを決定するために、計画された間隔で内部監査を実施しているか？組織は、監査の計画及び実施、並びに監査結果の記録及び報告に関する責任及び要求事項を記述した手順を文書化しているか？",
        "audit_questions_en": [
            "Does the organization conduct internal audits at planned intervals to determine whether the QMS conforms to planned and documented arrangements, requirements of this International Standard, QMS requirements established by the organization, and applicable regulatory requirements, and is effectively implemented and maintained? Does the organization document a procedure to describe the responsibilities and requirements for planning and conducting audits, and recording and reporting audit results?",
            "Is the internal audit plan risk-based? Are the audit frequency, scope, and auditors arranged to ensure full QMS coverage?",
            "Per ISO 13485:2016 §8.2.4, are internal audits conducted at planned intervals to determine QMS conformity and effectiveness? Is the audit procedure documented?",
            "Are internal auditors independent of the area being audited? Are their qualifications (training, experience) sufficient?",
            "Are internal audit findings handled via CAPA process? Are the corrective actions verified for effectiveness?",
            "How is the periodic full coverage of the QMS by internal audits ensured? What is the audit cycle for each process?",
            "Are internal audit results reported to management review? Are the root cause analyses of recurring findings conducted?",
        ],
        "audit_questions_ja": [
            "組織は、品質マネジメントシステムが計画され文書化された取決め、本国際規格の要求事項、組織によって確立された品質マネジメントシステム要求事項、及び適用される規制要求事項に適合しているかどうか、並びに有効に実施され維持されているかどうかを決定するために、計画された間隔で内部監査を実施しているか？組織は、監査の計画及び実施、並びに監査結果の記録及び報告に関する責任及び要求事項を記述した手順を文書化しているか？",
            "内部監査計画はリスクに基づいているか？監査頻度、範囲、監査員は品質マネジメントシステム全体のカバレッジを確実にするよう計画されているか？",
            "ISO 13485:2016 §8.2.4に従い、内部監査は計画された間隔で実施され、品質マネジメントシステムの適合性及び有効性を決定しているか？監査手順は文書化されているか？",
            "内部監査員は監査対象領域から独立しているか？その適格性（訓練、経験）は十分か？",
            "内部監査所見はCAPAプロセスを通じて処理されているか？是正処置の有効性は検証されているか？",
            "内部監査による品質マネジメントシステムの定期的な完全カバレッジはどのように確実にされているか？各プロセスの監査周期は？",
            "内部監査結果はマネジメントレビューに報告されているか？再発する所見の根本原因分析は実施されているか？",
        ],
        "expected_evidence_en": [
            "Internal audit procedure",
            "Annual audit plan",
            "Internal audit reports",
            "Auditor qualification records",
        ],
        "expected_evidence_ja": [
            "内部監査手順書",
            "年次監査計画",
            "内部監査報告書",
            "監査員適格性記録",
        ],
    },
    "8.2.4.1": {
        "title": "內部稽核 — 稽核準則",
        "title_en": "Internal Audit — Audit Criteria",
        "title_ja": "内部監査 — 監査基準",
        "audit_impact": "major",
        "audit_question": (
            "是否界定稽核準則、範圍、頻率及方法？"
            "稽核員的選擇及稽核的執行是否確保稽核過程的客觀性與公正性？"
            "稽核員是否不稽核自己的工作？"
        ),
        "audit_questions": [
            (
                "是否界定稽核準則、範圍、頻率及方法？"
                "稽核員的選擇及稽核的執行是否確保稽核過程的客觀性與公正性？"
                "稽核員是否不稽核自己的工作？"
            ),
            "稽核準則的制定來源為何？如何確保稽核準則涵蓋最新的法規要求？稽核員的客觀性如何在實務中驗證？",
            "依 ISO 13485:2016 §8.2.4，稽核範圍、準則、頻率和方法是否在稽核計畫中明確界定並被核准？",
            "稽核準則（Audit Criteria）的更新機制為何？當相關法規或標準修訂時，稽核準則如何及時更新？",
            "稽核員的培訓課程包含哪些要素（如 ISO 13485 標準知識、稽核技巧、產業知識）？培訓記錄如何維持？",
            "跨部門或跨功能的聯合稽核如何規劃？如何確保多名稽核員對同一稽核發現的判斷具有一致性？",
            "稽核前的文件審查（Document Review）是否作為稽核準備的標準步驟？哪些文件需要在現場稽核前預先審查？",
        ],
        "expected_evidence": [
            "稽核員資格要求",
            "稽核員獨立性紀錄",
        ],
        "audit_question_en": "Does the organization plan the audit programme, including frequency and methods, taking into consideration the status and importance of the processes and areas to be audited, as well as the results of previous audits? Are the audit criteria, scope, interval and methods defined and recorded?",
        "audit_question_ja": "組織は、監査されるべきプロセス及び領域の状態及び重要性、並びに前回の監査の結果を考慮して、頻度及び方法を含む監査プログラムを計画しているか？監査の基準、範囲、間隔及び方法は定義され記録されているか？",
        "audit_questions_en": [
            "Does the organization plan the audit programme, including frequency and methods, taking into consideration the status and importance of the processes and areas to be audited, as well as the results of previous audits? Are the audit criteria, scope, interval and methods defined and recorded?",
            "Is the audit program plan risk-based? Does the audit frequency of high-risk processes exceed that of low-risk processes?",
            "Per ISO 13485:2016 §8.2.4.1, does the audit program plan include frequency and methods, considering process status, importance, and previous audit results?",
            "Are audit criteria (standards, procedures, regulations) defined for each audit? Are they known to the auditee and auditor in advance?",
            "How is the audit scope (e.g., sites, processes, time period) defined for each audit? Are the audit scope documented?",
            "When previous audit results show concerns (e.g., repeated findings), does the audit frequency or depth adjust accordingly?",
            "Is the audit method combination (document review, interview, observation, sampling) appropriate for each audit type?",
        ],
        "audit_questions_ja": [
            "組織は、監査されるべきプロセス及び領域の状態及び重要性、並びに前回の監査の結果を考慮して、頻度及び方法を含む監査プログラムを計画しているか？監査の基準、範囲、間隔及び方法は定義され記録されているか？",
            "監査プログラム計画はリスクに基づいているか？高リスクプロセスの監査頻度は低リスクプロセスを超えているか？",
            "ISO 13485:2016 §8.2.4.1に従い、監査プログラム計画は頻度及び方法を含み、プロセス状態、重要性、前回監査結果を考慮しているか？",
            "各監査の監査基準（規格、手順、法規制）は定義されているか？被監査者及び監査員に事前に周知されているか？",
            "各監査の監査範囲（拠点、プロセス、期間等）はどのように定義されているか？監査範囲は文書化されているか？",
            "前回の監査結果に懸念がある場合（繰り返される所見等）、監査頻度又は深さは相応に調整されているか？",
            "各監査の種類に対する監査方法の組合せ（文書レビュー、インタビュー、観察、サンプリング）は適切か？",
        ],
        "expected_evidence_en": [
            "Audit program",
            "Audit criteria/scope documents",
        ],
        "expected_evidence_ja": [
            "監査プログラム",
            "監査基準／範囲文書",
        ],
    },
    "8.2.4.2": {
        "title": "內部稽核 — 矯正措施",
        "title_en": "Internal Audit — Corrective Actions",
        "title_ja": "内部監査 — 是正処置",
        "audit_impact": "major",
        "audit_question": (
            "受稽核區域的管理階層是否確保適時採取矯正措施以消除已發現的不符合及其原因？"
            "後續行動是否包含對所採措施的驗證及驗證結果的報告？"
        ),
        "audit_questions": [
            (
                "受稽核區域的管理階層是否確保適時採取矯正措施以消除已發現的不符合及其原因？"
                "後續行動是否包含對所採措施的驗證及驗證結果的報告？"
            ),
            "矯正措施有效性驗證的方法與時間點如何確定？若矯正措施效果不佳，升級程序為何？",
            "依 ISO 13485:2016 §8.2.4，受稽核區域的管理階層是否確保及時採取矯正措施消除不符合及其原因，且驗證所採措施的有效性？",
            "矯正措施的實施期限如何設定？設定依據（如不符合的嚴重程度、根本原因複雜度）是否文件化？",
            "稽核矯正措施的追蹤是否整合至 CAPA 系統？關閉流程的授權層級為何？",
            "重複性稽核缺失（同一缺失在多次稽核中反覆出現）如何被識別和上報？升級處理機制為何？",
            "內部稽核的矯正措施有效性如何在後續稽核中客觀驗證？是否有結構化的驗證清單？",
        ],
        "expected_evidence": [
            "稽核矯正措施紀錄",
            "矯正措施有效性驗證紀錄",
        ],
        "audit_question_en": "Does the organization document a procedure to describe the responsibilities and requirements for planning and conducting audits, and recording and reporting audit results? Does management responsible for the area being audited ensure that any necessary corrections and corrective actions are taken without undue delay to eliminate detected nonconformities and their causes? Do follow-up activities include the verification of the actions taken and the reporting of verification results? Are records maintained?",
        "audit_question_ja": "組織は、監査の計画及び実施、並びに監査結果の記録及び報告に関する責任及び要求事項を記述した手順を文書化しているか？監査された領域を担当する管理者は、検出された不適合及びその原因を除去するために必要な是正及び是正処置が過度な遅延なく取られることを確実にしているか？フォローアップ活動には取られた処置の検証及び検証結果の報告が含まれているか？記録は維持されているか？",
        "audit_questions_en": [
            "Does the organization document a procedure to describe the responsibilities and requirements for planning and conducting audits, and recording and reporting audit results? Does management responsible for the area being audited ensure that any necessary corrections and corrective actions are taken without undue delay to eliminate detected nonconformities and their causes? Do follow-up activities include the verification of the actions taken and the reporting of verification results? Are records maintained?",
            "Are the audit reports, audit findings, and follow-up actions complete? Is the management of the audited area required to implement corrective actions without delay?",
            "Per ISO 13485:2016 §8.2.4.2, is the audit follow-up mechanism documented? Does it require verification of action effectiveness and reporting of verification results?",
            "Are audit non-conformities classified (major, minor, observation)? Is the handling priority of each class defined?",
            "How is the timeline for implementing corrective actions on audit non-conformities tracked? When not completed on time, what is the escalation procedure?",
            "How is the effectiveness verification of the corrective action performed? Does the verification include both document review and on-site confirmation?",
            "Are audit records retained according to the procedure? Are audit records complete and traceable?",
        ],
        "audit_questions_ja": [
            "組織は、監査の計画及び実施、並びに監査結果の記録及び報告に関する責任及び要求事項を記述した手順を文書化しているか？監査された領域を担当する管理者は、検出された不適合及びその原因を除去するために必要な是正及び是正処置が過度な遅延なく取られることを確実にしているか？フォローアップ活動には取られた処置の検証及び検証結果の報告が含まれているか？記録は維持されているか？",
            "監査報告書、監査所見、フォローアップ処置は完全か？被監査領域の管理者は遅延なく是正処置を実施することが要求されているか？",
            "ISO 13485:2016 §8.2.4.2に従い、監査フォローアップ機構は文書化されているか？処置の有効性検証及び検証結果の報告が要求されているか？",
            "監査不適合は分類されているか（重大、軽微、観察事項）？各分類の処理優先順位は定義されているか？",
            "監査不適合に対する是正処置の実施期限はどのように追跡されているか？期限内に完了しない場合のエスカレーション手順は？",
            "是正処置の有効性検証はどのように実施されているか？検証には文書レビュー及び現場確認の両方が含まれているか？",
            "監査記録は手順に従って保管されているか？監査記録は完全で追跡可能か？",
        ],
        "expected_evidence_en": [
            "Audit procedure",
            "Audit findings tracking records",
        ],
        "expected_evidence_ja": [
            "監査手順書",
            "監査所見追跡記録",
        ],
    },
    "8.2.5": {
        "title": "過程之監督與量測",
        "title_en": "Monitoring and Measurement of Processes",
        "title_ja": "プロセスの監視及び測定",
        "audit_impact": "major",
        "audit_question": (
            "組織是否應用適當的方法監督及適用時量測品質管理系統過程？"
            "這些方法是否展示過程達成規劃結果的能力？"
            "當未達成規劃結果時，是否採取適當的矯正及矯正措施？"
        ),
        "audit_questions": [
            (
                "組織是否應用適當的方法監督及適用時量測品質管理系統過程？"
                "這些方法是否展示過程達成規劃結果的能力？"
                "當未達成規劃結果時，是否採取適當的矯正及矯正措施？"
            ),
            "過程監督的量測指標如何選定？指標失效時的替代監督機制為何？",
            "依 ISO 13485:2016 §8.2.5，組織是否應用適當方法監督和量測 QMS 過程，展示過程達成規劃結果的能力，且當未達成規劃結果時採取矯正措施？",
            "關鍵過程的績效指標（KPI）設定依據為何？指標的目標值和管制界限如何確定？",
            "過程監督數據的收集頻率和方法是否文件化？數據品質（如完整性、準確性）如何確保？",
            "過程績效數據如何定期彙整並用於管理決策？數據分析由誰負責且多久進行一次？",
            "當過程績效指標持續未達目標時，如何觸發系統性的根本原因分析和改善行動？",
        ],
        "expected_evidence": [
            "過程監督紀錄",
            "過程績效指標",
        ],
        "audit_question_en": "Does the organization apply suitable methods for the monitoring and, where applicable, measurement of the QMS processes? Do these methods demonstrate the ability of the processes to achieve planned results? When planned results are not achieved, are correction and corrective action taken, as appropriate?",
        "audit_question_ja": "組織は、品質マネジメントシステムプロセスの監視及び、該当する場合には、測定のための適切な方法を適用しているか？これらの方法は、プロセスが計画された結果を達成する能力を実証しているか？計画された結果が達成されない場合、適切に是正及び是正処置が取られているか？",
        "audit_questions_en": [
            "Does the organization apply suitable methods for the monitoring and, where applicable, measurement of the QMS processes? Do these methods demonstrate the ability of the processes to achieve planned results? When planned results are not achieved, are correction and corrective action taken, as appropriate?",
            "Are the process monitoring indicators well defined for each QMS process? Is the monitoring data collected continuously?",
            "Per ISO 13485:2016 §8.2.5, are suitable methods applied for monitoring and measurement of QMS processes? Are corrections and corrective actions taken when planned results are not achieved?",
            "How are process monitoring indicators (KPIs) set to be meaningful and quantifiable? Is the quantification method validated?",
            "Is the statistical process control (SPC) applied to critical processes? How is the sensitivity of detection of process variation?",
            "When process monitoring indicates abnormality, how is the corrective action initiated? Is the timeline for correction defined?",
            "Are the results of process monitoring reviewed in management reviews? Is the root cause analysis of continuously unachieved indicators conducted?",
        ],
        "audit_questions_ja": [
            "組織は、品質マネジメントシステムプロセスの監視及び、該当する場合には、測定のための適切な方法を適用しているか？これらの方法は、プロセスが計画された結果を達成する能力を実証しているか？計画された結果が達成されない場合、適切に是正及び是正処置が取られているか？",
            "プロセス監視指標は各品質マネジメントシステムプロセスについて適切に定義されているか？監視データは継続的に収集されているか？",
            "ISO 13485:2016 §8.2.5に従い、品質マネジメントシステムプロセスの監視及び測定のための適切な方法が適用されているか？計画された結果が達成されない場合、是正及び是正処置が取られているか？",
            "プロセス監視指標（KPI）は意味があり定量化可能か？定量化方法はバリデーションされているか？",
            "統計的プロセス管理（SPC）は重要プロセスに適用されているか？プロセス変動の検出感度は？",
            "プロセス監視で異常が示された場合、是正処置はどのように開始されるか？是正期限は定義されているか？",
            "プロセス監視の結果はマネジメントレビューでレビューされているか？継続的に未達となる指標の根本原因分析は実施されているか？",
        ],
        "expected_evidence_en": [
            "Process monitoring indicators",
            "Process monitoring records",
        ],
        "expected_evidence_ja": [
            "プロセス監視指標",
            "プロセス監視記録",
        ],
    },
    "8.2.6": {
        "title": "產品之監督與量測",
        "title_en": "Monitoring and Measurement of Products",
        "title_ja": "製品の監視及び測定",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否在產品實現的適當階段，依規劃安排監督與量測產品特性，"
            "以驗證產品要求已被滿足？"
            "是否維持符合驗收準則的證據及授權放行人員的紀錄？"
            "產品是否在所有規劃安排被圓滿完成後才予以放行？"
        ),
        "audit_questions": [
            (
                "組織是否在產品實現的適當階段，依規劃安排監督與量測產品特性，"
                "以驗證產品要求已被滿足？"
                "是否維持符合驗收準則的證據及授權放行人員的紀錄？"
                "產品是否在所有規劃安排被圓滿完成後才予以放行？"
            ),
            "抽樣計畫的統計依據為何？抽樣計畫是否定期重新評估以確保對過程變化的敏感度？",
            "依 ISO 13485:2016 §8.2.6，組織是否在產品實現各適當階段監督和量測產品特性，且授權放行人員的紀錄是否維持？",
            "最終產品放行前，所有規劃的檢驗和測試是否均已圓滿完成？緊急放行的管制條件和核准程序為何？",
            "在製品（In-process）的檢驗點如何設置？如何確保在製品的品質狀態在生產過程中始終可識別？",
            "成品測試的設備是否定期校正，且測試環境是否符合規範要求？如何確保測試結果的可靠性？",
            "批次放行決策基準（如允收品質界限 AQL）的設定依據為何？批次拒收後的處置程序為何？",
        ],
        "expected_evidence": [
            "成品檢驗/測試程序書",
            "檢驗/測試紀錄",
            "放行核准紀錄",
        ],
        "audit_question_en": "Does the organization monitor and measure the characteristics of the product to verify that product requirements have been met? Is this carried out at appropriate stages of the product realization process in accordance with the planned and documented arrangements? Is evidence of conformity with the acceptance criteria maintained? Do the records indicate the person(s) authorizing the release of product? Is the release of product and delivery of service not to proceed until the planned and documented arrangements have been satisfactorily completed?",
        "audit_question_ja": "組織は、製品要求事項が満たされたことを検証するために、製品の特性を監視し測定しているか？これは、計画され文書化された取決めに従って、製品実現プロセスの適切な段階で実施されているか？合否判定基準への適合の証拠は維持されているか？記録は製品出荷を許可する者を示しているか？計画され文書化された取決めが満足に完了するまで、製品の出荷及びサービスの提供は進められないことになっているか？",
        "audit_questions_en": [
            "Does the organization monitor and measure the characteristics of the product to verify that product requirements have been met? Is this carried out at appropriate stages of the product realization process in accordance with the planned and documented arrangements? Is evidence of conformity with the acceptance criteria maintained? Do the records indicate the person(s) authorizing the release of product? Is the release of product and delivery of service not to proceed until the planned and documented arrangements have been satisfactorily completed?",
            "Are the product monitoring and measurement stages defined (incoming inspection, in-process inspection, final inspection)? Are the records of each stage complete?",
            "Per ISO 13485:2016 §8.2.6, is the product monitoring and measurement conducted at appropriate stages, with evidence of conformity to acceptance criteria maintained, and the releasing person identified in the records?",
            "Are the sampling plan and acceptance criteria for product inspection risk-based? Is the statistical basis adequate?",
            "Is the product release authority authority clearly defined? Can the released person be identified in the records?",
            "For non-conformities detected in product monitoring, is the handling procedure documented (acceptance under concession, rework, scrap)?",
            "Is pre-release satisfactorily completion of all planned arrangements verified before product release? What is the verification procedure?",
        ],
        "audit_questions_ja": [
            "組織は、製品要求事項が満たされたことを検証するために、製品の特性を監視し測定しているか？これは、計画され文書化された取決めに従って、製品実現プロセスの適切な段階で実施されているか？合否判定基準への適合の証拠は維持されているか？記録は製品出荷を許可する者を示しているか？計画され文書化された取決めが満足に完了するまで、製品の出荷及びサービスの提供は進められないことになっているか？",
            "製品監視及び測定の段階は定義されているか（受入検査、工程内検査、最終検査）？各段階の記録は完全か？",
            "ISO 13485:2016 §8.2.6に従い、製品監視及び測定は適切な段階で実施され、合否判定基準への適合の証拠が維持され、出荷許可者が記録で識別されているか？",
            "製品検査のサンプリング計画及び合否判定基準はリスクに基づいているか？統計的根拠は十分か？",
            "製品出荷権限は明確に定義されているか？出荷者は記録で識別可能か？",
            "製品監視で検出された不適合に対する処理手順は文書化されているか（特別採用、手直し、廃棄等）？",
            "製品出荷前、すべての計画された取決めの満足な完了は検証されているか？検証手順は？",
        ],
        "expected_evidence_en": [
            "Inspection and test records",
            "Release authorization records",
            "Product acceptance criteria",
        ],
        "expected_evidence_ja": [
            "検査・試験記録",
            "出荷許可記録",
            "製品合否判定基準",
        ],
    },
    "8.3": {
        "title": "不合格品管制 — 一般",
        "title_en": "Control of Nonconforming Products — General",
        "title_ja": "不適合製品の管理 — 一般",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否確保不符合產品要求的產品被識別並予以管制，以防止其非預期使用或交付？"
            "是否建立不合格品管制及相關責任與權限的文件化程序？"
        ),
        "audit_questions": [
            (
                "組織是否確保不符合產品要求的產品被識別並予以管制，以防止其非預期使用或交付？"
                "是否建立不合格品管制及相關責任與權限的文件化程序？"
            ),
            "不合格品的識別標示與隔離措施如何防止意外使用？不合格品處理的決策授權層級為何？",
            "依 ISO 13485:2016 §8.3，組織是否建立不合格品管制的文件化程序，確保不合格品被識別並防止非預期使用或交付？",
            "不合格品隔離區（Quarantine Area）的設置方式為何？如何確保隔離的有效性（防止人員誤取）？",
            "不合格品的分類（如廢棄、返工、讓步接收）決策者資格要求為何？各類決策的記錄要求為何？",
            "不合格品數量和類型的趨勢如何監測？趨勢分析結果是否被用於觸發 CAPA 或過程改善？",
            "電子化不合格品管理系統（如 NCR 系統）的使用方式為何？紙本和電子記錄如何保持一致性？",
        ],
        "expected_evidence": [
            "不合格品管制程序書",
            "不合格品處理紀錄",
        ],
        "audit_question_en": "Does the organization ensure that product which does not conform to product requirements is identified and controlled to prevent its unintended use or delivery? Does the organization document a procedure to define the controls and related responsibilities and authorities for the identification, documentation, segregation, evaluation, and disposition of nonconforming product?",
        "audit_question_ja": "組織は、製品要求事項に適合しない製品が、その意図しない使用又は引渡しを防止するために識別され管理されることを確実にしているか？組織は、不適合製品の識別、文書化、分離、評価、及び処理のための管理並びに関連する責任及び権限を定義する手順を文書化しているか？",
        "audit_questions_en": [
            "Does the organization ensure that product which does not conform to product requirements is identified and controlled to prevent its unintended use or delivery? Does the organization document a procedure to define the controls and related responsibilities and authorities for the identification, documentation, segregation, evaluation, and disposition of nonconforming product?",
            "Is the non-conforming product control procedure complete? Does it cover identification, documentation, segregation, evaluation, and disposition?",
            "Per ISO 13485:2016 §8.3, does the organization have a documented procedure for identification, documentation, segregation, evaluation, and disposition of non-conforming products?",
            "Is the identification (e.g., red tag, quarantine area) of non-conforming products clearly defined? Can it effectively prevent unintended use?",
            "How are the authorities for non-conforming product disposition (acceptance under concession, rework, scrap) distributed among different roles?",
            "How are non-conforming products handled during manufacturing, pre-shipment, and post-shipment stages? Are the procedures different for each stage?",
            "When non-conforming products are disposed, are the records complete? Does the record include all rationales, decisions, and authorizing personnel?",
        ],
        "audit_questions_ja": [
            "組織は、製品要求事項に適合しない製品が、その意図しない使用又は引渡しを防止するために識別され管理されることを確実にしているか？組織は、不適合製品の識別、文書化、分離、評価、及び処理のための管理並びに関連する責任及び権限を定義する手順を文書化しているか？",
            "不適合製品管理手順は完全か？識別、文書化、分離、評価、処理を網羅しているか？",
            "ISO 13485:2016 §8.3に従い、組織は不適合製品の識別、文書化、分離、評価、処理のための文書化手順を有しているか？",
            "不適合製品の識別（赤タグ、隔離区域等）は明確に定義されているか？意図しない使用を有効に防止できるか？",
            "不適合製品の処理（特別採用、手直し、廃棄等）に対する権限は異なる役割間でどのように配分されているか？",
            "製造中、出荷前、出荷後の各段階における不適合製品はどのように処理されているか？各段階で手順は異なるか？",
            "不適合製品が処理された場合、記録は完全か？記録にはすべての根拠、決定、承認者が含まれているか？",
        ],
        "expected_evidence_en": [
            "Non-conforming product control procedure",
            "Non-conforming product records",
        ],
        "expected_evidence_ja": [
            "不適合製品管理手順書",
            "不適合製品記録",
        ],
    },
    "8.3.1": {
        "title": "不合格品管制 — 交付前",
        "title_en": "Control of Nonconforming Products — Before Delivery",
        "title_ja": "不適合製品の管理 — 引渡し前",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否以一種或多種方式處理不合格品：採取措施消除已發現的不符合、"
            "授權讓步使用/放行/接收、採取措施排除其原來預期使用或應用？"
            "是否維持不符合性質及所採取後續措施的紀錄？"
        ),
        "audit_questions": [
            (
                "組織是否以一種或多種方式處理不合格品：採取措施消除已發現的不符合、"
                "授權讓步使用/放行/接收、採取措施排除其原來預期使用或應用？"
                "是否維持不符合性質及所採取後續措施的紀錄？"
            ),
            "讓步接收的授權層級與限制條件為何？如何追蹤讓步接收的累積頻率以避免系統性問題被忽視？",
            "依 ISO 13485:2016 §8.3，在交付前發現的不合格品，組織是否以一種或多種方式處理：消除不符合、授權讓步使用、或排除其原本預期用途？",
            "讓步接收（Concession/Deviation）是否要求風險評估作為決策依據？評估範本或標準是否存在？",
            "不合格品的返工程序是否確保返工品再次經過原有（或更嚴格）的驗收準則檢驗？",
            "不合格品處理紀錄（如 NCR）是否包含不符合描述、根本原因初評、處置決策及核准人？紀錄格式是否標準化？",
            "不合格品的廢棄處置（包含識別、隔離和最終處置）是否有防止廢棄品被誤用的管控措施？",
        ],
        "expected_evidence": [
            "不合格品處理/讓步紀錄",
            "不合格品識別標示",
        ],
        "audit_question_en": "Does the organization establish actions to deal with nonconforming product by one or more of the following ways: taking action to eliminate the detected nonconformity; taking action to preclude its original intended use or application; authorizing its use, release, or acceptance under concession? Does the organization ensure that nonconforming product is accepted by concession only if the justification is provided, approval is obtained, and applicable regulatory requirements are met?",
        "audit_question_ja": "組織は、次の1つ又はそれ以上の方法で不適合製品に対処するための処置を確立しているか。検出された不適合を除去するための処置を取ること、その当初の意図された使用又は適用を排除するための処置を取ること、特別採用の下での使用、出荷、又は受入を許可すること。組織は、正当化が提供され、承認が得られ、適用される規制要求事項が満たされた場合にのみ、不適合製品が特別採用によって受け入れられることを確実にしているか？",
        "audit_questions_en": [
            "Does the organization establish actions to deal with nonconforming product by one or more of the following ways: taking action to eliminate the detected nonconformity; taking action to preclude its original intended use or application; authorizing its use, release, or acceptance under concession? Does the organization ensure that nonconforming product is accepted by concession only if the justification is provided, approval is obtained, and applicable regulatory requirements are met?",
            "Are the actions for non-conforming products documented (eliminate, preclude use, accept under concession)? Are approval levels clearly defined?",
            "Per ISO 13485:2016 §8.3.1, are non-conforming product actions documented, covering elimination, use/application prohibition, and concession acceptance (only with justification and approval)?",
            "When non-conforming product is accepted under concession, are the justification, approval, and regulatory compliance documented?",
            "Does the concession acceptance procedure consider the potential risk to patients/users? Is the risk assessment documented?",
            "What are the criteria for declaring a product to be precluded from its original intended use? Is the alternative use documented?",
            "When non-conforming product is eliminated (e.g., scrapped), how is the disposal documented? Is there a traceable scrap record?",
        ],
        "audit_questions_ja": [
            "組織は、次の1つ又はそれ以上の方法で不適合製品に対処するための処置を確立しているか。検出された不適合を除去するための処置を取ること、その当初の意図された使用又は適用を排除するための処置を取ること、特別採用の下での使用、出荷、又は受入を許可すること。組織は、正当化が提供され、承認が得られ、適用される規制要求事項が満たされた場合にのみ、不適合製品が特別採用によって受け入れられることを確実にしているか？",
            "不適合製品に対する処置は文書化されているか（除去、使用排除、特別採用受入）？承認レベルは明確に定義されているか？",
            "ISO 13485:2016 §8.3.1に従い、不適合製品の処置は文書化されているか、除去、使用／適用禁止、特別採用受入（正当化及び承認の場合のみ）を網羅しているか？",
            "不適合製品が特別採用で受け入れられる場合、正当化、承認、規制適合性は文書化されているか？",
            "特別採用受入手順は患者／利用者への潜在的リスクを考慮しているか？リスク評価は文書化されているか？",
            "製品が当初の意図された使用から排除されると宣言される基準は何か？代替使用は文書化されているか？",
            "不適合製品が除去される場合（廃棄等）、処分はどのように文書化されているか？追跡可能な廃棄記録はあるか？",
        ],
        "expected_evidence_en": [
            "Non-conforming product action procedure",
            "Concession approval records",
        ],
        "expected_evidence_ja": [
            "不適合製品処置手順書",
            "特別採用承認記録",
        ],
    },
    "8.3.2": {
        "title": "不合格品管制 — 交付後",
        "title_en": "Control of Nonconforming Products — After Delivery",
        "title_ja": "不適合製品の管理 — 引渡し後",
        "audit_impact": "critical",
        "audit_question": (
            "當交付或開始使用後才偵測到不合格品時，組織是否採取與不符合的影響"
            "（或潛在影響）相稱的措施？"
            "是否維持所採取措施的紀錄？"
        ),
        "audit_questions": [
            (
                "當交付或開始使用後才偵測到不合格品時，組織是否採取與不符合的影響"
                "（或潛在影響）相稱的措施？"
                "是否維持所採取措施的紀錄？"
            ),
            "市場不合格品召回決策的觸發條件與評估流程為何？如何確保召回行動的有效性被追蹤？",
            "依 ISO 13485:2016 §8.3，交付後發現不合格品時，組織是否採取與不符合影響（或潛在影響）相稱的措施，並維持所採取措施的紀錄？",
            "市場反饋（如客訴、服務報告）中發現的可能不合格品，如何觸發正式的不合格品評估程序？",
            "當評估確認需要採取 Field Safety Corrective Action（FSCA）時，行動計畫的制定和核准流程為何？",
            "召回行動的執行效率如何評估（如召回率、完成率）？評估結果如何被報告給管理階層？",
            "交付後不合格品的紀錄（如事件報告、FSCA 文件）保存期限和存放位置是否符合法規要求？",
        ],
        "expected_evidence": [
            "交付後不合格品處理紀錄",
            "產品召回/矯正程序（如適用）",
        ],
        "audit_question_en": "Does the organization ensure that nonconforming product detected before delivery is either corrected or excluded from its intended use? Does the organization retain records including the nature of the nonconformities, the actions taken, and concessions obtained?",
        "audit_question_ja": "組織は、引渡し前に検出された不適合製品が、是正されるか又はその意図された使用から除外されることを確実にしているか？組織は、不適合の性質、取られた処置、及び得られた特別採用を含む記録を保持しているか？",
        "audit_questions_en": [
            "Does the organization ensure that nonconforming product detected before delivery is either corrected or excluded from its intended use? Does the organization retain records including the nature of the nonconformities, the actions taken, and concessions obtained?",
            "How is the non-conforming product detected before delivery handled? Is correction or exclusion from intended use systematically implemented?",
            "Per ISO 13485:2016 §8.3.2, are non-conforming products detected before delivery either corrected or excluded from intended use? Are records (nature of non-conformity, actions, concessions) retained?",
            "When non-conforming product is corrected by rework, is the rework validated? Is the reworked product subject to the same acceptance criteria?",
            "How is the effectiveness of correction/exclusion verified before re-release? Is the re-inspection documented?",
            "Do the records include the nature of the non-conformities, actions taken, and concessions obtained? Are they complete and traceable?",
            "Is the impact of the non-conformity on other related batches or units assessed? How are the findings extended?",
        ],
        "audit_questions_ja": [
            "組織は、引渡し前に検出された不適合製品が、是正されるか又はその意図された使用から除外されることを確実にしているか？組織は、不適合の性質、取られた処置、及び得られた特別採用を含む記録を保持しているか？",
            "引渡し前に検出された不適合製品はどのように処理されているか？是正又は意図された使用からの除外は体系的に実施されているか？",
            "ISO 13485:2016 §8.3.2に従い、引渡し前に検出された不適合製品は是正される又は意図された使用から除外されるか？記録（不適合の性質、処置、特別採用）は保管されているか？",
            "不適合製品が手直しで是正される場合、手直しはバリデーションされているか？手直し製品は同じ合否判定基準の対象か？",
            "再出荷前、是正／除外の有効性はどのように検証されているか？再検査は文書化されているか？",
            "記録には不適合の性質、取られた処置、得られた特別採用が含まれているか？完全で追跡可能か？",
            "不適合が他の関連バッチ又はユニットに与える影響は評価されているか？知見はどのように展開されているか？",
        ],
        "expected_evidence_en": [
            "Pre-delivery non-conformity records",
            "Correction/exclusion records",
        ],
        "expected_evidence_ja": [
            "引渡し前不適合記録",
            "是正／除外記録",
        ],
    },
    "8.3.3": {
        "title": "不合格品管制 — 讓步",
        "title_en": "Control of Nonconforming Products — Concession",
        "title_ja": "不適合製品の管理 — 特別採用",
        "audit_impact": "critical",
        "audit_question": (
            "讓步使用/放行/接收是否只在滿足法規要求、"
            "經授權人員核准、且有理由說明的情況下才被接受？"
        ),
        "audit_questions": [
            (
                "讓步使用/放行/接收是否只在滿足法規要求、"
                "經授權人員核准、且有理由說明的情況下才被接受？"
            ),
            "讓步授權人員的資格要求為何？讓步決策是否有獨立審查機制以防止授權濫用？",
            "依 ISO 13485:2016 §8.3，讓步使用/放行/接收是否僅在符合法規要求、經授權人員核准且有理由說明的情況下才被接受？",
            "顧客讓步（Customer Concession/Waiver）的申請和核准程序為何？顧客核准文件如何保存？",
            "讓步接收的記錄是否清楚說明不符合的性質、影響評估、批准理由及核准人員？",
            "對於需要法規主管機關批准或通知的讓步，識別和通報程序為何？是否有相關案例記錄？",
            "讓步數量和類型的統計分析是否定期進行？是否設有讓步接受率的警戒門檻以觸發系統性改善？",
        ],
        "expected_evidence": [
            "讓步核准紀錄",
            "讓步理由說明文件",
        ],
        "audit_question_en": "When nonconforming product is detected after delivery or use has started, does the organization take action appropriate to the effects, or potential effects, of the nonconformity? Does the organization retain records of the actions taken? Does the organization document procedures for issuing advisory notices in accordance with applicable regulatory requirements?",
        "audit_question_ja": "引渡し後又は使用開始後に不適合製品が検出された場合、組織は不適合の影響又は潜在的影響に適切な処置を取っているか？組織は取られた処置の記録を保持しているか？組織は、適用される規制要求事項に従って勧告通知を発行する手順を文書化しているか？",
        "audit_questions_en": [
            "When nonconforming product is detected after delivery or use has started, does the organization take action appropriate to the effects, or potential effects, of the nonconformity? Does the organization retain records of the actions taken? Does the organization document procedures for issuing advisory notices in accordance with applicable regulatory requirements?",
            "When non-conforming products are detected post-delivery, are appropriate actions taken (recall, advisory notice, field safety corrective action)? Are records retained?",
            "Per ISO 13485:2016 §8.3.3, when non-conforming product is detected after delivery, are actions appropriate to effects taken? Is the advisory notice procedure documented?",
            "Is the advisory notice procedure consistent with applicable regulatory requirements (e.g., FDA recall, EU MDR FSCA)?",
            "When products need to be recalled, is the recall effectiveness tracked? What is the recall effectiveness threshold?",
            "How is the timeline for responding to post-delivery non-conformities? Does it meet regulatory timeline requirements?",
            "How is the post-delivery non-conformity information shared with distributors and users? Is the communication traceable?",
        ],
        "audit_questions_ja": [
            "引渡し後又は使用開始後に不適合製品が検出された場合、組織は不適合の影響又は潜在的影響に適切な処置を取っているか？組織は取られた処置の記録を保持しているか？組織は、適用される規制要求事項に従って勧告通知を発行する手順を文書化しているか？",
            "引渡し後に不適合製品が検出された場合、適切な処置（リコール、勧告通知、現地安全是正処置等）が取られているか？記録は保管されているか？",
            "ISO 13485:2016 §8.3.3に従い、引渡し後に不適合製品が検出された場合、影響に応じた処置が取られているか？勧告通知手順は文書化されているか？",
            "勧告通知手順は適用法規制要求事項（FDA Recall、EU MDR FSCA等）と整合しているか？",
            "製品のリコールが必要な場合、リコールの有効性は追跡されているか？リコール有効性の閾値は何か？",
            "引渡し後不適合への対応期限は？規制期限要求を満たしているか？",
            "引渡し後不適合情報は流通業者及び利用者とどのように共有されているか？コミュニケーションは追跡可能か？",
        ],
        "expected_evidence_en": [
            "Post-delivery non-conformity handling procedure",
            "Advisory notice records (if applicable)",
        ],
        "expected_evidence_ja": [
            "引渡し後不適合処理手順書",
            "勧告通知記録（該当する場合）",
        ],
    },
    "8.3.4": {
        "title": "不合格品管制 — 返工",
        "title_en": "Control of Nonconforming Products — Rework",
        "title_ja": "不適合製品の管理 — 手直し",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否依文件化程序進行返工？"
            "返工後是否依據原有的或更嚴格的準則重新檢查？"
            "返工是否考量其對產品的不利影響？"
        ),
        "audit_questions": [
            (
                "組織是否依文件化程序進行返工？"
                "返工後是否依據原有的或更嚴格的準則重新檢查？"
                "返工是否考量其對產品的不利影響？"
            ),
            "返工對產品的潛在風險如何在返工前評估？返工作業指導書的版本管制如何確保？",
            "依 ISO 13485:2016 §8.3，組織是否依文件化程序進行返工，且返工後依據原有（或更嚴格）的準則重新檢查，並考量返工對產品的不利影響？",
            "返工前是否進行可行性評估，以確認返工不會對產品安全性、有效性或符合性造成不利影響？",
            "返工紀錄是否包含返工的原因、批准、方法、操作人員及再檢驗結果？紀錄與原始批次紀錄如何連結？",
            "返工過程使用的工具、設備和材料是否受到管制，確保其品質狀態符合返工要求？",
            "返工品的最終驗收標準是否與正常品相同？若有差異，差異的理由和法規符合性如何評估？",
        ],
        "expected_evidence": [
            "返工程序書",
            "返工紀錄",
            "返工後檢驗紀錄",
        ],
        "audit_question_en": "Does the organization document procedures for rework? In determining rework activities, does the organization consider the potential adverse effect of rework on the product? Is rework carried out in accordance with work instructions that have undergone the same review and approval as the original work instructions? After the completion of rework, does product undergo reverification or revalidation to ensure that it meets the applicable acceptance criteria and regulatory requirements? Are records of rework maintained?",
        "audit_question_ja": "組織は手直しの手順を文書化しているか？手直し活動を決定する際、組織は手直しの製品への潜在的な有害影響を考慮しているか？手直しは、当初の作業指示書と同じレビュー及び承認を受けた作業指示書に従って実施されているか？手直しの完了後、製品は適用される合否判定基準及び規制要求事項を満たすことを確実にするため、再検証又は再妥当性確認を受けているか？手直しの記録は維持されているか？",
        "audit_questions_en": [
            "Does the organization document procedures for rework? In determining rework activities, does the organization consider the potential adverse effect of rework on the product? Is rework carried out in accordance with work instructions that have undergone the same review and approval as the original work instructions? After the completion of rework, does product undergo reverification or revalidation to ensure that it meets the applicable acceptance criteria and regulatory requirements? Are records of rework maintained?",
            "Is the rework procedure documented? Are the potential adverse effects on the product considered and mitigated?",
            "Per ISO 13485:2016 §8.3.4, is the rework procedure documented, with rework instructions approved at the same level as original instructions, and re-verification/re-validation performed?",
            "Are rework instructions reviewed and approved at the same level as the original work instructions? Is the history preserved?",
            "Is the re-verification/re-validation after rework comprehensive? Does it cover all acceptance criteria affected by rework?",
            "Are rework records complete? Do they include rework reason, method, operator, inspection results, and verification/validation results?",
            "How is the impact assessment of the rework performed? Is the potential adverse effect to the product considered and documented?",
        ],
        "audit_questions_ja": [
            "組織は手直しの手順を文書化しているか？手直し活動を決定する際、組織は手直しの製品への潜在的な有害影響を考慮しているか？手直しは、当初の作業指示書と同じレビュー及び承認を受けた作業指示書に従って実施されているか？手直しの完了後、製品は適用される合否判定基準及び規制要求事項を満たすことを確実にするため、再検証又は再妥当性確認を受けているか？手直しの記録は維持されているか？",
            "手直し手順は文書化されているか？製品への潜在的有害影響は考慮され緩和されているか？",
            "ISO 13485:2016 §8.3.4に従い、手直し手順は文書化され、手直し指示書は当初の指示書と同じレベルで承認され、再検証／再妥当性確認が実施されているか？",
            "手直し指示書は当初の作業指示書と同じレベルでレビューされ承認されているか？履歴は保管されているか？",
            "手直し後の再検証／再妥当性確認は包括的か？手直しの影響を受けるすべての合否判定基準を網羅しているか？",
            "手直し記録は完全か？手直し理由、方法、作業者、検査結果、検証／妥当性確認結果を含むか？",
            "手直しの影響評価はどのように実施されているか？製品への潜在的有害影響は考慮され文書化されているか？",
        ],
        "expected_evidence_en": [
            "Rework procedure",
            "Rework records",
            "Re-verification/re-validation records",
        ],
        "expected_evidence_ja": [
            "手直し手順書",
            "手直し記録",
            "再検証／再妥当性確認記録",
        ],
    },
    "8.4": {
        "title": "數據分析",
        "title_en": "Data Analysis",
        "title_ja": "データの分析",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定、蒐集及分析適當的數據，以展示品質管理系統的適切性及有效性？"
            "數據分析是否包含回饋、產品符合性、過程與產品趨勢、供應商、稽核、"
            "及服務報告（適用時）等方面的資料？"
        ),
        "audit_questions": [
            (
                "組織是否決定、蒐集及分析適當的數據，以展示品質管理系統的適切性及有效性？"
                "數據分析是否包含回饋、產品符合性、過程與產品趨勢、供應商、稽核、"
                "及服務報告（適用時）等方面的資料？"
            ),
            "數據分析如何確保其代表性與可靠性？分析結果的解讀是否有書面準則以避免主觀判斷？",
            "資料分析的範疇是否涵蓋所有 ISO 13485:2016 §8.4 要求的來源（供應商績效、過程績效、產品品質、顧客回饋）？",
            "依 ISO 13485:2016 §8.4，分析結果是否用於識別改善機會並驅動 CAPA？最近一個因資料分析啟動的 CAPA 為何？",
            "趨勢分析的工具與方法是否文件化？分析結果是否在管理審查中報告？",
            "產品品質趨勢（如不良品率、退貨率）的管制界限如何設定？超出管制界限時的反應計劃為何？",
            "依 ISO 13485:2016 §8.4，資料分析是否包含外部資料（如市場抱怨、競爭者警示）？如何識別並納入分析？",
        ],
        "expected_evidence": [
            "數據分析程序書",
            "品質指標/趨勢報告",
            "統計分析紀錄",
        ],
        "audit_question_en": "Does the organization document procedures to determine, collect, and analyse appropriate data to demonstrate the suitability, adequacy, and effectiveness of the QMS? Does the organization determine appropriate methods, including statistical techniques and the extent of their use? Does the analysis of data include data generated as a result of monitoring and measurement and from other relevant sources including feedback, conformity to product requirements, characteristics and trends of processes and products, suppliers, audits, and service reports, where appropriate?",
        "audit_question_ja": "組織は、品質マネジメントシステムの適合性、妥当性、及び有効性を実証するために適切なデータを決定し、収集し、分析する手順を文書化しているか？組織は、統計的手法及びその使用の程度を含む適切な方法を決定しているか？データの分析には、監視及び測定並びにその他の関連する情報源から生成されたデータ（適切な場合には、フィードバック、製品要求事項への適合性、プロセス及び製品の特性及び傾向、供給者、監査、並びにサービス報告を含む）が含まれているか？",
        "audit_questions_en": [
            "Does the organization document procedures to determine, collect, and analyse appropriate data to demonstrate the suitability, adequacy, and effectiveness of the QMS? Does the organization determine appropriate methods, including statistical techniques and the extent of their use? Does the analysis of data include data generated as a result of monitoring and measurement and from other relevant sources including feedback, conformity to product requirements, characteristics and trends of processes and products, suppliers, audits, and service reports, where appropriate?",
            "Is the data analysis procedure documented? Does it cover all data sources (feedback, product conformity, process/product trends, suppliers, audits, service reports)?",
            "Per ISO 13485:2016 §8.4, does the data analysis procedure cover QMS effectiveness demonstration, using statistical techniques to analyze data from all relevant sources?",
            "What statistical techniques are applied to data analysis? Is the technique selection appropriate for the data characteristics?",
            "How are the data analysis outputs used in management reviews, CAPA decisions, and QMS improvements?",
            "Are the data analysis conclusions actionable? Is the root cause analysis of trend abnormalities performed?",
            "Is the data quality (completeness, accuracy, timeliness) assessed before analysis? How is data quality assurance mechanism designed?",
        ],
        "audit_questions_ja": [
            "組織は、品質マネジメントシステムの適合性、妥当性、及び有効性を実証するために適切なデータを決定し、収集し、分析する手順を文書化しているか？組織は、統計的手法及びその使用の程度を含む適切な方法を決定しているか？データの分析には、監視及び測定並びにその他の関連する情報源から生成されたデータ（適切な場合には、フィードバック、製品要求事項への適合性、プロセス及び製品の特性及び傾向、供給者、監査、並びにサービス報告を含む）が含まれているか？",
            "データ分析手順は文書化されているか？すべてのデータ源（フィードバック、製品適合性、プロセス／製品傾向、供給者、監査、サービス報告）を網羅しているか？",
            "ISO 13485:2016 §8.4に従い、データ分析手順は品質マネジメントシステム有効性の実証を網羅し、統計的手法を用いてすべての関連データ源からのデータを分析しているか？",
            "どの統計的手法がデータ分析に適用されているか？手法の選定はデータ特性に対して適切か？",
            "データ分析のアウトプットはマネジメントレビュー、CAPA決定、品質マネジメントシステム改善にどのように使用されているか？",
            "データ分析の結論は実行可能か？傾向異常の根本原因分析は実施されているか？",
            "データ品質（完全性、正確性、適時性）は分析前に評価されているか？データ品質保証機構はどのように設計されているか？",
        ],
        "expected_evidence_en": [
            "Data analysis procedure",
            "Data analysis report",
            "Statistical analysis records",
        ],
        "expected_evidence_ja": [
            "データ分析手順書",
            "データ分析報告書",
            "統計分析記録",
        ],
    },
    "8.5.1": {
        "title": "改善 — 一般",
        "title_en": "Improvement — General",
        "title_ja": "改善 — 一般",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否識別並實施任何變更，以確保並維持品質管理系統的持續適切性及有效性？"
            "改善是否透過品質政策、品質目標、稽核結果、數據分析、矯正措施、"
            "預防措施及管理審查來實現？"
        ),
        "audit_questions": [
            (
                "組織是否識別並實施任何變更，以確保並維持品質管理系統的持續適切性及有效性？"
                "改善是否透過品質政策、品質目標、稽核結果、數據分析、矯正措施、"
                "預防措施及管理審查來實現？"
            ),
            "持續改善的優先順序如何決定？改善行動的資源投入如何與其潛在效益進行評估？",
            "依 ISO 13485:2016 §8.5.1，組織是否透過品質政策、品質目標、稽核結果、數據分析、矯正措施、預防措施及管理審查，識別並實施改善以確保 QMS 的持續適切性和有效性？",
            "持續改善的文化如何在組織中推廣？員工改善提案（如 Kaizen 建議）的機制是否存在且被積極使用？",
            "持續改善行動的追蹤系統為何？已識別的改善機會如何確保不被忽視或遺忘？",
            "改善績效的指標為何（如 CAPA 完成率、客訴趨勢改善、過程能力指數）？這些指標如何在管理審查中報告？",
            "組織如何學習業界最佳實踐（Benchmarking）或法規主管機關的查廠反饋，並將學習成果轉化為改善行動？",
        ],
        "expected_evidence": [
            "持續改善紀錄",
            "改善提案/行動計畫",
        ],
        "audit_question_en": "Does the organization identify and implement any changes necessary to ensure and maintain the continued suitability, adequacy, and effectiveness of the QMS as well as medical device safety and performance through the use of the quality policy, quality objectives, audit results, post-market surveillance, analysis of data, corrective actions, preventive actions, and management review?",
        "audit_question_ja": "組織は、品質方針、品質目標、監査結果、市販後調査、データ分析、是正処置、予防処置、及びマネジメントレビューの使用を通して、品質マネジメントシステムの継続的な適合性、妥当性、及び有効性、並びに医療機器の安全性及び性能を確実にし維持するために必要なあらゆる変更を識別し実施しているか？",
        "audit_questions_en": [
            "Does the organization identify and implement any changes necessary to ensure and maintain the continued suitability, adequacy, and effectiveness of the QMS as well as medical device safety and performance through the use of the quality policy, quality objectives, audit results, post-market surveillance, analysis of data, corrective actions, preventive actions, and management review?",
            "Is the continual improvement mechanism systematic? Does it integrate QMS inputs from quality policy, objectives, audits, PMS, data analysis, CAPA, and management reviews?",
            "Per ISO 13485:2016 §8.5.1, does the organization identify and implement changes to maintain continued QMS suitability, adequacy, effectiveness, and device safety/performance?",
            "How are improvement opportunities identified? Is the identification based on data analysis and trend reviews?",
            "Are improvement projects/activities documented and tracked? How is the effectiveness of improvement verified?",
            "How are improvements prioritized? Are the criteria based on impact and feasibility?",
            "Is the continual improvement culture established in the organization? Are employees encouraged to propose improvement suggestions?",
        ],
        "audit_questions_ja": [
            "組織は、品質方針、品質目標、監査結果、市販後調査、データ分析、是正処置、予防処置、及びマネジメントレビューの使用を通して、品質マネジメントシステムの継続的な適合性、妥当性、及び有効性、並びに医療機器の安全性及び性能を確実にし維持するために必要なあらゆる変更を識別し実施しているか？",
            "継続的改善機構は体系的か？品質方針、目標、監査、市販後調査、データ分析、CAPA、マネジメントレビューからの品質マネジメントシステムインプットを統合しているか？",
            "ISO 13485:2016 §8.5.1に従い、組織は品質マネジメントシステムの継続的な適合性、妥当性、有効性、並びに機器の安全性／性能を維持するために変更を識別し実施しているか？",
            "改善機会はどのように識別されているか？識別はデータ分析及び傾向レビューに基づいているか？",
            "改善プロジェクト／活動は文書化され追跡されているか？改善の有効性はどのように検証されているか？",
            "改善はどのように優先順位付けされているか？基準は影響度及び実現可能性に基づいているか？",
            "継続的改善の文化は組織内で確立されているか？従業員は改善提案の提出を奨励されているか？",
        ],
        "expected_evidence_en": [
            "Continual improvement records",
            "Improvement project tracking",
        ],
        "expected_evidence_ja": [
            "継続的改善記録",
            "改善プロジェクト追跡記録",
        ],
    },
    "8.5.2": {
        "title": "矯正措施",
        "title_en": "Corrective Action",
        "title_ja": "是正処置",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否採取措施消除不符合的原因以防止再發生？"
            "矯正措施是否與所遭遇的不符合影響相稱？"
            "是否建立文件化程序，規定審查不符合（含客訴）、判定不符合的原因、"
            "評估確保不符合不再發生的行動需要、規劃與文件化行動並實施、"
            "驗證措施有效性、以及審查所採取的矯正措施及其有效性？"
        ),
        "audit_questions": [
            (
                "組織是否採取措施消除不符合的原因以防止再發生？"
                "矯正措施是否與所遭遇的不符合影響相稱？"
                "是否建立文件化程序，規定審查不符合（含客訴）、判定不符合的原因、"
                "評估確保不符合不再發生的行動需要、規劃與文件化行動並實施、"
                "驗證措施有效性、以及審查所採取的矯正措施及其有效性？"
            ),
            "根本原因分析的方法選擇依據為何？CAPA 的有效性驗證週期如何確定？若根本原因無法完全消除，剩餘風險如何管控？",
            "矯正措施的根本原因分析方法是否文件化（如 5-Why、魚骨圖）？最近一件重大 CAPA 使用了哪種方法？",
            "依 ISO 13485:2016 §8.5.2，矯正措施的有效性驗證是否在關閉前完成？驗證方式為何？",
            "CAPA 系統是否追蹤每件案例的根本原因、措施、完成日期、責任人？是否有逾期未關閉的案例？",
            "矯正措施是否定期被彙整並於管理審查中報告？最近一次管理審查中矯正措施的結案率為何？",
            "依 ISO 13485:2016 §8.5.2(f)，矯正措施是否在必要時更新風險管理文件？風險更新的觸發標準為何？",
        ],
        "expected_evidence": [
            "矯正措施程序書 (CAPA)",
            "CAPA 紀錄",
            "根本原因分析紀錄",
            "有效性驗證紀錄",
        ],
        "audit_question_en": "Does the organization take action to eliminate the cause of nonconformities in order to prevent recurrence? Are corrective actions appropriate to the effects of the nonconformities encountered? Does the organization document a procedure to define requirements for reviewing nonconformities (including complaints); determining the causes of nonconformities; evaluating the need for action to ensure that nonconformities do not recur; planning and documenting action needed and implementing such action, including, as appropriate, updating documentation; verifying that the corrective action does not adversely affect the ability to meet applicable regulatory requirements or the safety and performance of the medical device; and reviewing the effectiveness of corrective action taken?",
        "audit_question_ja": "組織は、再発防止のために不適合の原因を除去する処置を取っているか？是正処置は、遭遇した不適合の影響に適切か？組織は、不適合のレビュー（苦情を含む）、不適合の原因の決定、不適合が再発しないことを確実にするための処置の必要性の評価、必要な処置の計画と文書化及びそのような処置の実施（適切な場合には文書の更新を含む）、是正処置が適用される規制要求事項又は医療機器の安全性及び性能を満たす能力に悪影響を及ぼさないことの検証、並びに取られた是正処置の有効性のレビューのための要求事項を定義する手順を文書化しているか？",
        "audit_questions_en": [
            "Does the organization take action to eliminate the cause of nonconformities in order to prevent recurrence? Are corrective actions appropriate to the effects of the nonconformities encountered? Does the organization document a procedure to define requirements for reviewing nonconformities (including complaints); determining the causes of nonconformities; evaluating the need for action to ensure that nonconformities do not recur; planning and documenting action needed and implementing such action, including, as appropriate, updating documentation; verifying that the corrective action does not adversely affect the ability to meet applicable regulatory requirements or the safety and performance of the medical device; and reviewing the effectiveness of corrective action taken?",
            "Is the corrective action procedure complete? Does it cover the 6 elements (review, cause determination, need evaluation, planning/implementation, verification, effectiveness review)?",
            "Per ISO 13485:2016 §8.5.2, does the CAPA procedure cover non-conformity review, root cause determination, action need evaluation, action planning and documentation, effect verification on regulatory/safety/performance, and effectiveness review?",
            "What root cause analysis methods are used (5-Why, Ishikawa, Fault Tree)? Is the analysis process documented?",
            "How is the effectiveness of corrective actions verified? Is the verification time frame defined based on risk?",
            "Does the corrective action evaluation include assessment of adverse effects on regulatory requirements and device safety/performance?",
            "Are CAPAs prioritized based on risk and impact? How is the tracking of CAPA progress and timeline?",
        ],
        "audit_questions_ja": [
            "組織は、再発防止のために不適合の原因を除去する処置を取っているか？是正処置は、遭遇した不適合の影響に適切か？組織は、不適合のレビュー（苦情を含む）、不適合の原因の決定、不適合が再発しないことを確実にするための処置の必要性の評価、必要な処置の計画と文書化及びそのような処置の実施（適切な場合には文書の更新を含む）、是正処置が適用される規制要求事項又は医療機器の安全性及び性能を満たす能力に悪影響を及ぼさないことの検証、並びに取られた是正処置の有効性のレビューのための要求事項を定義する手順を文書化しているか？",
            "是正処置手順は完全か？6つの要素（レビュー、原因決定、必要性評価、計画／実施、検証、有効性レビュー）を網羅しているか？",
            "ISO 13485:2016 §8.5.2に従い、CAPA手順は不適合レビュー、根本原因決定、処置必要性評価、処置計画及び文書化、規制／安全性／性能への影響検証、有効性レビューを網羅しているか？",
            "どの根本原因分析手法が使用されているか（5-Why、特性要因図、FTA等）？分析プロセスは文書化されているか？",
            "是正処置の有効性はどのように検証されているか？検証期間はリスクに基づいて定義されているか？",
            "是正処置評価には規制要求事項及び機器安全性／性能への悪影響評価が含まれているか？",
            "CAPAはリスク及び影響度に基づいて優先順位付けされているか？CAPA進捗及び期限の追跡は？",
        ],
        "expected_evidence_en": [
            "Corrective action procedure",
            "CAPA records",
            "Root cause analysis",
            "Effectiveness verification records",
        ],
        "expected_evidence_ja": [
            "是正処置手順書",
            "CAPA記録",
            "根本原因分析",
            "有効性検証記録",
        ],
    },
    "8.5.3": {
        "title": "預防措施",
        "title_en": "Preventive Action",
        "title_ja": "予防処置",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否決定消除潛在不符合原因的措施以防止其發生？"
            "預防措施是否與潛在問題的影響相稱？"
            "是否建立文件化程序，規定判定潛在不符合及其原因、"
            "評估預防行動的需要、規劃與文件化行動並實施、"
            "驗證措施有效性、以及審查所採取的預防措施及其有效性？"
        ),
        "audit_questions": [
            (
                "組織是否決定消除潛在不符合原因的措施以防止其發生？"
                "預防措施是否與潛在問題的影響相稱？"
                "是否建立文件化程序，規定判定潛在不符合及其原因、"
                "評估預防行動的需要、規劃與文件化行動並實施、"
                "驗證措施有效性、以及審查所採取的預防措施及其有效性？"
            ),
            "預防措施的觸發來源有哪些（趨勢分析、設計審查、風險評估等）？如何確保預防措施的效果不被後續過程變化所抵消？",
            "依 ISO 13485:2016 §8.5.3，組織是否決定消除潛在不符合原因的措施以防止其發生，且措施與潛在問題的影響相稱？",
            "預防措施的識別是否系統化（如來自趨勢分析、風險評估、設計審查、員工回饋）？各來源的管理方式如何整合？",
            "預防措施的根本原因分析方法是否文件化？潛在原因的識別如何與實際風險水準掛鉤？",
            "預防措施的有效性如何在一段時間後進行驗證？驗證的時間框架和方法是否在措施計畫中預先定義？",
            "預防措施系統是否與風險管理過程整合？識別的潛在失效模式是否回饋至 FMEA 或風險分析文件？",
        ],
        "expected_evidence": [
            "預防措施程序書",
            "預防措施紀錄",
            "風險評估紀錄",
        ],
        "audit_question_en": "Does the organization determine action to eliminate the causes of potential nonconformities to prevent their occurrence? Are preventive actions appropriate to the effects of the potential problems? Does the organization document a procedure to describe requirements for determining potential nonconformities and their causes; evaluating the need for action to prevent occurrence of nonconformities; planning and documenting action needed and implementing such action, including, as appropriate, updating documentation; verifying that the action does not adversely affect the ability to meet applicable regulatory requirements or the safety and performance of the medical device; and reviewing the effectiveness of preventive action taken?",
        "audit_question_ja": "組織は、発生を防止するために潜在的不適合の原因を除去する処置を決定しているか？予防処置は、潜在的な問題の影響に適切か？組織は、潜在的不適合及びその原因の決定、不適合の発生を防止するための処置の必要性の評価、必要な処置の計画と文書化及びそのような処置の実施（適切な場合には文書の更新を含む）、処置が適用される規制要求事項又は医療機器の安全性及び性能を満たす能力に悪影響を及ぼさないことの検証、並びに取られた予防処置の有効性のレビューのための要求事項を記述する手順を文書化しているか？",
        "audit_questions_en": [
            "Does the organization determine action to eliminate the causes of potential nonconformities to prevent their occurrence? Are preventive actions appropriate to the effects of the potential problems? Does the organization document a procedure to describe requirements for determining potential nonconformities and their causes; evaluating the need for action to prevent occurrence of nonconformities; planning and documenting action needed and implementing such action, including, as appropriate, updating documentation; verifying that the action does not adversely affect the ability to meet applicable regulatory requirements or the safety and performance of the medical device; and reviewing the effectiveness of preventive action taken?",
            "What are the sources of preventive actions (trend analysis, design review, risk assessment)? How is the effect of preventive actions ensured not to be negated by subsequent process changes?",
            "Per ISO 13485:2016 §8.5.3, does the organization determine actions to eliminate causes of potential non-conformities to prevent occurrence, commensurate with the effects of the potential problems?",
            "Is the identification of preventive actions systematic (e.g., from trend analysis, risk assessment, design review, employee feedback)? How are these sources integrated?",
            "Is the root cause analysis method for preventive actions documented? Is the identification of potential causes linked to actual risk level?",
            "How is the effectiveness of preventive actions verified after a period of time? Is the verification time frame and method predefined in the action plan?",
            "Is the preventive action system integrated with the risk management process? Are identified potential failure modes fed back to FMEA or risk analysis documents?",
        ],
        "audit_questions_ja": [
            "組織は、発生を防止するために潜在的不適合の原因を除去する処置を決定しているか？予防処置は、潜在的な問題の影響に適切か？組織は、潜在的不適合及びその原因の決定、不適合の発生を防止するための処置の必要性の評価、必要な処置の計画と文書化及びそのような処置の実施（適切な場合には文書の更新を含む）、処置が適用される規制要求事項又は医療機器の安全性及び性能を満たす能力に悪影響を及ぼさないことの検証、並びに取られた予防処置の有効性のレビューのための要求事項を記述する手順を文書化しているか？",
            "予防処置のトリガー源は何か（傾向分析、設計レビュー、リスク評価等）？予防処置の効果が後続のプロセス変更で打ち消されないことをどのように確実にしているか？",
            "ISO 13485:2016 §8.5.3に従い、組織は潜在的不適合の原因を除去する処置を決定し、発生を防止しているか、また処置は潜在的問題の影響に比例しているか？",
            "予防処置の識別は体系化されているか（傾向分析、リスク評価、設計レビュー、従業員フィードバック等）？各源の管理方法はどのように統合されているか？",
            "予防処置の根本原因分析手法は文書化されているか？潜在的原因の識別は実際のリスク水準と連動しているか？",
            "予防処置の有効性は一定期間後どのように検証されるか？検証期間及び方法は処置計画で事前定義されているか？",
            "予防処置システムはリスクマネジメントプロセスと統合されているか？識別された潜在的故障モードはFMEA又はリスク分析文書にフィードバックされているか？",
        ],
        "expected_evidence_en": [
            "Preventive action procedure",
            "Preventive action records",
            "Risk assessment records",
        ],
        "expected_evidence_ja": [
            "予防処置手順書",
            "予防処置記録",
            "リスク評価記録",
        ],
    },
}


# ============================================================
# Supported Standards Registry
# ============================================================

SUPPORTED_STANDARDS: dict[str, dict] = {
    "ISO_13485": {
        "name": "ISO 13485:2016",
        "full_name": "Medical devices — Quality management systems — Requirements for regulatory purposes",
        "full_name_zh": "醫療器材 — 品質管理系統 — 法規目的之要求",
        "checklist": ISO_13485_CHECKLIST,
    },
    # Future: FDA_QMSR, EU_MDR, etc. can be added here
}


# ============================================================
# Public API
# ============================================================


def get_checklist(standard: str = "ISO_13485") -> dict:
    """Return the full checklist dict for a given standard.

    Args:
        standard: Standard identifier (default: "ISO_13485")

    Returns:
        dict mapping clause_id -> clause_info

    Raises:
        ValueError: If standard is not supported
    """
    entry = SUPPORTED_STANDARDS.get(standard)
    if entry is None:
        raise ValueError(
            f"Unsupported standard: {standard!r}. "
            f"Supported: {list(SUPPORTED_STANDARDS.keys())}"
        )
    return entry["checklist"]


def get_clause(standard: str, clause_id: str) -> Optional[dict]:
    """Return a single clause from a checklist.

    Args:
        standard: Standard identifier (e.g., "ISO_13485")
        clause_id: Clause number (e.g., "4.2.3")

    Returns:
        Clause dict or None if not found
    """
    try:
        checklist = get_checklist(standard)
    except ValueError:
        return None
    return checklist.get(clause_id)


def list_clauses(standard: str = "ISO_13485") -> list[str]:
    """Return sorted list of clause IDs for a given standard.

    Args:
        standard: Standard identifier (default: "ISO_13485")

    Returns:
        Sorted list of clause ID strings

    Raises:
        ValueError: If standard is not supported
    """
    checklist = get_checklist(standard)
    # Sort by numeric value for proper ordering (4.1 < 4.2.1 < 4.2.2 < ... < 8.5.3)
    return sorted(
        checklist.keys(),
        key=lambda x: [int(n) for n in x.split(".")],
    )


# ============================================================
# Layer 2: Multi-Regulation Cross-Reference Framework
# ============================================================


class MappingStatus(str, Enum):
    """How a country's regulation covers an ISO 13485 clause."""

    FULL = "full"  # Regulation fully adopts / covers this clause
    PARTIAL = "partial"  # Regulation partially covers (some gaps or additions)
    NOT_APPLICABLE = "na"  # Regulation does not address this clause area
    EXCEEDS = "exceeds"  # Regulation exceeds ISO 13485 requirements for this clause


class MappingMethod(str, Enum):
    """How the mapping was determined — for explainability."""

    OFFICIAL_CROSSREF = "official_crossref"  # Official mapping doc exists (e.g., FDA preamble, EN ISO 13485/A11 Annex ZA)
    CLAUSE_STRUCTURE = "clause_structure"  # Same clause numbering/structure (e.g., TFDA 84 Articles mirror ISO 13485)
    SEMANTIC_EN = "semantic_en"  # English semantic analysis of requirement text
    SEMANTIC_ZH = "semantic_zh"  # Chinese semantic analysis of requirement text
    KEYWORD_MATCH = (
        "keyword_match"  # Keyword/term overlap between regulation and ISO clause
    )
    EXPERT_JUDGMENT = "expert_judgment"  # Domain expert manual classification
    LLM_ANALYSIS = "llm_analysis"  # LLM-assisted analysis (for crawled regulations)


@dataclass
class WithinClauseDelta:
    """A country-specific strictness variation WITHIN an ISO 13485 clause.

    Unlike UniqueRequirement (which is entirely outside ISO 13485 scope),
    this captures cases where ISO 13485 already requires something but the
    country imposes stricter timelines, specific forms, local authority steps,
    or scope extensions within the same clause area.
    """
    delta_id: str               # e.g., "TFDA-WITHIN-8.2.3-001"
    iso_clause: str             # e.g., "8.2.3"
    title_en: str
    title_zh: str               # Chinese title
    title_ja: str               # Japanese title
    iso_baseline_en: str        # What ISO 13485 requires (brief)
    iso_baseline_zh: str
    iso_baseline_ja: str
    country_specific_en: str    # What this country requires (stricter/additional)
    country_specific_zh: str
    country_specific_ja: str
    regulation_ref: str         # "Article 46(2)" / "第46條第2項"
    original_text: str          # Raw regulatory text in native language
    original_lang: str          # "zh-TW", "en", "ko", etc.
    english_translation: str    # English translation if not English
    delta_type: str             # "stricter_timeline" | "additional_form" |
                                # "local_authority_specific" | "scope_extension" | "other"
    audit_impact: str           # "critical" | "major" | "minor"
    expected_evidence: list[str]
    confidence: float           # 0.0-1.0


@dataclass
class ClauseMapping:
    """How one ISO 13485 clause is covered by a specific country's regulation.

    Includes rationale for WHY this mapping was determined,
    what method was used, and confidence level.
    Also includes native-language regulatory text for cross-language comparison.
    """

    iso_clause: str  # e.g., "4.2.3"
    status: MappingStatus  # full / partial / na / exceeds
    regulation_ref: str  # e.g., "§820.10 (adopts ISO 13485)" or "Article 10"
    rationale_en: str  # WHY this mapping: English explanation
    rationale_zh: str  # WHY this mapping: Chinese explanation
    method: MappingMethod  # HOW determined: official crossref, semantic, etc.
    confidence: float  # 0.0–1.0 how confident in this mapping
    notes: str = ""  # Additional notes (e.g., "FDA removed exemption for mgmt review")
    # Native-language fields for cross-language comparison
    original_text: str = ""  # Regulatory clause text in its NATIVE language (法規原文)
    original_lang: str = ""  # Language code: "en", "zh-TW", "de", "fr", etc.
    english_translation: str = ""  # English translation (if original is NOT English)
    semantic_note: str = ""  # Interpretation: what this clause means in practice
    within_clause_deltas: list["WithinClauseDelta"] = field(default_factory=list)
    # Populated when status == EXCEEDS: specific ways this country is stricter than ISO 13485


@dataclass
class UniqueRequirement:
    """A country-specific requirement that goes BEYOND ISO 13485.

    These are the DELTA items — the most critical for cross-examination
    because quality documents are least likely to cover them.
    Includes native-language text for cross-language semantic comparison.
    """

    req_id: str  # e.g., "QMSR-001", "MDR-001", "TFDA-001"
    regulation_ref: str  # e.g., "§820.35", "Article 15", "第33條"
    title_en: str  # English title
    title_zh: str  # Chinese title
    requirement_en: str  # Full requirement description (English)
    requirement_zh: str  # Full requirement description (Chinese)
    related_iso_clauses: list[str]  # Which ISO 13485 clauses this is closest to
    audit_impact: str  # "critical" / "major" / "minor"
    audit_question_en: str  # Audit question in English
    audit_question_zh: str  # Audit question in Chinese
    expected_evidence: list[str]  # What evidence should exist
    rationale_en: str  # WHY this is classified under these ISO clauses
    rationale_zh: str  # WHY (Chinese)
    method: MappingMethod  # HOW determined
    confidence: float  # 0.0–1.0
    # Native-language fields for cross-language comparison
    original_text: str = ""  # Regulatory text in its NATIVE language (法規原文)
    original_lang: str = ""  # Language code: "en", "zh-TW", "de", "fr", etc.
    english_translation: str = ""  # English translation (if original is NOT English)
    semantic_note: str = ""  # Interpretation: what this means in practice, and how it differs across countries
    is_within_clause_delta: bool = False  # True if this is a within-clause delta (TYPE 2), False if fully outside ISO 13485 (TYPE 1)
    within_clause_delta_vs_iso: str = ""  # Brief statement: "ISO says X, this country says Y"


@dataclass
class RegulationProfile:
    """Complete profile for one country's QMS regulation.

    This is the UNIFIED format for both predefined and crawled regulations.
    When a user selects a country, this profile is used to:
      1. Show the cross-reference table (overlap vs delta)
      2. Generate per-document cross-examination questions
      3. Feed the risk matrix for compliance verdicts
    """

    regulation_id: str  # e.g., "QMSR", "EU_MDR", "TFDA", "PMDA"
    name_en: str  # e.g., "US FDA QMSR (21 CFR Part 820)"
    name_zh: str  # e.g., "美國 FDA QMSR（21 CFR 第820部分）"
    country: str  # e.g., "US", "EU", "TW", "JP"
    country_name_en: str  # e.g., "United States"
    country_name_zh: str  # e.g., "美國"
    source: str  # "predefined" or "crawled"
    source_url: str = ""  # Official regulation URL
    last_updated: str = ""  # ISO date of last update
    effective_date: str = ""  # When regulation became effective
    # Mapping: ISO 13485 clause → how this regulation covers it
    iso_mapped: dict[str, ClauseMapping] = field(default_factory=dict)
    # Delta: requirements UNIQUE to this country (not in ISO 13485)
    unique_requirements: list[UniqueRequirement] = field(default_factory=list)


# ============================================================
# Supplemental Standards — Product-Profile-Triggered Standards
# ============================================================
# ISO/IEC standards that SUPPLEMENT ISO 13485.
# Country regulations = WHAT to comply with;
# Supplemental standards = HOW to comply with specific clauses.
#
# Trigger sources for product characteristics (5 sources):
#   1. Quality docs scan (quality manual, IFU, specs, design dev docs)
#   2. Referenced standards list in documents
#   3. User-uploaded ISO/IEC files (most reliable signal)
#   4. User manual selection in HTML UI checkboxes
#   5. Real-time correction during cross-examination dialog


class StandardCategory(str, Enum):
    """Category of supplemental standard — determines where it fits."""

    RISK_MANAGEMENT = "risk_management"  # ISO 14971
    SOFTWARE = "software"  # IEC 62304
    USABILITY = "usability"  # IEC 62366
    ELECTRICAL_SAFETY = "electrical_safety"  # IEC 60601
    STERILIZATION = "sterilization"  # ISO 11135/11137/17665
    PACKAGING = "packaging"  # ISO 11607
    BIOCOMPATIBILITY = "biocompatibility"  # ISO 10993
    IMPLANTABLE = "implantable"  # ISO 14708
    LABELING = "labeling"  # ISO 15223
    EMC = "emc"  # IEC 60601-1-2
    CLINICAL = "clinical"  # ISO 14155
    PROCESS_VALIDATION = "process_validation"  # Process-specific validation
    ENVIRONMENTAL = "environmental"  # IEC 60068


@dataclass
class StandardClauseLink:
    """How one supplemental standard clause links to an ISO 13485 clause.

    Defines the 'HOW' relationship: the supplemental standard
    tells you HOW to satisfy a specific ISO 13485 requirement.
    """

    standard_clause: str  # e.g., "ISO 14971 Clause 4"
    iso_13485_clause: str  # e.g., "7.1"
    relationship: str  # "elaborates" / "implements" / "supplements" / "verifies"
    description_en: str  # What this link means
    description_zh: str  # What this link means (Chinese)


@dataclass
class SupplementalStandardProfile:
    """Profile for a supplemental standard (ISO/IEC) that supports ISO 13485.

    Unlike RegulationProfile (country regulations = WHAT to comply with),
    SupplementalStandardProfile defines HOW to comply with specific
    ISO 13485 clauses for specific product types.

    Activation sources (multi-source product profile):
      1. Document scan: quality manual, IFU, specs, design dev docs
      2. Referenced standards list in quality documents
      3. User-uploaded ISO/IEC files (direct signal)
      4. User manual selection in HTML UI checkboxes
      5. Real-time correction during cross-examination dialog
    """

    standard_id: str  # e.g., "ISO_14971", "IEC_62304"
    name_en: str  # e.g., "ISO 14971:2019 Risk Management"
    name_zh: str  # e.g., "ISO 14971:2019 風險管理"
    category: StandardCategory
    version: str = ""
    is_universal: bool = False  # True = applies to ALL products (e.g., ISO 14971)
    # Keywords to detect in documents / uploaded files
    detection_keywords_en: list[str] = field(default_factory=list)
    detection_keywords_zh: list[str] = field(default_factory=list)
    # How this standard's clauses link to ISO 13485
    clause_links: list[StandardClauseLink] = field(default_factory=list)
    # Primary ISO 13485 clauses this standard supports
    primary_iso_clauses: list[str] = field(default_factory=list)
    # How country regulations reference this standard
    # e.g., {"US": "FDA recognized consensus standard", "EU": "Harmonized standard under MDR"}
    regulatory_references: dict[str, str] = field(default_factory=dict)
    # Additional audit questions triggered by this standard
    audit_questions: list[dict] = field(default_factory=list)
    notes: str = ""


@dataclass
class ProductProfile:
    """Product characteristics that determine which supplemental standards apply.

    Built from 5 sources:
      1. LLM scan of quality docs (quality manual, IFU, specs, design dev)
      2. Referenced standards list scan from documents
      3. User-uploaded ISO/IEC files (most reliable signal)
      4. User manual selection in HTML UI
      5. Corrections from cross-examination dialog

    Each characteristic stores: (value, confidence, source)
    source: 'document_scan' / 'standards_list' / 'uploaded_file' / 'user_manual' / 'dialog_correction'
    """

    has_software: tuple[bool, float, str] = (False, 0.0, "")
    has_electrical: tuple[bool, float, str] = (False, 0.0, "")
    is_implantable: tuple[bool, float, str] = (False, 0.0, "")
    is_sterile: tuple[bool, float, str] = (False, 0.0, "")
    sterilization_method: str = ""  # "eo" / "radiation" / "steam" / "other" / ""
    has_biological_contact: tuple[bool, float, str] = (False, 0.0, "")
    is_ivd: tuple[bool, float, str] = (False, 0.0, "")
    has_clinical_investigation: tuple[bool, float, str] = (False, 0.0, "")
    has_wireless_connectivity: tuple[bool, float, str] = (False, 0.0, "")
    # Risk class per regulation
    risk_class: dict[str, str] = field(
        default_factory=dict
    )  # {"EU": "IIb", "US": "II", "TW": "2"}
    # User confirmation overrides
    user_confirmed_standards: list[str] = field(default_factory=list)
    user_rejected_standards: list[str] = field(default_factory=list)
    # Detection results
    detected_standard_refs: list[str] = field(
        default_factory=list
    )  # Standards found in docs
    uploaded_standard_files: list[str] = field(
        default_factory=list
    )  # ISO files user uploaded
    detection_notes: str = ""


# ============================================================
# Predefined Regulation: US FDA QMSR
# ============================================================


def _build_qmsr_profile() -> RegulationProfile:
    """Build the US FDA QMSR regulation profile.

    QMSR (Quality Management System Regulation) replaced 21 CFR 820 QSR.
    Finalized Feb 2, 2024 (89 FR 7496). Effective Feb 2, 2026.
    Core mechanism: incorporates ISO 13485:2016 by reference via §820.10.

    Mapping source: FDA Federal Register preamble (89 FR 7496)
    + AAMI TIR102:2019 cross-reference guide.
    """
    # QMSR adopts ALL ISO 13485 clauses via §820.10
    # Every single ISO 13485 clause is "full" status
    iso_mapped: dict[str, ClauseMapping] = {}
    for clause_id, clause_info in ISO_13485_CHECKLIST.items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=clause_id,
            status=MappingStatus.FULL,
            regulation_ref=f"§820.10 (incorporates ISO 13485:2016 Clause {clause_id} by reference)",
            rationale_en=(
                f"QMSR §820.10 formally incorporates ISO 13485:2016 by reference. "
                f"FDA determined ISO 13485 is 'substantially similar' to legacy 21 CFR 820. "
                f"Clause {clause_id} ({clause_info['title']}) is fully adopted without modification."
            ),
            rationale_zh=(
                f"QMSR §820.10 正式引用 ISO 13485:2016。"
                f"FDA 認定 ISO 13485 與原 21 CFR 820 '實質相似'。"
                f"條款 {clause_id}（{clause_info['title']}）完全採用，未修改。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=1.0,
            notes="FDA Federal Register 89 FR 7496, Feb 2 2024",
        )

    # FDA-specific unique requirements (delta)
    unique_reqs = [
        UniqueRequirement(
            req_id="QMSR-001",
            regulation_ref="§820.35(a)",
            title_en="Control of Records — Signature & Date",
            title_zh="記錄管制 — 簽名與日期",
            requirement_en=(
                "All records required by FDA must include the signature of the person "
                "performing the activity and the date the activity was performed. "
                "This is more explicit than ISO 13485 Clause 4.2.5 which says records "
                "shall remain legible, readily identifiable and retrievable."
            ),
            requirement_zh=(
                "FDA 要求的所有記錄必須包含執行人員的簽名及執行日期。"
                "此要求比 ISO 13485 條款 4.2.5 更為明確，ISO 僅要求記錄應保持"
                "清晰、易於識別及可檢索。"
            ),
            related_iso_clauses=["4.2.4", "4.2.5"],
            audit_impact="major",
            audit_question_en=(
                "Do quality records include the signature of the person performing "
                "the activity and the date, as required by FDA §820.35(a)?"
            ),
            audit_question_zh=(
                "品質記錄是否包含執行人員的簽名與執行日期？（FDA §820.35(a) 要求）"
            ),
            expected_evidence=[
                "Records with handwritten or electronic signatures / 含手寫或電子簽名之記錄",
                "Date stamps on all quality records / 所有品質記錄上之日期戳記",
            ],
            rationale_en=(
                "§820.35(a) explicitly requires signature + date on records. "
                "ISO 13485 Clause 4.2.5 requires records be identifiable but does not "
                "explicitly mandate signature + date format. Classified under 4.2.4/4.2.5 "
                "because both address record control."
            ),
            rationale_zh=(
                "§820.35(a) 明確要求記錄須有簽名與日期。"
                "ISO 13485 條款 4.2.5 要求記錄可識別，但未明確規定簽名+日期格式。"
                "歸類於 4.2.4/4.2.5 因兩者皆涉及記錄管制。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.95,
            original_text=(
                "Each manufacturer shall maintain records of all quality activities in accordance with §820.184. "
                "Such records shall include... the signature of the individual(s) performing "
                "the activity and the date(s) the activity was performed."
            ),
            original_lang="en",
            english_translation="",  # Already in English
            semantic_note=(
                "FDA uses 'signature of the individual(s)' and 'date(s)' as explicit mandatory fields. "
                "ISO 13485 Cl. 4.2.5 uses broader language: 'records shall remain legible, readily identifiable "
                "and retrievable' — which does NOT explicitly require signature+date format. "
                "Practical impact: US-market quality records MUST have name/signature + date on every entry, "
                "while ISO 13485 alone allows other identification methods (e.g., ID codes, system logs)."
            ),
        ),
        UniqueRequirement(
            req_id="QMSR-002",
            regulation_ref="§820.35(b)",
            title_en="Control of Records — Complaint Records with UDI",
            title_zh="記錄管制 — 含UDI之客訴記錄",
            requirement_en=(
                "Complaint and servicing records must include the Unique Device "
                "Identifier (UDI) or universal product code (UPC), the date of the event, "
                "and specific data points not mandated by ISO 13485 in the same format."
            ),
            requirement_zh=(
                "客訴與服務記錄必須包含唯一裝置識別碼（UDI）或通用產品代碼（UPC）、"
                "事件日期，以及 ISO 13485 未以相同格式要求之特定資料點。"
            ),
            related_iso_clauses=["4.2.4", "4.2.5", "8.2.2", "7.5.9.2"],
            audit_impact="critical",
            audit_question_en=(
                "Do complaint and servicing records include the UDI/UPC, date of event, "
                "and all FDA-required data fields per §820.35(b)?"
            ),
            audit_question_zh=(
                "客訴與服務記錄是否包含 UDI/UPC、事件日期，及 FDA §820.35(b) "
                "要求之所有必要資料欄位？"
            ),
            expected_evidence=[
                "Complaint records with UDI field populated / 含UDI欄位之客訴記錄",
                "Event date recorded for each complaint / 每筆客訴之事件日期記錄",
                "Servicing records with device identification / 含裝置識別之服務記錄",
            ],
            rationale_en=(
                "§820.35(b) requires specific data fields in complaint/servicing records "
                "that are not in ISO 13485. UDI is an FDA-specific identifier system. "
                "Related to 8.2.2 (complaint handling), 4.2.4/4.2.5 (records), "
                "and 7.5.9.2 (UDI traceability)."
            ),
            rationale_zh=(
                "§820.35(b) 要求客訴/服務記錄中的特定資料欄位，ISO 13485 無此要求。"
                "UDI 是 FDA 特有的識別系統。相關條款：8.2.2（客訴處理）、"
                "4.2.4/4.2.5（記錄）及 7.5.9.2（UDI 追溯性）。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.95,
            original_text=(
                "Each manufacturer shall maintain complaint files and records of servicing activities... "
                "including the unique device identifier (UDI) or universal product code (UPC), "
                "the date of the event, and such information as is reasonably necessary."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "FDA explicitly mandates 'unique device identifier (UDI)' in complaint records. "
                "ISO 13485 Cl. 8.2.2 requires complaint handling but does NOT specify UDI inclusion. "
                "EU MDR has its own UDI system (Art 27) but does not require it in complaint records the same way. "
                "Taiwan TFDA uses its own license number system, not UDI. "
                "Cross-country difference: the IDENTIFIER used in complaint records varies by jurisdiction."
            ),
        ),
        UniqueRequirement(
            req_id="QMSR-003",
            regulation_ref="§820.45",
            title_en="Device Labeling and Packaging Controls",
            title_zh="裝置標示與包裝管制",
            requirement_en=(
                "FDA requires specific inspection of labeling for accuracy before release, "
                "including verification of correct expiration dates, UDI placement, "
                "and labeling content. This is more prescriptive than ISO 13485 Clause 7.5.1 "
                "which addresses production controls generally."
            ),
            requirement_zh=(
                "FDA 要求在放行前對標示進行特定的正確性檢查，包括驗證有效日期、"
                "UDI 標示位置及標示內容。此要求比 ISO 13485 條款 7.5.1 的一般性"
                "生產管制要求更為具體。"
            ),
            related_iso_clauses=["7.5.1", "7.5.8", "7.5.11"],
            audit_impact="major",
            audit_question_en=(
                "Is there a specific labeling inspection step before device release "
                "that verifies accuracy of expiration dates, UDI, and content per §820.45?"
            ),
            audit_question_zh=(
                "在裝置放行前是否有特定的標示檢查步驟，驗證有效日期、UDI "
                "及內容的正確性？（§820.45 要求）"
            ),
            expected_evidence=[
                "Labeling inspection procedure / 標示檢查程序書",
                "Labeling verification records before release / 放行前標示驗證記錄",
                "UDI placement verification / UDI 標示位置確認",
            ],
            rationale_en=(
                "§820.45 was retained because FDA determined ISO 13485 Clause 7.5.1 "
                "does not provide equivalent specificity for labeling inspection. "
                "Related to 7.5.8 (identification), 7.5.11 (preservation) as labeling "
                "is part of product identification and protection."
            ),
            rationale_zh=(
                "§820.45 被保留，因 FDA 認定 ISO 13485 條款 7.5.1 在標示檢查方面"
                "未提供同等的具體要求。相關條款：7.5.8（識別）、7.5.11（防護），"
                "因標示屬產品識別與保護之一部分。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.95,
            original_text=(
                "Each manufacturer shall examine the labeling and packaging of each batch, lot, "
                "or unit to determine that the labeling has not been mislabeled. Labeling inspection "
                "shall be adequate to detect labeling mixups."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "FDA §820.45 requires a SPECIFIC labeling inspection step — i.e., an active check "
                "that labeling has not been mixed up before release. ISO 13485 7.5.1 addresses production "
                "controls generally but has no equivalent 'labeling inspection' gate. "
                "EU MDR Annex I Chapter III has detailed labeling content requirements but focuses on WHAT "
                "must be on the label, not on a mandatory inspection step. "
                "Taiwan TFDA Art 33 mandates Chinese-language labeling but does not specify a labeling "
                "inspection procedure. Cross-country: US is the only jurisdiction with an explicit "
                "pre-release labeling inspection requirement."
            ),
        ),
        UniqueRequirement(
            req_id="QMSR-004",
            regulation_ref="§820.65",
            title_en="Traceability — Life-Sustaining/Supporting Devices",
            title_zh="追溯性 — 維生/生命支持裝置",
            requirement_en=(
                "Manufacturers of devices intended to be used in supporting or sustaining "
                "life must maintain distribution records with specific traceability data "
                "(name/address of consignee, quantity, date shipped, control numbers). "
                "This exceeds ISO 13485 Clause 7.5.9 general traceability."
            ),
            requirement_zh=(
                "維生或生命支持裝置之製造商必須維持特定的配銷追溯紀錄"
                "（受貨人名稱/地址、數量、出貨日期、管制編號）。"
                "此要求超越 ISO 13485 條款 7.5.9 的一般追溯性要求。"
            ),
            related_iso_clauses=["7.5.9", "7.5.9.1", "7.5.9.2"],
            audit_impact="critical",
            audit_question_en=(
                "For life-sustaining/supporting devices, are distribution records maintained "
                "with consignee details, quantities, dates, and control numbers per §820.65?"
            ),
            audit_question_zh=(
                "對於維生/生命支持裝置，是否維持含受貨人資料、數量、日期"
                "及管制編號之配銷追溯紀錄？（§820.65 要求）"
            ),
            expected_evidence=[
                "Distribution records for life-sustaining devices / 維生裝置配銷記錄",
                "Consignee name, address, quantity, date, control number / 受貨人名稱、地址、數量、日期、管制編號",
            ],
            rationale_en=(
                "§820.65 is a legacy FDA requirement for heightened traceability of "
                "life-critical devices. ISO 13485 7.5.9 requires traceability but does not "
                "mandate this specific level of distribution detail. Classified under "
                "7.5.9/7.5.9.1/7.5.9.2 as all address traceability."
            ),
            rationale_zh=(
                "§820.65 是 FDA 對維生裝置的加強追溯性要求。"
                "ISO 13485 7.5.9 要求追溯性但未規定此等級之配銷細節。"
                "歸類於 7.5.9/7.5.9.1/7.5.9.2 因均涉及追溯性。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.95,
            original_text=(
                "Any device used in supporting or sustaining life, and whose failure to perform when "
                "properly used in accordance with instructions for use provided in the labeling can be "
                "reasonably expected to result in a significant injury to the user, shall be identified "
                "with a control number... each manufacturer of such a device shall maintain distribution "
                "records which include the name and address of the consignee, the quantity distributed, "
                "the date shipped, and the control number(s) used."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "FDA §820.65 creates a HEIGHTENED traceability tier specifically for life-sustaining/supporting "
                "devices, requiring distribution records with consignee details. ISO 13485 7.5.9 requires "
                "traceability but does not differentiate by device risk level. "
                "EU MDR has its own UDI-based traceability system (Art 25/27) but applies to ALL devices, "
                "not just life-sustaining ones — however, Class III and implantable devices have "
                "additional traceability via Art 27(9). "
                "Taiwan TFDA has general traceability requirements but no specific life-sustaining device "
                "tier. Cross-country: US uniquely applies enhanced distribution traceability based on "
                "device criticality classification."
            ),
        ),
        UniqueRequirement(
            req_id="QMSR-005",
            regulation_ref="§820.35 / FD&C Act",
            title_en="FDA Inspection Access — No Management Review Exemption",
            title_zh="FDA 稽查權限 — 管理審查記錄無豁免",
            requirement_en=(
                "Under QMSR, FDA explicitly has the right to inspect ALL quality records, "
                "including management reviews and internal audits. The previous QSR §820.180(c) "
                "exemption for management review records has been REMOVED. ISO 13485 does not "
                "address regulatory authority inspection rights."
            ),
            requirement_zh=(
                "在 QMSR 下，FDA 明確有權檢查所有品質記錄，包含管理審查和內部稽核。"
                "原 QSR §820.180(c) 對管理審查記錄的豁免已被移除。"
                "ISO 13485 未涉及法規主管機關稽查權限。"
            ),
            related_iso_clauses=["5.6.1", "8.2.4", "4.2.4"],
            audit_impact="major",
            audit_question_en=(
                "Are management review and internal audit records maintained in a manner "
                "that allows full FDA inspection access, without claiming exemptions?"
            ),
            audit_question_zh=(
                "管理審查及內部稽核記錄是否以允許 FDA 完整稽查的方式維護，"
                "不主張豁免權？"
            ),
            expected_evidence=[
                "Management review records accessible for inspection / 可供稽查之管理審查記錄",
                "Internal audit records without access restrictions / 無存取限制之內部稽核記錄",
            ],
            rationale_en=(
                "QMSR removed the §820.180(c) exemption. Management reviews (5.6.1) "
                "and internal audits (8.2.4) records must now be fully accessible. "
                "Related to 4.2.4 (record control) for access/retention policies."
            ),
            rationale_zh=(
                "QMSR 移除了 §820.180(c) 豁免。管理審查（5.6.1）與內部稽核（8.2.4）"
                "記錄現在必須完全可供存取。相關條款 4.2.4（記錄管制）涉及存取/保存政策。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "Under the revised QMSR, FDA removed the exemption previously found in §820.180(c) "
                "which had allowed manufacturers to withhold management review records from FDA "
                "inspection. All quality records, including management review and internal audit "
                "records, are now subject to FDA inspection under Section 704 of the FD&C Act."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "Under previous QSR §820.180(c), manufacturers could refuse to show management review "
                "records to FDA inspectors. QMSR removes this exemption — FDA now has FULL access. "
                "ISO 13485 does not address regulatory authority inspection rights at all (it is a QMS "
                "standard, not a regulatory framework). "
                "EU MDR: Notified Body audits have broad access to QMS records including management review, "
                "but scope depends on the conformity assessment procedure (Annex IX/X/XI). "
                "Taiwan TFDA: TFDA inspectors have access to all QMS records under the Medical Device Act. "
                "Cross-country: the US change is significant because it REVERSES a previous protection, "
                "meaning US-market manufacturers must now ensure management review records are "
                "inspection-ready."
            ),
        ),
    ]

    return RegulationProfile(
        regulation_id="QMSR",
        name_en="US FDA QMSR (21 CFR Part 820)",
        name_zh="美國 FDA QMSR（21 CFR 第820部分）",
        country="US",
        country_name_en="United States",
        country_name_zh="美國",
        source="predefined",
        source_url="https://www.federalregister.gov/documents/2024/02/02/2024-01709/medical-devices-quality-system-regulation-amendments",
        last_updated="2024-02-02",
        effective_date="2026-02-02",
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )


# ============================================================
# Predefined Regulation: EU MDR 2017/745
# ============================================================


def _build_eu_mdr_profile() -> RegulationProfile:
    """Build the EU MDR 2017/745 regulation profile.

    EU MDR is a PRODUCT SAFETY regulation (not just a QMS standard).
    ISO 13485 covers the process side; EU MDR adds product-level requirements.

    Mapping source: EN ISO 13485:2016/A11:2021 Annex ZA (official harmonized mapping)
    + ISO/TR 17223:2018 (clause-by-clause correlation)
    """
    # EU MDR partially maps to ISO 13485 — some clauses fully covered,
    # some exceeded, some only partially addressed
    iso_mapped: dict[str, ClauseMapping] = {}

    # Clauses where EU MDR fully aligns with ISO 13485 via Article 10(9)
    full_clauses = {
        "4.1": (
            "Annex IX Sec 2.2 / Art 10(9)",
            "EU MDR Annex IX Section 2.2 requires a QMS. Article 10(9) lists QMS elements that align with ISO 13485 Clause 4.1 general requirements.",
            "EU MDR 附錄 IX 第2.2節要求建立QMS。第10(9)條列出的QMS要素與 ISO 13485 條款 4.1 一般要求對齊。",
        ),
        "4.2.1": (
            "Annex IX Sec 2.2 / Art 10(9)",
            "Technical documentation requirements (Annex II/III) align with QMS documentation needs.",
            "技術文件要求（附錄 II/III）與QMS文件化需求對齊。",
        ),
        "4.2.2": (
            "Annex IX Sec 2.2",
            "Quality manual requirements aligned.",
            "品質手冊要求對齊。",
        ),
        "4.2.3": (
            "Annex IX Sec 2.2",
            "Document control requirements aligned.",
            "文件管制要求對齊。",
        ),
        "4.2.4": (
            "Annex IX Sec 2.2",
            "Record control requirements aligned.",
            "記錄管制要求對齊。",
        ),
        "5.1": (
            "Art 10(9)(b)",
            "Management responsibility fully covered by Article 10(9)(b).",
            "管理責任完全由第10(9)(b)條涵蓋。",
        ),
        "5.2": (
            "Art 10(9)(a)",
            "Customer/regulatory focus via strategy for regulatory compliance.",
            "透過法規合規策略涵蓋顧客/法規關注。",
        ),
        "5.3": (
            "Art 10(9)(b)",
            "Quality policy under management responsibility.",
            "品質政策屬管理責任範疇。",
        ),
        "5.4.1": (
            "Art 10(9)(b)",
            "Quality objectives under management responsibility.",
            "品質目標屬管理責任範疇。",
        ),
        "5.4.2": (
            "Art 10(9)(b)",
            "QMS planning under management responsibility.",
            "QMS規劃屬管理責任範疇。",
        ),
        "5.5.1": (
            "Art 10(9)(b)",
            "Responsibility and authority aligned.",
            "責任與權限對齊。",
        ),
        "5.5.2": (
            "Art 10(9)(b)",
            "Management representative aligned.",
            "管理代表對齊。",
        ),
        "5.5.3": ("Art 10(9)(b)", "Internal communication aligned.", "內部溝通對齊。"),
        "5.6.1": ("Art 10(9)(b)", "Management review aligned.", "管理審查對齊。"),
        "5.6.2": (
            "Art 10(9)(b)",
            "Management review input aligned.",
            "管理審查輸入對齊。",
        ),
        "5.6.3": (
            "Art 10(9)(b)",
            "Management review output aligned.",
            "管理審查輸出對齊。",
        ),
        "6.1": ("Art 10(9)(c)", "Resource provision aligned.", "資源提供對齊。"),
        "6.2": (
            "Art 10(9)(c)",
            "Human resources / competence aligned.",
            "人力資源/能力對齊。",
        ),
        "6.3": ("Art 10(9)(c)", "Infrastructure aligned.", "基礎設施對齊。"),
        "6.4.1": ("Art 10(9)(c)", "Work environment aligned.", "工作環境對齊。"),
        "6.4.2": ("Art 10(9)(c)", "Contamination control aligned.", "污染管制對齊。"),
        "7.1": (
            "Art 10(9)(f)",
            "Product realization planning aligned.",
            "產品實現規劃對齊。",
        ),
        "7.2.1": (
            "Art 10(9)(f)",
            "Determination of product requirements aligned.",
            "產品要求確定對齊。",
        ),
        "7.2.2": (
            "Art 10(9)(f)",
            "Review of product requirements aligned.",
            "產品要求審查對齊。",
        ),
        "7.2.3": (
            "Art 10(9)(i)",
            "Communication with authorities and stakeholders aligned.",
            "與主管機關及利害關係人溝通對齊。",
        ),
        "7.4.1": (
            "Art 10(9)(c)",
            "Purchasing process aligned (suppliers/subcontractors).",
            "採購過程對齊（供應商/分包商）。",
        ),
        "7.4.2": ("Art 10(9)(c)", "Purchasing information aligned.", "採購資訊對齊。"),
        "7.4.3": (
            "Art 10(9)(c)",
            "Verification of purchased product aligned.",
            "採購產品驗證對齊。",
        ),
        "7.5.1": ("Art 10(9)(f)", "Control of production aligned.", "生產管制對齊。"),
        "7.5.2": ("Art 10(9)(f)", "Product cleanliness aligned.", "產品潔淨對齊。"),
        "7.5.3": ("Art 10(9)(f)", "Installation activities aligned.", "安裝活動對齊。"),
        "7.5.4": ("Art 10(9)(f)", "Servicing activities aligned.", "服務活動對齊。"),
        "7.5.5": (
            "Art 10(9)(f)",
            "Sterile device requirements aligned.",
            "無菌裝置要求對齊。",
        ),
        "7.5.6": ("Art 10(9)(f)", "Process validation aligned.", "過程確認對齊。"),
        "7.5.7": (
            "Art 10(9)(f)",
            "Sterilization process validation aligned.",
            "滅菌過程確認對齊。",
        ),
        "7.5.8": ("Art 10(9)(f)", "Identification aligned.", "識別對齊。"),
        "7.5.9": ("Art 10(9)(f)", "Traceability aligned.", "追溯性對齊。"),
        "7.5.9.1": (
            "Art 10(9)(f)",
            "Implant traceability aligned.",
            "植入物追溯性對齊。",
        ),
        "7.5.10": ("Art 10(9)(f)", "Customer property aligned.", "顧客財產對齊。"),
        "7.5.11": ("Art 10(9)(f)", "Product preservation aligned.", "產品防護對齊。"),
        "7.6": (
            "Art 10(9)(f)",
            "Monitoring and measuring equipment aligned.",
            "監督與量測設備對齊。",
        ),
        "8.1": (
            "Art 10(9)(k)",
            "General measurement and improvement aligned.",
            "一般量測與改善對齊。",
        ),
        "8.2.4": ("Art 10(9)(k)", "Internal audit aligned.", "內部稽核對齊。"),
        "8.2.4.1": ("Art 10(9)(k)", "Audit criteria aligned.", "稽核準則對齊。"),
        "8.2.4.2": (
            "Art 10(9)(k)",
            "Audit corrective actions aligned.",
            "稽核矯正措施對齊。",
        ),
        "8.2.5": ("Art 10(9)(k)", "Process monitoring aligned.", "過程監督對齊。"),
        "8.2.6": ("Art 10(9)(k)", "Product monitoring aligned.", "產品監督對齊。"),
        "8.3": (
            "Art 10(9)(j)",
            "Nonconforming product control aligned.",
            "不合格品管制對齊。",
        ),
        "8.3.1": (
            "Art 10(9)(j)",
            "Pre-delivery nonconformance aligned.",
            "交付前不合格對齊。",
        ),
        "8.3.2": (
            "Art 10(9)(j)",
            "Post-delivery nonconformance aligned.",
            "交付後不合格對齊。",
        ),
        "8.3.3": ("Art 10(9)(j)", "Concession control aligned.", "讓步管制對齊。"),
        "8.3.4": ("Art 10(9)(j)", "Rework control aligned.", "返工管制對齊。"),
        "8.4": ("Art 10(9)(k)", "Data analysis aligned.", "數據分析對齊。"),
        "8.5.1": ("Art 10(9)(k)", "Improvement aligned.", "改善對齊。"),
        "8.5.2": (
            "Art 10(9)(j)",
            "Corrective action aligned with CAPA.",
            "矯正措施與CAPA對齊。",
        ),
        "8.5.3": (
            "Art 10(9)(j)",
            "Preventive action aligned with CAPA.",
            "預防措施與CAPA對齊。",
        ),
    }
    for clause_id, (ref, rationale_en, rationale_zh) in full_clauses.items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=clause_id,
            status=MappingStatus.FULL,
            regulation_ref=ref,
            rationale_en=rationale_en,
            rationale_zh=rationale_zh,
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            notes="EN ISO 13485:2016/A11:2021 Annex ZA",
        )

    # Clauses where EU MDR EXCEEDS ISO 13485
    exceeds_clauses = {
        "4.2.5": (
            "Annex II/III",
            MappingStatus.EXCEEDS,
            "EU MDR requires Technical Documentation per Annex II/III format which is more structured than ISO 13485 device file.",
            "EU MDR 要求按附錄 II/III 格式的技術文件，比 ISO 13485 的器材檔案更結構化。",
        ),
        "7.3.1": (
            "Art 10(9)(f) / Annex IX Sec 2.2(c)",
            MappingStatus.EXCEEDS,
            "Design planning must integrate clinical evaluation strategy and GSPR compliance demonstration.",
            "設計規劃必須整合臨床評估策略和GSPR合規展示。",
        ),
        "7.3.2": (
            "Art 10(9)(d) / Annex I",
            MappingStatus.EXCEEDS,
            "Design input must include GSPR (General Safety & Performance Requirements, Annex I) and risk management per Annex I Sec 3.",
            "設計輸入必須包含GSPR（一般安全與性能要求，附錄I）及按附錄I第3節之風險管理。",
        ),
        "7.3.3": (
            "Art 10(9)(f) / Annex II",
            MappingStatus.EXCEEDS,
            "Design output must demonstrate GSPR compliance via Technical Documentation (Annex II).",
            "設計輸出必須透過技術文件（附錄II）展示GSPR合規。",
        ),
        "7.3.4": (
            "Art 10(9)(f)",
            MappingStatus.EXCEEDS,
            "Design review must include clinical evidence review and GSPR gap assessment.",
            "設計審查必須包含臨床證據審查和GSPR差距評估。",
        ),
        "7.3.5": (
            "Art 10(9)(f)",
            MappingStatus.EXCEEDS,
            "Design verification must include biocompatibility, electrical safety per applicable standards.",
            "設計驗證必須包含生物相容性、電氣安全等適用標準。",
        ),
        "7.3.6": (
            "Art 10(9)(e) / Annex XIV",
            MappingStatus.EXCEEDS,
            "Design validation must include clinical evaluation per Annex XIV with PMCF plan. Goes far beyond ISO 13485 clinical requirement.",
            "設計確認必須包含按附錄XIV之臨床評估及PMCF計畫。遠超ISO 13485的臨床要求。",
        ),
        "7.3.7": (
            "Art 10(9)(e) / Annex XIV",
            MappingStatus.EXCEEDS,
            "Design transfer must integrate clinical evaluation lifecycle and PMCF considerations.",
            "設計轉移必須整合臨床評估生命週期及PMCF考量。",
        ),
        "7.3.8": (
            "Art 10(9)(f)",
            MappingStatus.EXCEEDS,
            "Design changes must assess impact on GSPR compliance and clinical evaluation.",
            "設計變更必須評估對GSPR合規及臨床評估之影響。",
        ),
        "7.5.9.2": (
            "Art 27",
            MappingStatus.EXCEEDS,
            "UDI assignment must comply with EU UDI rules and EUDAMED registration.",
            "UDI指派必須符合歐盟UDI規則及EUDAMED註冊。",
        ),
        "8.2.1": (
            "Art 10(9)(h) / Art 83-86",
            MappingStatus.EXCEEDS,
            "Post-market surveillance must include formal PMS Plan, PMS Report (PMSR) or PSUR. Far exceeds ISO 13485 feedback.",
            "上市後監督必須包含正式的PMS計畫、PMS報告（PMSR）或PSUR。遠超ISO 13485的回饋要求。",
        ),
        "8.2.2": (
            "Art 10(9)(j) / Art 87-92",
            MappingStatus.EXCEEDS,
            "Complaint handling must integrate with vigilance system and specific reporting timelines (15 days serious, 2 days death/life-threatening).",
            "客訴處理必須與警戒系統整合，並有特定通報時限（嚴重15天、死亡/危及生命2天）。",
        ),
        "8.2.3": (
            "Art 87-92",
            MappingStatus.EXCEEDS,
            "Regulatory reporting has strict timelines and specific formats. Must report to EUDAMED.",
            "法規通報有嚴格時限和特定格式。必須向EUDAMED通報。",
        ),
    }
    for clause_id, (ref, status, rationale_en, rationale_zh) in exceeds_clauses.items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=clause_id,
            status=status,
            regulation_ref=ref,
            rationale_en=rationale_en,
            rationale_zh=rationale_zh,
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.85,
            notes="EN ISO 13485:2016/A11:2021 Annex ZA + ISO/TR 17223:2018",
        )

    # EU MDR-specific unique requirements (delta)
    unique_reqs = [
        UniqueRequirement(
            req_id="MDR-001",
            regulation_ref="Article 15",
            title_en="Person Responsible for Regulatory Compliance (PRRC)",
            title_zh="法規合規負責人 (PRRC)",
            requirement_en=(
                "Manufacturers must designate at least one Person Responsible for "
                "Regulatory Compliance (PRRC) with specific qualifications: degree in law/medicine/"
                "pharmacy/engineering + 1yr professional experience, OR 4 years experience. "
                "PRRC must ensure conformity is checked, technical documentation and DoC are "
                "up to date, and PMS/vigilance obligations are fulfilled."
            ),
            requirement_zh=(
                "製造商必須指定至少一名法規合規負責人（PRRC），需具備特定資格："
                "法律/醫學/藥學/工程學位+1年專業經驗，或4年經驗。"
                "PRRC須確保符合性檢查、技術文件和DoC保持最新、"
                "及上市後監督/警戒義務之履行。"
            ),
            related_iso_clauses=["5.5.1", "5.5.2"],
            audit_impact="critical",
            audit_question_en=(
                "Has the organization designated a PRRC with the required qualifications "
                "per EU MDR Article 15? Are PRRC responsibilities documented?"
            ),
            audit_question_zh=(
                "組織是否依 EU MDR 第15條指定具備所需資格的 PRRC？"
                "PRRC 的職責是否已文件化？"
            ),
            expected_evidence=[
                "PRRC appointment letter with qualifications / PRRC 任命書及資格證明",
                "PRRC responsibility description / PRRC 職責說明",
                "PRRC qualification evidence (degree + experience) / PRRC 資格證據（學歷+經驗）",
            ],
            rationale_en=(
                "PRRC (Article 15) has no equivalent in ISO 13485. The closest clauses are "
                "5.5.1 (responsibility & authority) and 5.5.2 (management representative), "
                "but PRRC has specific qualification requirements and legal liability that go "
                "far beyond a management representative role."
            ),
            rationale_zh=(
                "PRRC（第15條）在 ISO 13485 中無對應。最接近的條款是 5.5.1（責任與權限）"
                "和 5.5.2（管理代表），但 PRRC 有特定資格要求和法律責任，"
                "遠超管理代表的角色。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.95,
            original_text=(
                "Article 15(1): Manufacturers shall have available within their organisation at least one "
                "person responsible for regulatory compliance who possesses the requisite expertise in "
                "the field of medical devices. The requisite expertise shall be demonstrated by either "
                "of the following qualifications: (a) a diploma, certificate or other evidence of formal "
                "qualification... (b) four years of professional experience..."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "EU MDR uses 'person responsible for regulatory compliance' (PRRC) with LEGALLY DEFINED "
                "qualification requirements (diploma + experience OR 4yr experience). "
                "ISO 13485 Cl. 5.5.2 uses 'management representative' with no specific qualification criteria. "
                "US QMSR has no equivalent role — quality responsibility is general management duty. "
                "Taiwan TFDA has '技術人員' (Technical Personnel, Art 13/15) with 20hr/yr CE requirement "
                "— similar concept but different scope (focuses on technical competency vs regulatory compliance). "
                "Key difference: PRRC carries PERSONAL legal liability in EU; no equivalent personal liability "
                "concept exists in US, Taiwan, or ISO 13485."
            ),
        ),
        UniqueRequirement(
            req_id="MDR-002",
            regulation_ref="Annex XIV / Article 61",
            title_en="Clinical Evaluation & Post-Market Clinical Follow-up (PMCF)",
            title_zh="臨床評估與上市後臨床追蹤 (PMCF)",
            requirement_en=(
                "EU MDR requires a continuous clinical evaluation lifecycle throughout the device "
                "lifecycle, including a PMCF plan and PMCF evaluation report. This is a "
                "structured, ongoing process — not a one-time design validation activity. "
                "Class III and implantable devices have the strictest requirements."
            ),
            requirement_zh=(
                "EU MDR 要求在器材整個生命週期中進行持續的臨床評估，"
                "包含 PMCF 計畫和 PMCF 評估報告。這是結構化的持續過程，"
                "而非一次性的設計確認活動。第III類和植入式器材有最嚴格的要求。"
            ),
            related_iso_clauses=["7.3.6", "7.3.7", "8.2.1"],
            audit_impact="critical",
            audit_question_en=(
                "Does the organization maintain a clinical evaluation report with ongoing PMCF "
                "plan per EU MDR Annex XIV? Is clinical evidence updated periodically?"
            ),
            audit_question_zh=(
                "組織是否依 EU MDR 附錄XIV 維持臨床評估報告及持續的 PMCF 計畫？"
                "臨床證據是否定期更新？"
            ),
            expected_evidence=[
                "Clinical Evaluation Report (CER) / 臨床評估報告",
                "PMCF Plan / PMCF 計畫",
                "PMCF Evaluation Report / PMCF 評估報告",
                "Literature review records / 文獻回顧記錄",
            ],
            rationale_en=(
                "Clinical evaluation (Annex XIV) is an EU MDR-specific lifecycle requirement. "
                "ISO 13485 mentions clinical evaluation in 7.3.6/7.3.7 for design validation, "
                "but does not require the continuous PMCF lifecycle approach. "
                "Also relates to 8.2.1 (feedback) as PMCF feeds back to product improvement."
            ),
            rationale_zh=(
                "臨床評估（附錄XIV）是 EU MDR 特有的生命週期要求。"
                "ISO 13485 在 7.3.6/7.3.7 提及設計確認的臨床評估，"
                "但不要求持續的 PMCF 生命週期方法。"
                "也與 8.2.1（回饋）相關，因 PMCF 回饋至產品改善。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.95,
            original_text=(
                "Manufacturers shall ensure that each device is accompanied by the information needed to "
                "identify the device and the manufacturer, and by any safety and performance information "
                "relevant to the user... The manufacturer shall draw up and keep up to date a clinical "
                "evaluation report which shall, through a clinical evaluation in accordance with "
                "Annex XIV, support the conformity assessment of the device throughout its lifetime."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "EU MDR Art 61(1) mandates a CONTINUOUS clinical evaluation lifecycle, not a one-time "
                "design validation. The Clinical Evaluation Report (CER) must be updated throughout the "
                "device lifetime, supported by PMCF (Post-Market Clinical Follow-up). "
                "US FDA: 510(k) requires clinical data at submission but has no continuous CER requirement. "
                "PMA devices have annual reports but not a structured CER/PMCF framework. "
                "Taiwan TFDA: requires clinical data for 查驗登記 but no structured PMCF lifecycle. "
                "ISO 13485 7.3.6/7.3.7: mentions design validation including clinical evaluation but "
                "does not mandate the ongoing lifecycle approach. "
                "Cross-country: EU is the strictest with continuous lifecycle clinical evaluation."
            ),
        ),
        UniqueRequirement(
            req_id="MDR-003",
            regulation_ref="Article 83-86",
            title_en="Post-Market Surveillance (PMS) System",
            title_zh="上市後監督 (PMS) 系統",
            requirement_en=(
                "Manufacturers must establish a PMS system proportionate to device risk class. "
                "Must produce PMS Plan, PMS Report (PMSR, for Class I) or Periodic Safety "
                "Update Report (PSUR, for Class IIa/IIb/III). PMS feeds into clinical evaluation "
                "and risk management updates."
            ),
            requirement_zh=(
                "製造商必須建立與器材風險等級相稱的 PMS 系統。"
                "須產出 PMS 計畫、PMS 報告（PMSR，第I類）或定期安全更新報告"
                "（PSUR，第IIa/IIb/III類）。PMS 回饋至臨床評估與風險管理更新。"
            ),
            related_iso_clauses=["8.2.1", "8.4", "8.5.1"],
            audit_impact="critical",
            audit_question_en=(
                "Does the organization have a documented PMS system with PMS Plan "
                "and appropriate PMS reports (PMSR or PSUR) per EU MDR Articles 83-86?"
            ),
            audit_question_zh=(
                "組織是否建立文件化的 PMS 系統，含 PMS 計畫及適當的 PMS 報告"
                "（PMSR 或 PSUR）？（EU MDR 第83-86條）"
            ),
            expected_evidence=[
                "PMS Plan / PMS 計畫",
                "PMS Report (PMSR) or PSUR / PMS 報告或 PSUR",
                "PMS data collection procedures / PMS 資料收集程序",
            ],
            rationale_en=(
                "PMS system (Art 83-86) is an EU MDR-specific framework. ISO 13485 Clause "
                "8.2.1 covers feedback but does not require the structured PMS Plan/PMSR/PSUR "
                "approach. Relates to 8.4 (data analysis) and 8.5.1 (improvement) as PMS "
                "drives product improvement decisions."
            ),
            rationale_zh=(
                "PMS 系統（第83-86條）是 EU MDR 特有的架構。ISO 13485 條款 8.2.1 "
                "涵蓋回饋但不要求結構化的 PMS 計畫/PMSR/PSUR 方法。"
                "與 8.4（數據分析）和 8.5.1（改善）相關，因 PMS 驅動產品改善決策。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "Manufacturers shall plan, establish, document, implement, maintain and update a "
                "post-market surveillance system... The post-market surveillance plan shall cover: "
                "(a) a proactive and systematic process to collect and utilise information; "
                "(b) appropriate indicators and threshold values; (c) methods and protocols to "
                "collect and evaluate data."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "EU MDR Art 83 creates a structured PMS system with PMSR (Class I) or PSUR (Class IIa+). "
                "PSUR must be updated at least annually for Class IIa/IIb and at least every 2 years "
                "for Class IIa, with NB review. "
                "US FDA: \u00a7822 Post-Market Surveillance applies only to specific ordered devices. "
                "No mandatory PMSR/PSUR equivalent for all devices. "
                "Taiwan TFDA: has post-market monitoring requirements under 醫療器材安全監視管理辦法 "
                "but no structured PMSR/PSUR report format. "
                "ISO 13485 8.2.1: requires customer feedback system but not a structured PMS plan. "
                "Cross-country: EU has the most comprehensive mandatory PMS framework."
            ),
        ),
        UniqueRequirement(
            req_id="MDR-004",
            regulation_ref="Article 27 / Article 123",
            title_en="UDI System & EUDAMED Registration",
            title_zh="UDI 系統與 EUDAMED 註冊",
            requirement_en=(
                "Manufacturers must assign UDI to devices and register in EUDAMED database. "
                "UDI-DI and UDI-PI must be on device label and all higher packaging levels. "
                "EUDAMED registration includes device, economic operator, certificate, "
                "and clinical investigation data."
            ),
            requirement_zh=(
                "製造商必須為器材指派 UDI 並在 EUDAMED 資料庫中註冊。"
                "UDI-DI 和 UDI-PI 必須標示在器材標籤及所有上層包裝上。"
                "EUDAMED 註冊包含器材、經濟操作者、證書及臨床調查資料。"
            ),
            related_iso_clauses=["7.5.8", "7.5.9", "7.5.9.2"],
            audit_impact="critical",
            audit_question_en=(
                "Has UDI been assigned to all devices and registered in EUDAMED "
                "per EU MDR Article 27?"
            ),
            audit_question_zh=(
                "是否已依 EU MDR 第27條為所有器材指派 UDI 並在 EUDAMED 中註冊？"
            ),
            expected_evidence=[
                "UDI assignment records / UDI 指派記錄",
                "EUDAMED registration confirmation / EUDAMED 註冊確認",
                "UDI on device labels / 器材標籤上之 UDI",
            ],
            rationale_en=(
                "EU UDI/EUDAMED (Art 27) has no direct equivalent in ISO 13485. "
                "Clause 7.5.9.2 mentions UDI but only generically. EU MDR requires "
                "specific EU-format UDI and EUDAMED database registration. "
                "Related to 7.5.8 (identification) and 7.5.9 (traceability)."
            ),
            rationale_zh=(
                "歐盟 UDI/EUDAMED（第27條）在 ISO 13485 中無直接對應。"
                "條款 7.5.9.2 提及 UDI 但僅為一般性。EU MDR 要求特定的歐盟格式 "
                "UDI 和 EUDAMED 資料庫註冊。相關條款：7.5.8（識別）和 7.5.9（追溯性）。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "The unique device identifier ('UDI') referred to in Article 27(1) shall be created "
                "by a UDI assigning entity... Before placing a device, other than a custom-made device, "
                "on the market, the manufacturer shall assign to the device and, where applicable, "
                "to all higher levels of packaging, a UDI."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "EU MDR Art 27 requires UDI assigned via EU-recognized issuing entities and registration "
                "in EUDAMED. UDI has two components: UDI-DI (device identifier) + UDI-PI (production identifier). "
                "US FDA: has its own UDI system (GUDID) under 21 CFR 830, operational since 2013. "
                "FDA UDI uses the same issuing agencies (GS1, HIBCC, ICCBBA) but registers in GUDID, not EUDAMED. "
                "Taiwan TFDA: uses its own 許可證字號 (license number) system, not UDI. "
                "ISO 13485 7.5.9.2: mentions UDI but only as 'where applicable' and does not mandate "
                "a specific UDI system or database. "
                "Cross-country: US and EU both require UDI but in separate databases (GUDID vs EUDAMED); "
                "Taiwan has no UDI system."
            ),
        ),
        UniqueRequirement(
            req_id="MDR-005",
            regulation_ref="Article 87-92",
            title_en="Vigilance — Serious Incident Reporting",
            title_zh="警戒 — 嚴重事件通報",
            requirement_en=(
                "Manufacturers must report serious incidents to competent authorities within "
                "strict timelines: 2 days for death or unanticipated serious deterioration in "
                "health, 10 days for serious public health threats, 15 days for other serious "
                "incidents. Must also report Field Safety Corrective Actions (FSCA)."
            ),
            requirement_zh=(
                "製造商必須在嚴格時限內向主管機關通報嚴重事件："
                "死亡或非預期嚴重健康惡化2天、嚴重公共衛生威脅10天、"
                "其他嚴重事件15天。也必須通報現場安全矯正措施（FSCA）。"
            ),
            related_iso_clauses=["8.2.2", "8.2.3"],
            audit_impact="critical",
            audit_question_en=(
                "Does the vigilance system meet EU MDR timelines (2/10/15 days) "
                "for serious incident reporting and FSCA?"
            ),
            audit_question_zh=(
                "警戒系統是否符合 EU MDR 的嚴重事件通報時限（2/10/15天）及 FSCA 要求？"
            ),
            expected_evidence=[
                "Vigilance procedure with EU MDR timelines / 含 EU MDR 時限之警戒程序書",
                "Serious incident report forms / 嚴重事件通報表",
                "FSCA records / FSCA 記錄",
            ],
            rationale_en=(
                "EU MDR vigilance (Art 87-92) has stricter timelines than ISO 13485. "
                "ISO 13485 Clause 8.2.3 requires regulatory reporting but does not specify "
                "2/10/15 day timelines. Relates to 8.2.2 (complaint handling) as vigilance "
                "often originates from complaints."
            ),
            rationale_zh=(
                "EU MDR 警戒（第87-92條）比 ISO 13485 有更嚴格的時限。"
                "ISO 13485 條款 8.2.3 要求法規通報但未規定 2/10/15 天時限。"
                "與 8.2.2（客訴處理）相關，因警戒常源自客訴。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "Manufacturers of devices, other than serious public health threat devices, shall "
                "report... any serious incident involving devices made available on the Union market "
                "to the relevant competent authority... without delay after they become aware of the "
                "causal relationship... and not later than 15 days... In the event of a serious "
                "public health threat, the period shall be reduced to 2 days."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "EU MDR Art 87 has the strictest vigilance timelines globally: 2/10/15 days. "
                "US FDA MDR (Medical Device Reports under 21 CFR 803): 5 working days for death-related events, "
                "30 calendar days for serious injury/malfunction. No FSCA concept in US (uses recalls instead). "
                "Taiwan TFDA: 7 days for death/life-threatening, 15 days for other serious events. "
                "ISO 13485 8.2.3: requires reporting to regulatory authorities but specifies no timeline. "
                "Cross-country comparison of timelines: EU 2/10/15 days > Taiwan 7/15 days > US 5/30 days. "
                "EU is the most stringent and also requires FSCA (Field Safety Corrective Actions)."
            ),
        ),
        UniqueRequirement(
            req_id="MDR-006",
            regulation_ref="Article 32",
            title_en="Summary of Safety and Clinical Performance (SSCP)",
            title_zh="安全與臨床性能摘要 (SSCP)",
            requirement_en=(
                "For Class III devices and implantable devices (except sutures, staples, "
                "dental fillings, etc.), manufacturers must prepare an SSCP document, "
                "validated by the Notified Body, and uploaded to EUDAMED."
            ),
            requirement_zh=(
                "對於第III類器材和植入式器材（縫合線、釘等除外），"
                "製造商必須準備 SSCP 文件，經公告機構驗證後上傳至 EUDAMED。"
            ),
            related_iso_clauses=["4.2.5", "7.3.6"],
            audit_impact="critical",
            audit_question_en=(
                "For Class III/implantable devices, has an SSCP been prepared, "
                "validated by the Notified Body, and uploaded to EUDAMED?"
            ),
            audit_question_zh=(
                "對於第III類/植入式器材，是否已準備 SSCP 文件，"
                "經公告機構驗證並上傳至 EUDAMED？"
            ),
            expected_evidence=[
                "SSCP document / SSCP 文件",
                "Notified Body validation of SSCP / 公告機構對 SSCP 的驗證",
                "EUDAMED upload confirmation / EUDAMED 上傳確認",
            ],
            rationale_en=(
                "SSCP (Article 32) is entirely new in EU MDR with no equivalent in ISO 13485. "
                "Closest to 4.2.5 (medical device file) as SSCP is part of technical documentation, "
                "and 7.3.6 (design validation) as it references clinical performance data."
            ),
            rationale_zh=(
                "SSCP（第32條）是 EU MDR 全新的要求，ISO 13485 中無對應。"
                "最接近 4.2.5（醫療器材檔案）因 SSCP 是技術文件的一部分，"
                "及 7.3.6（設計確認）因引用臨床性能資料。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "For implantable devices and for class III devices, the manufacturer shall draw up a "
                "summary of safety and clinical performance. The summary of safety and clinical "
                "performance shall be written in a way that is clear to the intended user and, if "
                "relevant, to the patient and shall be made available to the public via EUDAMED."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "SSCP (Art 32) is a publicly available document unique to EU MDR — no equivalent exists "
                "in any other jurisdiction. It must be validated by the Notified Body and uploaded to EUDAMED. "
                "US FDA: no equivalent public-facing clinical performance summary document. "
                "Taiwan TFDA: no equivalent requirement. "
                "ISO 13485: no equivalent — the medical device file (4.2.5) is manufacturer-internal. "
                "Cross-country: SSCP is entirely EU-specific, combining transparency (public access), "
                "NB oversight (validation), and clinical evidence (safety+performance data) in one document."
            ),
        ),
        UniqueRequirement(
            req_id="MDR-007",
            regulation_ref="Annex I (GSPR)",
            title_en="General Safety and Performance Requirements (GSPR) Compliance",
            title_zh="一般安全與性能要求 (GSPR) 合規",
            requirement_en=(
                "Manufacturers must demonstrate compliance with ALL applicable General Safety "
                "and Performance Requirements in Annex I. Must use risk management approach "
                "to reduce risks 'as far as possible' (stricter than ALARP/ALARA). "
                "GSPR checklist must be part of Technical Documentation."
            ),
            requirement_zh=(
                "製造商必須展示符合附錄I所有適用的一般安全與性能要求。"
                "必須使用風險管理方法將風險降低'至盡可能低'（比ALARP/ALARA更嚴格）。"
                "GSPR 檢查表必須作為技術文件的一部分。"
            ),
            related_iso_clauses=["7.1", "7.3.2", "7.3.3"],
            audit_impact="critical",
            audit_question_en=(
                "Is there a GSPR checklist demonstrating compliance with all applicable "
                "Annex I requirements as part of the Technical Documentation?"
            ),
            audit_question_zh=(
                "是否有 GSPR 檢查表作為技術文件的一部分，展示符合所有適用的附錄I要求？"
            ),
            expected_evidence=[
                "GSPR checklist / GSPR 檢查表",
                "Risk-benefit analysis per Annex I / 依附錄I之風險效益分析",
                "Standards applied per GSPR / 每項GSPR適用之標準",
            ],
            rationale_en=(
                "GSPR (Annex I) is the core safety framework of EU MDR with no ISO 13485 "
                "equivalent. Closest to 7.1 (product realization planning), 7.3.2 (design input) "
                "and 7.3.3 (design output) as GSPR defines what the device must achieve."
            ),
            rationale_zh=(
                "GSPR（附錄I）是 EU MDR 的核心安全架構，ISO 13485 無對應。"
                "最接近 7.1（產品實現規劃）、7.3.2（設計輸入）和 7.3.3（設計輸出），"
                "因 GSPR 定義器材必須達到的目標。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "Devices shall achieve the performance intended by their manufacturer and shall be "
                "designed and manufactured in such a way that, during normal conditions of use, they "
                "are suitable for their intended purpose... The requirement in this Annex to reduce "
                "risks as far as possible means the reduction of risks as far as possible without "
                "adversely affecting the benefit-risk ratio."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "EU MDR Annex I uses 'as far as possible' for risk reduction, which is STRICTER than the "
                "ALARP (As Low As Reasonably Practicable) or ALARA (As Low As Reasonably Achievable) "
                "principles used in ISO 14971 and other jurisdictions. The difference: 'reasonably' allows "
                "cost/practicality arguments; 'as far as possible' does not. "
                "US FDA: uses Essential Performance concept and 'reasonable assurance of safety and effectiveness' "
                "from the FD&C Act. Less stringent than EU 'as far as possible'. "
                "Taiwan TFDA: follows 基本原則 (Essential Principles) similar to EU GSPR but without the "
                "explicit 'as far as possible' language. "
                "ISO 13485 7.1: requires risk management during product realization but does not define "
                "risk acceptability criteria — defers to ISO 14971 and manufacturer's risk policy. "
                "Cross-country: EU has the strictest risk reduction standard globally."
            ),
        ),
    ]

    return RegulationProfile(
        regulation_id="EU_MDR",
        name_en="EU MDR 2017/745 (Medical Device Regulation)",
        name_zh="歐盟 MDR 2017/745（醫療器材法規）",
        country="EU",
        country_name_en="European Union",
        country_name_zh="歐盟",
        source="predefined",
        source_url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32017R0745",
        last_updated="2017-05-05",
        effective_date="2021-05-26",
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )


# ============================================================
# Predefined Regulation: Taiwan TFDA
# ============================================================


def _build_tfda_profile() -> RegulationProfile:
    """Build the Taiwan TFDA regulation profile.

    Taiwan's Medical Device QMS Regulations (醫療器材品質管理系統準則)
    84 Articles, promulgated 2021, directly references ISO 13485:2016.

    Mapping source: Official regulation text (laws.moj.gov.tw)
    + TFDA QMS/GMP Explanatory Notes
    """
    # TFDA 84 Articles directly map to ISO 13485 clauses
    iso_mapped: dict[str, ClauseMapping] = {}

    # Article-to-clause mapping (from TFDA regulation structure)
    tfda_article_map = {
        "4.1": (
            "Art. 6",
            "Article 6 establishes general QMS requirements, directly referencing ISO 13485 Clause 4.1.",
            "第6條建立一般QMS要求，直接引用ISO 13485條款4.1。",
        ),
        "4.2.1": (
            "Art. 7",
            "Article 7 covers documentation requirements.",
            "第7條涵蓋文件化要求。",
        ),
        "4.2.2": ("Art. 9", "Article 9 covers quality manual.", "第9條涵蓋品質手冊。"),
        "4.2.3": (
            "Art. 10",
            "Article 10 covers document control.",
            "第10條涵蓋文件管制。",
        ),
        "4.2.4": (
            "Art. 11",
            "Article 11 covers record control.",
            "第11條涵蓋記錄管制。",
        ),
        "4.2.5": (
            "Art. 8",
            "Article 8 covers medical device file.",
            "第8條涵蓋醫療器材檔案。",
        ),
        "5.1": (
            "Art. 12",
            "Article 12 covers management commitment.",
            "第12條涵蓋管理承諾。",
        ),
        "5.2": (
            "Art. 13",
            "Article 13 covers customer focus.",
            "第13條涵蓋以顧客為重。",
        ),
        "5.3": ("Art. 14", "Article 14 covers quality policy.", "第14條涵蓋品質政策。"),
        "5.4.1": (
            "Art. 15",
            "Article 15 covers quality objectives.",
            "第15條涵蓋品質目標。",
        ),
        "5.4.2": ("Art. 16", "Article 16 covers QMS planning.", "第16條涵蓋QMS規劃。"),
        "5.5.1": (
            "Art. 17",
            "Article 17 covers responsibility and authority.",
            "第17條涵蓋責任與權限。",
        ),
        "5.5.2": (
            "Art. 18",
            "Article 18 covers management representative.",
            "第18條涵蓋管理代表。",
        ),
        "5.5.3": (
            "Art. 19",
            "Article 19 covers internal communication.",
            "第19條涵蓋內部溝通。",
        ),
        "5.6.1": (
            "Art. 20",
            "Article 20 covers management review.",
            "第20條涵蓋管理審查。",
        ),
        "5.6.2": (
            "Art. 20",
            "Article 20 includes management review input.",
            "第20條包含管理審查輸入。",
        ),
        "5.6.3": (
            "Art. 20",
            "Article 20 includes management review output.",
            "第20條包含管理審查輸出。",
        ),
        "6.1": (
            "Art. 21",
            "Article 21 covers resource provision.",
            "第21條涵蓋資源提供。",
        ),
        "6.2": (
            "Art. 22",
            "Article 22 covers human resources.",
            "第22條涵蓋人力資源。",
        ),
        "6.3": (
            "Art. 23-24",
            "Articles 23-24 cover infrastructure.",
            "第23-24條涵蓋基礎設施。",
        ),
        "6.4.1": (
            "Art. 25",
            "Article 25 covers work environment.",
            "第25條涵蓋工作環境。",
        ),
        "6.4.2": (
            "Art. 26",
            "Article 26 covers contamination control.",
            "第26條涵蓋污染管制。",
        ),
        "7.1": (
            "Art. 27",
            "Article 27 covers product realization planning.",
            "第27條涵蓋產品實現規劃。",
        ),
        "7.2.1": (
            "Art. 28",
            "Article 28 covers determination of product requirements.",
            "第28條涵蓋產品要求確定。",
        ),
        "7.2.2": (
            "Art. 29",
            "Article 29 covers review of product requirements.",
            "第29條涵蓋產品要求審查。",
        ),
        "7.2.3": ("Art. 30", "Article 30 covers communication.", "第30條涵蓋溝通。"),
        "7.3.1": (
            "Art. 34",
            "Article 34 covers design planning.",
            "第34條涵蓋設計規劃。",
        ),
        "7.3.2": ("Art. 35", "Article 35 covers design input.", "第35條涵蓋設計輸入。"),
        "7.3.3": (
            "Art. 36",
            "Article 36 covers design output.",
            "第36條涵蓋設計輸出。",
        ),
        "7.3.4": (
            "Art. 37",
            "Article 37 covers design review.",
            "第37條涵蓋設計審查。",
        ),
        "7.3.5": (
            "Art. 38",
            "Article 38 covers design verification.",
            "第38條涵蓋設計驗證。",
        ),
        "7.3.6": (
            "Art. 39",
            "Article 39 covers design validation.",
            "第39條涵蓋設計確認。",
        ),
        "7.3.7": (
            "Art. 40",
            "Article 40 covers design transfer.",
            "第40條涵蓋設計轉移。",
        ),
        "7.3.8": (
            "Art. 41",
            "Article 41 covers design change control.",
            "第41條涵蓋設計變更管制。",
        ),
        "7.3.9": ("Art. 42", "Article 42 covers design files.", "第42條涵蓋設計檔案。"),
        "7.3.10": (
            "Art. 43",
            "Article 43 covers design documentation.",
            "第43條涵蓋設計文件。",
        ),
        "7.4.1": (
            "Art. 44",
            "Article 44 covers purchasing process.",
            "第44條涵蓋採購過程。",
        ),
        "7.4.2": (
            "Art. 45",
            "Article 45 covers purchasing information.",
            "第45條涵蓋採購資訊。",
        ),
        "7.4.3": (
            "Art. 46",
            "Article 46 covers verification of purchased product.",
            "第46條涵蓋採購產品驗證。",
        ),
        "7.5.1": (
            "Art. 51",
            "Article 51 covers production control.",
            "第51條涵蓋生產管制。",
        ),
        "7.5.2": (
            "Art. 52",
            "Article 52 covers product cleanliness.",
            "第52條涵蓋產品潔淨。",
        ),
        "7.5.3": ("Art. 53", "Article 53 covers installation.", "第53條涵蓋安裝。"),
        "7.5.4": ("Art. 54", "Article 54 covers servicing.", "第54條涵蓋服務。"),
        "7.5.5": (
            "Art. 55",
            "Article 55 covers sterile device requirements.",
            "第55條涵蓋無菌裝置要求。",
        ),
        "7.5.6": (
            "Art. 56",
            "Article 56 covers process validation.",
            "第56條涵蓋過程確認。",
        ),
        "7.5.7": (
            "Art. 57",
            "Article 57 covers sterilization validation.",
            "第57條涵蓋滅菌確認。",
        ),
        "7.5.8": ("Art. 58", "Article 58 covers identification.", "第58條涵蓋識別。"),
        "7.5.9": ("Art. 59", "Article 59 covers traceability.", "第59條涵蓋追溯性。"),
        "7.5.9.1": (
            "Art. 60",
            "Article 60 covers implant traceability.",
            "第60條涵蓋植入物追溯性。",
        ),
        "7.5.9.2": ("Art. 61", "Article 61 covers UDI.", "第61條涵蓋UDI。"),
        "7.5.10": (
            "Art. 47",
            "Article 47 covers customer property.",
            "第47條涵蓋顧客財產。",
        ),
        "7.5.11": (
            "Art. 48-50",
            "Articles 48-50 cover product preservation.",
            "第48-50條涵蓋產品防護。",
        ),
        "7.6": (
            "Art. 62",
            "Article 62 covers monitoring equipment.",
            "第62條涵蓋監測設備。",
        ),
        "8.1": (
            "Art. 63",
            "Article 63 covers general measurement requirements.",
            "第63條涵蓋一般量測要求。",
        ),
        "8.2.1": ("Art. 64", "Article 64 covers feedback.", "第64條涵蓋回饋。"),
        "8.2.2": (
            "Art. 65",
            "Article 65 covers complaint handling.",
            "第65條涵蓋客訴處理。",
        ),
        "8.2.3": (
            "Art. 66",
            "Article 66 covers regulatory reporting.",
            "第66條涵蓋法規通報。",
        ),
        "8.2.4": (
            "Art. 67",
            "Article 67 covers internal audit.",
            "第67條涵蓋內部稽核。",
        ),
        "8.2.4.1": (
            "Art. 67",
            "Article 67 includes audit criteria.",
            "第67條包含稽核準則。",
        ),
        "8.2.4.2": (
            "Art. 68",
            "Article 68 covers audit corrective actions.",
            "第68條涵蓋稽核矯正措施。",
        ),
        "8.2.5": (
            "Art. 69",
            "Article 69 covers process monitoring.",
            "第69條涵蓋過程監督。",
        ),
        "8.2.6": (
            "Art. 70-71",
            "Articles 70-71 cover product monitoring.",
            "第70-71條涵蓋產品監督。",
        ),
        "8.3": (
            "Art. 72",
            "Article 72 covers nonconforming product.",
            "第72條涵蓋不合格品。",
        ),
        "8.3.1": (
            "Art. 73",
            "Article 73 covers pre-delivery nonconformance.",
            "第73條涵蓋交付前不合格。",
        ),
        "8.3.2": (
            "Art. 74",
            "Article 74 covers post-delivery nonconformance.",
            "第74條涵蓋交付後不合格。",
        ),
        "8.3.3": ("Art. 75", "Article 75 covers concessions.", "第75條涵蓋讓步。"),
        "8.3.4": ("Art. 76", "Article 76 covers rework.", "第76條涵蓋返工。"),
        "8.4": ("Art. 77", "Article 77 covers data analysis.", "第77條涵蓋數據分析。"),
        "8.5.1": ("Art. 78", "Article 78 covers improvement.", "第78條涵蓋改善。"),
        "8.5.2": (
            "Art. 79",
            "Article 79 covers corrective action.",
            "第79條涵蓋矯正措施。",
        ),
        "8.5.3": (
            "Art. 80",
            "Article 80 covers preventive action.",
            "第80條涵蓋預防措施。",
        ),
    }
    for clause_id, (ref, rationale_en, rationale_zh) in tfda_article_map.items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=clause_id,
            status=MappingStatus.FULL,
            regulation_ref=ref,
            rationale_en=rationale_en,
            rationale_zh=rationale_zh,
            method=MappingMethod.CLAUSE_STRUCTURE,
            confidence=0.95,
            notes="醫療器材品質管理系統準則 (laws.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0030097)",
        )

    # Taiwan-specific unique requirements (delta)
    unique_reqs = [
        UniqueRequirement(
            req_id="TFDA-001",
            regulation_ref="第11條 / Art. 11",
            title_en="Record Retention — 3-Year Minimum",
            title_zh="記錄保存 — 最少3年",
            requirement_en=(
                "Records must be kept for at least the lifetime of the medical device, "
                "but no less than 3 years from the date the product was released. "
                "ISO 13485 Clause 4.2.5 requires retention for at least 2 years "
                "or as specified by regulations. Taiwan's 3-year minimum is a specific local floor."
            ),
            requirement_zh=(
                "記錄必須保存至少醫療器材的壽命期間，但不少於產品放行日起3年。"
                "ISO 13485 條款 4.2.5 要求保存至少2年或依法規規定。"
                "台灣的3年最低要求是特定的本地底限。"
            ),
            related_iso_clauses=["4.2.4", "4.2.5"],
            audit_impact="major",
            audit_question_en=(
                "Are quality records retained for at least 3 years from product release, "
                "or the lifetime of the device, whichever is longer, per TFDA Article 11?"
            ),
            audit_question_zh=(
                "品質記錄是否依 TFDA 第11條保存至少產品放行日起3年，"
                "或器材壽命期間（取較長者）？"
            ),
            expected_evidence=[
                "Record retention policy showing 3-year minimum / 顯示3年最低要求之記錄保存政策",
                "Record retention schedule / 記錄保存期限表",
            ],
            rationale_en=(
                "TFDA Article 11 sets a 3-year floor vs ISO 13485's 2-year minimum. "
                "Classified under 4.2.4/4.2.5 as both address record retention policies."
            ),
            rationale_zh=(
                "TFDA 第11條設定3年底限，vs ISO 13485 的2年最低要求。"
                "歸類於 4.2.4/4.2.5 因兩者皆涉及記錄保存政策。"
            ),
            method=MappingMethod.CLAUSE_STRUCTURE,
            confidence=0.95,
            original_text=(
                "醫療器材品質管理系統準則第十一條：製造業者應將品質紀錄至少保存自產品放行日起三年"
                "或醫療器材有效期限加一年（取較長者）。"
            ),
            original_lang="zh-TW",
            english_translation=(
                "TFDA QMS Regulations Article 11: Manufacturers shall retain quality records for at least "
                "three years from the date of product release, or the expiry date of the medical device "
                "plus one year, whichever is longer."
            ),
            semantic_note=(
                "Taiwan uses '至少保存自產品放行日起三年' (at least 3 years from release). "
                "ISO 13485 Cl. 4.2.5 uses 'at least the lifetime of the medical device as defined by the organization, "
                "but not less than two years from the date of product release'. "
                "US QMSR §820.35 follows ISO 13485 (2-year floor). EU MDR does not specify a minimum floor but "
                "defers to notified body expectations (typically 10-15 years for implants). "
                "Key difference: Taiwan's 3-year floor is HIGHER than ISO/US 2-year floor, "
                "but LOWER than typical EU expectations for higher-risk devices."
            ),
        ),
        UniqueRequirement(
            req_id="TFDA-002",
            regulation_ref="醫療器材管理法 第33條",
            title_en="Chinese Labeling & Instructions for Use",
            title_zh="中文標示與使用說明",
            requirement_en=(
                "All medical devices sold in Taiwan must have labeling, instructions for use "
                "(IFU), and packaging text in Traditional Chinese. This is a market access "
                "requirement not addressed by ISO 13485."
            ),
            requirement_zh=(
                "所有在台灣銷售的醫療器材必須以繁體中文標示標籤、"
                "使用說明書（IFU）及包裝文字。此為市場准入要求，ISO 13485 未涉及。"
            ),
            related_iso_clauses=["7.5.1", "7.5.8", "7.5.11"],
            audit_impact="major",
            audit_question_en=(
                "Do device labels, IFU, and packaging include Traditional Chinese text "
                "as required by Taiwan Medical Device Act Article 33?"
            ),
            audit_question_zh=(
                "器材標籤、使用說明書及包裝是否依醫療器材管理法第33條包含繁體中文文字？"
            ),
            expected_evidence=[
                "Chinese-language labels / 中文標籤",
                "Chinese IFU / 中文使用說明書",
                "Chinese packaging text / 中文包裝文字",
            ],
            rationale_en=(
                "Chinese labeling is a Taiwan market access requirement with no ISO 13485 clause. "
                "Closest to 7.5.1 (production control includes labeling), 7.5.8 (identification), "
                "7.5.11 (preservation/packaging). Determined by regulatory text analysis."
            ),
            rationale_zh=(
                "中文標示是台灣市場准入要求，ISO 13485 無對應條款。"
                "最接近 7.5.1（生產管制含標示）、7.5.8（識別）、7.5.11（防護/包裝）。"
                "由法規文本分析確定。"
            ),
            method=MappingMethod.SEMANTIC_ZH,
            confidence=0.90,
            original_text=(
                "醫療器材管理法第三十三條：醫療器材之標籤、說明書及包裝，應以中文為主，"
                "必要時輔以外文。不得僅以外文標示。"
            ),
            original_lang="zh-TW",
            english_translation=(
                "Medical Device Act Article 33: Labels, instructions for use, and packaging of medical devices "
                "shall be primarily in Chinese, supplemented by foreign languages when necessary. "
                "Foreign language only labeling is NOT permitted."
            ),
            semantic_note=(
                "Taiwan uses '以中文為主' (Chinese as primary), which means Chinese must be the DOMINANT language. "
                "US FDA requires English but allows bilingual labeling. "
                "EU MDR Art 10(11) requires labeling in the language(s) accepted by the Member State — this varies "
                "by country (e.g., German in Germany, French in France, could be multiple languages). "
                "Key difference: Taiwan mandates Traditional Chinese as PRIMARY; EU varies by member state; "
                "US mandates English. Each jurisdiction has different 'native language' requirements for labeling."
            ),
        ),
        UniqueRequirement(
            req_id="TFDA-003",
            regulation_ref="醫療器材管理法 第13、15條",
            title_en="Medical Device Technical Personnel",
            title_zh="醫療器材技術人員",
            requirement_en=(
                "Manufacturers must appoint qualified Technical Personnel who meet specific "
                "educational and experience criteria and complete 20 hours of continuing "
                "education every year. This is a personnel qualification requirement "
                "beyond ISO 13485 Clause 6.2."
            ),
            requirement_zh=(
                "製造商必須任命符合特定學歷與經驗條件的技術人員，"
                "並每年完成20小時的持續教育。此為超出 ISO 13485 條款 6.2 的人員資格要求。"
            ),
            related_iso_clauses=["6.2", "5.5.1"],
            audit_impact="critical",
            audit_question_en=(
                "Are Technical Personnel appointed with required qualifications, "
                "and do they complete 20 hours of annual continuing education per TFDA requirements?"
            ),
            audit_question_zh=(
                "是否任命具備所需資格的技術人員，"
                "且每年完成20小時持續教育？（TFDA 要求）"
            ),
            expected_evidence=[
                "Technical Personnel appointment records / 技術人員任命記錄",
                "Qualification certificates / 資格證書",
                "Annual CE training records (20 hrs) / 年度持續教育訓練記錄（20小時）",
            ],
            rationale_en=(
                "TFDA Technical Personnel (Art 13/15) has no direct ISO 13485 equivalent. "
                "Closest to 6.2 (human resources/competence) and 5.5.1 (responsibility). "
                "The 20-hour CE and specific qualification criteria exceed ISO requirements."
            ),
            rationale_zh=(
                "TFDA 技術人員（第13/15條）在 ISO 13485 中無直接對應。"
                "最接近 6.2（人力資源/能力）和 5.5.1（責任）。"
                "20小時持續教育和特定資格條件超出 ISO 要求。"
            ),
            method=MappingMethod.SEMANTIC_ZH,
            confidence=0.90,
            original_text=(
                "醫療器材製造業者應置技術人員，其資格條件如下：一、具有醫學、藥學、"
                "化學、生物學、工程或其他相關學系之大學以上學歷。二、具有醫療器材相關"
                "工作經驗三年以上。技術人員每年應接受不少於二十小時之持續教育。"
            ),
            original_lang="zh-TW",
            english_translation=(
                "Medical device manufacturers shall appoint technical personnel meeting the following "
                "qualifications: 1. University degree or above in medicine, pharmacy, chemistry, biology, "
                "engineering, or related fields. 2. At least 3 years of medical device-related work experience. "
                "Technical personnel shall receive at least 20 hours of continuing education annually."
            ),
            semantic_note=(
                "Taiwan Technical Personnel (技術人員) is a NAMED ROLE with specific qualification requirements. "
                "EU MDR PRRC (Art 15): also a named role with personal legal liability, requires 4+ years of "
                "professional experience, but focuses on regulatory compliance rather than technical qualifications. "
                "US FDA QMSR: no specific named individual requirement — only requires 'competent personnel' "
                "generally under ISO 13485 Clause 6.2. "
                "ISO 13485 6.2: requires personnel competence based on education, training, skills, experience, "
                "but does not mandate a specific named role or annual CE hours. "
                "Cross-country: Taiwan and EU both require named qualified individuals; US does not. "
                "Taiwan’s 20hr/year CE requirement is the most prescriptive of all three."
            ),
        ),
        UniqueRequirement(
            req_id="TFDA-004",
            regulation_ref="醫療器材安全監視管理辦法",
            title_en="Adverse Event Reporting — 7/15 Day Timelines",
            title_zh="不良事件通報 — 7/15天時限",
            requirement_en=(
                "TFDA requires reporting adverse events within specific timelines: "
                "7 days for death or serious life-threatening risks, "
                "15 days for other serious adverse events. ISO 13485 Clause 8.2.3 "
                "requires regulatory reporting but does not specify these timelines."
            ),
            requirement_zh=(
                "TFDA 要求在特定時限內通報不良事件："
                "死亡或嚴重危及生命風險7天、其他嚴重不良事件15天。"
                "ISO 13485 條款 8.2.3 要求法規通報但未規定這些時限。"
            ),
            related_iso_clauses=["8.2.2", "8.2.3"],
            audit_impact="critical",
            audit_question_en=(
                "Does the adverse event reporting procedure specify 7-day (death/life-threatening) "
                "and 15-day (other serious) reporting timelines per TFDA requirements?"
            ),
            audit_question_zh=(
                "不良事件通報程序是否規定7天（死亡/危及生命）"
                "和15天（其他嚴重事件）的通報時限？（TFDA 要求）"
            ),
            expected_evidence=[
                "Adverse event reporting procedure with TFDA timelines / 含TFDA時限之不良事件通報程序",
                "Reporting timeline compliance records / 通報時限合規記錄",
            ],
            rationale_en=(
                "TFDA adverse event timelines (7/15 days) are Taiwan-specific. "
                "ISO 13485 8.2.3 requires reporting but without specific day counts. "
                "Also relates to 8.2.2 (complaint handling) as adverse events often "
                "originate from complaints."
            ),
            rationale_zh=(
                "TFDA 不良事件時限（7/15天）為台灣特有要求。"
                "ISO 13485 8.2.3 要求通報但無特定天數。"
                "也與 8.2.2（客訴處理）相關，因不良事件常源自客訴。"
            ),
            method=MappingMethod.SEMANTIC_ZH,
            confidence=0.90,
            original_text=(
                "醫療器材業者於知悉所製造、輸入或販賣之醫療器材發生嚴重不良事件時，"
                "應於知悉之日起七日內通報中央主管機關。其他不良事件應於知悉之日起"
                "十五日內通報。"
            ),
            original_lang="zh-TW",
            english_translation=(
                "Medical device businesses, upon becoming aware of serious adverse events involving devices "
                "they manufacture, import, or sell, shall report to the central competent authority within "
                "7 days from the date of awareness. Other adverse events shall be reported within 15 days."
            ),
            semantic_note=(
                "Taiwan TFDA adverse event timelines: 7 days (serious/death) + 15 days (other). "
                "EU MDR Art 87: 2 days (death/serious public health threat), 10 days (public health threat), "
                "15 days (other serious). EU has the most granular tiers and SHORTEST deadlines. "
                "US FDA 21 CFR 803: 5 working days for death, 30 calendar days for serious injury/malfunction. "
                "ISO 13485 8.2.3: requires regulatory reporting but NO specific timeline. "
                "Cross-country timeline comparison (death/serious): EU 2 days < Taiwan 7 days < US 5 working days. "
                "For other serious events: Taiwan 15 days = EU 15 days < US 30 days. "
                "Taiwan is between EU (strictest) and US (most lenient) in stringency."
            ),
        ),
        UniqueRequirement(
            req_id="TFDA-005",
            regulation_ref="醫療器材管理法 第13條",
            title_en="Taiwan Authorized Representative",
            title_zh="台灣在地授權代表",
            requirement_en=(
                "Foreign manufacturers must appoint a Taiwan-based legal representative "
                "(authorized representative) to hold the medical device license and manage "
                "QMS compliance within Taiwan. This is a market access requirement."
            ),
            requirement_zh=(
                "外國製造商必須指定台灣在地法定代理人（授權代表）"
                "持有醫療器材許可證並管理台灣境內的QMS合規。此為市場准入要求。"
            ),
            related_iso_clauses=["5.5.1", "7.2.3"],
            audit_impact="major",
            audit_question_en=(
                "For foreign manufacturers: has a Taiwan-based authorized representative "
                "been appointed per Medical Device Act Article 13?"
            ),
            audit_question_zh=(
                "外國製造商：是否依醫療器材管理法第13條指定台灣在地授權代表？"
            ),
            expected_evidence=[
                "Authorized representative agreement / 授權代表合約",
                "Representative registration with TFDA / 代表之TFDA登記",
            ],
            rationale_en=(
                "Taiwan authorized representative (Art 13) has no ISO 13485 equivalent. "
                "Closest to 5.5.1 (responsibility/authority) for organizational structure, "
                "and 7.2.3 (communication) for regulatory communication channel."
            ),
            rationale_zh=(
                "台灣授權代表（第13條）在 ISO 13485 中無對應。"
                "最接近 5.5.1（責任/權限）涉及組織架構，"
                "及 7.2.3（溝通）涉及法規溝通管道。"
            ),
            method=MappingMethod.SEMANTIC_ZH,
            confidence=0.85,
            original_text=(
                "外國之醫療器材製造業者，應由其在中華民國境內設立並依法登記之"
                "分公司或指定在中華民國境內具有住所之代理人，申請醫療器材許可證。"
                "代理人將代為執行品質管理系統相關義務。"
            ),
            original_lang="zh-TW",
            english_translation=(
                "Foreign medical device manufacturers shall apply for medical device licenses through "
                "their branch companies established and registered in the territory of the Republic of China, "
                "or through designated agents with domicile in the territory. "
                "The agent shall perform QMS-related obligations on behalf of the manufacturer."
            ),
            semantic_note=(
                "Taiwan requires foreign manufacturers to have a local legal entity or designated agent (代理人) "
                "who holds the medical device license and manages QMS compliance. "
                "EU MDR Art 11: requires a European Authorized Representative (EU AR) for non-EU manufacturers, "
                "who ensures compliance and is the contact for competent authorities. "
                "US FDA: requires a US Agent for foreign establishments (21 CFR 807.40) for FDA correspondence, "
                "but the US Agent does NOT hold the registration — it’s just a communication contact. "
                "ISO 13485: does not address authorized representative requirements (this is a regulatory "
                "market access issue, not a QMS process issue). "
                "Cross-country: all three jurisdictions require some form of local representation for foreign "
                "manufacturers, but the scope of responsibility varies: Taiwan’s agent holds the license, "
                "EU AR ensures compliance, US Agent is only a communication contact."
            ),
        ),
    ]

    return RegulationProfile(
        regulation_id="TFDA",
        name_en="Taiwan TFDA Medical Device QMS Regulations",
        name_zh="台灣 TFDA 醫療器材品質管理系統準則",
        country="TW",
        country_name_en="Taiwan",
        country_name_zh="台灣",
        source="predefined",
        source_url="https://laws.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0030097",
        last_updated="2021-04-14",
        effective_date="2021-05-01",
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )


# ============================================================
# Predefined Regulation: Health Canada CMDR (SOR/98-282)
# ============================================================


def _build_hc_profile() -> RegulationProfile:
    """Build the Health Canada (HC) regulation profile.

    Canada Medical Devices Regulations (CMDR) SOR/98-282,
    administered by Health Canada. MDSAP participant country.
    Since January 1, 2019, MDSAP is the EXCLUSIVE pathway for QMS
    certification of Class II-IV medical devices in Canada.
    CMDCAS (Canadian Medical Devices Conformity Assessment System) has been
    fully retired and replaced by MDSAP.
    Canada requires ISO 13485 certification via MDSAP as a prerequisite
    for Medical Device Licenses (MDL).

    Mapping source: CMDR regulatory text (laws-lois.justice.gc.ca)
    + MDSAP Companion Document for Canada
    + Agile Licensing Amendments (Nov 29, 2024)
    """
    iso_mapped: dict[str, ClauseMapping] = {}

    # HC CMDR — QMS compliance is exclusively via MDSAP since Jan 2019
    # (CMDCAS retired). ISO 13485 certification is mandatory for Class II-IV devices.
    hc_clause_map = {
        "4.1": (
            "CMDR s.32(1)",
            "CMDR requires manufacturers of Class II-IV devices to hold a valid ISO 13485 certificate. Clause 4.1 general QMS requirements are fully adopted.",
            "CMDR要求II-IV類醫療器材製造商持有有效的ISO 13485證書。條款4.1一般QMS要求完全採用。",
        ),
        "4.2.1": (
            "CMDR s.32(2)",
            "Documentation requirements are covered through mandatory ISO 13485 certification.",
            "文件化要求通過強制性ISO 13485認證涵蓋。",
        ),
        "4.2.2": (
            "CMDR s.32(2)",
            "Quality manual requirements adopted via ISO 13485.",
            "品質手冊要求通過ISO 13485採用。",
        ),
        "4.2.3": (
            "CMDR s.32(2)",
            "Document control adopted via ISO 13485.",
            "文件管制通過ISO 13485採用。",
        ),
        "4.2.4": (
            "CMDR s.32(2) / s.56",
            "Record control adopted via ISO 13485. CMDR s.56 adds distribution record requirements.",
            "記錄管制通過ISO 13485採用。CMDR s.56增加配銷記錄要求。",
        ),
        "4.2.5": (
            "CMDR s.32(2)",
            "Medical device file requirements adopted via ISO 13485.",
            "醫療器材檔案要求通過ISO 13485採用。",
        ),
        "5.1": (
            "CMDR s.32(2)",
            "Management commitment adopted via ISO 13485.",
            "管理承諾通過ISO 13485採用。",
        ),
        "5.2": (
            "CMDR s.32(2)",
            "Customer focus adopted via ISO 13485.",
            "以顧客為重通過ISO 13485採用。",
        ),
        "5.3": (
            "CMDR s.32(2)",
            "Quality policy adopted via ISO 13485.",
            "品質政策通過ISO 13485採用。",
        ),
        "5.4.1": (
            "CMDR s.32(2)",
            "Quality objectives adopted via ISO 13485.",
            "品質目標通過ISO 13485採用。",
        ),
        "5.4.2": (
            "CMDR s.32(2)",
            "QMS planning adopted via ISO 13485.",
            "QMS規劃通過ISO 13485採用。",
        ),
        "5.5.1": (
            "CMDR s.32(2)",
            "Responsibility and authority adopted via ISO 13485.",
            "責任與權限通過ISO 13485採用。",
        ),
        "5.5.2": (
            "CMDR s.32(2)",
            "Management representative adopted via ISO 13485.",
            "管理代表通過ISO 13485採用。",
        ),
        "5.5.3": (
            "CMDR s.32(2)",
            "Internal communication adopted via ISO 13485.",
            "內部溝通通過ISO 13485採用。",
        ),
        "5.6.1": (
            "CMDR s.32(2)",
            "Management review adopted via ISO 13485.",
            "管理審查通過ISO 13485採用。",
        ),
        "5.6.2": (
            "CMDR s.32(2)",
            "Management review input adopted via ISO 13485.",
            "管理審查輸入通過ISO 13485採用。",
        ),
        "5.6.3": (
            "CMDR s.32(2)",
            "Management review output adopted via ISO 13485.",
            "管理審查輸出通過ISO 13485採用。",
        ),
        "6.1": (
            "CMDR s.32(2)",
            "Resource provision adopted via ISO 13485.",
            "資源提供通過ISO 13485採用。",
        ),
        "6.2": (
            "CMDR s.32(2)",
            "Human resources adopted via ISO 13485.",
            "人力資源通過ISO 13485採用。",
        ),
        "6.3": (
            "CMDR s.32(2)",
            "Infrastructure adopted via ISO 13485.",
            "基礎設施通過ISO 13485採用。",
        ),
        "6.4.1": (
            "CMDR s.32(2)",
            "Work environment adopted via ISO 13485.",
            "工作環境通過ISO 13485採用。",
        ),
        "6.4.2": (
            "CMDR s.32(2)",
            "Contamination control adopted via ISO 13485.",
            "污染管制通過ISO 13485採用。",
        ),
        "7.1": (
            "CMDR s.32(2)",
            "Product realization planning adopted via ISO 13485.",
            "產品實現規劃通過ISO 13485採用。",
        ),
        "7.2.1": (
            "CMDR s.10-20",
            "Determination of product requirements — CMDR sections 10-20 define device classification and licensing requirements that exceed ISO 13485.",
            "產品要求確定 — CMDR第10-20條定義器材分類和許可要求，超出ISO 13485。",
        ),
        "7.2.2": (
            "CMDR s.32(2)",
            "Review of product requirements adopted via ISO 13485.",
            "產品要求審查通過ISO 13485採用。",
        ),
        "7.2.3": (
            "CMDR s.32(2) / s.57-58",
            "Communication adopted via ISO 13485. CMDR s.57-58 add mandatory problem reporting to HC.",
            "溝通通過ISO 13485採用。CMDR s.57-58增加向HC強制性問題通報。",
        ),
        "7.3.1": (
            "CMDR s.32(2)",
            "Design planning adopted via ISO 13485.",
            "設計規劃通過ISO 13485採用。",
        ),
        "7.3.2": (
            "CMDR s.32(2)",
            "Design input adopted via ISO 13485.",
            "設計輸入通過ISO 13485採用。",
        ),
        "7.3.3": (
            "CMDR s.32(2)",
            "Design output adopted via ISO 13485.",
            "設計輸出通過ISO 13485採用。",
        ),
        "7.3.4": (
            "CMDR s.32(2)",
            "Design review adopted via ISO 13485.",
            "設計審查通過ISO 13485採用。",
        ),
        "7.3.5": (
            "CMDR s.32(2)",
            "Design verification adopted via ISO 13485.",
            "設計驗證通過ISO 13485採用。",
        ),
        "7.3.6": (
            "CMDR s.32(2)",
            "Design validation adopted via ISO 13485.",
            "設計確認通過ISO 13485採用。",
        ),
        "7.3.7": (
            "CMDR s.32(2)",
            "Design transfer adopted via ISO 13485.",
            "設計轉移通過ISO 13485採用。",
        ),
        "7.3.8": (
            "CMDR s.32(2)",
            "Design change control adopted via ISO 13485.",
            "設計變更管制通過ISO 13485採用。",
        ),
        "7.3.9": (
            "CMDR s.32(2)",
            "Design files adopted via ISO 13485.",
            "設計檔案通過ISO 13485採用。",
        ),
        "7.3.10": (
            "CMDR s.32(2)",
            "Design documentation adopted via ISO 13485.",
            "設計文件通過ISO 13485採用。",
        ),
        "7.4.1": (
            "CMDR s.32(2)",
            "Purchasing process adopted via ISO 13485.",
            "採購過程通過ISO 13485採用。",
        ),
        "7.4.2": (
            "CMDR s.32(2)",
            "Purchasing information adopted via ISO 13485.",
            "採購資訊通過ISO 13485採用。",
        ),
        "7.4.3": (
            "CMDR s.32(2)",
            "Verification of purchased product adopted via ISO 13485.",
            "採購產品驗證通過ISO 13485採用。",
        ),
        "7.5.1": (
            "CMDR s.32(2) / s.21-23",
            "Production control adopted via ISO 13485. CMDR s.21-23 add labeling requirements for Canadian market.",
            "生產管制通過ISO 13485採用。CMDR s.21-23增加加拿大市場標示要求。",
        ),
        "7.5.6": (
            "CMDR s.32(2)",
            "Process validation adopted via ISO 13485.",
            "過程確認通過ISO 13485採用。",
        ),
        "7.5.8": (
            "CMDR s.32(2)",
            "Identification adopted via ISO 13485.",
            "識別通過ISO 13485採用。",
        ),
        "7.5.9": (
            "CMDR s.32(2) / s.56",
            "Traceability adopted via ISO 13485. CMDR s.56 adds distribution record requirements.",
            "追溯性通過ISO 13485採用。CMDR s.56增加配銷記錄要求。",
        ),
        "7.5.11": (
            "CMDR s.32(2)",
            "Product preservation adopted via ISO 13485.",
            "產品防護通過ISO 13485採用。",
        ),
        "7.6": (
            "CMDR s.32(2)",
            "Monitoring equipment adopted via ISO 13485.",
            "監測設備通過ISO 13485採用。",
        ),
        "8.1": (
            "CMDR s.32(2)",
            "General measurement requirements adopted via ISO 13485.",
            "一般量測要求通過ISO 13485採用。",
        ),
        "8.2.1": (
            "CMDR s.32(2)",
            "Feedback adopted via ISO 13485.",
            "回饋通過ISO 13485採用。",
        ),
        "8.2.2": (
            "CMDR s.32(2) / s.57-58",
            "Complaint handling adopted via ISO 13485. CMDR s.57-58 add mandatory problem reporting.",
            "客訴處理通過ISO 13485採用。CMDR s.57-58增加強制性問題通報。",
        ),
        "8.2.3": (
            "CMDR s.57-58",
            "Regulatory reporting — CMDR s.57-58 mandate reporting of incidents and recalls to Health Canada within specific timelines.",
            "法規通報 — CMDR s.57-58要求在特定時限內向加拿大衛生部通報事故和召回。",
        ),
        "8.2.4": (
            "CMDR s.32(2)",
            "Internal audit adopted via ISO 13485.",
            "內部稽核通過ISO 13485採用。",
        ),
        "8.2.5": (
            "CMDR s.32(2)",
            "Process monitoring adopted via ISO 13485.",
            "過程監督通過ISO 13485採用。",
        ),
        "8.2.6": (
            "CMDR s.32(2)",
            "Product monitoring adopted via ISO 13485.",
            "產品監督通過ISO 13485採用。",
        ),
        "8.3": (
            "CMDR s.32(2)",
            "Nonconforming product adopted via ISO 13485.",
            "不合格品通過ISO 13485採用。",
        ),
        "8.4": (
            "CMDR s.32(2)",
            "Data analysis adopted via ISO 13485.",
            "數據分析通過ISO 13485採用。",
        ),
        "8.5.1": (
            "CMDR s.32(2)",
            "Improvement adopted via ISO 13485.",
            "改善通過ISO 13485採用。",
        ),
        "8.5.2": (
            "CMDR s.32(2) / s.57-58",
            "Corrective action adopted via ISO 13485. CMDR s.57-58 require mandatory corrective action for reported problems.",
            "矯正措施通過ISO 13485採用。CMDR s.57-58要求對已通報問題採取強制矯正措施。",
        ),
        "8.5.3": (
            "CMDR s.32(2)",
            "Preventive action adopted via ISO 13485.",
            "預防措施通過ISO 13485採用。",
        ),
    }

    for clause_id, (ref, rationale_en, rationale_zh) in hc_clause_map.items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=clause_id,
            status=MappingStatus.FULL,
            regulation_ref=ref,
            rationale_en=rationale_en,
            rationale_zh=rationale_zh,
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            notes="CMDR SOR/98-282 (laws-lois.justice.gc.ca)",
        )

    # HC-specific unique requirements (delta from ISO 13485)
    unique_reqs = [
        UniqueRequirement(
            req_id="HC-001",
            regulation_ref="CMDR s.57-58",
            title_en="Mandatory Problem Reporting",
            title_zh="強制性問題通報",
            requirement_en=(
                "Manufacturers and importers must report incidents involving death, serious "
                "deterioration in health, or device deficiency within 10 days (preliminary) "
                "and 30 days (final) to Health Canada. Medical Device Problem Reporting form is mandatory."
            ),
            requirement_zh=(
                "製造商和進口商必須在10天內（初步）和30天內（最終）向加拿大衛生部通報"
                "涉及死亡、健康嚴重惡化或器材缺陷的事故。必須使用醫療器材問題通報表。"
            ),
            related_iso_clauses=["8.2.2", "8.2.3", "8.5.2"],
            audit_impact="critical",
            audit_question_en=(
                "Does the problem reporting procedure include 10-day preliminary and 30-day "
                "final reporting timelines to Health Canada per CMDR s.57-58?"
            ),
            audit_question_zh=(
                "問題通報程序是否包含依CMDR s.57-58向加拿大衛生部的10天初步"
                "及30天最終通報時限？"
            ),
            expected_evidence=[
                "Problem reporting procedure with HC timelines / 含HC時限之問題通報程序",
                "Completed Medical Device Problem Report forms / 已完成之醫療器材問題通報表",
                "Incident tracking log / 事故追蹤記錄",
            ],
            rationale_en=(
                "CMDR s.57-58 mandate specific timelines for reporting device problems. "
                "ISO 13485 8.2.3 requires regulatory reporting but without specific day counts. "
                "Related to 8.2.2 (complaint handling) and 8.5.2 (corrective action)."
            ),
            rationale_zh=(
                "CMDR s.57-58規定器材問題通報的特定時限。"
                "ISO 13485 8.2.3要求法規通報但無特定天數。"
                "相關條款8.2.2（客訴處理）和8.5.2（矯正措施）。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "A manufacturer who becomes aware that a device may have caused or contributed to "
                "the death or a serious deterioration in the state of health of a patient, user or other "
                "person shall report the incident within 10 days (preliminary) and submit a final report "
                "within 30 days."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "HC CMDR uses 10-day preliminary + 30-day final dual-stage reporting. "
                "US FDA: 5 working days (death), 30 days (serious injury/malfunction). "
                "EU MDR: 2 days (death/serious threat), 10 days (public health), 15 days (other). "
                "Taiwan TFDA: 7 days (death/serious), 15 days (other). "
                "Canada is unique in its dual-stage (preliminary + final) approach. "
                "Most other jurisdictions require a single submission within their timeline."
            ),
        ),
        UniqueRequirement(
            req_id="HC-002",
            regulation_ref="CMDR s.44-46",
            title_en="Mandatory Recall Procedures",
            title_zh="強制性召回程序",
            requirement_en=(
                "Health Canada may order a mandatory recall of devices. Manufacturers must have "
                "documented recall procedures and maintain distribution records enabling "
                "effective recall within 24 hours of decision. CMDR s.64-66 define recall "
                "classification (Type I/II/III) and public communication requirements."
            ),
            requirement_zh=(
                "加拿大衛生部可命令強制召回器材。製造商必須有文件化的召回程序，"
                "並維持配銷記錄以便在決定後24小時內有效召回。CMDR s.64-66定義"
                "召回分類（I/II/III類）和公眾溝通要求。"
            ),
            related_iso_clauses=["7.5.9", "8.2.3", "8.3.2"],
            audit_impact="critical",
            audit_question_en=(
                "Is there a documented recall procedure enabling recalls within 24 hours, "
                "with distribution records supporting traceability per CMDR s.44-46?"
            ),
            audit_question_zh=(
                "是否有文件化的召回程序可在24小時內執行召回，"
                "且配銷記錄支持追溯性？（CMDR s.44-46）"
            ),
            expected_evidence=[
                "Recall procedure document / 召回程序書",
                "Distribution records / 配銷記錄",
                "Mock recall exercise records / 模擬召回演練記錄",
            ],
            rationale_en=(
                "CMDR mandates recall capabilities with specific timing. "
                "ISO 13485 8.3.2 covers post-delivery nonconformance but not recall specifics. "
                "Related to 7.5.9 (traceability) for distribution records."
            ),
            rationale_zh=(
                "CMDR要求具備特定時限的召回能力。"
                "ISO 13485 8.3.2涵蓋交付後不合格但無召回細節。"
                "相關條款7.5.9（追溯性）涉及配銷記錄。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "Where the Minister believes that a medical device poses a risk to the health or "
                "safety of patients, users, or other persons, the Minister may order the manufacturer "
                "to recall the device. The manufacturer shall maintain distribution records adequate "
                "to permit a complete and rapid recall of the device."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "HC emphasizes 'complete and rapid recall' capability. US FDA 21 CFR 7 has voluntary "
                "and mandatory recall classes (I/II/III). EU MDR Art 95 gives authorities power to "
                "order recalls. Taiwan TFDA Act Art 58 mandates recalls. Canada's recall "
                "classification system (Type I/II/III) mirrors FDA's but with different procedural "
                "requirements. Key difference: HC's CMDR explicitly requires distribution records "
                "that enable 'rapid' recall, which is a more prescriptive standard than ISO 13485."
            ),
        ),
        UniqueRequirement(
            req_id="HC-003",
            regulation_ref="CMDR s.21-23 / SOR/2020-154",
            title_en="Canadian Bilingual Labeling (English/French)",
            title_zh="加拿大雙語標示（英文/法文）",
            requirement_en=(
                "All medical device labels and instructions for use must be in both English "
                "and French (Canada's two official languages). This is a constitutional "
                "requirement under the Official Languages Act and enforced through CMDR."
            ),
            requirement_zh=(
                "所有醫療器材標籤和使用說明書必須以英文和法文（加拿大兩種官方語言）"
                "提供。此為《官方語言法》下的憲法要求，通過CMDR執行。"
            ),
            related_iso_clauses=["7.5.1", "7.5.8"],
            audit_impact="major",
            audit_question_en=(
                "Do all device labels and IFU include both English and French text "
                "as required by CMDR s.21-23 and the Official Languages Act?"
            ),
            audit_question_zh=(
                "所有器材標籤和使用說明書是否包含英文和法文文字？"
                "（CMDR s.21-23及《官方語言法》要求）"
            ),
            expected_evidence=[
                "Bilingual labels (EN/FR) / 雙語標籤（英文/法文）",
                "Bilingual IFU / 雙語使用說明書",
            ],
            rationale_en=(
                "Bilingual labeling is a Canadian constitutional requirement with no ISO 13485 equivalent. "
                "Closest to 7.5.1 (production control includes labeling) and 7.5.8 (identification)."
            ),
            rationale_zh=(
                "雙語標示是加拿大憲法要求，ISO 13485無對應。"
                "最接近7.5.1（生產管制含標示）和7.5.8（識別）。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.95,
            original_text=(
                "All labeling, including device labels and instructions for use, must be provided "
                "in both official languages of Canada (English and French)."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "Canada is unique in requiring BILINGUAL labeling (English + French). "
                "US FDA requires English only. EU MDR requires member state language(s). "
                "Taiwan TFDA requires Traditional Chinese as primary. Japan PMDA requires Japanese. "
                "Brazil ANVISA requires Portuguese. Each jurisdiction has different language requirements "
                "but Canada is the only MDSAP country requiring TWO languages on all labeling."
            ),
        ),
        UniqueRequirement(
            req_id="HC-004",
            regulation_ref="CMDR s.32(3) / MDSAP",
            title_en="MDSAP as Exclusive QMS Certification Pathway",
            title_zh="MDSAP 作為唯一 QMS 認證途徑",
            requirement_en=(
                "Since January 1, 2019, the Medical Device Single Audit Program (MDSAP) is the "
                "EXCLUSIVE pathway for QMS certification of Class II, III, and IV medical devices "
                "in Canada. The previous CMDCAS (Canadian Medical Devices Conformity Assessment System) "
                "has been fully retired. Manufacturers must obtain an MDSAP certificate from a "
                "recognized Auditing Organization (AO) covering Canadian regulatory requirements. "
                "The MDSAP audit integrates ISO 13485:2016 with CMDR-specific elements in a "
                "single audit that can satisfy multiple jurisdictions (US, CA, JP, BR, AU)."
            ),
            requirement_zh=(
                "自2019年1月1日起，醫療器材單一審核方案（MDSAP）是加拿大II、III、IV類"
                "醫療器材QMS認證的唯一途徑。先前的CMDCAS（加拿大醫療器材合格評定系統）"
                "已完全退役。製造商必須從認可的稽核組織（AO）獲得涵蓋加拿大法規要求的"
                "MDSAP證書。MDSAP稽核將ISO 13485:2016與CMDR特定要素整合在單一稽核中，"
                "可同時滿足多個司法管轄區（US, CA, JP, BR, AU）。"
            ),
            related_iso_clauses=["4.1", "8.2.4"],
            audit_impact="critical",
            audit_question_en=(
                "Does the manufacturer hold a current MDSAP certificate issued by a "
                "Health Canada-recognized Auditing Organization, covering Canadian "
                "regulatory requirements per CMDR s.32?"
            ),
            audit_question_zh=(
                "製造商是否持有加拿大衛生部認可的稽核組織所核發、涵蓋CMDR s.32"
                "加拿大法規要求的有效MDSAP證書？"
            ),
            expected_evidence=[
                "Current MDSAP certificate covering Canada / 涵蓋加拿大的現行MDSAP證書",
                "MDSAP audit report / MDSAP稽核報告",
                "Auditing Organization (AO) accreditation / 稽核組織認可資格",
            ],
            rationale_en=(
                "MDSAP is the sole QMS certification pathway for Canada since 2019. "
                "CMDCAS was retired. No ISO 13485 equivalent — this is a regulatory "
                "infrastructure requirement. Related to 4.1 (QMS) and 8.2.4 (internal audit "
                "as part of the broader audit framework)."
            ),
            rationale_zh=(
                "自2019年起MDSAP是加拿大唯一的QMS認證途徑。CMDCAS已退役。"
                "ISO 13485無對應——此為法規基礎設施要求。相關條款4.1（QMS）"
                "及8.2.4（作為更廣泛稽核框架一部分的內部稽核）。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.95,
            original_text=(
                "Effective January 1, 2019, Health Canada requires manufacturers of Class II, III, "
                "and IV medical devices to have a valid Medical Device Single Audit Program (MDSAP) "
                "certificate to obtain or renew a Medical Device Licence (MDL). The CMDCAS program "
                "has been retired and is no longer accepted as evidence of QMS compliance."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "Canada is the FIRST and MOST committed MDSAP country — making it the exclusive "
                "pathway. Other MDSAP participants (US, JP, BR, AU) accept MDSAP as an ALTERNATIVE "
                "but still allow traditional audit pathways. For Canada: no MDSAP certificate = "
                "no Medical Device Licence = cannot sell in Canada. This makes Canada unique among "
                "MDSAP participants in mandating single-audit exclusivity. "
                "The 3-year MDSAP cycle (initial + 2 surveillance + recertification) replaces "
                "the old CMDCAS annual audit requirement."
            ),
        ),
    ]

    return RegulationProfile(
        regulation_id="HC",
        name_en="Health Canada CMDR (SOR/98-282) — MDSAP Exclusive",
        name_zh="加拿大衛生部 CMDR（SOR/98-282）— MDSAP 獨佔",
        country="CA",
        country_name_en="Canada",
        country_name_zh="加拿大",
        source="predefined",
        source_url="https://laws-lois.justice.gc.ca/eng/regulations/SOR-98-282/",
        last_updated="2024-11-29",
        effective_date="1998-11-01",
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )


# ============================================================
# Predefined Regulation: Japan PMDA (QMS省令 + PMD Act)
# ============================================================


def _build_pmda_profile() -> RegulationProfile:
    """Build the Japan PMDA regulation profile.

    Japan's QMS Ordinance (QMS省令, MHLW Ordinance No.169 of 2004, revised 2021)
    and Pharmaceuticals and Medical Devices Act (PMD Act, 薬機法).
    MDSAP participant country.
    Japan's QMS Ordinance is structurally aligned with ISO 13485:2016.

    Mapping source: QMS省令 regulatory text
    + MDSAP Companion Document for Japan
    """
    iso_mapped: dict[str, ClauseMapping] = {}

    # PMDA QMS Ordinance mirrors ISO 13485 structure closely
    pmda_clause_map = {
        "4.1": (
            "QMS省令 §5",
            "QMS Ordinance Article 5 establishes general QMS requirements, structurally aligned with ISO 13485 Clause 4.1.",
            "QMS省令第5條建立一般QMS要求，結構上與ISO 13485條款4.1對齊。",
        ),
        "4.2.1": (
            "QMS省令 §6",
            "Article 6 covers documentation requirements.",
            "第6條涵蓋文件化要求。",
        ),
        "4.2.2": (
            "QMS省令 §7",
            "Article 7 covers quality manual.",
            "第7條涵蓋品質手冊。",
        ),
        "4.2.3": (
            "QMS省令 §8",
            "Article 8 covers document control.",
            "第8條涵蓋文件管制。",
        ),
        "4.2.4": (
            "QMS省令 §9",
            "Article 9 covers record control.",
            "第9條涵蓋記錄管制。",
        ),
        "4.2.5": (
            "QMS省令 §10",
            "Article 10 covers medical device file.",
            "第10條涵蓋醫療器材檔案。",
        ),
        "5.1": (
            "QMS省令 §11",
            "Article 11 covers management commitment.",
            "第11條涵蓋管理承諾。",
        ),
        "5.2": (
            "QMS省令 §12",
            "Article 12 covers customer focus.",
            "第12條涵蓋以顧客為重。",
        ),
        "5.3": (
            "QMS省令 §13",
            "Article 13 covers quality policy.",
            "第13條涵蓋品質政策。",
        ),
        "5.4.1": (
            "QMS省令 §14",
            "Article 14 covers quality objectives.",
            "第14條涵蓋品質目標。",
        ),
        "5.4.2": (
            "QMS省令 §15",
            "Article 15 covers QMS planning.",
            "第15條涵蓋QMS規劃。",
        ),
        "5.5.1": (
            "QMS省令 §16",
            "Article 16 covers responsibility and authority.",
            "第16條涵蓋責任與權限。",
        ),
        "5.5.2": (
            "QMS省令 §17",
            "Article 17 covers management representative.",
            "第17條涵蓋管理代表。",
        ),
        "5.5.3": (
            "QMS省令 §18",
            "Article 18 covers internal communication.",
            "第18條涵蓋內部溝通。",
        ),
        "5.6.1": (
            "QMS省令 §19",
            "Article 19 covers management review.",
            "第19條涵蓋管理審查。",
        ),
        "5.6.2": (
            "QMS省令 §19",
            "Article 19 includes management review input.",
            "第19條包含管理審查輸入。",
        ),
        "5.6.3": (
            "QMS省令 §19",
            "Article 19 includes management review output.",
            "第19條包含管理審查輸出。",
        ),
        "6.1": (
            "QMS省令 §20",
            "Article 20 covers resource provision.",
            "第20條涵蓋資源提供。",
        ),
        "6.2": (
            "QMS省令 §21-22",
            "Articles 21-22 cover human resources and competence.",
            "第21-22條涵蓋人力資源和能力。",
        ),
        "6.3": (
            "QMS省令 §23",
            "Article 23 covers infrastructure.",
            "第23條涵蓋基礎設施。",
        ),
        "6.4.1": (
            "QMS省令 §24",
            "Article 24 covers work environment.",
            "第24條涵蓋工作環境。",
        ),
        "6.4.2": (
            "QMS省令 §25",
            "Article 25 covers contamination control.",
            "第25條涵蓋污染管制。",
        ),
        "7.1": (
            "QMS省令 §26",
            "Article 26 covers product realization planning.",
            "第26條涵蓋產品實現規劃。",
        ),
        "7.2.1": (
            "QMS省令 §27",
            "Article 27 covers determination of product requirements.",
            "第27條涵蓋產品要求確定。",
        ),
        "7.2.2": (
            "QMS省令 §28",
            "Article 28 covers review of product requirements.",
            "第28條涵蓋產品要求審查。",
        ),
        "7.2.3": (
            "QMS省令 §29",
            "Article 29 covers communication.",
            "第29條涵蓋溝通。",
        ),
        "7.3.1": (
            "QMS省令 §30",
            "Article 30 covers design planning.",
            "第30條涵蓋設計規劃。",
        ),
        "7.3.2": (
            "QMS省令 §31",
            "Article 31 covers design input.",
            "第31條涵蓋設計輸入。",
        ),
        "7.3.3": (
            "QMS省令 §32",
            "Article 32 covers design output.",
            "第32條涵蓋設計輸出。",
        ),
        "7.3.4": (
            "QMS省令 §33",
            "Article 33 covers design review.",
            "第33條涵蓋設計審查。",
        ),
        "7.3.5": (
            "QMS省令 §34",
            "Article 34 covers design verification.",
            "第34條涵蓋設計驗證。",
        ),
        "7.3.6": (
            "QMS省令 §35",
            "Article 35 covers design validation.",
            "第35條涵蓋設計確認。",
        ),
        "7.3.7": (
            "QMS省令 §36",
            "Article 36 covers design transfer.",
            "第36條涵蓋設計轉移。",
        ),
        "7.3.8": (
            "QMS省令 §37",
            "Article 37 covers design change control.",
            "第37條涵蓋設計變更管制。",
        ),
        "7.3.9": (
            "QMS省令 §38",
            "Article 38 covers design files.",
            "第38條涵蓋設計檔案。",
        ),
        "7.3.10": (
            "QMS省令 §38",
            "Article 38 includes design documentation.",
            "第38條包含設計文件。",
        ),
        "7.4.1": (
            "QMS省令 §39",
            "Article 39 covers purchasing process.",
            "第39條涵蓋採購過程。",
        ),
        "7.4.2": (
            "QMS省令 §40",
            "Article 40 covers purchasing information.",
            "第40條涵蓋採購資訊。",
        ),
        "7.4.3": (
            "QMS省令 §41",
            "Article 41 covers verification of purchased product.",
            "第41條涵蓋採購產品驗證。",
        ),
        "7.5.1": (
            "QMS省令 §42",
            "Article 42 covers production control.",
            "第42條涵蓋生產管制。",
        ),
        "7.5.6": (
            "QMS省令 §46",
            "Article 46 covers process validation.",
            "第46條涵蓋過程確認。",
        ),
        "7.5.8": (
            "QMS省令 §48",
            "Article 48 covers identification.",
            "第48條涵蓋識別。",
        ),
        "7.5.9": (
            "QMS省令 §49",
            "Article 49 covers traceability.",
            "第49條涵蓋追溯性。",
        ),
        "7.5.11": (
            "QMS省令 §51",
            "Article 51 covers product preservation.",
            "第51條涵蓋產品防護。",
        ),
        "7.6": (
            "QMS省令 §52",
            "Article 52 covers monitoring equipment.",
            "第52條涵蓋監測設備。",
        ),
        "8.1": (
            "QMS省令 §53",
            "Article 53 covers general measurement requirements.",
            "第53條涵蓋一般量測要求。",
        ),
        "8.2.1": ("QMS省令 §54", "Article 54 covers feedback.", "第54條涵蓋回饋。"),
        "8.2.2": (
            "QMS省令 §55",
            "Article 55 covers complaint handling.",
            "第55條涵蓋客訴處理。",
        ),
        "8.2.3": (
            "QMS省令 §56",
            "Article 56 covers regulatory reporting.",
            "第56條涵蓋法規通報。",
        ),
        "8.2.4": (
            "QMS省令 §57",
            "Article 57 covers internal audit.",
            "第57條涵蓋內部稽核。",
        ),
        "8.2.5": (
            "QMS省令 §58",
            "Article 58 covers process monitoring.",
            "第58條涵蓋過程監督。",
        ),
        "8.2.6": (
            "QMS省令 §59",
            "Article 59 covers product monitoring.",
            "第59條涵蓋產品監督。",
        ),
        "8.3": (
            "QMS省令 §60",
            "Article 60 covers nonconforming product.",
            "第60條涵蓋不合格品。",
        ),
        "8.4": (
            "QMS省令 §62",
            "Article 62 covers data analysis.",
            "第62條涵蓋數據分析。",
        ),
        "8.5.1": ("QMS省令 §63", "Article 63 covers improvement.", "第63條涵蓋改善。"),
        "8.5.2": (
            "QMS省令 §64",
            "Article 64 covers corrective action.",
            "第64條涵蓋矯正措施。",
        ),
        "8.5.3": (
            "QMS省令 §65",
            "Article 65 covers preventive action.",
            "第65條涵蓋預防措施。",
        ),
    }

    for clause_id, (ref, rationale_en, rationale_zh) in pmda_clause_map.items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=clause_id,
            status=MappingStatus.FULL,
            regulation_ref=ref,
            rationale_en=rationale_en,
            rationale_zh=rationale_zh,
            method=MappingMethod.CLAUSE_STRUCTURE,
            confidence=0.90,
            notes="QMS省令 (MHLW Ordinance No.169)",
        )

    # PMDA-specific unique requirements (delta from ISO 13485)
    unique_reqs = [
        UniqueRequirement(
            req_id="PMDA-001",
            regulation_ref="PMD Act Art.68-10 / QMS省令 §56",
            title_en="Adverse Event Reporting — 15/30 Day Timelines",
            title_zh="不良事件通報 — 15/30天時限",
            requirement_en=(
                "Manufacturers must report adverse events to PMDA/MHLW: 15 days for "
                "serious events (death, life-threatening), 30 days for other reportable "
                "events. Reports must be in Japanese language."
            ),
            requirement_zh=(
                "製造商必須向PMDA/MHLW通報不良事件：嚴重事件（死亡、危及生命）15天，"
                "其他應通報事件30天。通報必須使用日文。"
            ),
            related_iso_clauses=["8.2.2", "8.2.3"],
            audit_impact="critical",
            audit_question_en=(
                "Does the adverse event reporting procedure specify 15-day (serious) "
                "and 30-day (other) reporting timelines to PMDA per PMD Act Art.68-10?"
            ),
            audit_question_zh=(
                "不良事件通報程序是否規定依PMD Act Art.68-10向PMDA的15天（嚴重）"
                "和30天（其他）通報時限？"
            ),
            expected_evidence=[
                "Adverse event reporting procedure with PMDA timelines / 含PMDA時限之不良事件通報程序",
                "Japanese-language report forms / 日文通報表",
            ],
            rationale_en=(
                "PMD Act specifies 15/30-day reporting timelines not in ISO 13485. "
                "Related to 8.2.2 (complaints) and 8.2.3 (regulatory reporting)."
            ),
            rationale_zh=(
                "PMD Act規定ISO 13485中沒有的15/30天通報時限。"
                "相關條款8.2.2（客訴）和8.2.3（法規通報）。"
            ),
            method=MappingMethod.CLAUSE_STRUCTURE,
            confidence=0.90,
            original_text=(
                "医薬品医療機器等法第68条の10：医療機器の製造販売業者は、その製造販売する"
                "医療機器について、重篤な有害事象を知った場合は15日以内に、その他の有害事象は"
                "30日以内に厚生労働大臣に報告しなければならない。"
            ),
            original_lang="ja",
            english_translation=(
                "PMD Act Art.68-10: MAH of medical devices, upon becoming aware of serious "
                "adverse events involving their devices, shall report to MHLW within 15 days. "
                "Other reportable adverse events shall be reported within 30 days."
            ),
            semantic_note=(
                "Japan uses 15/30-day timelines. US FDA: 5 working days (death), 30 days (serious). "
                "EU MDR: 2 days (death/serious threat), 15 days (other). "
                "Taiwan TFDA: 7 days (death/serious), 15 days (other). "
                "HC Canada: 10 days preliminary, 30 days final. "
                "Japan's timelines are generally the most lenient among MDSAP countries. "
                "Key difference: Japan requires Japanese-language reports."
            ),
        ),
        UniqueRequirement(
            req_id="PMDA-002",
            regulation_ref="PMD Act Art.23-2-5 / QMS省令",
            title_en="Marketing Authorization Holder (MAH) System",
            title_zh="製造販売業者（MAH）制度",
            requirement_en=(
                "Japan requires a Marketing Authorization Holder (製造販売業者) who holds "
                "the marketing authorization and bears full legal responsibility for the device. "
                "The MAH must be a Japan-based entity and is separate from the manufacturer. "
                "MAH must maintain their own QMS."
            ),
            requirement_zh=(
                "日本要求製造販売業者持有上市許可並對器材承擔全部法律責任。"
                "MAH必須是日本境內實體，與製造商分開。MAH必須維持自己的QMS。"
            ),
            related_iso_clauses=["5.5.1", "7.2.3", "4.1"],
            audit_impact="critical",
            audit_question_en=(
                "Is a Japan-based MAH appointed with its own QMS, holding marketing "
                "authorization per PMD Act Art.23-2-5?"
            ),
            audit_question_zh=(
                "是否任命具有自己QMS的日本境內MAH，持有上市許可？（PMD Act Art.23-2-5）"
            ),
            expected_evidence=[
                "MAH registration certificate / MAH登記證書",
                "MAH QMS documentation / MAH品質管理系統文件",
                "MAH-manufacturer agreement / MAH與製造商之合約",
            ],
            rationale_en=(
                "Japan's MAH system has no direct ISO 13485 equivalent. "
                "Closest to 5.5.1 (responsibility), 7.2.3 (communication), 4.1 (QMS). "
                "The MAH maintains a separate QMS that must comply with QMS省令."
            ),
            rationale_zh=(
                "日本的MAH制度在ISO 13485中無直接對應。"
                "最接近5.5.1（責任）、7.2.3（溝通）、4.1（QMS）。"
                "MAH維持獨立的QMS，必須符合QMS省令。"
            ),
            method=MappingMethod.CLAUSE_STRUCTURE,
            confidence=0.90,
            original_text=(
                "医薬品医療機器等法第23条の2の5：医療機器の製造販売をしようとする者は、"
                "品目ごとにその製造販売についての厚生労働大臣の承認を受けなければならない。"
                "製造販売業者は、品質管理の方法が基準に適合しなければならない。"
            ),
            original_lang="ja",
            english_translation=(
                "PMD Act Art.23-2-5: Any person who intends to manufacture and sell medical devices "
                "shall obtain marketing authorization from MHLW for each product. "
                "The MAH shall ensure quality management methods comply with the applicable standards."
            ),
            semantic_note=(
                "Japan's MAH system is unique in requiring a SEPARATE entity (MAH) from the manufacturer. "
                "EU MDR Art 11: Authorized Representative role, but for foreign manufacturers only. "
                "US FDA: Establishment registration, no separate MAH concept. "
                "Taiwan TFDA: Authorized representative for foreign manufacturers (Art 13). "
                "HC Canada: MDEL holder. "
                "Cross-country: Japan is the only jurisdiction where the entity holding marketing "
                "authorization MUST be domestic and MUST maintain its own QMS independently."
            ),
        ),
        UniqueRequirement(
            req_id="PMDA-003",
            regulation_ref="QMS省令 §8 / PMD Act",
            title_en="Japanese Language Documentation Requirements",
            title_zh="日文文件要求",
            requirement_en=(
                "All regulatory submissions, labeling, and instructions for use "
                "must be in Japanese. QMS documentation submitted to PMDA during "
                "inspections must be available in Japanese or with certified translations."
            ),
            requirement_zh=(
                "所有法規提交文件、標籤和使用說明書必須以日文提供。"
                "PMDA稽查時提交的QMS文件必須有日文版或經認證的翻譯。"
            ),
            related_iso_clauses=["4.2.3", "7.5.1", "7.5.8"],
            audit_impact="major",
            audit_question_en=(
                "Are regulatory submissions, labels, and IFU available in Japanese? "
                "Are QMS documents available in Japanese for PMDA inspections?"
            ),
            audit_question_zh=(
                "法規提交文件、標籤和使用說明書是否有日文版？"
                "QMS文件是否有日文版供PMDA稽查？"
            ),
            expected_evidence=[
                "Japanese-language labels and IFU / 日文標籤和使用說明書",
                "Japanese QMS documents or certified translations / 日文QMS文件或認證翻譯",
            ],
            rationale_en=(
                "Japanese language requirement is a PMDA market access requirement. "
                "ISO 13485 does not specify language. Closest to 4.2.3 (document control), "
                "7.5.1 (production control), 7.5.8 (identification)."
            ),
            rationale_zh=(
                "日文要求是PMDA市場准入要求。ISO 13485未規定語言。"
                "最接近4.2.3（文件管制）、7.5.1（生產管制）、7.5.8（識別）。"
            ),
            method=MappingMethod.SEMANTIC_EN,
            confidence=0.90,
            original_text=(
                "医療機器の添付文書、ラベル及び使用上の注意事項は日本語で記載しなければならない。"
                "PMDA査察時に提示するQMS文書は日本語又は公的翻訳が必要。"
            ),
            original_lang="ja",
            english_translation=(
                "Medical device package inserts, labels, and precautions for use must be written "
                "in Japanese. QMS documents presented during PMDA inspections must be in Japanese "
                "or have certified translations."
            ),
            semantic_note=(
                "Japan requires Japanese for ALL regulatory submissions and labeling. "
                "US requires English. EU varies by member state. Taiwan requires Traditional Chinese. "
                "Canada requires English + French bilingual. Brazil requires Portuguese. "
                "Japan's requirement extends to QMS documents during inspections, meaning "
                "foreign manufacturers must translate core QMS docs to Japanese."
            ),
        ),
    ]

    return RegulationProfile(
        regulation_id="PMDA",
        name_en="Japan PMDA QMS Ordinance (QMS省令)",
        name_zh="日本 PMDA QMS省令",
        country="JP",
        country_name_en="Japan",
        country_name_zh="日本",
        source="predefined",
        source_url="https://www.pmda.go.jp/",
        last_updated="2021-03-26",
        effective_date="2005-04-01",
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )


# ============================================================
# Predefined Regulation: Brazil ANVISA (RDC 665:2022)
# ============================================================


def _build_anvisa_profile() -> RegulationProfile:
    """Build the Brazil ANVISA regulation profile.

    ANVISA RDC 665:2022 (formerly RDC 16:2013) establishes Good Manufacturing
    Practices (GMP/BPF) for medical devices in Brazil.
    MDSAP participant country.
    Structurally modeled on ISO 13485, with additional Brazilian requirements.

    Mapping source: RDC 665:2022 regulatory text
    + MDSAP Companion Document for Brazil
    """
    iso_mapped: dict[str, ClauseMapping] = {}

    # ANVISA RDC 665:2022 is closely aligned with ISO 13485
    anvisa_clause_map = {
        "4.1": (
            "RDC 665 Art.8",
            "RDC 665 Article 8 establishes general QMS/GMP requirements aligned with ISO 13485.",
            "RDC 665第8條建立與ISO 13485對齊的一般QMS/GMP要求。",
        ),
        "4.2.1": (
            "RDC 665 Art.9",
            "Article 9 covers documentation requirements.",
            "第9條涵蓋文件化要求。",
        ),
        "4.2.2": (
            "RDC 665 Art.10",
            "Article 10 covers quality manual.",
            "第10條涵蓋品質手冊。",
        ),
        "4.2.3": (
            "RDC 665 Art.11",
            "Article 11 covers document control.",
            "第11條涵蓋文件管制。",
        ),
        "4.2.4": (
            "RDC 665 Art.12",
            "Article 12 covers record control.",
            "第12條涵蓋記錄管制。",
        ),
        "4.2.5": (
            "RDC 665 Art.13",
            "Article 13 covers medical device file.",
            "第13條涵蓋醫療器材檔案。",
        ),
        "5.1": (
            "RDC 665 Art.14",
            "Article 14 covers management commitment.",
            "第14條涵蓋管理承諾。",
        ),
        "5.2": (
            "RDC 665 Art.15",
            "Article 15 covers customer focus.",
            "第15條涵蓋以顧客為重。",
        ),
        "5.3": (
            "RDC 665 Art.16",
            "Article 16 covers quality policy.",
            "第16條涵蓋品質政策。",
        ),
        "5.4.1": (
            "RDC 665 Art.17",
            "Article 17 covers quality objectives.",
            "第17條涵蓋品質目標。",
        ),
        "5.4.2": (
            "RDC 665 Art.18",
            "Article 18 covers QMS planning.",
            "第18條涵蓋QMS規劃。",
        ),
        "5.5.1": (
            "RDC 665 Art.19",
            "Article 19 covers responsibility and authority.",
            "第19條涵蓋責任與權限。",
        ),
        "5.5.2": (
            "RDC 665 Art.20",
            "Article 20 covers management representative.",
            "第20條涵蓋管理代表。",
        ),
        "5.5.3": (
            "RDC 665 Art.21",
            "Article 21 covers internal communication.",
            "第21條涵蓋內部溝通。",
        ),
        "5.6.1": (
            "RDC 665 Art.22",
            "Article 22 covers management review.",
            "第22條涵蓋管理審查。",
        ),
        "5.6.2": (
            "RDC 665 Art.22",
            "Article 22 includes management review input.",
            "第22條包含管理審查輸入。",
        ),
        "5.6.3": (
            "RDC 665 Art.22",
            "Article 22 includes management review output.",
            "第22條包含管理審查輸出。",
        ),
        "6.1": (
            "RDC 665 Art.23",
            "Article 23 covers resource provision.",
            "第23條涵蓋資源提供。",
        ),
        "6.2": (
            "RDC 665 Art.24",
            "Article 24 covers human resources.",
            "第24條涵蓋人力資源。",
        ),
        "6.3": (
            "RDC 665 Art.25",
            "Article 25 covers infrastructure.",
            "第25條涵蓋基礎設施。",
        ),
        "6.4.1": (
            "RDC 665 Art.26",
            "Article 26 covers work environment.",
            "第26條涵蓋工作環境。",
        ),
        "6.4.2": (
            "RDC 665 Art.27",
            "Article 27 covers contamination control.",
            "第27條涵蓋污染管制。",
        ),
        "7.1": (
            "RDC 665 Art.28",
            "Article 28 covers product realization planning.",
            "第28條涵蓋產品實現規劃。",
        ),
        "7.2.1": (
            "RDC 665 Art.29",
            "Article 29 covers determination of product requirements.",
            "第29條涵蓋產品要求確定。",
        ),
        "7.2.2": (
            "RDC 665 Art.30",
            "Article 30 covers review of product requirements.",
            "第30條涵蓋產品要求審查。",
        ),
        "7.2.3": (
            "RDC 665 Art.31",
            "Article 31 covers communication.",
            "第31條涵蓋溝通。",
        ),
        "7.3.1": (
            "RDC 665 Art.32",
            "Article 32 covers design planning.",
            "第32條涵蓋設計規劃。",
        ),
        "7.3.2": (
            "RDC 665 Art.33",
            "Article 33 covers design input.",
            "第33條涵蓋設計輸入。",
        ),
        "7.3.3": (
            "RDC 665 Art.34",
            "Article 34 covers design output.",
            "第34條涵蓋設計輸出。",
        ),
        "7.3.4": (
            "RDC 665 Art.35",
            "Article 35 covers design review.",
            "第35條涵蓋設計審查。",
        ),
        "7.3.5": (
            "RDC 665 Art.36",
            "Article 36 covers design verification.",
            "第36條涵蓋設計驗證。",
        ),
        "7.3.6": (
            "RDC 665 Art.37",
            "Article 37 covers design validation.",
            "第37條涵蓋設計確認。",
        ),
        "7.3.7": (
            "RDC 665 Art.38",
            "Article 38 covers design transfer.",
            "第38條涵蓋設計轉移。",
        ),
        "7.3.8": (
            "RDC 665 Art.39",
            "Article 39 covers design change control.",
            "第39條涵蓋設計變更管制。",
        ),
        "7.3.9": (
            "RDC 665 Art.40",
            "Article 40 covers design files.",
            "第40條涵蓋設計檔案。",
        ),
        "7.3.10": (
            "RDC 665 Art.40",
            "Article 40 includes design documentation.",
            "第40條包含設計文件。",
        ),
        "7.4.1": (
            "RDC 665 Art.41",
            "Article 41 covers purchasing process.",
            "第41條涵蓋採購過程。",
        ),
        "7.4.2": (
            "RDC 665 Art.42",
            "Article 42 covers purchasing information.",
            "第42條涵蓋採購資訊。",
        ),
        "7.4.3": (
            "RDC 665 Art.43",
            "Article 43 covers verification of purchased product.",
            "第43條涵蓋採購產品驗證。",
        ),
        "7.5.1": (
            "RDC 665 Art.44",
            "Article 44 covers production control.",
            "第44條涵蓋生產管制。",
        ),
        "7.5.6": (
            "RDC 665 Art.48",
            "Article 48 covers process validation.",
            "第48條涵蓋過程確認。",
        ),
        "7.5.8": (
            "RDC 665 Art.50",
            "Article 50 covers identification.",
            "第50條涵蓋識別。",
        ),
        "7.5.9": (
            "RDC 665 Art.51",
            "Article 51 covers traceability.",
            "第51條涵蓋追溯性。",
        ),
        "7.5.11": (
            "RDC 665 Art.53",
            "Article 53 covers product preservation.",
            "第53條涵蓋產品防護。",
        ),
        "7.6": (
            "RDC 665 Art.54",
            "Article 54 covers monitoring equipment.",
            "第54條涵蓋監測設備。",
        ),
        "8.1": (
            "RDC 665 Art.55",
            "Article 55 covers general measurement requirements.",
            "第55條涵蓋一般量測要求。",
        ),
        "8.2.1": ("RDC 665 Art.56", "Article 56 covers feedback.", "第56條涵蓋回饋。"),
        "8.2.2": (
            "RDC 665 Art.57",
            "Article 57 covers complaint handling.",
            "第57條涵蓋客訴處理。",
        ),
        "8.2.3": (
            "RDC 665 Art.58",
            "Article 58 covers regulatory reporting to ANVISA.",
            "第58條涵蓋向ANVISA的法規通報。",
        ),
        "8.2.4": (
            "RDC 665 Art.59",
            "Article 59 covers internal audit.",
            "第59條涵蓋內部稽核。",
        ),
        "8.2.5": (
            "RDC 665 Art.60",
            "Article 60 covers process monitoring.",
            "第60條涵蓋過程監督。",
        ),
        "8.2.6": (
            "RDC 665 Art.61",
            "Article 61 covers product monitoring.",
            "第61條涵蓋產品監督。",
        ),
        "8.3": (
            "RDC 665 Art.62",
            "Article 62 covers nonconforming product.",
            "第62條涵蓋不合格品。",
        ),
        "8.4": (
            "RDC 665 Art.64",
            "Article 64 covers data analysis.",
            "第64條涵蓋數據分析。",
        ),
        "8.5.1": (
            "RDC 665 Art.65",
            "Article 65 covers improvement.",
            "第65條涵蓋改善。",
        ),
        "8.5.2": (
            "RDC 665 Art.66",
            "Article 66 covers corrective action.",
            "第66條涵蓋矯正措施。",
        ),
        "8.5.3": (
            "RDC 665 Art.67",
            "Article 67 covers preventive action.",
            "第67條涵蓋預防措施。",
        ),
    }

    for clause_id, (ref, rationale_en, rationale_zh) in anvisa_clause_map.items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=clause_id,
            status=MappingStatus.FULL,
            regulation_ref=ref,
            rationale_en=rationale_en,
            rationale_zh=rationale_zh,
            method=MappingMethod.CLAUSE_STRUCTURE,
            confidence=0.85,
            notes="ANVISA RDC 665:2022 (gov.br/anvisa)",
        )

    # ANVISA-specific unique requirements (delta from ISO 13485)
    unique_reqs = [
        UniqueRequirement(
            req_id="ANVISA-001",
            regulation_ref="RDC 551:2021 / Tecnovigilância",
            title_en="Tecnovigilance — Adverse Event Reporting",
            title_zh="技術警戒 — 不良事件通報",
            requirement_en=(
                "Brazil requires adverse event reporting through ANVISA's Tecnovigilance system "
                "(NOTIVISA/VigiMed). Serious events must be reported within 10 calendar days. "
                "Manufacturers must also submit periodic trend reports (Relatórios Periódicos). "
                "Reports must be in Portuguese."
            ),
            requirement_zh=(
                "巴西要求通過ANVISA的技術警戒系統（NOTIVISA/VigiMed）通報不良事件。"
                "嚴重事件必須在10個日曆天內通報。製造商還必須提交定期趨勢報告"
                "（Relatórios Periódicos）。通報必須使用葡萄牙文。"
            ),
            related_iso_clauses=["8.2.2", "8.2.3"],
            audit_impact="critical",
            audit_question_en=(
                "Does the adverse event reporting procedure address ANVISA Tecnovigilance "
                "requirements including 10-day serious event reporting via NOTIVISA/VigiMed?"
            ),
            audit_question_zh=(
                "不良事件通報程序是否涵蓋ANVISA技術警戒要求，"
                "包括通過NOTIVISA/VigiMed的10天嚴重事件通報？"
            ),
            expected_evidence=[
                "Tecnovigilance reporting procedure / 技術警戒通報程序",
                "NOTIVISA/VigiMed registration / NOTIVISA/VigiMed註冊",
                "Periodic trend reports / 定期趨勢報告",
            ],
            rationale_en=(
                "ANVISA Tecnovigilance system is Brazil-specific. ISO 13485 8.2.3 requires "
                "regulatory reporting but not via a specific system with specific timelines. "
                "Periodic trend reporting has no ISO 13485 equivalent."
            ),
            rationale_zh=(
                "ANVISA技術警戒系統為巴西特有。ISO 13485 8.2.3要求法規通報但未規定"
                "特定系統和時限。定期趨勢報告在ISO 13485中無對應。"
            ),
            method=MappingMethod.CLAUSE_STRUCTURE,
            confidence=0.85,
            original_text=(
                "RDC 551:2021: O detentor de registro deve notificar à ANVISA queixas técnicas e eventos "
                "adversos envolvendo produtos para saúde. Eventos adversos graves devem ser notificados "
                "no prazo de 10 dias corridos. Relatórios periódicos de tendência devem ser submetidos."
            ),
            original_lang="pt",
            english_translation=(
                "RDC 551:2021: Registration holders must notify ANVISA of technical complaints and "
                "adverse events involving health products. Serious adverse events must be notified "
                "within 10 calendar days. Periodic trend reports must be submitted."
            ),
            semantic_note=(
                "Brazil uses 'Tecnovigilância' system (NOTIVISA/VigiMed) — a dedicated adverse event "
                "reporting platform. 10-day timeline for serious events. "
                "US FDA: 5 working days (death), 30 days (serious). EU MDR: 2 days (death), 15 days (other). "
                "Taiwan: 7 days (death/serious), 15 days (other). Canada: 10 days preliminary, 30 days final. "
                "Japan: 15 days (serious), 30 days (other). "
                "Brazil uniquely requires periodic TREND reports in addition to individual event reports. "
                "All submissions must be in Portuguese."
            ),
        ),
        UniqueRequirement(
            req_id="ANVISA-002",
            regulation_ref="RDC 185:2001 / ANVISA Registration",
            title_en="ANVISA Product Registration (Registro)",
            title_zh="ANVISA產品登記（Registro）",
            requirement_en=(
                "All medical devices marketed in Brazil require ANVISA registration (Registro) "
                "or notification (Cadastro) depending on risk class. Class III/IV devices require "
                "full registration with GMP certification (Certificado de Boas Práticas de Fabricação). "
                "Brazilian Good Manufacturing Practice (BPF) certification involves ANVISA on-site inspection."
            ),
            requirement_zh=(
                "所有在巴西銷售的醫療器材需ANVISA登記（Registro）或通報（Cadastro），"
                "取決於風險分類。III/IV類器材需完整登記，附GMP認證"
                "（Certificado de Boas Práticas de Fabricação）。BPF認證涉及ANVISA現場檢查。"
            ),
            related_iso_clauses=["4.1", "7.2.1"],
            audit_impact="critical",
            audit_question_en=(
                "Does the company hold a valid ANVISA registration (Registro) or notification (Cadastro) "
                "for devices marketed in Brazil, with current GMP/BPF certification where required?"
            ),
            audit_question_zh=(
                "公司是否持有有效的ANVISA產品登記或通報，以及所需的GMP/BPF認證？"
            ),
            expected_evidence=[
                "ANVISA registration certificate (Registro) / ANVISA登記證書",
                "BPF certificate / GMP認證（BPF）",
                "ANVISA inspection reports / ANVISA稽查報告",
            ],
            rationale_en=(
                "ANVISA product registration is a Brazilian market access requirement. "
                "ISO 13485 does not address product registration. Closest to 4.1 (QMS) "
                "and 7.2.1 (determination of product requirements)."
            ),
            rationale_zh=(
                "ANVISA產品登記是巴西市場准入要求。ISO 13485未涉及產品登記。"
                "最接近4.1（QMS）和7.2.1（產品要求確定）。"
            ),
            method=MappingMethod.CLAUSE_STRUCTURE,
            confidence=0.85,
            original_text=(
                "RDC 185:2001: Todos os produtos para saúde classificados nas classes III e IV "
                "devem obter registro junto à ANVISA antes de sua comercialização no Brasil. "
                "O registro requer certificação de Boas Práticas de Fabricação (BPF)."
            ),
            original_lang="pt",
            english_translation=(
                "RDC 185:2001: All health products classified as Class III and IV must obtain "
                "registration with ANVISA before marketing in Brazil. Registration requires "
                "Good Manufacturing Practice (GMP/BPF) certification."
            ),
            semantic_note=(
                "Brazil requires ANVISA on-site GMP inspection (BPF certification) for manufacturing sites, "
                "including FOREIGN manufacturing sites. This means ANVISA inspectors travel internationally "
                "to audit factories — a unique practice among MDSAP countries. "
                "US FDA also conducts foreign inspections but does not tie them to product registration. "
                "EU MDR: Notified Body audits, not regulatory authority directly. "
                "Key difference: ANVISA BPF certification is a PREREQUISITE for product registration, "
                "not just a QMS compliance check."
            ),
        ),
        UniqueRequirement(
            req_id="ANVISA-003",
            regulation_ref="RDC 665:2022 / Portuguese Language",
            title_en="Portuguese Language Requirements",
            title_zh="葡萄牙文語言要求",
            requirement_en=(
                "All medical device labeling, instructions for use, and regulatory "
                "submissions to ANVISA must be in Brazilian Portuguese. QMS documentation "
                "must be available in Portuguese for ANVISA inspections."
            ),
            requirement_zh=(
                "所有醫療器材標籤、使用說明書和向ANVISA的法規提交文件必須使用"
                "巴西葡萄牙文。QMS文件在ANVISA稽查時必須有葡萄牙文版本。"
            ),
            related_iso_clauses=["4.2.3", "7.5.1", "7.5.8"],
            audit_impact="major",
            audit_question_en=(
                "Are labels, IFU, and regulatory submissions in Brazilian Portuguese? "
                "Are QMS documents available in Portuguese for ANVISA inspections?"
            ),
            audit_question_zh=(
                "標籤、使用說明書和法規提交文件是否使用巴西葡萄牙文？"
                "QMS文件是否有葡萄牙文版供ANVISA稽查？"
            ),
            expected_evidence=[
                "Portuguese-language labels and IFU / 葡萄牙文標籤和使用說明書",
                "Portuguese QMS documents / 葡萄牙文QMS文件",
            ],
            rationale_en=(
                "Portuguese language is a Brazilian market access requirement. "
                "ISO 13485 does not specify language. Closest to 4.2.3, 7.5.1, 7.5.8."
            ),
            rationale_zh=(
                "葡萄牙文是巴西市場准入要求。ISO 13485未規定語言。"
                "最接近4.2.3、7.5.1、7.5.8。"
            ),
            method=MappingMethod.SEMANTIC_EN,
            confidence=0.90,
            original_text=(
                "A rotulagem e instruções de uso dos produtos para saúde devem ser redigidas "
                "em língua portuguesa. Documentos do SGQ devem estar disponíveis em português "
                "durante inspeções da ANVISA."
            ),
            original_lang="pt",
            english_translation=(
                "Labeling and instructions for use of health products must be written "
                "in Portuguese. QMS documents must be available in Portuguese "
                "during ANVISA inspections."
            ),
            semantic_note=(
                "Brazil requires Brazilian Portuguese for all labeling and regulatory submissions. "
                "Each MDSAP country has unique language requirements: US (English), Canada (English+French), "
                "Japan (Japanese), Australia (English), Brazil (Portuguese). "
                "Brazil and Japan both extend language requirements to QMS documents during inspections."
            ),
        ),
    ]

    return RegulationProfile(
        regulation_id="ANVISA",
        name_en="Brazil ANVISA RDC 665:2022",
        name_zh="巴西 ANVISA RDC 665:2022",
        country="BR",
        country_name_en="Brazil",
        country_name_zh="巴西",
        source="predefined",
        source_url="https://www.gov.br/anvisa/",
        last_updated="2022-03-24",
        effective_date="2022-05-01",
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )


# ============================================================
# Predefined Regulation: Australia TGA (Therapeutic Goods Act 1989)
# ============================================================


def _build_tga_profile() -> RegulationProfile:
    """Build the Australia TGA regulation profile.

    Therapeutic Goods Act 1989 and Therapeutic Goods (Medical Devices)
    Regulations 2002. Administered by the Therapeutic Goods Administration (TGA).
    MDSAP participant country.
    Australia's Essential Principles are harmonized with EU requirements.
    ISO 13485 certification is a prerequisite for inclusion in the ARTG.

    Mapping source: TG(MD)R 2002 regulatory text
    + MDSAP Companion Document for Australia
    """
    iso_mapped: dict[str, ClauseMapping] = {}

    # TGA requires ISO 13485 certification — all clauses are adopted
    tga_clause_map = {
        "4.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "TGA requires ISO 13485 certification for ARTG inclusion. General QMS requirements fully adopted.",
            "TGA要求ISO 13485認證以納入ARTG。一般QMS要求完全採用。",
        ),
        "4.2.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Documentation requirements adopted via mandatory ISO 13485.",
            "文件化要求通過強制性ISO 13485採用。",
        ),
        "4.2.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Quality manual adopted via ISO 13485.",
            "品質手冊通過ISO 13485採用。",
        ),
        "4.2.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Document control adopted via ISO 13485.",
            "文件管制通過ISO 13485採用。",
        ),
        "4.2.4": (
            "TG(MD)R Sch.3 Part 1.2",
            "Record control adopted via ISO 13485.",
            "記錄管制通過ISO 13485採用。",
        ),
        "4.2.5": (
            "TG(MD)R Sch.3 Part 1.2",
            "Medical device file adopted via ISO 13485.",
            "醫療器材檔案通過ISO 13485採用。",
        ),
        "5.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Management commitment adopted via ISO 13485.",
            "管理承諾通過ISO 13485採用。",
        ),
        "5.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Customer focus adopted via ISO 13485.",
            "以顧客為重通過ISO 13485採用。",
        ),
        "5.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Quality policy adopted via ISO 13485.",
            "品質政策通過ISO 13485採用。",
        ),
        "5.4.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Quality objectives adopted via ISO 13485.",
            "品質目標通過ISO 13485採用。",
        ),
        "5.4.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "QMS planning adopted via ISO 13485.",
            "QMS規劃通過ISO 13485採用。",
        ),
        "5.5.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Responsibility and authority adopted via ISO 13485.",
            "責任與權限通過ISO 13485採用。",
        ),
        "5.5.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Management representative adopted via ISO 13485.",
            "管理代表通過ISO 13485採用。",
        ),
        "5.5.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Internal communication adopted via ISO 13485.",
            "內部溝通通過ISO 13485採用。",
        ),
        "5.6.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Management review adopted via ISO 13485.",
            "管理審查通過ISO 13485採用。",
        ),
        "5.6.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Management review input adopted via ISO 13485.",
            "管理審查輸入通過ISO 13485採用。",
        ),
        "5.6.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Management review output adopted via ISO 13485.",
            "管理審查輸出通過ISO 13485採用。",
        ),
        "6.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Resource provision adopted via ISO 13485.",
            "資源提供通過ISO 13485採用。",
        ),
        "6.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Human resources adopted via ISO 13485.",
            "人力資源通過ISO 13485採用。",
        ),
        "6.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Infrastructure adopted via ISO 13485.",
            "基礎設施通過ISO 13485採用。",
        ),
        "6.4.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Work environment adopted via ISO 13485.",
            "工作環境通過ISO 13485採用。",
        ),
        "6.4.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Contamination control adopted via ISO 13485.",
            "污染管制通過ISO 13485採用。",
        ),
        "7.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Product realization planning adopted via ISO 13485.",
            "產品實現規劃通過ISO 13485採用。",
        ),
        "7.2.1": (
            "TG(MD)R Sch.3 Part 1.2 / Essential Principles",
            "Determination of product requirements — TGA Essential Principles add product safety requirements.",
            "產品要求確定 — TGA基本原則增加產品安全要求。",
        ),
        "7.2.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Review of product requirements adopted via ISO 13485.",
            "產品要求審查通過ISO 13485採用。",
        ),
        "7.2.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Communication adopted via ISO 13485.",
            "溝通通過ISO 13485採用。",
        ),
        "7.3.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design planning adopted via ISO 13485.",
            "設計規劃通過ISO 13485採用。",
        ),
        "7.3.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design input adopted via ISO 13485.",
            "設計輸入通過ISO 13485採用。",
        ),
        "7.3.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design output adopted via ISO 13485.",
            "設計輸出通過ISO 13485採用。",
        ),
        "7.3.4": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design review adopted via ISO 13485.",
            "設計審查通過ISO 13485採用。",
        ),
        "7.3.5": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design verification adopted via ISO 13485.",
            "設計驗證通過ISO 13485採用。",
        ),
        "7.3.6": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design validation adopted via ISO 13485.",
            "設計確認通過ISO 13485採用。",
        ),
        "7.3.7": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design transfer adopted via ISO 13485.",
            "設計轉移通過ISO 13485採用。",
        ),
        "7.3.8": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design change control adopted via ISO 13485.",
            "設計變更管制通過ISO 13485採用。",
        ),
        "7.3.9": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design files adopted via ISO 13485.",
            "設計檔案通過ISO 13485採用。",
        ),
        "7.3.10": (
            "TG(MD)R Sch.3 Part 1.2",
            "Design documentation adopted via ISO 13485.",
            "設計文件通過ISO 13485採用。",
        ),
        "7.4.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Purchasing process adopted via ISO 13485.",
            "採購過程通過ISO 13485採用。",
        ),
        "7.4.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Purchasing information adopted via ISO 13485.",
            "採購資訊通過ISO 13485採用。",
        ),
        "7.4.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Verification of purchased product adopted via ISO 13485.",
            "採購產品驗證通過ISO 13485採用。",
        ),
        "7.5.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Production control adopted via ISO 13485.",
            "生產管制通過ISO 13485採用。",
        ),
        "7.5.6": (
            "TG(MD)R Sch.3 Part 1.2",
            "Process validation adopted via ISO 13485.",
            "過程確認通過ISO 13485採用。",
        ),
        "7.5.8": (
            "TG(MD)R Sch.3 Part 1.2",
            "Identification adopted via ISO 13485.",
            "識別通過ISO 13485採用。",
        ),
        "7.5.9": (
            "TG(MD)R Sch.3 Part 1.2",
            "Traceability adopted via ISO 13485.",
            "追溯性通過ISO 13485採用。",
        ),
        "7.5.11": (
            "TG(MD)R Sch.3 Part 1.2",
            "Product preservation adopted via ISO 13485.",
            "產品防護通過ISO 13485採用。",
        ),
        "7.6": (
            "TG(MD)R Sch.3 Part 1.2",
            "Monitoring equipment adopted via ISO 13485.",
            "監測設備通過ISO 13485採用。",
        ),
        "8.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "General measurement requirements adopted via ISO 13485.",
            "一般量測要求通過ISO 13485採用。",
        ),
        "8.2.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Feedback adopted via ISO 13485.",
            "回饋通過ISO 13485採用。",
        ),
        "8.2.2": (
            "TG(MD)R Sch.3 Part 1.2 / TG Act s.41G",
            "Complaint handling adopted via ISO 13485. TG Act s.41G adds mandatory adverse event reporting to TGA.",
            "客訴處理通過ISO 13485採用。TG Act s.41G增加向TGA的強制性不良事件通報。",
        ),
        "8.2.3": (
            "TG Act s.41G-41K",
            "Regulatory reporting — TG Act mandates adverse event and recall reporting to TGA.",
            "法規通報 — TG Act要求向TGA進行不良事件和召回通報。",
        ),
        "8.2.4": (
            "TG(MD)R Sch.3 Part 1.2",
            "Internal audit adopted via ISO 13485.",
            "內部稽核通過ISO 13485採用。",
        ),
        "8.2.5": (
            "TG(MD)R Sch.3 Part 1.2",
            "Process monitoring adopted via ISO 13485.",
            "過程監督通過ISO 13485採用。",
        ),
        "8.2.6": (
            "TG(MD)R Sch.3 Part 1.2",
            "Product monitoring adopted via ISO 13485.",
            "產品監督通過ISO 13485採用。",
        ),
        "8.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Nonconforming product adopted via ISO 13485.",
            "不合格品通過ISO 13485採用。",
        ),
        "8.4": (
            "TG(MD)R Sch.3 Part 1.2",
            "Data analysis adopted via ISO 13485.",
            "數據分析通過ISO 13485採用。",
        ),
        "8.5.1": (
            "TG(MD)R Sch.3 Part 1.2",
            "Improvement adopted via ISO 13485.",
            "改善通過ISO 13485採用。",
        ),
        "8.5.2": (
            "TG(MD)R Sch.3 Part 1.2",
            "Corrective action adopted via ISO 13485.",
            "矯正措施通過ISO 13485採用。",
        ),
        "8.5.3": (
            "TG(MD)R Sch.3 Part 1.2",
            "Preventive action adopted via ISO 13485.",
            "預防措施通過ISO 13485採用。",
        ),
    }

    for clause_id, (ref, rationale_en, rationale_zh) in tga_clause_map.items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=clause_id,
            status=MappingStatus.FULL,
            regulation_ref=ref,
            rationale_en=rationale_en,
            rationale_zh=rationale_zh,
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            notes="TG(MD)R 2002 Schedule 3 (legislation.gov.au)",
        )

    # TGA-specific unique requirements (delta from ISO 13485)
    unique_reqs = [
        UniqueRequirement(
            req_id="TGA-001",
            regulation_ref="TG Act s.41G-41K",
            title_en="Mandatory Adverse Event Reporting to TGA",
            title_zh="向TGA強制性不良事件通報",
            requirement_en=(
                "Sponsors (manufacturers/importers) must report adverse events to TGA: "
                "2 days for events involving death or serious threat to public health, "
                "10 days for serious deterioration in health, 30 days for other reportable events. "
                "Reports are submitted through TGA's IRIS system."
            ),
            requirement_zh=(
                "贊助商（製造商/進口商）必須向TGA通報不良事件："
                "涉及死亡或嚴重公共衛生威脅2天、健康嚴重惡化10天、"
                "其他應通報事件30天。通過TGA的IRIS系統提交報告。"
            ),
            related_iso_clauses=["8.2.2", "8.2.3"],
            audit_impact="critical",
            audit_question_en=(
                "Does the adverse event reporting procedure specify 2-day (death/public health), "
                "10-day (serious), and 30-day (other) reporting timelines to TGA per TG Act s.41G?"
            ),
            audit_question_zh=(
                "不良事件通報程序是否規定依TG Act s.41G向TGA的2天（死亡/公共衛生）、"
                "10天（嚴重）和30天（其他）通報時限？"
            ),
            expected_evidence=[
                "Adverse event reporting procedure with TGA timelines / 含TGA時限之不良事件通報程序",
                "TGA IRIS system registration / TGA IRIS系統註冊",
                "Adverse event report records / 不良事件通報記錄",
            ],
            rationale_en=(
                "TGA adverse event timelines are Australia-specific. ISO 13485 8.2.3 requires "
                "regulatory reporting but without specific day counts. TGA uses a multi-tier "
                "timeline system similar to EU MDR."
            ),
            rationale_zh=(
                "TGA不良事件時限為澳洲特有。ISO 13485 8.2.3要求法規通報但無特定天數。"
                "TGA使用與EU MDR類似的多層級時限系統。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "Therapeutic Goods Act 1989 s.41G: The sponsor of a kind of therapeutic goods "
                "must, within 2 days (death/serious public health threat), 10 days (serious "
                "deterioration), or 30 days (other), report to the Secretary any adverse event "
                "involving those therapeutic goods."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "TGA uses a 3-tier timeline: 2/10/30 days, closely mirroring EU MDR (2/10/15 days). "
                "US FDA: 5 working days (death), 30 days (serious). Canada: 10/30 days. "
                "Japan: 15/30 days. Taiwan: 7/15 days. "
                "Australia's 2-day deadline for death/public health threat matches EU as the strictest. "
                "TGA uses IRIS system; EU uses EUDAMED; US uses MedWatch/eMDR. "
                "Cross-country: Australia and EU are most stringent, Japan most lenient."
            ),
        ),
        UniqueRequirement(
            req_id="TGA-002",
            regulation_ref="TG Act s.41FN-41FR / ARTG",
            title_en="ARTG Inclusion (Australian Register of Therapeutic Goods)",
            title_zh="ARTG納入（澳洲治療用品登記冊）",
            requirement_en=(
                "All medical devices must be included in the Australian Register of "
                "Therapeutic Goods (ARTG) before marketing. ARTG inclusion requires: "
                "ISO 13485 certification, compliance with Essential Principles (Schedule 1), "
                "and an Australian Sponsor. Class IIb/III/AIMD devices require conformity "
                "assessment by a TGA-recognized conformity assessment body."
            ),
            requirement_zh=(
                "所有醫療器材在上市前必須納入澳洲治療用品登記冊（ARTG）。"
                "ARTG納入要求：ISO 13485認證、符合基本原則（附表1）、"
                "澳洲贊助商。IIb/III/AIMD類器材需由TGA認可的合格評定機構進行評估。"
            ),
            related_iso_clauses=["4.1", "7.2.1"],
            audit_impact="critical",
            audit_question_en=(
                "Are all devices marketed in Australia included in the ARTG with current "
                "ISO 13485 certification and Essential Principles compliance?"
            ),
            audit_question_zh=(
                "所有在澳洲銷售的器材是否已納入ARTG，"
                "具有現行ISO 13485認證和基本原則合規？"
            ),
            expected_evidence=[
                "ARTG inclusion certificate / ARTG納入證書",
                "ISO 13485 certificate / ISO 13485證書",
                "Essential Principles compliance evidence / 基本原則合規證據",
                "Australian Sponsor agreement / 澳洲贊助商合約",
            ],
            rationale_en=(
                "ARTG inclusion is an Australian market access requirement. "
                "ISO 13485 does not address product registration. Closest to 4.1 (QMS) "
                "and 7.2.1 (determination of product requirements)."
            ),
            rationale_zh=(
                "ARTG納入是澳洲市場准入要求。ISO 13485未涉及產品登記。"
                "最接近4.1（QMS）和7.2.1（產品要求確定）。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "Therapeutic Goods Act 1989: A person must not import, export, or supply "
                "therapeutic goods unless the goods are included in the ARTG. "
                "Inclusion requires evidence of conformity with applicable Essential Principles "
                "and a quality management system certificate."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "Australia's ARTG is similar to EU CE marking + product registration combined. "
                "It requires BOTH QMS certification (ISO 13485) AND product-level evidence "
                "(Essential Principles = similar to EU Essential Requirements). "
                "US FDA: 510(k)/PMA is product-focused, establishment registration is separate. "
                "Canada: MDEL for establishment + device license for product. "
                "Key difference: TGA's Essential Principles are heavily derived from EU Essential "
                "Requirements, reflecting Australia's historical regulatory alignment with EU."
            ),
        ),
        UniqueRequirement(
            req_id="TGA-003",
            regulation_ref="TG Act s.41C / Sponsor Requirements",
            title_en="Australian Sponsor Obligations",
            title_zh="澳洲贊助商義務",
            requirement_en=(
                "An Australian Sponsor (person or company resident in Australia) is required "
                "for all therapeutic goods. The Sponsor bears legal responsibility for "
                "compliance, adverse event reporting, recall management, and post-market "
                "surveillance. Foreign manufacturers cannot directly register devices."
            ),
            requirement_zh=(
                "所有治療用品需要澳洲贊助商（在澳洲居住的個人或公司）。"
                "贊助商承擔合規、不良事件通報、召回管理和上市後監督的法律責任。"
                "外國製造商不能直接登記器材。"
            ),
            related_iso_clauses=["5.5.1", "7.2.3", "8.2.3"],
            audit_impact="major",
            audit_question_en=(
                "Is an Australian Sponsor appointed who fulfills all regulatory obligations "
                "including adverse event reporting and recall management per TG Act s.41C?"
            ),
            audit_question_zh=(
                "是否任命澳洲贊助商履行所有法規義務，"
                "包括不良事件通報和召回管理？（TG Act s.41C）"
            ),
            expected_evidence=[
                "Sponsor agreement / 贊助商合約",
                "Sponsor registration with TGA / 贊助商TGA登記",
                "Sponsor post-market surveillance plan / 贊助商上市後監督計畫",
            ],
            rationale_en=(
                "Australian Sponsor is a TGA market access requirement with no ISO 13485 equivalent. "
                "Closest to 5.5.1 (responsibility), 7.2.3 (communication), 8.2.3 (regulatory reporting). "
                "Sponsor bears broader obligations than EU AR or US Agent."
            ),
            rationale_zh=(
                "澳洲贊助商是TGA市場准入要求，ISO 13485無對應。"
                "最接近5.5.1（責任）、7.2.3（溝通）、8.2.3（法規通報）。"
                "贊助商承擔比EU授權代表或US代理人更廣泛的義務。"
            ),
            method=MappingMethod.OFFICIAL_CROSSREF,
            confidence=0.90,
            original_text=(
                "Therapeutic Goods Act 1989 s.41C: The sponsor of therapeutic goods included "
                "in the ARTG is responsible for ensuring the goods comply with all applicable "
                "requirements, including adverse event reporting, recall procedures, and "
                "post-market surveillance."
            ),
            original_lang="en",
            english_translation="",
            semantic_note=(
                "Australia's Sponsor role is the BROADEST local representative requirement among MDSAP countries. "
                "The Sponsor bears full legal liability including criminal penalties. "
                "EU MDR Art 11 AR: ensures compliance, communication contact. "
                "US FDA: US Agent is only a communication contact (very limited role). "
                "Canada: MDEL holder. Japan: MAH holds marketing authorization. "
                "Taiwan: Authorized representative holds the license. "
                "Cross-country: Australia > Taiwan ≈ Japan > EU > Canada > US in terms of "
                "local representative legal liability scope."
            ),
        ),
    ]

    return RegulationProfile(
        regulation_id="TGA",
        name_en="Australia TGA Therapeutic Goods Act 1989",
        name_zh="澳洲 TGA 治療用品法 1989",
        country="AU",
        country_name_en="Australia",
        country_name_zh="澳洲",
        source="predefined",
        source_url="https://www.legislation.gov.au/Details/C2021C00376",
        last_updated="2023-07-01",
        effective_date="1991-02-15",
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )


# ============================================================
# Build predefined profiles (loaded once at import time)
# ============================================================

PREDEFINED_REGULATIONS: dict[str, RegulationProfile] = {}


def _init_predefined() -> None:
    """Initialize predefined regulation profiles."""
    global PREDEFINED_REGULATIONS
    PREDEFINED_REGULATIONS["QMSR"] = _build_qmsr_profile()
    PREDEFINED_REGULATIONS["EU_MDR"] = _build_eu_mdr_profile()
    PREDEFINED_REGULATIONS["TFDA"] = _build_tfda_profile()
    PREDEFINED_REGULATIONS["HC"] = _build_hc_profile()
    PREDEFINED_REGULATIONS["PMDA"] = _build_pmda_profile()
    PREDEFINED_REGULATIONS["ANVISA"] = _build_anvisa_profile()
    PREDEFINED_REGULATIONS["TGA"] = _build_tga_profile()


_init_predefined()

# ============================================================
# Region ↔ Profile ID Mapping (for crawler → profile resolution)
# ============================================================

# Static mapping for predefined 7-country profiles.
# Key: REGION_SITES key (from regulatory_crawler.py)
# Value: PREDEFINED_REGULATIONS key
_REGION_TO_PROFILE_STATIC: dict[str, str] = {
    "台灣 (Taiwan)": "TFDA",
    "美國 (USA)": "QMSR",
    "歐盟 (EU)": "EU_MDR",
    "加拿大 (Canada)": "HC",
    "日本 (Japan)": "PMDA",
    "巴西 (Brazil)": "ANVISA",
    "澳洲 (Australia)": "TGA",
}


def get_profile_id_for_region(region_name: str) -> Optional[str]:
    """Resolve a crawler region name to a RegulationProfile ID.

    Checks in order:
      1. Static mapping (predefined 7 countries)
      2. Dynamically loaded crawled profiles (by country_name_zh match)
      3. None if no profile exists yet

    Args:
        region_name: REGION_SITES key, e.g., "新加坡 (Singapore)"

    Returns:
        Profile ID (e.g., "TFDA", "SG_HSA") or None
    """
    # 1. Check static mapping first (predefined 7)
    if region_name in _REGION_TO_PROFILE_STATIC:
        return _REGION_TO_PROFILE_STATIC[region_name]

    # 2. Check dynamically registered profiles (crawled / loaded)
    #    Match by country_name_zh which contains the region display name
    for profile_id, profile in PREDEFINED_REGULATIONS.items():
        if profile_id in _REGION_TO_PROFILE_STATIC.values():
            continue  # Skip predefined — already checked
        # Match: region "新加坡 (Singapore)" → profile.country_name_zh "新加坡"
        region_zh = region_name.split(" (")[0] if " (" in region_name else region_name
        if profile.country_name_zh == region_zh:
            return profile_id
        # Also try matching by English name in parentheses
        if "(" in region_name and ")" in region_name:
            region_en = region_name.split("(")[1].rstrip(")")
            if profile.country_name_en.lower() == region_en.lower():
                return profile_id

    return None


def get_region_for_profile(profile_id: str) -> Optional[str]:
    """Reverse lookup: profile ID → crawler region name.

    Args:
        profile_id: e.g., "TFDA", "SG_HSA"

    Returns:
        Region name (e.g., "台灣 (Taiwan)") or None
    """
    # 1. Check static reverse mapping
    for region, pid in _REGION_TO_PROFILE_STATIC.items():
        if pid == profile_id:
            return region

    # 2. Check dynamically registered profiles
    profile = PREDEFINED_REGULATIONS.get(profile_id)
    if profile:
        # Reconstruct region name format: "{zh_name} ({en_name})"
        return f"{profile.country_name_zh} ({profile.country_name_en})"

    return None


def get_profile_ids_for_regions(region_names: list[str]) -> list[str]:
    """Resolve a list of crawler region names to profile IDs.

    Only returns IDs for regions that have a registered profile.
    Regions without profiles are silently skipped.

    Args:
        region_names: List of REGION_SITES keys

    Returns:
        List of profile IDs (may be shorter than input)
    """
    result = []
    for region in region_names:
        pid = get_profile_id_for_region(region)
        if pid:
            result.append(pid)
    return result


def get_regions_without_profile(region_names: list[str]) -> list[str]:
    """Find regions that do NOT have a registered RegulationProfile.

    These regions need LLM analysis to generate a profile.

    Args:
        region_names: List of REGION_SITES keys

    Returns:
        List of region names that lack a profile
    """
    return [r for r in region_names if get_profile_id_for_region(r) is None]


def generate_profile_id_from_region(region_name: str) -> str:
    """Generate a regulation_id for a new country based on its region name.

    Convention: {ISO2_COUNTRY_CODE}_{PRIMARY_AGENCY}
    Fallback:   {EN_NAME_UPPER} if country code unknown

    Examples:
        "新加坡 (Singapore)" → "SG_HSA"
        "韓國 (Korea)" → "KR_MFDS"
        "印度 (India)" → "IN_CDSCO"
    """
    # Known country code + primary agency mapping
    _REGION_TO_ID: dict[str, str] = {
        "英國 (UK)": "UK_MHRA",
        "中國 (China)": "CN_NMPA",
        "韓國 (Korea)": "KR_MFDS",
        "瑞士 (Switzerland)": "CH_SWISSMEDIC",
        "國際標準 (International)": "INTL_STD",
        "印度 (India)": "IN_CDSCO",
        "新加坡 (Singapore)": "SG_HSA",
        "沙烏地阿拉伯 (Saudi Arabia)": "SA_SFDA",
        "泰國 (Thailand)": "TH_FDA",
        "紐西蘭 (New Zealand)": "NZ_MEDSAFE",
        "墨西哥 (Mexico)": "MX_COFEPRIS",
        "阿根廷 (Argentina)": "AR_ANMAT",
        "南非 (South Africa)": "ZA_SAHPRA",
        "土耳其 (Turkey)": "TR_TITCK",
        "印尼 (Indonesia)": "ID_BPOM",
        "馬來西亞 (Malaysia)": "MY_MDA",
        "以色列 (Israel)": "IL_AMAR",
        "菲律賓 (Philippines)": "PH_FDA",
        "越南 (Vietnam)": "VN_MOH",
        "哥倫比亞 (Colombia)": "CO_INVIMA",
        "俄羅斯 (Russia)": "RU_ROSZDRAVNADZOR",
        "埃及 (Egypt)": "EG_EDA",
        "智利 (Chile)": "CL_ISP",
        "阿聯酋 (UAE)": "AE_MOHAP",
    }
    if region_name in _REGION_TO_ID:
        return _REGION_TO_ID[region_name]

    # Fallback: extract English name and uppercase
    if "(" in region_name and ")" in region_name:
        en_name = region_name.split("(")[1].rstrip(")")
        return en_name.upper().replace(" ", "_")
    return region_name.upper().replace(" ", "_")


# ============================================================
# Predefined Supplemental Standards Library
# ============================================================


def _build_predefined_standards() -> dict[str, SupplementalStandardProfile]:
    """Build the predefined supplemental standards library.

    These are the most commonly referenced standards in medical device QMS.
    Each standard defines:
      - WHEN it applies (detection keywords + universal flag)
      - HOW it links to ISO 13485 clauses
      - HOW country regulations reference it
    """
    standards: dict[str, SupplementalStandardProfile] = {}

    # ---- ISO 14971: Risk Management (Universal) ----
    standards["ISO_14971"] = SupplementalStandardProfile(
        standard_id="ISO_14971",
        name_en="ISO 14971:2019 Medical devices — Application of risk management",
        name_zh="ISO 14971:2019 醫療器材 — 風險管理之應用",
        category=StandardCategory.RISK_MANAGEMENT,
        version="2019",
        is_universal=True,  # Applies to ALL medical devices
        detection_keywords_en=[
            "risk management",
            "risk analysis",
            "risk evaluation",
            "risk control",
            "hazard",
            "14971",
            "risk-based approach",
        ],
        detection_keywords_zh=[
            "風險管理",
            "風險分析",
            "風險評估",
            "風險控制",
            "危害",
            "14971",
            "風險基礎方法",
        ],
        primary_iso_clauses=["7.1", "7.3.3", "7.3.9", "8.2.1", "8.5.2"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Clause 4 (Risk management process)",
                iso_13485_clause="7.1",
                relationship="elaborates",
                description_en="ISO 14971 Clause 4 defines the risk management process that satisfies ISO 13485 Clause 7.1 requirement for risk management during product realization planning.",
                description_zh="ISO 14971 第4條定義的風險管理過程滿足 ISO 13485 條款 7.1 對產品實現規劃中風險管理的要求。",
            ),
            StandardClauseLink(
                standard_clause="Clause 5-8 (Analysis, evaluation, control, residual risk)",
                iso_13485_clause="7.3.3",
                relationship="implements",
                description_en="Risk analysis/evaluation/control outputs feed into design input (ISO 13485 7.3.3c requires risk management output as design input).",
                description_zh="風險分析/評估/控制輸出作為設計輸入（ISO 13485 7.3.3c 要求風險管理輸出作為設計輸入）。",
            ),
            StandardClauseLink(
                standard_clause="Clause 9 (Production and post-production)",
                iso_13485_clause="8.2.1",
                relationship="supplements",
                description_en="Post-production risk monitoring feeds into ISO 13485 8.2.1 feedback system.",
                description_zh="上市後風險監控回饋至 ISO 13485 8.2.1 回饋系統。",
            ),
            StandardClauseLink(
                standard_clause="Clause 7 (Risk control)",
                iso_13485_clause="7.3.9",
                relationship="elaborates",
                description_en="Design changes must trigger risk re-evaluation per ISO 14971 Clause 7.",
                description_zh="設計變更必須依 ISO 14971 第7條觸發風險重新評估。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard; required under QMSR for risk-based approach (21 CFR 820.10 + ISO 13485 Clause 7.1)",
            "EU": "Harmonized standard under EU MDR; Annex I GSPR requires risk management system per ISO 14971",
            "TW": "TFDA 醫療器材品質管理系統準則要求依循 ISO 14971 執行產品實現之風險管理",
        },
        audit_questions=[
            {
                "question_zh": "組織是否建立並維持風險管理過程，包含風險分析、風險評估、風險控制及殘餘風險評價？",
                "question_en": "Has the organization established and maintained a risk management process including risk analysis, evaluation, control, and residual risk assessment?",
                "expected_evidence": [
                    "風險管理計畫 / Risk management plan",
                    "風險管理報告 / Risk management report",
                    "風險管理檔案 / Risk management file",
                    "FMEA / FTA / HAZOP 分析紀錄",
                ],
                "audit_impact": "critical",
                "iso_clause": "7.1",
            },
        ],
    )

    # ---- IEC 62304: Software Lifecycle ----
    standards["IEC_62304"] = SupplementalStandardProfile(
        standard_id="IEC_62304",
        name_en="IEC 62304:2006+A1:2015 Medical device software — Software life cycle processes",
        name_zh="IEC 62304:2006+A1:2015 醫療器材軟體 — 軟體生命週期過程",
        category=StandardCategory.SOFTWARE,
        version="2006+A1:2015",
        detection_keywords_en=[
            "software",
            "SaMD",
            "software as medical device",
            "62304",
            "software lifecycle",
            "software development",
            "firmware",
            "software unit",
            "software system",
            "SOUP",
        ],
        detection_keywords_zh=[
            "軟體",
            "韌體",
            "軟體醫療器材",
            "62304",
            "軟體生命週期",
            "軟體開發",
            "軟體單元",
            "SOUP",
        ],
        primary_iso_clauses=[
            "7.3",
            "7.3.1",
            "7.3.2",
            "7.3.3",
            "7.3.4",
            "7.3.5",
            "7.3.6",
            "7.3.7",
            "4.1.6",
            "7.5.6",
        ],
        clause_links=[
            StandardClauseLink(
                standard_clause="Clause 5 (Software development process)",
                iso_13485_clause="7.3",
                relationship="implements",
                description_en="IEC 62304 Clause 5 is the software-specific implementation of ISO 13485 Section 7.3 design and development controls.",
                description_zh="IEC 62304 第5條是 ISO 13485 第7.3節設計開發控制在軟體領域的具體實作。",
            ),
            StandardClauseLink(
                standard_clause="Clause 7 (Software risk management)",
                iso_13485_clause="7.1",
                relationship="supplements",
                description_en="Software-specific risk management supplements ISO 14971 and satisfies ISO 13485 7.1 risk requirements for software.",
                description_zh="軟體特定風險管理補充 ISO 14971，滿足 ISO 13485 7.1 對軟體的風險要求。",
            ),
            StandardClauseLink(
                standard_clause="Clause 6 (Software maintenance)",
                iso_13485_clause="7.5.4",
                relationship="elaborates",
                description_en="Software maintenance process elaborates servicing activities for software medical devices.",
                description_zh="軟體維護過程細化軟體醫療器材的服務活動。",
            ),
            StandardClauseLink(
                standard_clause="Clause 8 (Software configuration management)",
                iso_13485_clause="4.2.3",
                relationship="supplements",
                description_en="Software configuration management supplements document control for software artifacts.",
                description_zh="軟體配置管理補充軟體產出物的文件控制。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard; required for software medical devices under QMSR",
            "EU": "Harmonized standard under EU MDR for SaMD and software components",
            "TW": "TFDA 醫療器材軟體製造業者品質管理系統指導文件建議參考",
        },
        audit_questions=[
            {
                "question_zh": "軟體開發過程是否依循 IEC 62304 建立軟體開發計畫、架構設計、單元測試、整合測試及系統測試？",
                "question_en": "Does the software development process follow IEC 62304 with development plan, architecture, unit testing, integration testing, and system testing?",
                "expected_evidence": [
                    "軟體開發計畫 / Software development plan",
                    "軟體架構文件 / Software architecture document",
                    "SOUP 清單 / SOUP list",
                    "軟體測試紀錄 / Software test records",
                ],
                "audit_impact": "critical",
                "iso_clause": "7.3",
            },
        ],
    )

    # ---- IEC 62366-1: Usability Engineering ----
    standards["IEC_62366"] = SupplementalStandardProfile(
        standard_id="IEC_62366",
        name_en="IEC 62366-1:2015+A1:2020 Medical devices — Application of usability engineering",
        name_zh="IEC 62366-1:2015+A1:2020 醫療器材 — 可用性工程之應用",
        category=StandardCategory.USABILITY,
        version="2015+A1:2020",
        detection_keywords_en=[
            "usability",
            "human factors",
            "62366",
            "use error",
            "user interface",
            "formative evaluation",
            "summative evaluation",
        ],
        detection_keywords_zh=[
            "可用性",
            "人因工程",
            "62366",
            "使用錯誤",
            "使用者介面",
            "形成性評估",
            "總結性評估",
        ],
        primary_iso_clauses=["7.3.3", "7.3.6", "7.3.10"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Clause 5 (Usability engineering process)",
                iso_13485_clause="7.3.3",
                relationship="implements",
                description_en="IEC 62366-1 Clause 5 implements the usability requirement explicitly cited in ISO 13485 Clause 7.3.3 notes.",
                description_zh="IEC 62366-1 第5條實施 ISO 13485 條款 7.3.3 註釋中明確引用的可用性要求。",
            ),
            StandardClauseLink(
                standard_clause="Usability Engineering File (UEF)",
                iso_13485_clause="7.3.10",
                relationship="supplements",
                description_en="The UEF is a required component of the ISO 13485 Design and Development File (DHF).",
                description_zh="可用性工程檔案 (UEF) 是 ISO 13485 設計開發檔案 (DHF) 的必要組成。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard; Human Factors guidance requires usability engineering",
            "EU": "Harmonized standard under EU MDR; usability is core safety requirement",
            "TW": "TFDA 建議參考之可用性標準",
        },
    )

    # ---- IEC 60601-1: Electrical Safety ----
    standards["IEC_60601"] = SupplementalStandardProfile(
        standard_id="IEC_60601",
        name_en="IEC 60601-1:2005+A1:2012+A2:2020 Medical electrical equipment — General requirements for basic safety and essential performance",
        name_zh="IEC 60601-1:2005+A1:2012+A2:2020 醫用電氣設備 — 基本安全與必要性能的一般要求",
        category=StandardCategory.ELECTRICAL_SAFETY,
        version="2005+A1:2012+A2:2020",
        detection_keywords_en=[
            "electrical",
            "60601",
            "ME equipment",
            "medical electrical",
            "basic safety",
            "essential performance",
            "leakage current",
            "dielectric strength",
            "protective earth",
        ],
        detection_keywords_zh=[
            "電氣安全",
            "60601",
            "醫用電氣",
            "醫用電子",
            "基本安全",
            "必要性能",
            "漏電流",
            "介電強度",
        ],
        primary_iso_clauses=["7.3.3", "7.3.5", "7.3.6", "4.2.5"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Clause 4 (General requirements)",
                iso_13485_clause="7.3.3",
                relationship="supplements",
                description_en="IEC 60601-1 safety requirements feed into design input as regulatory/safety requirements.",
                description_zh="IEC 60601-1 安全要求作為法規/安全要求納入設計輸入。",
            ),
            StandardClauseLink(
                standard_clause="Type tests / routine tests",
                iso_13485_clause="7.3.6",
                relationship="verifies",
                description_en="IEC 60601-1 test reports are core design verification evidence for electrical medical devices.",
                description_zh="IEC 60601-1 測試報告是電氣醫療器材設計驗證的核心證據。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard; mandatory for 510(k)/PMA of electrical medical devices",
            "EU": "Harmonized standard under EU MDR; testing required for CE marking",
            "TW": "TFDA 查驗登記必要測試標準",
        },
    )

    # ---- IEC 60601-1-2: EMC ----
    standards["IEC_60601_1_2"] = SupplementalStandardProfile(
        standard_id="IEC_60601_1_2",
        name_en="IEC 60601-1-2:2014+A1:2020 Medical electrical equipment — EMC requirements and tests",
        name_zh="IEC 60601-1-2:2014+A1:2020 醫用電氣設備 — 電磁相容性要求與測試",
        category=StandardCategory.EMC,
        version="2014+A1:2020",
        detection_keywords_en=[
            "EMC",
            "electromagnetic compatibility",
            "60601-1-2",
            "emissions",
            "immunity",
            "electromagnetic",
            "RF interference",
        ],
        detection_keywords_zh=[
            "電磁相容性",
            "EMC",
            "60601-1-2",
            "電磁放射",
            "電磁免疫",
            "射頻干擾",
        ],
        primary_iso_clauses=["7.3.3", "7.3.6"],
        clause_links=[
            StandardClauseLink(
                standard_clause="EMC test plan and risk assessment",
                iso_13485_clause="7.3.3",
                relationship="supplements",
                description_en="EMC requirements and intended EM environment feed into design input.",
                description_zh="EMC 要求及預期電磁環境納入設計輸入。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard; required for all electrical medical devices",
            "EU": "Harmonized standard under EU MDR",
            "TW": "TFDA 查驗登記 EMC 測試必要標準",
        },
    )

    # ---- ISO 10993 series: Biocompatibility ----
    standards["ISO_10993"] = SupplementalStandardProfile(
        standard_id="ISO_10993",
        name_en="ISO 10993 series — Biological evaluation of medical devices",
        name_zh="ISO 10993 系列 — 醫療器材的生物評估",
        category=StandardCategory.BIOCOMPATIBILITY,
        version="2018 (Part 1)",
        detection_keywords_en=[
            "biocompatibility",
            "10993",
            "biological evaluation",
            "cytotoxicity",
            "sensitization",
            "irritation",
            "implantation",
            "body contact",
            "tissue contact",
            "blood contact",
        ],
        detection_keywords_zh=[
            "生物相容性",
            "10993",
            "生物評估",
            "細胞毒性",
            "致敏",
            "刺激",
            "植入",
            "身體接觸",
            "組織接觸",
            "血液接觸",
        ],
        primary_iso_clauses=["7.3.3", "7.3.5", "7.3.6"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Part 1: Evaluation and testing within a risk management process",
                iso_13485_clause="7.3.3",
                relationship="supplements",
                description_en="Biocompatibility requirements based on device-body contact nature feed into design input.",
                description_zh="根據器材與人體接觸性質的生物相容性要求納入設計輸入。",
            ),
            StandardClauseLink(
                standard_clause="Biological test reports",
                iso_13485_clause="7.3.6",
                relationship="verifies",
                description_en="Biocompatibility test reports serve as design verification/validation evidence.",
                description_zh="生物相容性測試報告作為設計驗證/確認證據。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard; required for devices with body contact",
            "EU": "Harmonized standard under EU MDR; GSPR Annex I Chapter II",
            "TW": "TFDA 查驗登記生物相容性測試必要標準",
        },
    )

    # ---- ISO 11135: EO Sterilization ----
    standards["ISO_11135"] = SupplementalStandardProfile(
        standard_id="ISO_11135",
        name_en="ISO 11135:2014 Sterilization of health-care products — Ethylene oxide",
        name_zh="ISO 11135:2014 醫療保健產品滅菌 — 環氧乙烷 (EO)",
        category=StandardCategory.STERILIZATION,
        version="2014",
        detection_keywords_en=[
            "EO sterilization",
            "ethylene oxide",
            "11135",
            "EO residuals",
            "EtO",
            "gas sterilization",
        ],
        detection_keywords_zh=[
            "EO滅菌",
            "環氧乙烷",
            "11135",
            "EO殘留",
            "氣體滅菌",
            "環氧乙烷滅菌",
        ],
        primary_iso_clauses=["7.5.6", "7.5.7"],
        clause_links=[
            StandardClauseLink(
                standard_clause="EO sterilization validation (IQ/OQ/PQ)",
                iso_13485_clause="7.5.7",
                relationship="implements",
                description_en="ISO 11135 defines how to validate EO sterilization processes per ISO 13485 7.5.7.",
                description_zh="ISO 11135 定義如何依 ISO 13485 7.5.7 驗證 EO 滅菌過程。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard for EO sterilization validation",
            "EU": "Harmonized standard under EU MDR",
            "TW": "TFDA 滅菌確效必要標準",
        },
    )

    # ---- ISO 11137: Radiation Sterilization ----
    standards["ISO_11137"] = SupplementalStandardProfile(
        standard_id="ISO_11137",
        name_en="ISO 11137 series — Sterilization of health-care products — Radiation",
        name_zh="ISO 11137 系列 — 醫療保健產品滅菌 — 輻射",
        category=StandardCategory.STERILIZATION,
        version="2006 (Part 1/2), 2017 (Part 3)",
        detection_keywords_en=[
            "radiation sterilization",
            "gamma",
            "electron beam",
            "11137",
            "irradiation",
            "dose audit",
        ],
        detection_keywords_zh=[
            "輻射滅菌",
            "伽瑪",
            "電子束",
            "11137",
            "照射",
            "劑量稽核",
        ],
        primary_iso_clauses=["7.5.6", "7.5.7"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Radiation sterilization validation and dose setting",
                iso_13485_clause="7.5.7",
                relationship="implements",
                description_en="ISO 11137 defines radiation sterilization dose setting and validation per ISO 13485 7.5.7.",
                description_zh="ISO 11137 定義輻射滅菌劑量設定與驗證，依 ISO 13485 7.5.7。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard for radiation sterilization",
            "EU": "Harmonized standard under EU MDR",
            "TW": "TFDA 滅菌確效必要標準",
        },
    )

    # ---- ISO 17665: Steam Sterilization ----
    standards["ISO_17665"] = SupplementalStandardProfile(
        standard_id="ISO_17665",
        name_en="ISO 17665-1:2006 Sterilization of health-care products — Moist heat",
        name_zh="ISO 17665-1:2006 醫療保健產品滅菌 — 濕熱",
        category=StandardCategory.STERILIZATION,
        version="2006",
        detection_keywords_en=[
            "steam sterilization",
            "moist heat",
            "17665",
            "autoclave",
            "steam sterilizer",
        ],
        detection_keywords_zh=[
            "蒸氣滅菌",
            "濕熱滅菌",
            "17665",
            "高壓滅菌",
            "高壓蒸氣滅菌鍋",
        ],
        primary_iso_clauses=["7.5.6", "7.5.7"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Moist heat sterilization validation",
                iso_13485_clause="7.5.7",
                relationship="implements",
                description_en="ISO 17665 defines moist heat sterilization validation per ISO 13485 7.5.7.",
                description_zh="ISO 17665 定義濕熱滅菌驗證，依 ISO 13485 7.5.7。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard for steam sterilization",
            "EU": "Harmonized standard under EU MDR",
            "TW": "TFDA 滅菌確效必要標準",
        },
    )

    # ---- ISO 11607: Sterile Barrier Packaging ----
    standards["ISO_11607"] = SupplementalStandardProfile(
        standard_id="ISO_11607",
        name_en="ISO 11607 series — Packaging for terminally sterilized medical devices",
        name_zh="ISO 11607 系列 — 最終滅菌醫療器材之包裝",
        category=StandardCategory.PACKAGING,
        version="2019",
        detection_keywords_en=[
            "sterile barrier",
            "11607",
            "packaging validation",
            "seal strength",
            "package integrity",
            "peel test",
            "sterile packaging",
            "Tyvek",
        ],
        detection_keywords_zh=[
            "無菌屏障",
            "11607",
            "包裝確效",
            "密封強度",
            "包裝完整性",
            "剥離測試",
            "無菌包裝",
            "Tyvek",
        ],
        primary_iso_clauses=["7.5.1", "7.5.5", "7.5.11"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Part 2: Validation of forming, sealing, assembly processes",
                iso_13485_clause="7.5.5",
                relationship="implements",
                description_en="ISO 11607-2 validates sterile packaging processes per ISO 13485 7.5.5 sterile device requirements.",
                description_zh="ISO 11607-2 依 ISO 13485 7.5.5 無菌裝置要求驗證無菌包裝過程。",
            ),
            StandardClauseLink(
                standard_clause="Part 1: Materials, sterile barrier systems",
                iso_13485_clause="7.5.11",
                relationship="supplements",
                description_en="Packaging materials and design requirements supplement product preservation (ISO 13485 7.5.11).",
                description_zh="包裝材料與設計要求補充產品防護（ISO 13485 7.5.11）。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard for sterile barrier packaging",
            "EU": "Harmonized standard under EU MDR",
            "TW": "TFDA 無菌包裝確效必要標準",
        },
    )

    # ---- ISO 14708: Active Implantable Medical Devices ----
    standards["ISO_14708"] = SupplementalStandardProfile(
        standard_id="ISO_14708",
        name_en="ISO 14708 series — Implants for surgery — Active implantable medical devices",
        name_zh="ISO 14708 系列 — 手術植入物 — 主動式植入醫療器材",
        category=StandardCategory.IMPLANTABLE,
        version="2014 (Part 1)",
        detection_keywords_en=[
            "implantable",
            "implant",
            "14708",
            "active implant",
            "pacemaker",
            "cochlear",
            "neurostimulator",
            "cardiac",
        ],
        detection_keywords_zh=[
            "植入式",
            "植入物",
            "14708",
            "主動植入",
            "心律調整器",
            "人工耳蜘",
            "神經刺激器",
        ],
        primary_iso_clauses=["7.3.3", "7.3.6", "7.5.9", "7.5.9.1"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Product-specific safety and performance requirements",
                iso_13485_clause="7.3.3",
                relationship="supplements",
                description_en="ISO 14708 adds implant-specific design input requirements beyond ISO 13485 7.3.3.",
                description_zh="ISO 14708 在 ISO 13485 7.3.3 之外增加植入物特定的設計輸入要求。",
            ),
            StandardClauseLink(
                standard_clause="Implant-specific testing (biocompatibility, fatigue, EMC)",
                iso_13485_clause="7.3.6",
                relationship="verifies",
                description_en="ISO 14708 testing requirements provide design verification evidence for active implants.",
                description_zh="ISO 14708 測試要求提供主動植入物的設計驗證證據。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized; specific product guidance documents apply",
            "EU": "Harmonized standard under EU MDR; previously under AIMDD 90/385/EEC",
            "TW": "TFDA 植入式器材查驗登記參考標準",
        },
    )

    # ---- ISO 15223-1: Symbols for Medical Device Labeling ----
    standards["ISO_15223"] = SupplementalStandardProfile(
        standard_id="ISO_15223",
        name_en="ISO 15223-1:2021 Medical devices — Symbols to be used with information to be supplied by the manufacturer",
        name_zh="ISO 15223-1:2021 醫療器材 — 製造商提供資訊所用的符號",
        category=StandardCategory.LABELING,
        version="2021",
        detection_keywords_en=[
            "15223",
            "labeling symbols",
            "medical device symbols",
            "graphical symbols",
            "label symbols",
        ],
        detection_keywords_zh=[
            "15223",
            "標示符號",
            "醫療器材符號",
            "圖形符號",
            "標籤符號",
        ],
        primary_iso_clauses=["7.5.1", "7.5.8"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Standardized symbols for labeling",
                iso_13485_clause="7.5.8",
                relationship="supplements",
                description_en="ISO 15223-1 provides standardized symbols that support device identification and labeling per ISO 13485 7.5.8.",
                description_zh="ISO 15223-1 提供標準化符號，支援 ISO 13485 7.5.8 器材識別與標示。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized consensus standard for device labeling symbols",
            "EU": "Harmonized standard under EU MDR; required for CE marking labels",
            "TW": "TFDA 醫療器材標示參考標準",
        },
    )

    # ---- ISO 14155: Clinical Investigation ----
    standards["ISO_14155"] = SupplementalStandardProfile(
        standard_id="ISO_14155",
        name_en="ISO 14155:2020 Clinical investigation of medical devices for human subjects — Good clinical practice",
        name_zh="ISO 14155:2020 醫療器材人體臨床試驗 — 優良臨床規範",
        category=StandardCategory.CLINICAL,
        version="2020",
        detection_keywords_en=[
            "clinical investigation",
            "clinical trial",
            "14155",
            "GCP",
            "good clinical practice",
            "clinical study",
            "informed consent",
            "clinical evidence",
        ],
        detection_keywords_zh=[
            "臨床試驗",
            "臨床調查",
            "14155",
            "GCP",
            "優良臨床規範",
            "臨床研究",
            "知情同意",
            "臨床證據",
        ],
        primary_iso_clauses=["7.3.6", "7.3.7"],
        clause_links=[
            StandardClauseLink(
                standard_clause="Clinical investigation planning and conduct",
                iso_13485_clause="7.3.6",
                relationship="implements",
                description_en="ISO 14155 defines how to conduct clinical investigations that provide design validation evidence per ISO 13485 7.3.6.",
                description_zh="ISO 14155 定義如何執行臨床試驗，提供 ISO 13485 7.3.6 設計確認證據。",
            ),
        ],
        regulatory_references={
            "US": "FDA recognized; aligns with 21 CFR 812 (IDE regulations)",
            "EU": "Harmonized standard under EU MDR; required for clinical investigations per Art 62-82",
            "TW": "TFDA 醫療器材臨床試驗參考標準",
        },
    )

    return standards


PREDEFINED_STANDARDS: dict[str, SupplementalStandardProfile] = (
    _build_predefined_standards()
)


def get_standard(standard_id: str) -> Optional[SupplementalStandardProfile]:
    """Get a supplemental standard profile by ID.

    Args:
        standard_id: e.g., 'ISO_14971', 'IEC_62304'
    """
    return PREDEFINED_STANDARDS.get(standard_id)


def get_all_standards() -> dict[str, SupplementalStandardProfile]:
    """Return all available supplemental standard profiles."""
    return dict(PREDEFINED_STANDARDS)


def adjust_standard_clause_mapping(
    standard_id: str,
    standard_clause: str,
    old_iso_clause: str,
    new_iso_clause: str,
) -> dict:
    """Adjust a supplemental standard's clause-to-ISO-13485 mapping.

    Used when a user decides that a standard clause should map to a different
    ISO 13485 clause than the default. For example, moving ISO 14971 Clause 4
    from ISO 13485 Clause 7.1 to 7.3.3.

    This modifies the in-memory PREDEFINED_STANDARDS dict. The change persists
    for the duration of the server session.

    Args:
        standard_id: e.g., 'ISO_14971'
        standard_clause: The standard's clause to remap, e.g., 'ISO 14971 Clause 4'
        old_iso_clause: Current ISO 13485 clause (for verification)
        new_iso_clause: New ISO 13485 clause to map to

    Returns:
        dict with 'success', 'message', and optionally 'adjusted_link' details
    """
    std = PREDEFINED_STANDARDS.get(standard_id)
    if std is None:
        return {
            "success": False,
            "message": f"Standard '{standard_id}' not found.",
        }

    # Find the clause link to adjust
    target_link: Optional[StandardClauseLink] = None
    for cl in std.clause_links:
        if cl.standard_clause == standard_clause:
            target_link = cl
            break

    if target_link is None:
        return {
            "success": False,
            "message": (
                f"Clause link '{standard_clause}' not found in {standard_id}. "
                f"Available: {[cl.standard_clause for cl in std.clause_links]}"
            ),
        }

    # Verify the old clause matches (safety check)
    if old_iso_clause and target_link.iso_13485_clause != old_iso_clause:
        return {
            "success": False,
            "message": (
                f"Current mapping is '{target_link.iso_13485_clause}', "
                f"not '{old_iso_clause}' as specified. Aborting to prevent conflicts."
            ),
        }

    # Verify new_iso_clause is a valid ISO 13485 clause
    valid_clauses = list_clauses("ISO_13485")
    if new_iso_clause not in valid_clauses:
        return {
            "success": False,
            "message": (
                f"'{new_iso_clause}' is not a valid ISO 13485 clause. "
                f"Valid clauses: {valid_clauses[:10]}... ({len(valid_clauses)} total)"
            ),
        }

    # Apply the adjustment
    old_value = target_link.iso_13485_clause
    target_link.iso_13485_clause = new_iso_clause

    # Update primary_iso_clauses if the old clause was listed there
    if old_value in std.primary_iso_clauses:
        idx = std.primary_iso_clauses.index(old_value)
        std.primary_iso_clauses[idx] = new_iso_clause

    return {
        "success": True,
        "message": (
            f"Adjusted {standard_id}: '{standard_clause}' mapping changed "
            f"from ISO 13485 Clause {old_value} to {new_iso_clause}."
        ),
        "adjusted_link": {
            "standard_id": standard_id,
            "standard_clause": standard_clause,
            "old_iso_clause": old_value,
            "new_iso_clause": new_iso_clause,
        },
    }


def get_applicable_standards(
    product_profile: ProductProfile,
) -> list[SupplementalStandardProfile]:
    """Determine which supplemental standards apply based on product profile.

    Logic:
      1. Universal standards (e.g., ISO 14971) always apply
      2. User-confirmed standards always apply
      3. User-rejected standards never apply
      4. Otherwise: match detection keywords against product characteristics

    Args:
        product_profile: Product characteristics from multi-source detection

    Returns:
        List of applicable SupplementalStandardProfile, sorted by category
    """
    applicable: list[SupplementalStandardProfile] = []

    for std in PREDEFINED_STANDARDS.values():
        # User explicit overrides
        if std.standard_id in product_profile.user_rejected_standards:
            continue
        if std.standard_id in product_profile.user_confirmed_standards:
            applicable.append(std)
            continue

        # Universal standards always apply
        if std.is_universal:
            applicable.append(std)
            continue

        # Check uploaded files (most reliable signal)
        for uploaded_file in product_profile.uploaded_standard_files:
            uploaded_lower = uploaded_file.lower()
            if std.standard_id.lower().replace("_", " ") in uploaded_lower:
                applicable.append(std)
                break
            # Check by standard number (e.g., "14971" in filename)
            std_num = std.standard_id.split("_")[-1]
            if std_num in uploaded_lower:
                applicable.append(std)
                break
        else:
            # Check detected standard references from documents
            for ref in product_profile.detected_standard_refs:
                ref_lower = ref.lower()
                std_num = std.standard_id.split("_")[-1]
                if std_num in ref_lower:
                    applicable.append(std)
                    break
            else:
                # Check product characteristics against keywords
                _check_product_keywords(std, product_profile, applicable)

    # Sort by category for display consistency
    applicable.sort(key=lambda s: s.category.value)
    return applicable


def _check_product_keywords(
    std: SupplementalStandardProfile,
    profile: ProductProfile,
    applicable: list[SupplementalStandardProfile],
) -> None:
    """Check if product characteristics match standard's trigger keywords."""
    # Map categories to product profile fields
    category_checks: dict[StandardCategory, tuple[bool, float, str]] = {
        StandardCategory.SOFTWARE: profile.has_software,
        StandardCategory.ELECTRICAL_SAFETY: profile.has_electrical,
        StandardCategory.EMC: profile.has_electrical,  # EMC applies to all electrical
        StandardCategory.IMPLANTABLE: profile.is_implantable,
        StandardCategory.BIOCOMPATIBILITY: profile.has_biological_contact,
        StandardCategory.CLINICAL: profile.has_clinical_investigation,
    }

    # Direct category match
    if std.category in category_checks:
        value, confidence, _source = category_checks[std.category]
        if value and confidence > 0.3:
            applicable.append(std)
            return

    # Sterilization: check both is_sterile and sterilization_method
    if std.category == StandardCategory.STERILIZATION:
        is_sterile, confidence, _source = profile.is_sterile
        if is_sterile and confidence > 0.3:
            # Match specific sterilization method to standard
            method = profile.sterilization_method.lower()
            if std.standard_id == "ISO_11135" and method in (
                "eo",
                "ethylene oxide",
                "",
            ):
                applicable.append(std)
            elif std.standard_id == "ISO_11137" and method in (
                "radiation",
                "gamma",
                "electron beam",
                "",
            ):
                applicable.append(std)
            elif std.standard_id == "ISO_17665" and method in (
                "steam",
                "moist heat",
                "autoclave",
                "",
            ):
                applicable.append(std)
            elif method == "":  # Unknown method, include all sterilization standards
                applicable.append(std)
            return

    # Packaging: applies if product is sterile
    if std.category == StandardCategory.PACKAGING:
        is_sterile, confidence, _source = profile.is_sterile
        if is_sterile and confidence > 0.3:
            applicable.append(std)
            return


# ============================================================
# Layer 3: Cross-Examination Question Generator
# ============================================================


def get_regulation(regulation_id: str) -> Optional[RegulationProfile]:
    """Get a regulation profile by ID (predefined or crawled).

    Args:
        regulation_id: e.g., "QMSR", "EU_MDR", "TFDA"

    Returns:
        RegulationProfile or None if not found
    """
    return PREDEFINED_REGULATIONS.get(regulation_id)


def get_all_regulations() -> dict[str, RegulationProfile]:
    """Return all available regulation profiles (predefined + loaded crawled)."""
    return dict(PREDEFINED_REGULATIONS)


def get_overlap_analysis(
    regulation_id: str,
    iso_clause: str,
) -> dict:
    """Analyze how a specific regulation covers an ISO 13485 clause.

    Returns a dict with:
      - status: full/partial/na/exceeds
      - is_overlap: True if regulation covers this clause
      - is_delta: True if regulation has unique requirements for this clause
      - delta_items: list of UniqueRequirement that relate to this clause
      - mapping: the ClauseMapping if exists
      - rationale: why this determination was made

    This is the core function for the HTML cross-reference table.
    """
    reg = get_regulation(regulation_id)
    if reg is None:
        return {"error": f"Regulation {regulation_id!r} not found"}

    result: dict = {
        "regulation_id": regulation_id,
        "regulation_name": reg.name_zh,
        "iso_clause": iso_clause,
        "status": "not_mapped",
        "is_overlap": False,
        "is_delta": False,
        "mapping": None,
        "delta_items": [],
    }

    # Check if this clause is mapped
    mapping = reg.iso_mapped.get(iso_clause)
    if mapping:
        result["status"] = mapping.status.value
        result["is_overlap"] = mapping.status in (
            MappingStatus.FULL,
            MappingStatus.PARTIAL,
            MappingStatus.EXCEEDS,
        )
        result["mapping"] = {
            "regulation_ref": mapping.regulation_ref,
            "rationale_en": mapping.rationale_en,
            "rationale_zh": mapping.rationale_zh,
            "method": mapping.method.value,
            "confidence": mapping.confidence,
            "notes": mapping.notes,
            "original_text": mapping.original_text,
            "original_lang": mapping.original_lang,
            "english_translation": mapping.english_translation,
            "semantic_note": mapping.semantic_note,
            "within_clause_deltas": [
                {
                    "delta_id": d.delta_id,
                    "title_en": d.title_en,
                    "title_zh": d.title_zh,
                    "title_ja": d.title_ja,
                    "iso_baseline_en": d.iso_baseline_en,
                    "iso_baseline_zh": d.iso_baseline_zh,
                    "iso_baseline_ja": d.iso_baseline_ja,
                    "country_specific_en": d.country_specific_en,
                    "country_specific_zh": d.country_specific_zh,
                    "country_specific_ja": d.country_specific_ja,
                    "delta_type": d.delta_type,
                    "audit_impact": d.audit_impact,
                    "regulation_ref": d.regulation_ref,
                    "expected_evidence": d.expected_evidence,
                    "confidence": d.confidence,
                }
                for d in mapping.within_clause_deltas
            ],
        }

    # Check if there are delta items that relate to this clause
    for req in reg.unique_requirements:
        if iso_clause in req.related_iso_clauses:
            result["is_delta"] = True
            result["delta_items"].append(
                {
                    "req_id": req.req_id,
                    "title_en": req.title_en,
                    "title_zh": req.title_zh,
                    "regulation_ref": req.regulation_ref,
                    "audit_impact": req.audit_impact,
                    "audit_question_zh": req.audit_question_zh,
                    "rationale_en": req.rationale_en,
                    "rationale_zh": req.rationale_zh,
                    "method": req.method.value,
                    "confidence": req.confidence,
                    "original_text": req.original_text,
                    "original_lang": req.original_lang,
                    "english_translation": req.english_translation,
                    "semantic_note": req.semantic_note,
                }
            )

    return result


def generate_cross_exam_questions(
    doc_id: str,
    doc_title: str,
    baseline_clause: str,
    selected_regulations: list[str],
    doc_content_summary: str = "",
) -> list[dict]:
    """Generate tailored cross-examination questions for a specific quality document.

    This is the CORE function that connects the cross-reference table to the
    cross-examination engine. Given a document and its baseline clause,
    it produces a prioritized list of questions:

      Priority 1 (HIGHEST): Delta items — country-unique requirements
                             Most likely to be non-compliant
      Priority 2: Exceeds items — regulation exceeds ISO 13485
                  Likely compliant but may have gaps
      Priority 3: Overlap items — regulation aligns with ISO 13485
                  Should be compliant, verification questions

    Args:
        doc_id: Quality document ID (e.g., 'QP-852')
        doc_title: Document title
        baseline_clause: ISO 13485 clause this document primarily covers (e.g., '8.5.2')
        selected_regulations: List of regulation IDs user selected (e.g., ['QMSR', 'EU_MDR', 'TFDA'])
        doc_content_summary: Optional brief summary of document content for context

    Returns:
        List of question dicts, sorted by priority (delta first)
        Each dict:
        {
            'priority': 1|2|3,
            'regulation_id': str,
            'regulation_name': str,
            'question_type': 'delta'|'exceeds'|'overlap',
            'iso_clause': str,
            'question_zh': str,
            'question_en': str,
            'expected_evidence': list[str],
            'audit_impact': str,
            'rationale_zh': str,
            'rationale_en': str,
            'method': str,
            'confidence': float,
        }
    """
    questions: list[dict] = []

    for reg_id in selected_regulations:
        reg = get_regulation(reg_id)
        if reg is None:
            continue

        # Priority 1: Delta items (country-unique requirements for this clause)
        for req in reg.unique_requirements:
            if baseline_clause in req.related_iso_clauses:
                questions.append(
                    {
                        "priority": 1,
                        "regulation_id": reg_id,
                        "regulation_name": reg.name_zh,
                        "country": reg.country_name_zh,
                        "question_type": "delta",
                        "iso_clause": baseline_clause,
                        "req_id": req.req_id,
                        "title_zh": req.title_zh,
                        "title_en": req.title_en,
                        "question_zh": req.audit_question_zh,
                        "question_en": req.audit_question_en,
                        "expected_evidence": req.expected_evidence,
                        "audit_impact": req.audit_impact,
                        "rationale_zh": req.rationale_zh,
                        "rationale_en": req.rationale_en,
                        "method": req.method.value,
                        "confidence": req.confidence,
                    }
                )

        # Priority 2 & 3: Mapped clauses (exceeds vs full overlap)
        mapping = reg.iso_mapped.get(baseline_clause)
        if mapping:
            is_exceeds = mapping.status == MappingStatus.EXCEEDS
            iso_clause_info = ISO_13485_CHECKLIST.get(baseline_clause, {})
            questions.append(
                {
                    "priority": 2 if is_exceeds else 3,
                    "regulation_id": reg_id,
                    "regulation_name": reg.name_zh,
                    "country": reg.country_name_zh,
                    "question_type": "exceeds" if is_exceeds else "overlap",
                    "iso_clause": baseline_clause,
                    "req_id": f"{reg_id}-MAP-{baseline_clause}",
                    "title_zh": f"{reg.country_name_zh}法規對應 — {iso_clause_info.get('title', baseline_clause)}",
                    "title_en": f"{reg.country_name_en} regulation mapping — {iso_clause_info.get('title', baseline_clause)}",
                    "question_zh": iso_clause_info.get(
                        "audit_question",
                        f"品質文件是否符合 {reg.name_zh} 對 ISO 13485 條款 {baseline_clause} 的要求？",
                    ),
                    "question_en": f"Does the quality document comply with {reg.name_en} requirements for ISO 13485 Clause {baseline_clause}?",
                    "expected_evidence": iso_clause_info.get("expected_evidence", []),
                    "audit_impact": iso_clause_info.get("audit_impact", "major"),
                    "rationale_zh": mapping.rationale_zh,
                    "rationale_en": mapping.rationale_en,
                    "method": mapping.method.value,
                    "confidence": mapping.confidence,
                }
            )

    # Sort: priority 1 (delta) first, then 2 (exceeds), then 3 (overlap)
    # Within same priority, sort by audit_impact severity
    impact_order = {"critical": 0, "major": 1, "minor": 2}
    questions.sort(
        key=lambda q: (q["priority"], impact_order.get(q["audit_impact"], 9))
    )

    return questions


# ============================================================
# Crawled Regulation Persistence (JSON save/load)
# ============================================================

CRAWLED_REGULATIONS_DIR = os.path.join("data", "regulations")


def save_crawled_regulation(profile: RegulationProfile) -> str:
    """Save a crawled regulation profile to JSON file.

    Returns the file path.
    """
    os.makedirs(CRAWLED_REGULATIONS_DIR, exist_ok=True)
    filepath = os.path.join(CRAWLED_REGULATIONS_DIR, f"{profile.regulation_id}.json")

    data = {
        "regulation_id": profile.regulation_id,
        "name_en": profile.name_en,
        "name_zh": profile.name_zh,
        "country": profile.country,
        "country_name_en": profile.country_name_en,
        "country_name_zh": profile.country_name_zh,
        "source": profile.source,
        "source_url": profile.source_url,
        "last_updated": profile.last_updated,
        "effective_date": profile.effective_date,
        "iso_mapped": {
            clause_id: {
                "iso_clause": m.iso_clause,
                "status": m.status.value,
                "regulation_ref": m.regulation_ref,
                "rationale_en": m.rationale_en,
                "rationale_zh": m.rationale_zh,
                "method": m.method.value,
                "confidence": m.confidence,
                "notes": m.notes,
                "original_text": m.original_text,
                "original_lang": m.original_lang,
                "english_translation": m.english_translation,
                "semantic_note": m.semantic_note,
                "within_clause_deltas": [
                    {
                        "delta_id": d.delta_id,
                        "iso_clause": d.iso_clause,
                        "title_en": d.title_en,
                        "title_zh": d.title_zh,
                        "title_ja": d.title_ja,
                        "iso_baseline_en": d.iso_baseline_en,
                        "iso_baseline_zh": d.iso_baseline_zh,
                        "iso_baseline_ja": d.iso_baseline_ja,
                        "country_specific_en": d.country_specific_en,
                        "country_specific_zh": d.country_specific_zh,
                        "country_specific_ja": d.country_specific_ja,
                        "regulation_ref": d.regulation_ref,
                        "original_text": d.original_text,
                        "original_lang": d.original_lang,
                        "english_translation": d.english_translation,
                        "delta_type": d.delta_type,
                        "audit_impact": d.audit_impact,
                        "expected_evidence": d.expected_evidence,
                        "confidence": d.confidence,
                    }
                    for d in m.within_clause_deltas
                ],
            }
            for clause_id, m in profile.iso_mapped.items()
        },
        "unique_requirements": [
            {
                "req_id": r.req_id,
                "regulation_ref": r.regulation_ref,
                "title_en": r.title_en,
                "title_zh": r.title_zh,
                "requirement_en": r.requirement_en,
                "requirement_zh": r.requirement_zh,
                "related_iso_clauses": r.related_iso_clauses,
                "audit_impact": r.audit_impact,
                "audit_question_en": r.audit_question_en,
                "audit_question_zh": r.audit_question_zh,
                "expected_evidence": r.expected_evidence,
                "rationale_en": r.rationale_en,
                "rationale_zh": r.rationale_zh,
                "method": r.method.value,
                "confidence": r.confidence,
                "original_text": r.original_text,
                "original_lang": r.original_lang,
                "english_translation": r.english_translation,
                "semantic_note": r.semantic_note,
                "is_within_clause_delta": r.is_within_clause_delta,
                "within_clause_delta_vs_iso": r.within_clause_delta_vs_iso,
            }
            for r in profile.unique_requirements
        ],
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Also register in memory
    PREDEFINED_REGULATIONS[profile.regulation_id] = profile
    return filepath


def load_crawled_regulation(filepath: str) -> RegulationProfile:
    """Load a crawled regulation profile from JSON file.

    Returns RegulationProfile and also registers it in memory.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    iso_mapped = {}
    for clause_id, m in data.get("iso_mapped", {}).items():
        iso_mapped[clause_id] = ClauseMapping(
            iso_clause=m["iso_clause"],
            status=MappingStatus(m["status"]),
            regulation_ref=m["regulation_ref"],
            rationale_en=m["rationale_en"],
            rationale_zh=m["rationale_zh"],
            method=MappingMethod(m["method"]),
            confidence=m["confidence"],
            notes=m.get("notes", ""),
            original_text=m.get("original_text", ""),
            original_lang=m.get("original_lang", ""),
            english_translation=m.get("english_translation", ""),
            semantic_note=m.get("semantic_note", ""),
            within_clause_deltas=[
                WithinClauseDelta(
                    delta_id=d.get("delta_id", ""),
                    iso_clause=d.get("iso_clause", ""),
                    title_en=d.get("title_en", ""),
                    title_zh=d.get("title_zh", ""),
                    title_ja=d.get("title_ja", ""),
                    iso_baseline_en=d.get("iso_baseline_en", ""),
                    iso_baseline_zh=d.get("iso_baseline_zh", ""),
                    iso_baseline_ja=d.get("iso_baseline_ja", ""),
                    country_specific_en=d.get("country_specific_en", ""),
                    country_specific_zh=d.get("country_specific_zh", ""),
                    country_specific_ja=d.get("country_specific_ja", ""),
                    regulation_ref=d.get("regulation_ref", ""),
                    original_text=d.get("original_text", ""),
                    original_lang=d.get("original_lang", ""),
                    english_translation=d.get("english_translation", ""),
                    delta_type=d.get("delta_type", "other"),
                    audit_impact=d.get("audit_impact", "major"),
                    expected_evidence=d.get("expected_evidence", []),
                    confidence=d.get("confidence", 0.5),
                )
                for d in m.get("within_clause_deltas", [])
            ],
        )

    unique_reqs = []
    for r in data.get("unique_requirements", []):
        unique_reqs.append(
            UniqueRequirement(
                req_id=r["req_id"],
                regulation_ref=r["regulation_ref"],
                title_en=r["title_en"],
                title_zh=r["title_zh"],
                requirement_en=r["requirement_en"],
                requirement_zh=r["requirement_zh"],
                related_iso_clauses=r["related_iso_clauses"],
                audit_impact=r["audit_impact"],
                audit_question_en=r["audit_question_en"],
                audit_question_zh=r["audit_question_zh"],
                expected_evidence=r["expected_evidence"],
                rationale_en=r["rationale_en"],
                rationale_zh=r["rationale_zh"],
                method=MappingMethod(r["method"]),
                confidence=r["confidence"],
                original_text=r.get("original_text", ""),
                original_lang=r.get("original_lang", ""),
                english_translation=r.get("english_translation", ""),
                semantic_note=r.get("semantic_note", ""),
                is_within_clause_delta=r.get("is_within_clause_delta", False),
                within_clause_delta_vs_iso=r.get("within_clause_delta_vs_iso", ""),
            )
        )

    profile = RegulationProfile(
        regulation_id=data["regulation_id"],
        name_en=data["name_en"],
        name_zh=data["name_zh"],
        country=data["country"],
        country_name_en=data["country_name_en"],
        country_name_zh=data["country_name_zh"],
        source=data.get("source", "crawled"),
        source_url=data.get("source_url", ""),
        last_updated=data.get("last_updated", ""),
        effective_date=data.get("effective_date", ""),
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )

    # Register in memory
    PREDEFINED_REGULATIONS[profile.regulation_id] = profile
    return profile


def load_all_crawled_regulations() -> int:
    """Load all crawled regulation profiles from the data directory.

    Returns the number of profiles loaded.
    """
    count = 0
    if not os.path.isdir(CRAWLED_REGULATIONS_DIR):
        return count
    for filename in os.listdir(CRAWLED_REGULATIONS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(CRAWLED_REGULATIONS_DIR, filename)
            try:
                load_crawled_regulation(filepath)
                count += 1
            except Exception:
                pass  # Skip malformed files
    return count


def cleanup_non_selected_crawled_profiles(selected_regions: list[str]) -> dict:
    """Remove crawled regulation profiles that are NOT in the selected regions.

    Predefined 7-country profiles are NEVER deleted.
    Only crawled profiles (stored as JSON in data/regulations/) are affected.

    Args:
        selected_regions: List of region names the user selected,
            e.g., ["中國 (China)", "韓國 (South Korea)"]

    Returns:
        dict with deleted_count, deleted_ids, kept_ids
    """
    predefined_ids = set(_REGION_TO_PROFILE_STATIC.values())

    selected_profile_ids = set()
    for region in selected_regions:
        pid = get_profile_id_for_region(region)
        if pid:
            selected_profile_ids.add(pid)

    deleted_ids = []
    kept_ids = []

    if not os.path.isdir(CRAWLED_REGULATIONS_DIR):
        return {"deleted_count": 0, "deleted_ids": [], "kept_ids": []}

    for filename in os.listdir(CRAWLED_REGULATIONS_DIR):
        if not filename.endswith(".json"):
            continue
        profile_id = filename.replace(".json", "")
        if profile_id in predefined_ids:
            kept_ids.append(profile_id)
            continue
        if profile_id in selected_profile_ids:
            kept_ids.append(profile_id)
            continue
        filepath = os.path.join(CRAWLED_REGULATIONS_DIR, filename)
        try:
            os.remove(filepath)
        except OSError:
            continue
        if profile_id in PREDEFINED_REGULATIONS:
            del PREDEFINED_REGULATIONS[profile_id]
        deleted_ids.append(profile_id)

    return {
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "kept_ids": kept_ids,
    }


def map_unique_to_iso_clause(
    requirement_text: str,
    language: str = "auto",
) -> list[str]:
    """Determine which ISO 13485 clause(s) a unique requirement relates to.

    For predefined regulations, this is already done manually.
    For crawled regulations, this function provides keyword-based initial mapping.
    The LLM can refine this during cross-examination.

    Args:
        requirement_text: The requirement text to classify
        language: 'en', 'zh', or 'auto' (detect from content)

    Returns:
        List of ISO 13485 clause IDs that this requirement most likely relates to
    """
    # Keyword-based mapping (fallback for non-LLM classification)
    keyword_map: dict[str, list[str]] = {
        # Document/record keywords
        "document control": ["4.2.3"],
        "文件管制": ["4.2.3"],
        "record": ["4.2.4", "4.2.5"],
        "記錄": ["4.2.4", "4.2.5"],
        "retention": ["4.2.4", "4.2.5"],
        "保存": ["4.2.4", "4.2.5"],
        # Management keywords
        "management review": ["5.6.1"],
        "管理審查": ["5.6.1"],
        "management representative": ["5.5.2"],
        "管理代表": ["5.5.2"],
        "responsibility": ["5.5.1"],
        "責任": ["5.5.1"],
        # Resource keywords
        "training": ["6.2"],
        "訓練": ["6.2"],
        "personnel": ["6.2"],
        "人員": ["6.2"],
        "infrastructure": ["6.3"],
        "設施": ["6.3"],
        # Design keywords
        "design": ["7.3.1"],
        "設計": ["7.3.1"],
        "clinical evaluation": ["7.3.6"],
        "臨床評估": ["7.3.6"],
        "validation": ["7.3.6"],
        "確認": ["7.3.6"],
        "verification": ["7.3.5"],
        "驗證": ["7.3.5"],
        # Production keywords
        "labeling": ["7.5.1", "7.5.8"],
        "標示": ["7.5.1", "7.5.8"],
        "標籤": ["7.5.1", "7.5.8"],
        "traceability": ["7.5.9"],
        "追溯": ["7.5.9"],
        "UDI": ["7.5.9.2"],
        "sterilization": ["7.5.7"],
        "滅菌": ["7.5.7"],
        "purchasing": ["7.4.1"],
        "採購": ["7.4.1"],
        "supplier": ["7.4.1"],
        "供應商": ["7.4.1"],
        # Monitoring/improvement keywords
        "complaint": ["8.2.2"],
        "客訴": ["8.2.2"],
        "抱怨": ["8.2.2"],
        "adverse event": ["8.2.3"],
        "不良事件": ["8.2.3"],
        "vigilance": ["8.2.3"],
        "警戒": ["8.2.3"],
        "reporting": ["8.2.3"],
        "通報": ["8.2.3"],
        "audit": ["8.2.4"],
        "稽核": ["8.2.4"],
        "CAPA": ["8.5.2"],
        "矯正": ["8.5.2"],
        "corrective": ["8.5.2"],
        "preventive": ["8.5.3"],
        "預防": ["8.5.3"],
        "nonconform": ["8.3"],
        "不合格": ["8.3"],
        "risk management": ["7.1"],
        "風險管理": ["7.1"],
        "post-market": ["8.2.1"],
        "上市後": ["8.2.1"],
    }

    text_lower = requirement_text.lower()
    matched_clauses: set[str] = set()

    for keyword, clauses in keyword_map.items():
        if keyword.lower() in text_lower:
            matched_clauses.update(clauses)

    if not matched_clauses:
        # Default: return general QMS clause
        return ["4.1"]

    # Sort by clause number
    return sorted(
        matched_clauses,
        key=lambda x: [int(n) for n in x.split(".")],
    )


# ============================================================
# Auto-load crawled regulation profiles at import time
# ============================================================
# Must be at END of file because load_all_crawled_regulations()
# is defined after _init_predefined() and the mapping helpers.
try:
    _loaded_crawled = load_all_crawled_regulations()
    if _loaded_crawled > 0:
        import logging as _logging

        _logging.getLogger(__name__).info(
            f"Loaded {_loaded_crawled} crawled regulation profile(s) from disk"
        )
except Exception:
    pass  # Non-critical — predefined profiles still available
