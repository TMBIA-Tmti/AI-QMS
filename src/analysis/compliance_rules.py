"""
AI-QMS — Compliance Rules (Audit Checklists)
=============================================

Predefined audit checklists for regulatory standards.
Each clause = one audit question + expected evidence list.

LLM's job is to:
  1. Search company documents for each expected_evidence item
  2. Found → quote the source text
  3. Not found → flag as gap

The audit_impact level determines risk severity when combined
with gap_severity in risk_matrix.py.

Currently supported standards:
  - ISO 13485:2016 (Medical devices — Quality management systems)
"""

from typing import Optional

__all__ = [
    "ISO_13485_CHECKLIST",
    "get_checklist",
    "get_clause",
    "list_clauses",
    "SUPPORTED_STANDARDS",
]


# ============================================================
# ISO 13485:2016 — Complete Audit Checklist
# ============================================================

ISO_13485_CHECKLIST: dict[str, dict] = {
    # --------------------------------------------------------
    # Section 4: 品質管理系統
    # --------------------------------------------------------
    "4.1": {
        "title": "品質管理系統 — 一般要求",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立、文件化、實施及維持品質管理系統，並維持其有效性？"
            "是否鑑別品質管理系統所需的過程及其在整個組織的應用？"
            "是否對外包過程實施管制？"
        ),
        "expected_evidence": [
            "品質手冊",
            "品質管理系統過程圖或過程清單",
            "外包過程管制紀錄（如適用）",
        ],
    },
    "4.2.1": {
        "title": "文件化要求 — 一般",
        "audit_impact": "major",
        "audit_question": (
            "品質管理系統文件是否包含品質政策與品質目標的聲明、品質手冊、"
            "本國際標準所要求的程序與紀錄、以及組織確定為確保過程有效策劃、"
            "運作及管制所需的文件？"
        ),
        "expected_evidence": [
            "品質政策聲明",
            "品質目標",
            "品質手冊",
            "程序書清單",
        ],
    },
    "4.2.2": {
        "title": "品質手冊",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立並維持品質手冊，包含品質管理系統的範圍（含排除的理由）、"
            "文件化程序或其引用、以及品質管理系統過程之間的交互作用描述？"
        ),
        "expected_evidence": [
            "品質手冊",
            "品質管理系統範圍說明",
            "排除條款理由說明（如適用）",
            "過程交互作用描述",
        ],
    },
    "4.2.3": {
        "title": "文件管制",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立文件管制程序，涵蓋審查、核准、發行、變更、"
            "版本識別、外來文件管制及作廢文件管制？"
        ),
        "expected_evidence": [
            "文件管制程序書",
            "文件發行/變更紀錄",
            "文件清單 (Master List)",
        ],
    },
    "4.2.4": {
        "title": "紀錄管制",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立紀錄管制程序，確保紀錄的識別、儲存、保護、"
            "檢索、保存期限及處置？"
        ),
        "expected_evidence": [
            "紀錄管制程序書",
            "紀錄保存期限清單",
        ],
    },
    "4.2.5": {
        "title": "醫療器材檔案",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否為每一醫療器材類型或醫療器材族建立並維持醫療器材檔案，"
            "包含或引用產生的文件以展示符合本標準要求及適用法規要求？"
        ),
        "expected_evidence": [
            "醫療器材檔案 (Device Master Record / Technical File)",
            "產品規格書",
            "適用法規要求清單",
        ],
    },
    # --------------------------------------------------------
    # Section 5: 管理責任
    # --------------------------------------------------------
    "5.1": {
        "title": "管理階層承諾",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否提供其對品質管理系統之開發與實施、"
            "以及維持其有效性之承諾的證據？"
        ),
        "expected_evidence": [
            "品質政策聲明",
            "管理審查會議紀錄",
            "資源配置紀錄",
        ],
    },
    "5.2": {
        "title": "以顧客為重",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保顧客要求與適用法規要求已被確定並予以滿足？"
        ),
        "expected_evidence": [
            "顧客要求確認紀錄",
            "顧客滿意度調查（如適用）",
            "適用法規要求清單",
        ],
    },
    "5.3": {
        "title": "品質政策",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保品質政策適合組織的目的、包含對滿足要求及維持"
            "品質管理系統有效性的承諾、提供建立及審查品質目標的架構、"
            "在組織內被溝通與理解、並被審查以持續適切？"
        ),
        "expected_evidence": [
            "品質政策文件",
            "品質政策溝通紀錄",
        ],
    },
    "5.4.1": {
        "title": "品質目標",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保在組織內相關職能與層級建立品質目標？"
            "品質目標是否可量測且與品質政策一致？"
        ),
        "expected_evidence": [
            "品質目標清單",
            "品質目標達成率追蹤紀錄",
        ],
    },
    "5.4.2": {
        "title": "品質管理系統規劃",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保品質管理系統的規劃已執行以滿足一般要求及品質目標？"
            "當規劃和實施品質管理系統的變更時，是否維持其完整性？"
        ),
        "expected_evidence": [
            "品質管理系統規劃文件",
            "變更管理紀錄",
        ],
    },
    "5.5.1": {
        "title": "責任與權限",
        "audit_impact": "major",
        "audit_question": (
            "最高管理階層是否確保組織內的責任與權限已被界定、文件化及溝通？"
            "是否建立互有關係人員之間的交互作用關係？"
        ),
        "expected_evidence": [
            "組織架構圖",
            "職務說明書或權責矩陣",
        ],
    },
    "5.5.2": {
        "title": "管理代表",
        "audit_impact": "major",
        "audit_question": (
            "最高管理階層是否指定管理階層中的一員作為管理代表，"
            "負責確保品質管理系統過程的建立與維持、向管理階層報告績效、"
            "以及確保在整個組織中促進對法規要求及品質管理系統要求的認知？"
        ),
        "expected_evidence": [
            "管理代表任命書",
            "管理代表職責說明",
        ],
    },
    "5.5.3": {
        "title": "內部溝通",
        "audit_impact": "minor",
        "audit_question": (
            "最高管理階層是否確保組織內建立適當的溝通過程，"
            "且針對品質管理系統的有效性進行溝通？"
        ),
        "expected_evidence": [
            "內部溝通程序或紀錄",
            "會議紀錄",
        ],
    },
    "5.6.1": {
        "title": "管理審查 — 一般",
        "audit_impact": "major",
        "audit_question": (
            "最高管理階層是否依規劃的時間間隔審查品質管理系統，以確保其持續的"
            "適切性、充分性及有效性？審查是否包含評估改善的機會及品質管理系統"
            "變更的需要？管理審查紀錄是否予以維持？"
        ),
        "expected_evidence": [
            "管理審查程序書",
            "管理審查會議紀錄",
            "管理審查排程計畫",
        ],
    },
    "5.6.2": {
        "title": "管理審查 — 輸入",
        "audit_impact": "major",
        "audit_question": (
            "管理審查的輸入是否包含稽核結果、顧客回饋、過程績效與產品符合性、"
            "預防及矯正措施狀況、先前管理審查之追蹤措施、可能影響品質管理系統的"
            "變更、改善建議、以及適用的新的或修訂的法規要求？"
        ),
        "expected_evidence": [
            "管理審查輸入資料",
            "稽核報告摘要",
            "顧客回饋彙整",
            "CAPA 狀態報告",
        ],
    },
    "5.6.3": {
        "title": "管理審查 — 輸出",
        "audit_impact": "major",
        "audit_question": (
            "管理審查的輸出是否包含品質管理系統及其過程有效性的改善、"
            "與顧客要求有關的產品改善、以及資源需求等相關決定及措施？"
        ),
        "expected_evidence": [
            "管理審查輸出/決議事項",
            "改善行動計畫",
            "資源配置決議",
        ],
    },
    # --------------------------------------------------------
    # Section 6: 資源管理
    # --------------------------------------------------------
    "6.1": {
        "title": "資源提供",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否決定並提供所需的資源，以實施品質管理系統並維持其有效性，"
            "以及滿足適用的法規要求及顧客要求？"
        ),
        "expected_evidence": [
            "資源規劃紀錄",
            "預算分配紀錄",
        ],
    },
    "6.2": {
        "title": "人力資源",
        "audit_impact": "major",
        "audit_question": (
            "執行影響產品品質工作的人員是否基於適當的教育、訓練、技能及經驗而能勝任？"
            "組織是否建立訓練需求的過程、提供訓練或採取其他措施以達成能力、"
            "並維持適當的紀錄？"
        ),
        "expected_evidence": [
            "教育訓練程序書",
            "員工訓練紀錄",
            "職能資格矩陣",
            "訓練有效性評估紀錄",
        ],
    },
    "6.3": {
        "title": "基礎設施",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定、提供及維持達成產品符合要求所需的基礎設施？"
            "基礎設施是否包含建築物、工作空間、過程設備及支援服務？"
            "是否建立基礎設施維護活動的文件化要求（含間隔）？"
        ),
        "expected_evidence": [
            "設備清單",
            "設備維護保養計畫與紀錄",
            "廠房配置圖",
        ],
    },
    "6.4.1": {
        "title": "工作環境",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定並管理達成產品符合要求所需的工作環境？"
            "如果工作環境條件可能對產品品質產生不利影響，"
            "組織是否建立工作環境要求、監督與管制這些條件的程序？"
        ),
        "expected_evidence": [
            "工作環境管制程序書",
            "環境監測紀錄（溫濕度、潔淨度等）",
        ],
    },
    "6.4.2": {
        "title": "污染管制",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否依適當情況規劃並文件化污染或潛在污染產品的管制安排，"
            "以防止工作環境對產品造成污染？"
            "對於無菌醫療器材，是否維持組裝或包裝過程中微生物污染管制的要求？"
        ),
        "expected_evidence": [
            "污染管制程序書",
            "潔淨室管制紀錄（如適用）",
            "微生物監測紀錄（如適用）",
        ],
    },
    # --------------------------------------------------------
    # Section 7: 產品實現
    # --------------------------------------------------------
    "7.1": {
        "title": "產品實現之規劃",
        "audit_impact": "major",
        "audit_question": (
            "組織是否規劃並開發產品實現所需的過程？"
            "規劃是否與品質管理系統其他過程的要求一致？"
            "是否建立風險管理的文件化要求？"
        ),
        "expected_evidence": [
            "產品實現規劃文件",
            "風險管理計畫",
            "品質計畫（如適用）",
        ],
    },
    "7.2.1": {
        "title": "與產品有關的要求之決定",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定顧客規定的要求（含交付及交付後活動的要求）、"
            "顧客未陳述但已知預期用途所必要的要求、與產品有關的適用法規要求、"
            "以及任何附加要求？"
        ),
        "expected_evidence": [
            "產品需求規格書",
            "顧客要求紀錄",
            "適用法規要求清單",
        ],
    },
    "7.2.2": {
        "title": "與產品有關的要求之審查",
        "audit_impact": "major",
        "audit_question": (
            "組織是否在承諾供應產品予顧客之前審查與產品有關的要求？"
            "審查是否確保產品要求已被界定、合約或訂單要求的差異已解決、"
            "以及組織有能力滿足已界定的要求？"
        ),
        "expected_evidence": [
            "合約審查紀錄",
            "訂單確認紀錄",
        ],
    },
    "7.2.3": {
        "title": "溝通",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否對以下事項規劃並文件化與顧客溝通的安排："
            "產品資訊、詢問/合約或訂單處理（含修訂）、顧客回饋（含抱怨）、"
            "以及諮詢通知？"
        ),
        "expected_evidence": [
            "顧客溝通程序書",
            "顧客抱怨處理紀錄",
            "諮詢通知程序（如適用）",
        ],
    },
    "7.3.1": {
        "title": "設計與開發規劃",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否規劃並管制產品的設計與開發？"
            "設計開發規劃是否涵蓋階段、審查/驗證/確認活動、"
            "責任與權限、以及設計開發輸入輸出之間的追溯方法？"
        ),
        "expected_evidence": [
            "設計開發計畫書",
            "設計開發階段定義",
            "設計開發團隊權責",
        ],
    },
    "7.3.2": {
        "title": "設計與開發輸入",
        "audit_impact": "critical",
        "audit_question": (
            "設計輸入是否包含功能與性能要求、適用的法規要求、"
            "風險管理輸出、及適用的先前類似設計資訊？"
            "輸入是否被審查其充分性並經核准？"
        ),
        "expected_evidence": [
            "設計輸入文件/規格書",
            "風險管理計畫",
            "法規要求清單",
        ],
    },
    "7.3.3": {
        "title": "設計與開發輸出",
        "audit_impact": "critical",
        "audit_question": (
            "設計輸出是否以能夠對照設計輸入進行驗證的形式提供？"
            "是否在發行前經核准？設計輸出是否滿足輸入要求、提供採購/生產/服務"
            "的適當資訊、包含或引用產品驗收準則、以及規定對安全和正常使用"
            "所必需的產品特性？"
        ),
        "expected_evidence": [
            "設計輸出文件",
            "設計輸出審查/核准紀錄",
            "產品規格書",
        ],
    },
    "7.3.4": {
        "title": "設計與開發審查",
        "audit_impact": "critical",
        "audit_question": (
            "是否在適當階段依規劃安排對設計與開發進行系統化審查？"
            "審查是否評估設計結果滿足要求的能力、識別問題並提出必要措施？"
            "審查紀錄是否予以維持？"
        ),
        "expected_evidence": [
            "設計審查會議紀錄",
            "設計審查檢查表",
            "設計審查行動項目追蹤",
        ],
    },
    "7.3.5": {
        "title": "設計與開發驗證",
        "audit_impact": "critical",
        "audit_question": (
            "是否依規劃安排執行設計與開發驗證，以確保設計輸出滿足設計輸入要求？"
            "驗證結果及必要措施的紀錄是否予以維持？"
        ),
        "expected_evidence": [
            "設計驗證計畫",
            "設計驗證報告/紀錄",
            "測試數據",
        ],
    },
    "7.3.6": {
        "title": "設計與開發確認",
        "audit_impact": "critical",
        "audit_question": (
            "是否依規劃安排執行設計與開發確認？"
            "確認是否在產品交付或實施之前完成（如可行）？"
            "確認是否包含臨床評估或效能評估（如適用法規要求）？"
        ),
        "expected_evidence": [
            "設計確認計畫",
            "設計確認報告",
            "臨床評估報告（如適用）",
        ],
    },
    "7.3.7": {
        "title": "設計與開發轉移",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立設計開發輸出轉移至製造的程序？"
            "轉移過程是否確保設計開發輸出在成為最終生產規格之前被驗證為適合製造？"
        ),
        "expected_evidence": [
            "設計轉移程序書",
            "設計轉移驗證紀錄",
        ],
    },
    "7.3.8": {
        "title": "設計與開發變更管制",
        "audit_impact": "critical",
        "audit_question": (
            "設計與開發變更是否被識別？變更在實施前是否經審查、驗證、確認（適當時）"
            "及核准？變更審查是否包含評估變更對組成零件、已交付產品、"
            "風險管理輸出及產品實現過程的影響？"
        ),
        "expected_evidence": [
            "設計變更管制程序書",
            "設計變更申請/核准紀錄",
            "變更影響評估紀錄",
        ],
    },
    "7.3.9": {
        "title": "設計與開發檔案",
        "audit_impact": "major",
        "audit_question": (
            "組織是否為每一醫療器材類型或族維持設計與開發檔案？"
            "檔案是否包含或引用展示設計開發符合要求的紀錄，"
            "以及設計開發變更的紀錄？"
        ),
        "expected_evidence": [
            "設計開發歷史檔案 (DHF)",
            "設計開發索引或目錄",
        ],
    },
    "7.3.10": {
        "title": "設計與開發文件",
        "audit_impact": "major",
        "audit_question": ("組織是否維持每一醫療器材的設計規格文件？"),
        "expected_evidence": [
            "設計規格文件",
            "設備主檔案 (DMR)",
        ],
    },
    "7.4.1": {
        "title": "採購過程",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立採購產品符合規定要求的程序？"
            "是否建立供應商評估與選擇準則？"
            "是否基於供應商提供符合要求產品的能力進行評估？"
            "評估結果及任何必要措施的紀錄是否予以維持？"
        ),
        "expected_evidence": [
            "採購管制程序書",
            "合格供應商清單 (ASL)",
            "供應商評估/稽核紀錄",
        ],
    },
    "7.4.2": {
        "title": "採購資訊",
        "audit_impact": "major",
        "audit_question": (
            "採購文件是否描述所採購的產品，適當時包含產品規格、"
            "驗收要求、供應商品質系統要求、以及書面協議中有關採購產品變更的通知？"
        ),
        "expected_evidence": [
            "採購規格書/訂單",
            "品質協議 (Quality Agreement)",
        ],
    },
    "7.4.3": {
        "title": "採購產品之驗證",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立並實施所需的檢驗或其他活動，以確保採購產品滿足規定的採購要求？"
        ),
        "expected_evidence": [
            "進料檢驗程序書",
            "進料檢驗紀錄",
        ],
    },
    "7.5.1": {
        "title": "生產與服務提供之管制",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否在管制條件下規劃並執行生產與服務提供？"
            "管制條件是否包含產品特性描述的文件化程序與要求、"
            "監督與量測設備、適當的生產基礎設施與工作環境、"
            "以及已界定的標示與包裝作業？"
        ),
        "expected_evidence": [
            "生產管制程序書",
            "作業指導書 (SOP/WI)",
            "批次紀錄 (Batch Record)",
        ],
    },
    "7.5.2": {
        "title": "產品之潔淨",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否將產品清潔或污染管制的要求文件化？"
            "如果產品在滅菌前或使用前需要清潔，或是清潔劑的殘留可能影響產品效能，"
            "是否有適當的清潔驗證？"
        ),
        "expected_evidence": [
            "產品清潔程序書",
            "清潔驗證紀錄（如適用）",
        ],
    },
    "7.5.3": {
        "title": "安裝活動",
        "audit_impact": "major",
        "audit_question": (
            "如適用，組織是否將醫療器材安裝與安裝驗證的驗收準則文件化？"
            "如果安裝由組織或其授權代理以外的人員執行，"
            "是否提供安裝與驗證要求的文件？"
        ),
        "expected_evidence": [
            "安裝程序書（如適用）",
            "安裝驗證紀錄（如適用）",
        ],
    },
    "7.5.4": {
        "title": "服務活動",
        "audit_impact": "major",
        "audit_question": (
            "如果服務是規定的要求，組織是否將服務活動的執行與驗證程序、"
            "參考量測程序、以及服務報告的分析文件化？"
        ),
        "expected_evidence": [
            "服務程序書（如適用）",
            "服務紀錄/報告（如適用）",
        ],
    },
    "7.5.5": {
        "title": "無菌醫療器材之特殊要求",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否記錄每一滅菌批次所使用的滅菌過程參數？"
            "滅菌紀錄是否可追溯至每一生產批次？"
        ),
        "expected_evidence": [
            "滅菌程序書",
            "滅菌批次紀錄",
            "滅菌驗證報告",
        ],
    },
    "7.5.6": {
        "title": "生產與服務提供過程之確認",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否確認生產和服務提供過程中，其輸出無法由後續的監督或量測加以驗證的過程？"
            "確認是否展示這些過程達成規劃結果的能力？"
            "是否建立確認安排，包含準則、方法、統計技術、"
            "設備資格鑑定以及人員資格？"
        ),
        "expected_evidence": [
            "過程確認程序書",
            "過程確認報告（IQ/OQ/PQ）",
            "特殊過程清單",
        ],
    },
    "7.5.7": {
        "title": "滅菌與無菌屏障系統過程之確認",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否確認滅菌過程與無菌屏障系統的過程？"
            "確認是否在首次使用前進行，且適當時在產品或過程變更後重新確認？"
        ),
        "expected_evidence": [
            "滅菌確認計畫與報告",
            "無菌屏障系統確認報告",
            "再確認紀錄",
        ],
    },
    "7.5.8": {
        "title": "識別",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立識別產品的文件化程序，並在整個產品實現過程中以適當方法識別產品？"
            "是否在退回的醫療器材與產品實現過程中識別產品狀態？"
        ),
        "expected_evidence": [
            "產品識別程序書",
            "標示管制紀錄",
        ],
    },
    "7.5.9": {
        "title": "追溯性 — 一般",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立追溯性的文件化程序？程序是否界定追溯的範圍及所需紀錄？"
        ),
        "expected_evidence": [
            "追溯性程序書",
            "追溯性紀錄範例",
        ],
    },
    "7.5.9.1": {
        "title": "追溯性 — 植入式醫療器材",
        "audit_impact": "critical",
        "audit_question": (
            "對於植入式醫療器材，追溯性紀錄是否包含所有可能導致醫療器材不滿足其"
            "規定安全與效能要求的零件、材料及工作環境條件？"
            "組織是否要求供應商維持追溯性紀錄？"
        ),
        "expected_evidence": [
            "植入物追溯性紀錄",
            "供應商追溯性要求文件（如適用）",
        ],
    },
    "7.5.9.2": {
        "title": "追溯性 — UDI",
        "audit_impact": "critical",
        "audit_question": ("組織是否建立符合適用法規要求的唯一裝置識別 (UDI) 系統？"),
        "expected_evidence": [
            "UDI 指派程序與紀錄（如適用）",
        ],
    },
    "7.5.10": {
        "title": "顧客財產",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否識別、驗證、保護與保管顧客所提供的財產？"
            "顧客財產發生遺失、損壞或不適用時，是否向顧客報告並維持紀錄？"
        ),
        "expected_evidence": [
            "顧客財產管制程序書（如適用）",
            "顧客財產紀錄（如適用）",
        ],
    },
    "7.5.11": {
        "title": "產品防護",
        "audit_impact": "major",
        "audit_question": (
            "組織是否建立在內部處理及交付至預定目的地期間，"
            "防護產品符合性的文件化程序或作業指導書？"
            "防護是否包含識別、搬運、包裝、儲存及保護？"
            "是否對有限壽命或需特殊儲存條件的產品建立管制？"
        ),
        "expected_evidence": [
            "產品防護/倉儲管理程序書",
            "儲存環境監測紀錄",
            "有效期限管制紀錄（如適用）",
        ],
    },
    "7.6": {
        "title": "監督與量測設備之管制",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定需執行的監督與量測及所需的設備，以提供產品符合已定要求的證據？"
            "設備是否依規劃的時間間隔或使用前校正或驗證？"
            "是否維持校正與驗證結果的紀錄？"
        ),
        "expected_evidence": [
            "量測設備管制程序書",
            "校正計畫與紀錄",
            "量測設備清單",
        ],
    },
    # --------------------------------------------------------
    # Section 8: 量測、分析與改善
    # --------------------------------------------------------
    "8.1": {
        "title": "量測、分析與改善 — 一般",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否規劃並實施所需的監督、量測、分析及改善過程，"
            "以展示產品的符合性、確保品質管理系統的符合性、以及維持其有效性？"
        ),
        "expected_evidence": [
            "監督量測分析改善規劃文件",
            "統計技術應用紀錄（如適用）",
        ],
    },
    "8.2.1": {
        "title": "回饋",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立收集與監督回饋資訊的文件化程序，作為品質管理系統績效的量測之一？"
            "回饋過程是否包含蒐集生產及生產後活動資料的規定？"
            "回饋過程中收集的資訊是否作為風險管理及產品實現或改善過程的輸入？"
        ),
        "expected_evidence": [
            "顧客回饋管制程序書",
            "顧客回饋/抱怨紀錄",
            "趨勢分析報告",
        ],
    },
    "8.2.2": {
        "title": "客訴處理",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否建立客訴處理的文件化程序，符合適用的法規要求？"
            "程序是否包含接收與記錄資訊的要求、評估是否構成客訴、"
            "調查/向法規機關報告/處理的要求？"
            "如果客訴未經調查，是否文件化理由？"
        ),
        "expected_evidence": [
            "客訴處理程序書",
            "客訴紀錄/調查報告",
            "法規通報紀錄（如適用）",
        ],
    },
    "8.2.3": {
        "title": "法規主管機關報告",
        "audit_impact": "critical",
        "audit_question": (
            "如果適用法規要求通報符合規定通報準則的客訴或諮詢通知，"
            "組織是否建立向法規主管機關提供通知的文件化程序？"
            "是否維持向法規主管機關報告的紀錄？"
        ),
        "expected_evidence": [
            "法規通報程序書",
            "不良事件通報紀錄（如適用）",
            "諮詢通知紀錄（如適用）",
        ],
    },
    "8.2.4": {
        "title": "內部稽核",
        "audit_impact": "major",
        "audit_question": (
            "組織是否依規劃的時間間隔執行內部稽核，以確定品質管理系統是否符合"
            "規劃的安排、本標準的要求、適用法規要求、以及組織所建立的品質管理系統要求？"
            "稽核方案的規劃是否考量過程與領域的狀態及重要性以及先前稽核結果？"
        ),
        "expected_evidence": [
            "內部稽核程序書",
            "年度稽核計畫",
            "稽核報告",
            "稽核發現追蹤紀錄",
        ],
    },
    "8.2.4.1": {
        "title": "內部稽核 — 稽核準則",
        "audit_impact": "major",
        "audit_question": (
            "是否界定稽核準則、範圍、頻率及方法？"
            "稽核員的選擇及稽核的執行是否確保稽核過程的客觀性與公正性？"
            "稽核員是否不稽核自己的工作？"
        ),
        "expected_evidence": [
            "稽核員資格要求",
            "稽核員獨立性紀錄",
        ],
    },
    "8.2.4.2": {
        "title": "內部稽核 — 矯正措施",
        "audit_impact": "major",
        "audit_question": (
            "受稽核區域的管理階層是否確保適時採取矯正措施以消除已發現的不符合及其原因？"
            "後續行動是否包含對所採措施的驗證及驗證結果的報告？"
        ),
        "expected_evidence": [
            "稽核矯正措施紀錄",
            "矯正措施有效性驗證紀錄",
        ],
    },
    "8.2.5": {
        "title": "過程之監督與量測",
        "audit_impact": "major",
        "audit_question": (
            "組織是否應用適當的方法監督及適用時量測品質管理系統過程？"
            "這些方法是否展示過程達成規劃結果的能力？"
            "當未達成規劃結果時，是否採取適當的矯正及矯正措施？"
        ),
        "expected_evidence": [
            "過程監督紀錄",
            "過程績效指標",
        ],
    },
    "8.2.6": {
        "title": "產品之監督與量測",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否在產品實現的適當階段，依規劃安排監督與量測產品特性，"
            "以驗證產品要求已被滿足？"
            "是否維持符合驗收準則的證據及授權放行人員的紀錄？"
            "產品是否在所有規劃安排被圓滿完成後才予以放行？"
        ),
        "expected_evidence": [
            "成品檢驗/測試程序書",
            "檢驗/測試紀錄",
            "放行核准紀錄",
        ],
    },
    "8.3": {
        "title": "不合格品管制 — 一般",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否確保不符合產品要求的產品被識別並予以管制，以防止其非預期使用或交付？"
            "是否建立不合格品管制及相關責任與權限的文件化程序？"
        ),
        "expected_evidence": [
            "不合格品管制程序書",
            "不合格品處理紀錄",
        ],
    },
    "8.3.1": {
        "title": "不合格品管制 — 交付前",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否以一種或多種方式處理不合格品：採取措施消除已發現的不符合、"
            "授權讓步使用/放行/接收、採取措施排除其原來預期使用或應用？"
            "是否維持不符合性質及所採取後續措施的紀錄？"
        ),
        "expected_evidence": [
            "不合格品處理/讓步紀錄",
            "不合格品識別標示",
        ],
    },
    "8.3.2": {
        "title": "不合格品管制 — 交付後",
        "audit_impact": "critical",
        "audit_question": (
            "當交付或開始使用後才偵測到不合格品時，組織是否採取與不符合的影響"
            "（或潛在影響）相稱的措施？"
            "是否維持所採取措施的紀錄？"
        ),
        "expected_evidence": [
            "交付後不合格品處理紀錄",
            "產品召回/矯正程序（如適用）",
        ],
    },
    "8.3.3": {
        "title": "不合格品管制 — 讓步",
        "audit_impact": "critical",
        "audit_question": (
            "讓步使用/放行/接收是否只在滿足法規要求、"
            "經授權人員核准、且有理由說明的情況下才被接受？"
        ),
        "expected_evidence": [
            "讓步核准紀錄",
            "讓步理由說明文件",
        ],
    },
    "8.3.4": {
        "title": "不合格品管制 — 返工",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否依文件化程序進行返工？"
            "返工後是否依據原有的或更嚴格的準則重新檢查？"
            "返工是否考量其對產品的不利影響？"
        ),
        "expected_evidence": [
            "返工程序書",
            "返工紀錄",
            "返工後檢驗紀錄",
        ],
    },
    "8.4": {
        "title": "數據分析",
        "audit_impact": "major",
        "audit_question": (
            "組織是否決定、蒐集及分析適當的數據，以展示品質管理系統的適切性及有效性？"
            "數據分析是否包含回饋、產品符合性、過程與產品趨勢、供應商、稽核、"
            "及服務報告（適用時）等方面的資料？"
        ),
        "expected_evidence": [
            "數據分析程序書",
            "品質指標/趨勢報告",
            "統計分析紀錄",
        ],
    },
    "8.5.1": {
        "title": "改善 — 一般",
        "audit_impact": "minor",
        "audit_question": (
            "組織是否識別並實施任何變更，以確保並維持品質管理系統的持續適切性及有效性？"
            "改善是否透過品質政策、品質目標、稽核結果、數據分析、矯正措施、"
            "預防措施及管理審查來實現？"
        ),
        "expected_evidence": [
            "持續改善紀錄",
            "改善提案/行動計畫",
        ],
    },
    "8.5.2": {
        "title": "矯正措施",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否採取措施消除不符合的原因以防止再發生？"
            "矯正措施是否與所遭遇的不符合影響相稱？"
            "是否建立文件化程序，規定審查不符合（含客訴）、判定不符合的原因、"
            "評估確保不符合不再發生的行動需要、規劃與文件化行動並實施、"
            "驗證措施有效性、以及審查所採取的矯正措施及其有效性？"
        ),
        "expected_evidence": [
            "矯正措施程序書 (CAPA)",
            "CAPA 紀錄",
            "根本原因分析紀錄",
            "有效性驗證紀錄",
        ],
    },
    "8.5.3": {
        "title": "預防措施",
        "audit_impact": "critical",
        "audit_question": (
            "組織是否決定消除潛在不符合原因的措施以防止其發生？"
            "預防措施是否與潛在問題的影響相稱？"
            "是否建立文件化程序，規定判定潛在不符合及其原因、"
            "評估預防行動的需要、規劃與文件化行動並實施、"
            "驗證措施有效性、以及審查所採取的預防措施及其有效性？"
        ),
        "expected_evidence": [
            "預防措施程序書",
            "預防措施紀錄",
            "風險評估紀錄",
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
