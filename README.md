# <img src="public/avatars/eira.svg" alt="Eira" width="40" height="40"> TMBIA-Tmti AI-QMS (Eira) — Intelligent Regulatory Compliance Agent for Medical Device Professionals

<p align="center">
  <strong>
    <a href="#中文說明">中文</a> | 
    <a href="#english">English</a> | 
    <a href="#日本語">日本語</a>
  </strong>
</p>

https://github.com/user-attachments/assets/68cf6037-aab2-41a1-9e01-768c763d8ae1

---

# 中文說明

## 專案簡介

**AI-QMS (Eira)** 是由 **TMBIA-Tmti** 開發的 AI 驅動品質管理系統，專為醫療器材產業的法規合規需求而設計。系統以 **ISO 13485 醫療器材品質管理系統**為核心標準，透過 AI Agent 架構將文件管制、稽核追蹤、版本控制、法規監控等繁瑣且高風險的品質管理作業智慧化與自動化。

TMBIA-Tmti 深知醫療器材法規人員在品質管理實務中面對的挑戰——從多國法規追蹤、文件版本管控到稽核準備，每一環節都需要高度精確且耗費大量人力。AI-QMS (Eira) 的開發初衷，正是讓 AI 承擔這些重複性高、容錯率低的工作，使法規專業人員能專注於更具策略價值的品質決策。

系統採用**主 Agent + 子 Agent** 架構設計，由主 Agent 統籌品質管理系統各模組，文件管制子 Agent 負責文件的上傳、OCR 辨識、版本偵測、簽章驗證及稽核紀錄等作業。

> **📌 開發進度：Phase 1（文件管制子 Agent）✅ 已完成 v3.5.0。Phase 2（稽核子 Agent）🔜 開發中。**

## Logo 設計理念

<p align="center">
  <img src="public/avatars/eira.svg" alt="Eira Logo" width="160" height="160">
</p>

Eira 的 Logo 由兩個核心符號交織而成，每一筆都承載著這個專案的使命：

- **🐍 阿斯克勒庇俄斯之杖（Rod of Asclepius）**（藍色）— 單蛇纏繞權杖，是全世界最古老且通用的醫療象徵，代表醫療與療癒。選用此符號，直接宣告 Eira 的核心領域：**醫療器材品質管理**。
- **🖊️ 鋼筆筆尖（Pen Nib）**（金色）— 象徵**品質管理系統（QMS）的全部流程**——文件管制、稽核管理、CAPA、不符合事項、設計管制等，QMS 的每一個環節都需要被嚴謹地記錄與管控。金色代表權威與正式性。目前已完成 Phase 1（文件管制），後續階段將逐步實現完整 QMS 管控。

兩者在 Logo 中**交疊融合**——筆尖觸及蛇杖，隱喻 Eira 將「醫療領域的專業知識」與「品質管理的全面管控能力」合而為一。




## 核心功能

### 主 Agent (Main Agent)
- QMS 品質管理系統智慧助手，自然語言對話介面，支援 20 國語言 UI
- 子系統統一調度與導航入口
- **文件管制子系統** — 文件上傳、OCR、版本管理、簽章偵測、稽核紀錄、匯出
- **稽核子系統** — CAPA、內部稽核、不符合事項管理（Phase 2 規劃中）

### 文件管制子 Agent (Document Control Sub-Agent) ✅ Phase 1 完成
- **文件上傳與 OCR 處理** — 支援 PDF、Word、Excel、PowerPoint、圖片等格式
- **Docling 主引擎 + MarkItDown fallback** — Docling 還原 PDF 表格結構與版面分析（>100KB 文件）；MarkItDown 輕量快速（<100KB）；掃描文件自動切換 LLM Vision 備援
- **智慧版本偵測** — 自動識別新文件 vs 版本更新，OCR 掃描文件內版本號
- **多語言簽章/印章偵測** — 支援 15+ 語言、200+ 關鍵字自動偵測簽章狀態
- **防竄改偵測稽核紀錄** — SHA-256 雜湊鏈，完整記錄所有文件操作，可偵測未經授權的變更
- **文件作廢管理** — 透過 AI 對話作廢文件，保留稽核追蹤
- **交叉引用偵測** — 版本更新後自動搜尋引用該文件的關聯文件
- **Markdown 儲存層** — 轉換文件為 Markdown 格式，供跨 Agent 資料提取
- **原始檔案下載** — 透過 AI 對話指令下載原始文件
- **文件清單匯出** — 現行正式版本文件清單匯出為 Word/Excel
- **全部文件紀錄匯出** — 所有文件紀錄（含進版、作廢）匯出為 Word/Excel
- **進版差異比對** — 版本更新後 LLM 自動比對新舊版本內容差異

### 稽核子 Agent (Audit Sub-Agent) 🔜 開發中
- CAPA（矯正與預防措施）管理
- 內部稽核排程與追蹤
- 不符合事項管理
- 稽核報告自動生成

### v3.6.0 新增功能
- **SQLite WAL 後端** — ACID 保證，取代 JSON 檔案資料庫
- **Docling 表格解析引擎** — PDF 表格結構還原（>100KB），MarkItDown fallback（<100KB）
- **Ollama 自動偵測** — 零設定本機 Embedding
- **Embedding 三級降級** — BGE-M3 → nomic-embed-text → multilingual-MiniLM
- **雙模式任務派發** — asyncio (standalone) / Celery (server) 切換
- **LightRAG 知識圖譜整合** — 跨文件語意搜尋基礎

### v3.5.0 新增功能（強烈建議更新）
- **法規地區自動查詢** — 查詢指定地區之最新法規資訊，與本地品質文件進行交叉分析與合規評估

### v3.4.0 新增功能
- **Arize Phoenix 可觀測性** — 即時追蹤 LLM Token 用量、延遲、成本
- **一鍵啟動 + 自動更新** — `start.bat` 同時啟動 Chainlit + Phoenix，自動安裝新套件

### v3.3.0 新增功能
- **`/web` 網路搜尋** — `/web 關鍵字` 搜尋網路最新資訊，結合本地文件作為 LLM 上下文
- **來源可信度排序** — 搜尋結果依來源權威性自動排序，醫療法規產業特別適用：
  - 🏛️ Tier 0（最高）：ISO、FDA、EMA、WHO 等國際標準與法規機構
  - 🏛️ Tier 1：政府網域（.gov、.go.jp 等）
  - 🎓 Tier 2：學術機構（.edu、.ac.uk 等）
  - ✅ Tier 3：驗證機構與學術出版商
  - 🌐 Tier 4：一般搜尋結果、⬇️ Tier 9：Wikipedia

### v3.2.0 新增功能
- **20 國語言 UI** — 支援 20 種語言即時切換

## 系統架構

```
┌─────────────────────────────────────────────────────┐
│                  Chainlit UI (Port 3000)             │
│  ┌─────────────────────┐ ┌────────────────────────┐  │
│  │  Profile: 主系統     │ │  Profile: 文件管制      │  │
│  │  Main Agent         │ │  Doc Control Sub-Agent  │  │
│  └─────────────────────┘ └────────────────────────┘  │
│  [ChatSettings: Provider | Model | API Key]          │
│  [Report UI: /api/report/page/{run_id}]              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│          LLM Provider 抽象層 (LiteLLM)               │
│  [OpenAI] [Anthropic] [Google] [Ollama] + 12 more   │
└──────────────┬───────────────────┬──────────────────┘
               │                   │
               │    ┌──────────────┴──────────────────┐
               │    │   LLM 可觀測性 (Arize Phoenix)    │
               │    │   OpenTelemetry Auto-Instrument  │
               │    │   Dashboard: http://localhost:6006│
               │    └─────────────────────────────────┘
               │
┌──────────────┴──────────────────────────────────────┐
│           Agent 編排引擎 (LangGraph)                  │
│  Main Agent ──→ Document Control Sub-Agent           │
│                 (Phase 2: Audit Sub-Agent 規劃中)     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│         合規分析引擎 (Analysis Pipeline)               │
│                                                     │
│  Phase 0:   Data Quality Gate (code)                 │
│  Phase 0.5: Reference Mapping (code)                 │
│  Phase 1:   Gap Scan (LLM)                           │
│  Phase 2:   Checklist Verification (LLM)             │
│  Phase 3:   Risk Assessment (rule engine)            │
│  Phase 4:   Remediation Suggestions (LLM)            │
│  Phase 5:   Cross-Examination (LLM, parallel)        │
│  Phase 6:   Source Verification (HTTP)               │
│                                                     │
│  [SSE Real-Time Events] [Pause/Resume/Inject]        │
│  [Daily Audit] [Cross-Ref Validation]                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              OCR 處理層                               │
│  [MarkItDown (主)] ──→ [LLM Vision (備援)]            │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                   資料層                              │
│  [JSON DB] [Markdown Storage] [Audit Log]            │
│  [Interaction Log] [CrossExam Store]                  │
│  [Regulatory Storage] [MDSAP Storage]                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│            斷線備援層 (Resilience Layer)               │
│                                                     │
│  [Baseline 報告] ──→ LLM 前生成 Word/Excel (保底)     │
│  [Analysis Cache] ──→ 定期存檔 + 斷線自動儲存         │
│  [User Settings] ──→ LLM 設定持久化 (自動重連)        │
│  [Safe I/O]      ──→ 原子寫入 + PermissionError 重試  │
│  [on_chat_end]   ──→ 斷線時自動存檔至 cache           │
│  [Reconnect]     ──→ 重連時自動顯示待下載報告         │
└─────────────────────────────────────────────────────┘
```

## 支援的 LLM 提供商 (16 家)

| 類型 | 提供商 |
|------|--------|
| **雲端 API** | OpenAI, Anthropic, Google, DeepSeek, xAI (Grok), Mistral, Cohere, Perplexity |
| **閘道平台** | OpenRouter, Groq, Together AI, Fireworks AI, Deep Infra, Requesty |
| **本地部署** | Ollama, LM Studio |

## 支援的檔案格式

| 類別 | 格式 | 處理方式 |
|------|------|----------|
| **PDF** | `.pdf` | MarkItDown (主) + LLM Vision (備援) |
| **圖片** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tiff`, `.tif`, `.bmp` | MarkItDown (主) + LLM Vision (備援) |
| **Word** | `.docx`, `.doc` | python-docx / pywin32 |
| **Excel** | `.xlsx`, `.xls` | openpyxl / pywin32 |
| **PowerPoint** | `.pptx`, `.ppt` | python-pptx / pywin32 |
| **文字** | `.txt`, `.md`, `.csv`, `.rtf` | 直接讀取 |

> **📝 備註：** 所有支援格式的文件皆可上傳，系統會自動偵測簽章狀態。手動建立的文件需要簽章，系統自動生成的文件則不需簽章。

## 下載與安裝

### 前置準備（第一次使用電腦開發的人請先完成以下步驟）

**步驟 1：安裝 Git**

Git 是一個版本控制工具，用來下載和管理程式碼。

1. 前往 https://git-scm.com/downloads
2. 點擊下載適合您作業系統的安裝檔（Windows / Mac / Linux）
3. 執行安裝檔，所有選項保持預設即可，一路點擊「Next」直到安裝完成

**步驟 2：安裝 Miniconda（推薦）**

Miniconda 是一個 Python 環境管理工具，可以幫您建立獨立的 Python 環境，避免套件衝突。

1. 前往 https://docs.anaconda.com/miniconda/install/
2. 下載適合您作業系統的安裝檔
3. 執行安裝檔，建議勾選「Add to PATH」選項
4. 安裝完成後，開啟「Anaconda Prompt」（可在開始選單中找到）

> **💡 想在 PowerShell 中使用 Conda？** 如果您偏好使用 PowerShell 而非 Anaconda Prompt，請執行以下步驟：
> 1. 以**系統管理員**身分開啟 PowerShell
> 2. 執行 `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`（輸入 `Y` 確認）
> 3. 執行 `conda init powershell`
> 4. **關閉並重新開啟 PowerShell** — 您會看到提示符前方出現 `(base)`，代表 Conda 已成功整合

> **不想安裝 Miniconda？** 您也可以直接安裝 Python 3.11：前往 https://www.python.org/downloads/ 下載 Python 3.11 版本，安裝時務必勾選「Add Python to PATH」。

### 下載專案

**方法一：使用 Git Clone（推薦）**

開啟命令提示字元（按 `Win + R`，輸入 `cmd`，按 Enter），然後輸入：

```bash
git clone https://github.com/TMBIA-Tmti/AI-QMS.git
cd AI-QMS
```

**方法二：下載 ZIP**

1. 點擊本頁面右上方綠色 **「Code」** 按鈕
2. 選擇 **「Download ZIP」**
3. 解壓縮至任意目錄

## 快速開始

### 1. 建立 Python 環境

開啟 Anaconda Prompt（或命令提示字元），輸入以下指令：

> **⚠️ 重要：** 請務必先 `cd` 到本專案的資料夾路徑下，再建立 Conda 環境並執行 `pip install`，否則 `requirements.txt` 會找不到，導致安裝失敗。

```bash
cd AI-QMS
conda create --name QMS python=3.11 --yes
conda activate QMS
```

> 如果您沒有安裝 Miniconda，請確認已安裝 Python 3.11，直接跳到步驟 2。

> **📋 Conda 服務條款 (TOS)：** 自 Miniconda 25.1.1 版本起，首次使用 Conda 時需要接受服務條款。如果遇到 `CondaToSNonInteractiveError` 錯誤，請執行以下指令：
> ```bash
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
> ```
> **注意：** `start.bat` 啟動腳本已自動處理 TOS 接受，通常無需手動執行。

### 2. 安裝相依套件

```bash
pip install -r requirements.txt
```

### 3. 啟動系統

```bash
start.bat
```

或直接啟動 Chainlit：

```bash
start_chainlit.bat
```

瀏覽器將自動開啟 http://localhost:3000

> **API Key 設定：** 啟動後在對話框左側的齒輪圖示（⚙️）中開啟設定面板，直接輸入 API Key，無需設定環境變數。語言切換選項也在同一個設定面板中。

### 4. 啟動 Phoenix 可觀測性（選用）

如需查看 LLM 呼叫追蹤與效能分析：

```bash
start_phoenix.bat
```

或在 `start.bat` 選單中選擇 **[3] Start Chainlit + Phoenix**，同時啟動 Chainlit 和 Phoenix。

Phoenix Dashboard：http://localhost:6006

> **舊使用者升級：** 如果您是透過 `git pull` 更新的舊使用者，無需手動安裝新套件。系統會在啟動時自動偵測並安裝缺少的套件（如 Phoenix）。

## 對話指令

> 以下為**文件管制子 Agent (Doc Control Sub-Agent)** 的對話指令。輸入資料顯示類指令後，下方會自動出現 Word / Excel 匯出按鈕，無需另外輸入匯出指令。

| 指令 | 說明 |
|------|------|
| `幫助` / `help` | 顯示使用指南 |
| `狀態` / `status` | 顯示系統狀態 |
| `文件清單` | 現行正式版本文件（附 Word/Excel 匯出按鈕） |
| `列表` / `list` | 所有文件紀錄（含進版、作廢）（附 Word/Excel 匯出按鈕） |
| `搜尋 <關鍵字>` | 搜尋文件內容 |
| `下載 <文件編號>` | 下載原始文件，所有 1-4 階皆可下載，下載自動記錄於稽核紀錄（如：下載 QP-852） |
| `作廢 <文件編號>` | 作廢文件（如：作廢 OTHER-016） |
| `文件更動紀錄` | 查看文件更動紀錄（附 Word/Excel 匯出按鈕） |
| `稽核驗證` | 驗證稽核紀錄 Hash 鏈完整性，顯示各資料檔 SHA-256 指紋供外部留存比對 |
| `法規清單` | 列出所有引用的法規標準（附 Word/Excel 匯出按鈕） |
| `法規清單更新` | 法規清單最新資訊評估分析（附 Word/Excel 匯出按鈕） |
| `下載法規更新報告 word/excel` | 匯出法規更新報告 |
| `下載引用清單 word/excel` | 匯出進版引用清單 |
| `/web <關鍵字>` | 搜尋網路取得最新資訊（如：/web 最新 ISO 13485 版本） |
| `刪除資料庫` | 刪除所有文件（需確認） |

## 技術堆疊

| 類別 | 技術 |
|------|------|
| 程式語言 | Python 3.11 |
| UI 框架 | Chainlit 2.9.6 |
| Agent 框架 | LangGraph |
| LLM 抽象層 | LiteLLM |
| OCR 引擎 | Docling + MarkItDown + LLM Vision |
| LLM 可觀測性 | Arize Phoenix |
| 追蹤框架 | OpenTelemetry + OpenInference |
| 網路搜尋 | DuckDuckGo |
| 本地 LLM | Ollama |
| HTTP 用戶端 | httpx (HTTP/2) |
| 印章/簽章偵測 | OpenCV + NumPy |
| 網頁爬蟲 | BeautifulSoup4 + lxml |
| PDF 生成 | reportlab |
| 原子檔案 I/O | safe_io (PermissionError 重試) |

---

# English

## Project Overview

**AI-QMS (Eira)** is an AI-powered Quality Management System developed by **TMBIA-Tmti**, purpose-built for the regulatory compliance needs of the medical device industry. Grounded in the **ISO 13485 Medical Device Quality Management System** standard, the system leverages AI Agent architecture to automate and intelligently manage document control, audit trails, version management, and regulatory monitoring — tasks that are both labor-intensive and high-risk.

TMBIA-Tmti understands the challenges that medical device regulatory professionals face in quality management — from tracking multi-country regulations and managing document versions to preparing for audits, every step demands precision and consumes significant manpower. AI-QMS (Eira) was built to let AI handle these repetitive, error-sensitive tasks, freeing regulatory professionals to focus on higher-value quality decisions.

The system adopts a **Main Agent + Sub-Agent** architecture, where the Main Agent orchestrates all QMS modules, and the Document Control Sub-Agent handles document upload, OCR processing, version detection, signature verification, and audit logging.

> **📌 Development Status: Phase 1 (Document Control Sub-Agent) ✅ complete v3.5.0. Phase 2 (Audit Sub-Agent) 🔜 in development.**

## Logo Design

<p align="center">
  <img src="public/avatars/eira.svg" alt="Eira Logo" width="160" height="160">
</p>

The Eira logo weaves together two core symbols, each embodying the project's mission:

- **🐍 Rod of Asclepius** (blue) — The single serpent entwined around a staff is the oldest and most universal symbol of medicine and healing. It declares Eira's core domain: **medical device quality management**.
- **🖊️ Pen Nib** (gold) — Represents the **entirety of the Quality Management System (QMS)** — document control, audit management, CAPA, non-conformance handling, design control, and more. Every QMS process must be rigorously recorded and governed. Gold signifies authority and formality. Phase 1 (Document Control) is complete; subsequent phases will progressively realize the full QMS vision.

The two symbols **overlap and merge** in the logo — the pen nib touches the serpent staff, symbolizing how Eira unifies "medical domain expertise" with "comprehensive quality management capability.


## Core Features

### Main Agent
- Intelligent QMS assistant with natural language interface, 20-language UI support
- Unified sub-system orchestration and navigation hub
- **Document Control Sub-System** — Document upload, OCR, version management, signature detection, audit trail, export
- **Audit Sub-System** — CAPA, internal audit, non-conformance management (Phase 2 Planned)

### Document Control Sub-Agent ✅ Phase 1 Complete
- **Document Upload & OCR** — Supports PDF, Word, Excel, PowerPoint, images
- **Docling Primary + MarkItDown Fallback** — Docling restores PDF table structure and layout analysis (>100KB files); MarkItDown lightweight and fast (<100KB); auto-fallback to LLM Vision for scanned documents
- **Intelligent Version Detection** — Auto-detect new document vs. version update, OCR-based version number scanning
- **Multilingual Signature/Stamp Detection** — 15+ languages, 200+ keywords for automatic signature status detection
- **Tamper-Evident Audit Trail** — SHA-256 hash chain recording all document operations, enabling detection of unauthorized changes
- **Document Obsolescence** — Obsolete documents via AI chat with full audit trail preservation
- **Cross-Reference Detection** — Auto-search for related documents after version updates
- **Markdown Storage Layer** — Convert documents to Markdown for cross-agent data extraction
- **Original File Download** — Download original files via AI chat commands
- **Document List Export** — Export current formal document list as Word/Excel
- **All Records Export** — Export all document records (incl. versions, obsolete) as Word/Excel
- **Version Diff Analysis** — LLM auto-compares old and new version content after version updates

### Audit Sub-Agent 🔜 In Development
- CAPA (Corrective and Preventive Actions) management
- Internal audit scheduling and tracking
- Non-conformance management
- Automated audit report generation

### v3.6.0 New Features
- **SQLite WAL Backend** — ACID guarantees, replacing JSON file database
- **Docling Table Parsing Engine** — PDF table structure restoration (>100KB), MarkItDown fallback (<100KB)
- **Ollama Auto-Detection** — Zero-config local Embedding
- **3-Tier Embedding Fallback** — BGE-M3 → nomic-embed-text → multilingual-MiniLM
- **Dual-Mode Task Dispatch** — asyncio (standalone) / Celery (server) switching
- **LightRAG Knowledge Graph Integration** — Cross-document semantic search foundation

### v3.5.0 New Features (Strongly Recommended Update)
- **Regulatory Region Auto-Query** — Retrieves latest regulatory info for selected regions and cross-analyzes with local quality documents for compliance assessment

### v3.4.0 New Features
- **Arize Phoenix Observability** — Real-time LLM token, latency, and cost tracking
- **One-Click Launch + Auto-Update** — `start.bat` launches Chainlit + Phoenix together, auto-installs new packages

### v3.3.0 New Features
- **`/web` Web Search** — `/web keyword` searches the web for latest info, combined with local documents as LLM context
- **Source Credibility Ranking** — Auto-ranks results by source authority, optimized for medical regulatory industry:
  - 🏛️ Tier 0 (Highest): ISO, FDA, EMA, WHO and other international standards/regulatory bodies
  - 🏛️ Tier 1: Government domains (.gov, .go.jp, etc.)
  - 🎓 Tier 2: Academic institutions (.edu, .ac.uk, etc.)
  - ✅ Tier 3: Certification bodies & academic publishers
  - 🌐 Tier 4: General results, ⬇️ Tier 9: Wikipedia

### v3.2.0 New Features
- **20-Language UI** — Supports 20 languages with real-time switching

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Chainlit UI (Port 3000)             │
│  ┌─────────────────────┐ ┌────────────────────────┐  │
│  │  Profile: Main Agent│ │  Profile: Doc Control   │  │
│  │  QMS Assistant      │ │  Document Management    │  │
│  └─────────────────────┘ └────────────────────────┘  │
│  [ChatSettings: Provider | Model | API Key]          │
│  [Report UI: /api/report/page/{run_id}]              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│        LLM Provider Abstraction (LiteLLM)            │
│  [OpenAI] [Anthropic] [Google] [Ollama] + 12 more   │
└──────────────┬───────────────────┬──────────────────┘
               │                   │
               │    ┌──────────────┴──────────────────┐
               │    │ LLM Observability (Arize Phoenix) │
               │    │ OpenTelemetry Auto-Instrument     │
               │    │ Dashboard: http://localhost:6006  │
               │    └─────────────────────────────────┘
               │
┌──────────────┴──────────────────────────────────────┐
│          Agent Orchestration (LangGraph)              │
│  Main Agent ──→ Document Control Sub-Agent           │
│                 (Phase 2: Audit Sub-Agent planned)    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│       Compliance Analysis Engine (Pipeline)           │
│                                                     │
│  Phase 0:   Data Quality Gate (code)                 │
│  Phase 0.5: Reference Mapping (code)                 │
│  Phase 1:   Gap Scan (LLM)                           │
│  Phase 2:   Checklist Verification (LLM)             │
│  Phase 3:   Risk Assessment (rule engine)            │
│  Phase 4:   Remediation Suggestions (LLM)            │
│  Phase 5:   Cross-Examination (LLM, parallel)        │
│  Phase 6:   Source Verification (HTTP)               │
│                                                     │
│  [SSE Real-Time Events] [Pause/Resume/Inject]        │
│  [Daily Audit] [Cross-Ref Validation]                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              OCR Processing Layer                     │
│  [MarkItDown (Primary)] ──→ [LLM Vision (Fallback)] │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                    Data Layer                         │
│  [JSON DB] [Markdown Storage] [Audit Log]            │
│  [Interaction Log] [CrossExam Store]                  │
│  [Regulatory Storage] [MDSAP Storage]                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│             Resilience Layer (Disconnect Recovery)    │
│                                                     │
│  [Baseline Report] ──→ Pre-LLM Word/Excel generation │
│  [Analysis Cache]  ──→ Periodic save + auto-save     │
│  [User Settings]   ──→ LLM config persistence        │
│  [Safe I/O]        ──→ Atomic writes + retry logic    │
│  [on_chat_end]     ──→ Auto-save on disconnect       │
│  [Reconnect Check] ──→ Show pending reports on login │
└─────────────────────────────────────────────────────┘
```

## Supported LLM Providers (16)

| Type | Providers |
|------|-----------|
| **Cloud API** | OpenAI, Anthropic, Google, DeepSeek, xAI (Grok), Mistral, Cohere, Perplexity |
| **Gateway** | OpenRouter, Groq, Together AI, Fireworks AI, Deep Infra, Requesty |
| **Local** | Ollama, LM Studio |

## Supported File Formats

| Category | Formats | Processing |
|----------|---------|------------|
| **PDF** | `.pdf` | MarkItDown (Primary) + LLM Vision (Fallback) |
| **Images** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tiff`, `.tif`, `.bmp` | MarkItDown + LLM Vision |
| **Word** | `.docx`, `.doc` | python-docx / pywin32 |
| **Excel** | `.xlsx`, `.xls` | openpyxl / pywin32 |
| **PowerPoint** | `.pptx`, `.ppt` | python-pptx / pywin32 |
| **Text** | `.txt`, `.md`, `.csv`, `.rtf` | Direct read |

> **📝 Note:** All supported file formats can be uploaded, and the system will automatically detect signature status. Manually created documents require signatures; system-generated documents do not.

## Download & Install

### Prerequisites (First-time setup for beginners)

**Step 1: Install Git**

Git is a version control tool used to download and manage source code.

1. Go to https://git-scm.com/downloads
2. Download the installer for your operating system (Windows / Mac / Linux)
3. Run the installer, keep all default options, click "Next" until installation is complete

**Step 2: Install Miniconda (Recommended)**

Miniconda is a Python environment manager that creates isolated Python environments to avoid package conflicts.

1. Go to https://docs.anaconda.com/miniconda/install/
2. Download the installer for your operating system
3. Run the installer, check "Add to PATH" option if available
4. After installation, open "Anaconda Prompt" (find it in Start Menu)

> **💡 Want to use Conda in PowerShell?** If you prefer PowerShell over Anaconda Prompt, follow these steps:
> 1. Open PowerShell as **Administrator**
> 2. Run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` (type `Y` to confirm)
> 3. Run `conda init powershell`
> 4. **Close and reopen PowerShell** — You should see `(base)` before your prompt, indicating Conda is successfully integrated

> **Don't want to install Miniconda?** You can install Python 3.11 directly: go to https://www.python.org/downloads/ and download Python 3.11. Make sure to check "Add Python to PATH" during installation.

### Download the Project

**Option 1: Git Clone (Recommended)**

Open a command prompt (press `Win + R`, type `cmd`, press Enter), then type:

```bash
git clone https://github.com/TMBIA-Tmti/AI-QMS.git
cd AI-QMS
```

**Option 2: Download ZIP**

1. Click the green **"Code"** button at the top of this page
2. Select **"Download ZIP"**
3. Extract to any directory

## Quick Start

### 1. Create Python Environment

Open Anaconda Prompt (or Command Prompt) and type:

> **⚠️ Important:** You must `cd` into the project folder first before creating the Conda environment and running `pip install`. Otherwise, `requirements.txt` will not be found and the installation will fail.

```bash
cd AI-QMS
conda create --name QMS python=3.11 --yes
conda activate QMS
```

> If you didn't install Miniconda, make sure Python 3.11 is installed and skip to step 2.

> **📋 Conda Terms of Service (TOS):** Starting from Miniconda 25.1.1, Conda requires you to accept the Terms of Service on first use. If you encounter a `CondaToSNonInteractiveError`, run the following commands:
> ```bash
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
> ```
> **Note:** The `start.bat` launcher script handles TOS acceptance automatically, so you usually don't need to run these manually.

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Launch System

```bash
start.bat
```

Or launch Chainlit directly:

```bash
start_chainlit.bat
```

Browser will automatically open http://localhost:3000

> **API Key Setup:** After launch, click the gear icon (⚙️) on the left side of the chat input to open the settings panel, then enter your API Key directly. No environment variables needed. The language selector is also available in the same settings panel.

### 4. Launch Phoenix Observability (Optional)

To view LLM call traces and performance analytics:

```bash
start_phoenix.bat
```

Or select **[3] Start Chainlit + Phoenix** from the `start.bat` menu to launch both Chainlit and Phoenix simultaneously.

Phoenix Dashboard: http://localhost:6006

> **Upgrading from older versions:** If you updated via `git pull`, no manual package installation is needed. The system will auto-detect and install missing packages (such as Phoenix) on startup.

## Chat Commands

> The following are **Document Control Sub-Agent** commands. After entering a data display command, Word / Excel export buttons appear automatically below — no separate export command needed.

| Command | Description |
|---------|-------------|
| `help` | Show usage guide |
| `status` | Show system status |
| `document list` | Current formal document versions (with Word/Excel export buttons) |
| `list` | All document records (incl. versions, obsolete) (with Word/Excel export buttons) |
| `search <keyword>` | Search document content |
| `download <doc_id>` | Download original file — all levels 1-4 downloadable, logged to audit trail (e.g., download QP-852) |
| `obsolete <doc_id>` | Obsolete a document (e.g., obsolete OTHER-016) |
| `audit trail` | View audit trail records (with Word/Excel export buttons) |
| `verify` | Verify audit log hash chain integrity and display SHA-256 fingerprints of all key data files for external archiving |
| `regulatory list` | List all referenced regulatory standards (with Word/Excel export buttons) |
| `regulatory update` | Regulatory list latest info assessment and analysis (with Word/Excel export buttons) |
| `download regulatory update word/excel` | Export regulatory update report |
| `download reference word/excel` | Export version reference list |
| `/web <keyword>` | Search the web for latest information (e.g., /web latest ISO 13485 version) |
| `delete database` | Delete all documents (confirmation required) |

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11 |
| UI Framework | Chainlit 2.9.6 |
| Agent Framework | LangGraph |
| LLM Abstraction | LiteLLM |
| OCR Engine | Docling + MarkItDown + LLM Vision |
| LLM Observability | Arize Phoenix |
| Tracing Framework | OpenTelemetry + OpenInference |
| Web Search | DuckDuckGo |
| Local LLM | Ollama |
| HTTP Client | httpx (HTTP/2) |
| Stamp/Seal Detection | OpenCV + NumPy |
| Web Scraping | BeautifulSoup4 + lxml |
| PDF Generation | reportlab |
| Atomic File I/O | safe_io (PermissionError retry) |

---

# 日本語

## プロジェクト概要

**AI-QMS (Eira)** は、**TMBIA-Tmti** が開発した AI 駆動の品質管理システムで、医療機器業界の法規制コンプライアンスニーズに特化して設計されています。**ISO 13485 医療機器品質マネジメントシステム**を基盤とし、AI Agent アーキテクチャを活用して、文書管理、監査証跡、バージョン管理、法規モニタリングなど、労力がかかりリスクの高い品質管理業務のインテリジェント化と自動化を実現しています。

TMBIA-Tmti は、医療機器の法規担当者が品質管理において直面する課題を深く理解しています — 多国間の法規追跡、文書バージョン管理から監査準備まで、あらゆるステップで高い精度が求められ、多大な人的リソースを消費します。AI-QMS (Eira) は、AI にこれらの反復的でエラーに敏感なタスクを委ね、法規専門家がより戦略的価値の高い品質意思決定に集中できるよう開発されました。

本システムは**メイン Agent + サブ Agent** アーキテクチャを採用しており、メイン Agent が品質管理システム全体のモジュールを統括し、文書管理サブ Agent が文書のアップロード、OCR 処理、バージョン検出、署名検証、監査ログなどの業務を担当します。

> **📌 開発状況：Phase 1（文書管理サブ Agent）✅ v3.5.0 完了。Phase 2（監査サブ Agent）🔜 開発中。**

## ロゴデザイン

<p align="center">
  <img src="public/avatars/eira.svg" alt="Eira Logo" width="160" height="160">
</p>

Eira のロゴは、プロジェクトの使命を体現する 2 つのコアシンボルで構成されています：

- **🐍 アスクレピオスの杖（Rod of Asclepius）**（青）— 杖に一匹の蛇が巻きついた、世界最古かつ最も普遍的な医療のシンボル。Eira のコア領域である**医療機器品質管理**を宣言しています。
- **🖊️ 万年筆のペン先（Pen Nib）**（金）— **品質管理システム（QMS）のすべてのプロセス**を象徴しています。文書管理、監査管理、CAPA、不適合管理、設計管理など、QMS のあらゆるプロセスは厳密に記録・管理される必要があります。金色は権威と正式性を表します。Phase 1（文書管理）は完了済み、今後のフェーズで完全な QMS 管理を段階的に実現します。

ロゴでは 2 つのシンボルが**重なり融合**しています。ペン先が蛇杖に触れ、Eira が「医療分野の専門知識」と「品質管理の包括的な管理能力」を統合することを表現しています。


## コア機能

### メイン Agent (Main Agent)
- QMS インテリジェントアシスタント（自然言語対話インターフェース）、20言語 UI 対応
- サブシステム統合オーケストレーションとナビゲーションハブ
- **文書管理サブシステム** — 文書アップロード、OCR、バージョン管理、署名検出、監査証跡、エクスポート
- **監査サブシステム** — CAPA、内部監査、不適合管理（Phase 2 計画中）

### 文書管理サブ Agent (Document Control Sub-Agent) ✅ Phase 1 完了
- **文書アップロードと OCR 処理** — PDF、Word、Excel、PowerPoint、画像に対応
- **Docling 主エンジン + MarkItDown フォールバック** — Docling で PDF テーブル構造復元とレイアウト分析（>100KB ファイル）；MarkItDown 軽量高速（<100KB）；スキャン文書は自動的に LLM Vision にフォールバック
- **インテリジェントバージョン検出** — 新規文書 vs バージョン更新を自動識別、OCR によるバージョン番号スキャン
- **多言語署名・印鑑検出** — 15以上の言語、200以上のキーワードによる署名状態の自動検出
- **改ざん検出監査証跡** — SHA-256 ハッシュチェーンによる全文書操作の記録、不正な変更の検出が可能
- **文書廃止管理** — AI チャットによる文書廃止、監査証跡の完全保持
- **相互参照検出** — バージョン更新後に関連文書を自動検索
- **Markdown ストレージ層** — 文書を Markdown 形式に変換し、Agent 間データ抽出に活用
- **原本ファイルダウンロード** — AI チャットコマンドによる原本ファイルのダウンロード
- **文書一覧エクスポート** — 現行正式版文書一覧を Word/Excel でエクスポート
- **全記録エクスポート** — 全文書記録（版更新・廃止含む）を Word/Excel でエクスポート
- **バージョン差分分析** — バージョン更新後に LLM が新旧バージョンの内容差異を自動比較

### 監査サブ Agent (Audit Sub-Agent) 🔜 開発中
- CAPA（是正・予防措置）管理
- 内部監査スケジュールと追跡
- 不適合管理
- 監査報告書の自動生成

### v3.6.0 新機能
- **SQLite WAL バックエンド** — ACID 保証、JSON ファイルデータベースを置換
- **Docling テーブル解析エンジン** — PDF テーブル構造復元（>100KB）、MarkItDown フォールバック（<100KB）
- **Ollama 自動検出** — ゼロ設定ローカル Embedding
- **Embedding 3段階フォールバック** — BGE-M3 → nomic-embed-text → multilingual-MiniLM
- **デュアルモードタスクディスパッチ** — asyncio (standalone) / Celery (server) 切替
- **LightRAG ナレッジグラフ統合** — 文書横断セマンティック検索基盤

### v3.5.0 新機能（強く推奨されるアップデート）
- **法規地域自動照会** — 指定地域の最新法規情報を取得し、ローカル品質文書とのクロス分析・準拠評価を実施

### v3.4.0 新機能
- **Arize Phoenix 可観測性** — リアルタイム LLM トークン・レイテンシ・コスト追跡
- **ワンクリック起動 + 自動更新** — `start.bat` で Chainlit + Phoenix 同時起動、不足パッケージ自動インストール

### v3.3.0 新機能
- **`/web` ウェブ検索** — `/web キーワード` でウェブ最新情報を取得、ローカル文書と組み合わせて LLM コンテキストとして使用
- **ソース信頼性ランキング** — 検索結果をソース権威性で自動ランキング、医療法規産業に最適：
  - 🏛️ Tier 0（最高）：ISO、FDA、EMA、WHO 等国際標準・法規機関
  - 🏛️ Tier 1：政府ドメイン（.gov、.go.jp 等）
  - 🎓 Tier 2：学術機関（.edu、.ac.uk 等）
  - ✅ Tier 3：認証機関・学術出版社
  - 🌐 Tier 4：一般結果、⬇️ Tier 9：Wikipedia

### v3.2.0 新機能
- **20言語 UI** — 20言語対応のリアルタイム切替

## システムアーキテクチャ

```
┌─────────────────────────────────────────────────────┐
│                  Chainlit UI (Port 3000)             │
│  ┌─────────────────────┐ ┌────────────────────────┐  │
│  │  メイン Agent        │ │  文書管理サブ Agent      │  │
│  │  QMS アシスタント    │ │  Document Control       │  │
│  └─────────────────────┘ └────────────────────────┘  │
│  [ChatSettings: プロバイダー | モデル | API Key]       │
│  [Report UI: /api/report/page/{run_id}]              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│        LLM プロバイダー抽象層 (LiteLLM)               │
│  [OpenAI] [Anthropic] [Google] [Ollama] + 12 more   │
└──────────────┬───────────────────┬──────────────────┘
               │                   │
               │    ┌──────────────┴──────────────────┐
               │    │  LLM 可観測性 (Arize Phoenix)     │
               │    │  OpenTelemetry 自動計装           │
               │    │  ダッシュボード: localhost:6006    │
               │    └─────────────────────────────────┘
               │
┌──────────────┴──────────────────────────────────────┐
│         Agent オーケストレーション (LangGraph)         │
│  Main Agent ──→ Document Control Sub-Agent           │
│                 (Phase 2: 監査サブ Agent 計画中)       │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│       コンプライアンス分析エンジン (Pipeline)          │
│                                                     │
│  Phase 0:   Data Quality Gate (code)                 │
│  Phase 0.5: Reference Mapping (code)                 │
│  Phase 1:   Gap Scan (LLM)                           │
│  Phase 2:   Checklist Verification (LLM)             │
│  Phase 3:   Risk Assessment (rule engine)            │
│  Phase 4:   Remediation Suggestions (LLM)            │
│  Phase 5:   Cross-Examination (LLM, parallel)        │
│  Phase 6:   Source Verification (HTTP)               │
│                                                     │
│  [SSE Real-Time Events] [Pause/Resume/Inject]        │
│  [Daily Audit] [Cross-Ref Validation]                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                OCR 処理層                             │
│  [MarkItDown (主)] ──→ [LLM Vision (フォールバック)]   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                  データ層                             │
│  [JSON DB] [Markdown Storage] [Audit Log]            │
│  [Interaction Log] [CrossExam Store]                  │
│  [Regulatory Storage] [MDSAP Storage]                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│           断線復旧層 (Resilience Layer)                │
│                                                     │
│  [ベースラインレポート] ──→ LLM前 Word/Excel 生成      │
│  [分析キャッシュ]      ──→ 定期保存 + 自動保存         │
│  [ユーザー設定]        ──→ LLM設定の永続化             │
│  [Safe I/O]           ──→ アトミック書込 + リトライ     │
│  [on_chat_end]        ──→ 切断時に自動キャッシュ保存   │
│  [再接続チェック]      ──→ ログイン時に保留レポート表示 │
└─────────────────────────────────────────────────────┘
```

## 対応 LLM プロバイダー (16社)

| タイプ | プロバイダー |
|--------|-------------|
| **クラウド API** | OpenAI, Anthropic, Google, DeepSeek, xAI (Grok), Mistral, Cohere, Perplexity |
| **ゲートウェイ** | OpenRouter, Groq, Together AI, Fireworks AI, Deep Infra, Requesty |
| **ローカル** | Ollama, LM Studio |

## 対応ファイル形式

| カテゴリ | 形式 | 処理方法 |
|----------|------|----------|
| **PDF** | `.pdf` | MarkItDown (主) + LLM Vision (フォールバック) |
| **画像** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tiff`, `.tif`, `.bmp` | MarkItDown + LLM Vision |
| **Word** | `.docx`, `.doc` | python-docx / pywin32 |
| **Excel** | `.xlsx`, `.xls` | openpyxl / pywin32 |
| **PowerPoint** | `.pptx`, `.ppt` | python-pptx / pywin32 |
| **テキスト** | `.txt`, `.md`, `.csv`, `.rtf` | 直接読取 |

> **📝 備考：** すべての対応形式のファイルがアップロード可能で、システムが署名状態を自動検出します。手動作成の文書は署名が必要ですが、システム自動生成の文書は署名不要です。

## ダウンロードとインストール

### 前提条件（初めての方はこちらから）

**ステップ 1：Git のインストール**

Git はソースコードのダウンロードと管理に使用するバージョン管理ツールです。

1. https://git-scm.com/downloads にアクセス
2. お使いの OS（Windows / Mac / Linux）に合ったインストーラーをダウンロード
3. インストーラーを実行し、デフォルト設定のまま「Next」をクリックしてインストール完了

**ステップ 2：Miniconda のインストール（推奨）**

Miniconda は Python 環境マネージャーで、パッケージの競合を避けるために独立した Python 環境を作成できます。

1. https://docs.anaconda.com/miniconda/install/ にアクセス
2. お使いの OS に合ったインストーラーをダウンロード
3. インストーラーを実行し、「Add to PATH」オプションにチェック
4. インストール後、「Anaconda Prompt」を開く（スタートメニューから検索）

> **💡 PowerShell で Conda を使いたい場合：** Anaconda Prompt ではなく PowerShell をお好みの場合、以下の手順を実行してください：
> 1. PowerShell を**管理者として**開く
> 2. `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` を実行（`Y` で確認）
> 3. `conda init powershell` を実行
> 4. **PowerShell を閉じて再度開く** — プロンプトの前に `(base)` が表示されれば、Conda の統合が成功です

> **Miniconda をインストールしない場合：** Python 3.11 を直接インストールできます。https://www.python.org/downloads/ から Python 3.11 をダウンロードし、インストール時に「Add Python to PATH」にチェックを入れてください。

### プロジェクトのダウンロード

**方法1：Git Clone（推奨）**

コマンドプロンプトを開き（`Win + R` を押して `cmd` と入力し Enter）、以下を入力：

```bash
git clone https://github.com/TMBIA-Tmti/AI-QMS.git
cd AI-QMS
```

**方法2：ZIP ダウンロード**

1. このページ上部の緑色の **「Code」** ボタンをクリック
2. **「Download ZIP」** を選択
3. 任意のディレクトリに解凍

## クイックスタート

### 1. Python 環境の作成

Anaconda Prompt（またはコマンドプロンプト）を開き、以下を入力：

> **⚠️ 重要：** 必ず先にプロジェクトフォルダに `cd` してから、Conda 環境の作成と `pip install` を実行してください。そうしないと `requirements.txt` が見つからず、インストールに失敗します。

```bash
cd AI-QMS
conda create --name QMS python=3.11 --yes
conda activate QMS
```

> Miniconda をインストールしていない場合は、Python 3.11 がインストールされていることを確認し、ステップ 2 に進んでください。

> **📋 Conda 利用規約 (TOS)：** Miniconda 25.1.1 以降、初回使用時に利用規約への同意が必要です。`CondaToSNonInteractiveError` エラーが発生した場合は、以下のコマンドを実行してください：
> ```bash
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
> conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
> ```
> **注意：** `start.bat` ランチャースクリプトは TOS の承認を自動的に処理するため、通常は手動で実行する必要はありません。

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. システム起動

```bash
start.bat
```

または Chainlit を直接起動：

```bash
start_chainlit.bat
```

ブラウザが自動的に http://localhost:3000 を開きます。

> **API Key の設定：** 起動後、チャット入力欄の左側にある歯車アイコン（⚙️）をクリックして設定パネルを開き、API Key を直接入力できます。環境変数の設定は不要です。言語切替もこの設定パネルから行えます。

### 4. Phoenix 可観測性の起動（オプション）

LLM 呼び出しトレースとパフォーマンス分析を表示するには：

```bash
start_phoenix.bat
```

または `start.bat` メニューで **[3] Start Chainlit + Phoenix** を選択し、Chainlit と Phoenix を同時に起動します。

Phoenix ダッシュボード：http://localhost:6006

> **旧バージョンからのアップグレード：** `git pull` で更新した場合、手動でのパッケージインストールは不要です。起動時に不足パッケージ（Phoenix など）を自動検出・インストールします。

## チャットコマンド

> 以下は**文書管理サブ Agent (Document Control Sub-Agent)** のコマンドです。データ表示コマンドを入力すると、下に Word / Excel エクスポートボタンが自動的に表示されます。別途エクスポートコマンドを入力する必要はありません。

| コマンド | 説明 |
|----------|------|
| `ヘルプ` / `help` | 使用ガイドを表示 |
| `ステータス` / `status` | システム状態を表示 |
| `文書一覧` | 現行正式版文書（Word/Excel エクスポートボタン付き） |
| `リスト` / `list` | 全記録（版更新・廃止含む）（Word/Excel エクスポートボタン付き） |
| `検索 <キーワード>` | 文書内容を検索 |
| `ダウンロード <文書ID>` | 原本ファイルをダウンロード（例：ダウンロード QP-852） |
| `廃止 <文書ID>` | 文書を廃止（例：廃止 OTHER-016） |
| `監査証跡` | 監査証跡を表示（Word/Excel エクスポートボタン付き） |
| `規制リスト` | 引用規格一覧を表示（Word/Excel エクスポートボタン付き） |
| `法規一覧更新` | 法規リスト最新情報の評価分析（Word/Excel エクスポートボタン付き） |
| `法規更新ダウンロード word/excel` | 法規更新レポートをエクスポート |
| `引用ダウンロード word/excel` | バージョン引用リストをエクスポート |
| `/web <キーワード>` | ウェブ検索で最新情報を取得（例：/web 最新 ISO 13485 バージョン） |
| `データベース削除` | 全文書を削除（確認必要） |

## 技術スタック

| カテゴリ | 技術 |
|----------|------|
| プログラミング言語 | Python 3.11 |
| UI フレームワーク | Chainlit 2.9.6 |
| Agent フレームワーク | LangGraph |
| LLM 抽象層 | LiteLLM |
| OCR エンジン | Docling + MarkItDown + LLM Vision |
| LLM 可観測性 | Arize Phoenix |
| トレースフレームワーク | OpenTelemetry + OpenInference |
| ウェブ検索 | DuckDuckGo |
| ローカル LLM | Ollama |
| HTTP クライアント | httpx (HTTP/2) |
| 印鑑・署名検出 | OpenCV + NumPy |
| ウェブスクレイピング | BeautifulSoup4 + lxml |
| PDF 生成 | reportlab |
| アトミックファイル I/O | safe_io (PermissionError リトライ) |

---

## Directory Structure / 目錄結構 / ディレクトリ構成

```
AI-QMS/
├── README.md                    # This file (中文/English/日本語)
├── LICENSE                      # Apache License 2.0
├── requirements.txt             # Python dependencies
├── start.bat                    # Main launcher / 主啟動腳本
├── start_chainlit.bat           # Chainlit direct launcher (+ Phoenix)
├── start_phoenix.bat            # Phoenix standalone launcher
├── chainlit.md                  # Chainlit welcome message
├── .gitignore
├── .chainlit/                   # Chainlit configuration
│   └── config.toml
├── public/                      # Chainlit public assets
│   ├── avatars/
│   │   └── eira.svg             # Eira AI assistant icon
│   ├── logo_dark.svg            # Dark theme logo
│   └── logo_light.svg           # Light theme logo
├── report_ui/                   # Compliance report web viewer
│   ├── report.html              # Report page template
│   ├── report.js                # Report rendering logic + SSE client
│   ├── report_i18n.js           # Report UI i18n (zh/en/ja)
│   └── report.css               # Report styles
├── src/                         # Source code
│   ├── config.py                # Global configuration
│   ├── llm_providers.py         # 16 LLM provider manager
│   ├── chainlit_app/            # Chainlit application
│   │   ├── app.py               # Main app entry point (v3.5.0)
│   │   ├── i18n.py              # 20-language translations (JSON loader)
│   │   ├── locales/             # i18n JSON locale files
│   │   │   ├── zh-TW.json       # Master locale (Traditional Chinese)
│   │   │   ├── en-US.json       # English
│   │   │   ├── ja-JP.json       # Japanese
│   │   │   └── ... (20 locales) # 20 languages total
│   │   └── handlers/
│   │       └── common.py        # Shared request handlers
│   ├── agents/                  # Agent modules
│   │   └── tools/
│   │       └── documents.py     # LangGraph document tools
│   ├── workflows/               # LangGraph workflows
│   │   └── doc_workflow.py      # Document control workflow
│   ├── ocr/                     # OCR processing
│   │   └── vision_ocr.py        # MarkItDown + Vision OCR
│   ├── analysis/                # Compliance analysis pipeline
│   │   ├── pipeline.py          # 8-phase analysis orchestrator
│   │   ├── pipeline_runner.py   # Pipeline execution manager
│   │   ├── state.py             # Pipeline state model
│   │   ├── data_quality.py      # Phase 0: Data quality gate
│   │   ├── reference_mapper.py  # Phase 0.5: Reference mapping
│   │   ├── gap_scanner.py       # Phase 1: Gap scan (LLM)
│   │   ├── checklist_verifier.py # Phase 2: Checklist verification (LLM)
│   │   ├── risk_matrix.py       # Phase 3: Risk assessment (rule engine)
│   │   ├── remediation.py       # Phase 4: Remediation suggestions (LLM)
│   │   ├── crossexam_qa_agent.py # Phase 5: Cross-examination (LLM)
│   │   ├── source_checker.py    # Phase 6: Source verification (HTTP)
│   │   ├── verifier.py          # Result verification
│   │   ├── comparison_table.py  # Version comparison tables
│   │   ├── compliance_rules.py  # Regulatory compliance rule engine
│   │   ├── report_api.py        # Report API endpoints + SSE
│   │   ├── crossref_report.py   # Cross-reference validation report
│   │   └── daily_audit.py       # Scheduled daily audit runner
│   ├── database/                # Database modules
│   │   ├── audit_log.py         # SHA-256 hash chain audit trail
│   │   ├── document_store.py    # JSON document store
│   │   ├── interaction_log.py   # User interaction logging
│   │   └── crossexam_store.py   # Cross-examination data store
│   ├── storage/                 # Markdown & regulatory storage
│   │   ├── markdown_storage.py  # Document markdown storage
│   │   ├── regulatory_storage.py # Regulatory reference storage
│   │   ├── regulatory_markdown_storage.py  # Regulatory markdown cache
│   │   ├── regulatory_analysis_storage.py  # Analysis result storage
│   │   ├── mdsap_markdown_storage.py       # MDSAP document storage
│   │   └── product_docs_storage.py         # Product document storage
│   ├── services/                # Business logic services
│   │   ├── regulatory_crawler.py    # Regulatory website crawler
│   │   ├── watermark_engine.py      # Watermark detection engine
│   │   ├── watermark_service.py     # Watermark service layer
│   │   ├── obsolete_detector.py     # Document obsolescence detector
│   │   ├── doc_hierarchy.py         # Document hierarchy manager
│   │   └── markdown_store_service.py # Markdown storage service
│   └── utils/                   # Utility modules
│       ├── safe_io.py           # Atomic file I/O + PermissionError retry
│       ├── analysis_cache.py    # Resilient analysis caching (disconnect recovery)
│       ├── user_settings.py     # User/LLM settings persistence
│       ├── audit_export.py      # Audit log Word/Excel export
│       ├── regulatory_export.py # Regulatory/Reference list export
│       ├── regulatory_update_export.py  # Regulatory update export
│       ├── doclist_export.py    # Document list Word/Excel export
│       └── crossexam_export.py  # Cross-examination report export
├── scripts/                     # Utility scripts
│   ├── auto_translate.py        # AI-powered i18n translation
│   ├── inject_missing_translations.py  # Missing translation injector
│   ├── add_i18n_keys.py         # Add new i18n keys
│   ├── extract_i18n.py          # Extract i18n strings from code
│   └── _update_titles.py        # Update locale title fields
├── tests/                       # Test suite (18 files)
│   ├── t2_import_chain.py       # Import chain validation
│   ├── t3_state_serialization.py # State serialization tests
│   ├── t4_comparison_table.py   # Comparison table tests
│   ├── t5_risk_compliance.py    # Risk matrix + compliance rules
│   ├── t6_report_api.py         # Report API endpoint tests
│   ├── t7_stamp_ocr.py          # Stamp/OCR detection tests
│   ├── t8_db_audit.py           # Database + audit trail tests
│   ├── t9_t10_storage_crawler.py # Storage + crawler tests
│   ├── t11_i18n.py              # i18n system tests
│   ├── t12_t13_llm_exports.py   # LLM + export tests
│   ├── t14_t15_storage_cache.py  # Storage + cache tests
│   ├── t16_integration.py        # Integration tests
│   ├── t17_t18_t19_t20_frontend_bat_env.py  # Frontend + env tests
│   ├── t21_assessment_mode.py    # Assessment mode tests
│   ├── t22_crossref_feedback.py  # Cross-ref + feedback tests
│   ├── t23_crossexam_system.py   # Cross-examination tests
│   ├── t24_html_api_integration.py # HTML API integration tests
│   └── t25_extreme_edge_cases.py  # Extreme edge case tests
├── data/                        # Runtime data (auto-generated, not in repo)
│   ├── analysis_cache/          # Resilient report cache (JSON)
│   ├── user_settings/           # Per-user settings (JSON)
│   └── exports/                 # Generated Word/Excel reports
├── uploads/                     # File upload staging (not in repo)
└── markdown_storage/            # Converted Markdown documents (not in repo)
```

## Disclaimer / 免責聲明 / 免責事項

> **❗ 重要聲明：** 本軟體僅供學習與參考用途，**不是**經過驗證的醫療器材品質管理系統軟體。本系統未經任何認證機構驗證，不應作為 ISO 13485 合規性的唯一依據。使用者應自行評估其適用性並承擔使用風險。本軟體的 AI 生成內容（包含法規分析、稽核建議等）僅供參考，不構成專業法律或法規合規建議。
>
> **❗ Important:** This software is provided for learning and reference purposes only and is **not** a validated medical device quality management system. It has not been verified by any certification body and should not be relied upon as the sole basis for ISO 13485 compliance. Users should evaluate its suitability and assume all risks of use. AI-generated content (including regulatory analysis, audit suggestions, etc.) is for reference only and does not constitute professional legal or regulatory compliance advice.
>
> **❗ 重要：** 本ソフトウェアは学習および参考目的でのみ提供されており、検証済みの医療機器品質管理システムソフトウェアでは**ありません**。認証機関による検証は行われておらず、ISO 13485 準拠の唯一の根拠として使用しないでください。ユーザーはその適用性を自ら評価し、使用におけるすべてのリスクを負うものとします。AI 生成コンテンツ（法規分析、監査提案等）は参考情報であり、専門的な法律または法規準拠に関する助言を構成するものではありません。

## Trademark Notice / 商標聲明 / 商標について

All product names, trademarks, and registered trademarks mentioned in this document are the property of their respective owners. Their use here is for identification purposes only and does not imply endorsement by or affiliation with any trademark holder.

- Microsoft®, Word®, Excel®, PowerPoint® are registered trademarks of Microsoft Corporation.
- Python® is a registered trademark of the Python Software Foundation.
- ISO® is a registered trademark of the International Organization for Standardization.
- OpenAI®, Anthropic™, Google™, and other LLM provider names are trademarks of their respective companies.
- Chainlit, LangGraph, LiteLLM, Arize Phoenix, OpenTelemetry, DuckDuckGo, Ollama, LM Studio, Miniconda, Anaconda, Git, and GitHub are trademarks or registered trademarks of their respective owners.
- FDA, EMA, WHO, PMDA, NMPA, and TFDA are government agencies. Mention of these agencies does not imply endorsement of this software.

本文件中所提及的所有產品名稱、商標及註冊商標均為其各自所有者的財產。此處僅為識別目的而使用，不代表任何商標持有人的背書或關聯。

本書に記載されているすべての製品名、商標、登録商標は、それぞれの所有者の財産です。ここでの使用は識別目的のみであり、商標所有者による推奨や提携を意味するものではありません。

## License / 授權 / ライセンス

This project is licensed under the [Apache License 2.0](LICENSE).

Copyright 2026 AI-QMS Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
