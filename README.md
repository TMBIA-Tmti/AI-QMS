# AI-QMS: AI-Powered Quality Management System for Medical Devices

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

**AI-QMS** 是一套依據 **ISO 13485 醫療器材品質管理系統**標準需求所開發的 AI 智慧品質管理系統。本系統考量醫療器材 QMS 的實際運作需求，運用 AI Agent 架構實現文件管制、稽核追蹤、版本控制等核心品質管理功能的智慧化與自動化。

系統採用**主 Agent + 子 Agent** 架構設計，由主 Agent 統籌品質管理系統各模組，文件管制子 Agent 負責文件的上傳、OCR 辨識、版本偵測、簽章驗證及稽核紀錄等作業。

> **📌 開發進度：Phase 1（文件管制子 Agent）已完成，即將開始製作 Phase 2（稽核子 Agent）。**

## 核心功能

### 主 Agent (Main Agent)
- QMS 品質管理系統智慧助手，自然語言對話介面，支援 20 國語言 UI
- 子系統統一調度與導航入口
- **文件管制子系統** — 文件上傳、OCR、版本管理、簽章偵測、稽核紀錄、匯出
- **稽核子系統** — CAPA、內部稽核、不符合事項管理（Phase 2 規劃中）

### 文件管制子 Agent (Document Control Sub-Agent) ✅ Phase 1 完成
- **文件上傳與 OCR 處理** — 支援 PDF、Word、Excel、PowerPoint、圖片等格式
- **MarkItDown-First OCR 引擎** — 本地處理 ~1 秒/檔案，零 Token 消耗；掃描文件自動切換 LLM Vision 備援
- **智慧版本偵測** — 自動識別新文件 vs 版本更新，OCR 掃描文件內版本號
- **多語言簽章/印章偵測** — 支援 15+ 語言、200+ 關鍵字自動偵測簽章狀態
- **防竄改稽核紀錄** — SHA-256 雜湊鏈，完整記錄所有文件操作
- **文件作廢管理** — 透過 AI 對話作廢文件，保留稽核追蹤
- **交叉引用偵測** — 版本更新後自動搜尋引用該文件的關聯文件
- **Markdown 儲存層** — 轉換文件為 Markdown 格式，供跨 Agent 資料提取
- **原始檔案下載** — 透過 AI 對話指令下載原始文件
- **文件清單匯出** — 現行正式版本文件清單匯出為 Word/Excel
- **全部文件紀錄匯出** — 所有文件紀錄（含進版、作廢）匯出為 Word/Excel
- **進版差異比對** — 版本更新後 LLM 自動比對新舊版本內容差異

### 稽核子 Agent (Audit Sub-Agent) 🔜 Phase 2 規劃中
- CAPA（矯正與預防措施）管理
- 內部稽核排程與追蹤
- 不符合事項管理
- 稽核報告自動生成

### v3.4.0 新增功能
- **Arize Phoenix LLM 可觀測性** — 整合 Phoenix 後台，即時追蹤所有 LLM 呼叫的 Token 用量、延遲、成本
- **OpenTelemetry 自動追蹤** — 透過 `LiteLLMInstrumentor` 零程式碼變更自動擷取所有 LLM 請求
- **Phoenix Dashboard** — 可在 http://localhost:6006 查看所有 LLM 互動追蹤記錄
- **多 Agent 追蹤分離** — 支援 Phoenix Projects 區分不同子 Agent 的追蹤資料
- **一鍵啟動 Chainlit + Phoenix** — `start.bat` 選單選項 [3] 同時啟動 Chainlit UI 與 Phoenix 可觀測性後台
- **自動套件更新** — 舊使用者 `git pull` 後啟動時自動偵測並安裝缺少的新套件，無需手動 `pip install`
- **Port 自動切換** — 啟動時自動偵測 Chainlit (3000) 和 Phoenix (6006) 預設 port 是否被佔用，若被佔用自動切換至下一個可用 port 並顯示提示

### v3.3.0 新增功能
- **`/web` 網路搜尋指令** — 使用 `/web 關鍵字` 搜尋網路取得最新資訊（如：`/web 最新 ISO 13485 版本`），搜尋結果結合本地文件資料庫作為 LLM 上下文
- **DuckDuckGo 搜尋引擎** — 免費、無需 API Key 的網路搜尋整合
- **雙重上下文** — `/web` 指令同時搜尋網路與本地 Markdown DB，提供完整來源引用
- **來源可信度排序 (Source Credibility Ranking)** — 搜尋結果依來源權威性自動排序，醫療法規產業特別適用：
  - 🏛️ Tier 0（最高）：ISO、FDA、EMA、WHO、PMDA、NMPA、TFDA 等國際標準與法規機構官方網站
  - 🏛️ Tier 1：政府網域（.gov、.go.jp、.gov.tw 等）
  - 🎓 Tier 2：學術機構（.edu、.ac.uk 等）
  - ✅ Tier 3：驗證機構（TÜV、BSI、SGS 等）、學術出版商（PubMed、Nature、Lancet 等）
  - 🌐 Tier 4：一般搜尋結果
  - ⬇️ Tier 9（最低）：Wikipedia（降低優先權）

### v3.2.0 新增功能
- **20 國語言 UI 介面** — 支援繁體中文、簡體中文、英文、日文、韓文、法文、德文、西班牙文、葡萄牙文、義大利文、俄文、阿拉伯文、印地文、泰文、越南文、印尼文、馬來文、土耳其文、荷蘭文、波蘭文，可在設定中即時切換
- **API Key 安全遮罩** — API Key 輸入後自動隱藏（僅顯示末 4 碼），可透過開關切換顯示/隱藏
- **語言選擇器** — ChatSettings 設定面板新增語言選擇，所有 UI 文字即時切換

## 系統架構

```
┌─────────────────────────────────────────────────────┐
│                  Chainlit UI (Port 3000)             │
│  ┌─────────────────────┐ ┌────────────────────────┐  │
│  │  Profile: 主系統     │ │  Profile: 文件管制      │  │
│  │  Main Agent         │ │  Doc Control Sub-Agent  │  │
│  └─────────────────────┘ └────────────────────────┘  │
│  [ChatSettings: Provider | Model | API Key]          │
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
│              OCR 處理層                               │
│  [MarkItDown (主)] ──→ [LLM Vision (備援)]            │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                   資料層                              │
│  [JSON DB] [Markdown Storage] [Audit Log]            │
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
| **圖片** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tiff`, `.bmp` | MarkItDown (主) + LLM Vision (備援) |
| **Word** | `.docx`, `.doc` | python-docx / pywin32 |
| **Excel** | `.xlsx`, `.xls` | openpyxl / pywin32 |
| **PowerPoint** | `.pptx`, `.ppt` | python-pptx / pywin32 |
| **文字** | `.txt`, `.md`, `.csv`, `.rtf` | 直接讀取 |

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

> **API Key 設定：** 啟動後在應用程式右上角的設定面板中直接輸入 API Key，無需設定環境變數。

### 4. 啟動 Phoenix 可觀測性（選用）

如需查看 LLM 呼叫追蹤與效能分析：

```bash
start_phoenix.bat
```

或在 `start.bat` 選單中選擇 **[3] Start Chainlit + Phoenix**，同時啟動 Chainlit 和 Phoenix。

Phoenix Dashboard：http://localhost:6006

> **舊使用者升級：** 如果您是透過 `git pull` 更新的舊使用者，無需手動安裝新套件。系統會在啟動時自動偵測並安裝缺少的套件（如 Phoenix）。

## 對話指令

| 指令 | 說明 |
|------|------|
| `幫助` / `help` | 顯示使用指南 |
| `狀態` / `status` | 顯示系統狀態 |
| `文件清單` | 現行正式版本文件 |
| `列表` / `list` | 所有文件紀錄（含進版、作廢） |
| `搜尋 <關鍵字>` | 搜尋文件內容 |
| `下載 <文件編號>` | 下載原始文件（如：下載 QP-852） |
| `作廢 <文件編號>` | 作廢文件（如：作廢 OTHER-016） |
| `文件更動紀錄` | 查看文件更動紀錄 |
| `下載文件更動紀錄 word` | 匯出文件更動紀錄為 .docx |
| `下載文件更動紀錄 excel` | 匯出文件更動紀錄為 .xlsx |
| `法規清單` | 列出所有引用的法規標準 |
| `下載法規清單 word/excel` | 匯出法規清單 |
| `下載引用清單 word/excel` | 匯出進版引用清單 |
| `下載文件清單 word/excel` | 匯出文件清單（現行正式版本） |
| `下載列表 word/excel` | 匯出所有文件紀錄（含進版、作廢） |
| `/web <關鍵字>` | 搜尋網路取得最新資訊（如：/web 最新 ISO 13485 版本） |
| `刪除資料庫` | 刪除所有文件（需確認） |

## 技術堆疊

| 類別 | 技術 |
|------|------|
| 程式語言 | Python 3.11 |
| UI 框架 | Chainlit 2.9.6 |
| Agent 框架 | LangGraph |
| LLM 抽象層 | LiteLLM |
| OCR 引擎 | MarkItDown + LLM Vision |
| LLM 可觀測性 | Arize Phoenix |
| 追蹤框架 | OpenTelemetry + OpenInference |
| 網路搜尋 | DuckDuckGo |
| 本地 LLM | Ollama |

---

# English

## Project Overview

**AI-QMS** is an AI-powered Quality Management System developed based on the requirements of **ISO 13485 Medical Device Quality Management System**. The system is designed to address the practical operational needs of medical device QMS, leveraging AI Agent architecture to automate and intelligently manage core quality functions including document control, audit trails, and version management.

The system adopts a **Main Agent + Sub-Agent** architecture, where the Main Agent orchestrates all QMS modules, and the Document Control Sub-Agent handles document upload, OCR processing, version detection, signature verification, and audit logging.

> **📌 Development Status: Phase 1 (Document Control Sub-Agent) is complete. Phase 2 (Audit Sub-Agent) is coming next.**

## Core Features

### Main Agent
- Intelligent QMS assistant with natural language interface, 20-language UI support
- Unified sub-system orchestration and navigation hub
- **Document Control Sub-System** — Document upload, OCR, version management, signature detection, audit trail, export
- **Audit Sub-System** — CAPA, internal audit, non-conformance management (Phase 2 Planned)

### Document Control Sub-Agent ✅ Phase 1 Complete
- **Document Upload & OCR** — Supports PDF, Word, Excel, PowerPoint, images
- **MarkItDown-First OCR Engine** — Local processing ~1s/file, zero token cost; auto-fallback to LLM Vision for scanned documents
- **Intelligent Version Detection** — Auto-detect new document vs. version update, OCR-based version number scanning
- **Multilingual Signature/Stamp Detection** — 15+ languages, 200+ keywords for automatic signature status detection
- **Tamper-Proof Audit Trail** — SHA-256 hash chain recording all document operations
- **Document Obsolescence** — Obsolete documents via AI chat with full audit trail preservation
- **Cross-Reference Detection** — Auto-search for related documents after version updates
- **Markdown Storage Layer** — Convert documents to Markdown for cross-agent data extraction
- **Original File Download** — Download original files via AI chat commands
- **Document List Export** — Export current formal document list as Word/Excel
- **All Records Export** — Export all document records (incl. versions, obsolete) as Word/Excel
- **Version Diff Analysis** — LLM auto-compares old and new version content after version updates

### Audit Sub-Agent 🔜 Phase 2 Planned
- CAPA (Corrective and Preventive Actions) management
- Internal audit scheduling and tracking
- Non-conformance management
- Automated audit report generation

### v3.4.0 New Features
- **Arize Phoenix LLM Observability** — Integrated Phoenix backend for real-time tracking of all LLM call token usage, latency, and cost
- **OpenTelemetry Auto-Instrumentation** — Zero code change auto-capture of all LLM requests via `LiteLLMInstrumentor`
- **Phoenix Dashboard** — View all LLM interaction traces at http://localhost:6006
- **Multi-Agent Trace Separation** — Phoenix Projects support for isolating traces from different sub-agents
- **One-Click Chainlit + Phoenix Launch** — `start.bat` menu option [3] launches both Chainlit UI and Phoenix observability backend simultaneously
- **Auto Dependency Update** — Existing users who `git pull` will have missing packages auto-detected and installed on startup, no manual `pip install` needed
- **Auto Port Switching** — On startup, automatically detects if default ports for Chainlit (3000) and Phoenix (6006) are occupied, and seamlessly switches to the next available port with a notification

### v3.3.0 New Features
- **`/web` Web Search Command** — Use `/web keyword` to search the web for the latest information (e.g., `/web latest ISO 13485 version`). Results are combined with local document database as LLM context
- **DuckDuckGo Search Engine** — Free, no API key required web search integration
- **Dual Context** — `/web` command simultaneously searches the web and local Markdown DB, providing complete source citations
- **Source Credibility Ranking** — Search results are automatically ranked by source authority, a game-changer for regulated industries:
  - 🏛️ Tier 0 (Highest): ISO, FDA, EMA, WHO, PMDA, NMPA, TFDA and other international standards/regulatory body official sites
  - 🏛️ Tier 1: Government domains (.gov, .go.jp, .gov.tw, etc.)
  - 🎓 Tier 2: Academic institutions (.edu, .ac.uk, etc.)
  - ✅ Tier 3: Certification bodies (TÜV, BSI, SGS, etc.), academic publishers (PubMed, Nature, Lancet, etc.)
  - 🌐 Tier 4: General results
  - ⬇️ Tier 9 (Lowest): Wikipedia (deprioritized)

### v3.2.0 New Features
- **20-Language UI** — Supports Traditional Chinese, Simplified Chinese, English, Japanese, Korean, French, German, Spanish, Portuguese, Italian, Russian, Arabic, Hindi, Thai, Vietnamese, Indonesian, Malay, Turkish, Dutch, Polish. Switch languages in real-time via settings
- **API Key Security Masking** — API Key is automatically masked after input (shows only last 4 characters). Toggle show/hide with a switch
- **Language Selector** — New language selector in ChatSettings panel for instant UI language switching

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Chainlit UI (Port 3000)             │
│  ┌─────────────────────┐ ┌────────────────────────┐  │
│  │  Profile: Main Agent│ │  Profile: Doc Control   │  │
│  │  QMS Assistant      │ │  Document Management    │  │
│  └─────────────────────┘ └────────────────────────┘  │
│  [ChatSettings: Provider | Model | API Key]          │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│        LLM Provider Abstraction (LiteLLM)            │
│  [OpenAI] [Anthropic] [Google] [Ollama] + 12 more   │
└──────────────┬───────────────────┬──────────────────┘
               │                   │
               │    ┌──────────────┴──────────────────┐
               │    │  LLM Observability (Arize Phoenix)│
               │    │  OpenTelemetry Auto-Instrument    │
               │    │  Dashboard: http://localhost:6006 │
               │    └─────────────────────────────────┘
               │
┌──────────────┴──────────────────────────────────────┐
│          Agent Orchestration (LangGraph)              │
│  Main Agent ──→ Document Control Sub-Agent           │
│                 (Phase 2: Audit Sub-Agent planned)    │
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
| **Images** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tiff`, `.bmp` | MarkItDown + LLM Vision |
| **Word** | `.docx`, `.doc` | python-docx / pywin32 |
| **Excel** | `.xlsx`, `.xls` | openpyxl / pywin32 |
| **PowerPoint** | `.pptx`, `.ppt` | python-pptx / pywin32 |
| **Text** | `.txt`, `.md`, `.csv`, `.rtf` | Direct read |

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

> **API Key Setup:** After launch, enter your API Key directly in the settings panel (top-right corner of the app). No environment variables needed.

### 4. Launch Phoenix Observability (Optional)

To view LLM call traces and performance analytics:

```bash
start_phoenix.bat
```

Or select **[3] Start Chainlit + Phoenix** from the `start.bat` menu to launch both Chainlit and Phoenix simultaneously.

Phoenix Dashboard: http://localhost:6006

> **Upgrading from older versions:** If you updated via `git pull`, no manual package installation is needed. The system will auto-detect and install missing packages (such as Phoenix) on startup.

## Chat Commands

| Command | Description |
|---------|-------------|
| `help` | Show usage guide |
| `status` | Show system status |
| `document list` | Current formal document versions |
| `list` | All document records (incl. versions, obsolete) |
| `search <keyword>` | Search document content |
| `download <doc_id>` | Download original file (e.g., download QP-852) |
| `obsolete <doc_id>` | Obsolete a document (e.g., obsolete OTHER-016) |
| `audit trail` | View audit trail records |
| `download audit word` | Export audit trail as .docx |
| `download audit excel` | Export audit trail as .xlsx |
| `regulatory list` | List all referenced regulatory standards |
| `download regulatory word/excel` | Export regulatory list |
| `download reference word/excel` | Export version reference list |
| `download doclist word/excel` | Export document list (current formal versions) |
| `download all records word/excel` | Export all document records (incl. versions, obsolete) |
| `/web <keyword>` | Search the web for latest information (e.g., /web latest ISO 13485 version) |
| `delete database` | Delete all documents (confirmation required) |

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11 |
| UI Framework | Chainlit 2.9.6 |
| Agent Framework | LangGraph |
| LLM Abstraction | LiteLLM |
| OCR Engine | MarkItDown + LLM Vision |
| LLM Observability | Arize Phoenix |
| Tracing Framework | OpenTelemetry + OpenInference |
| Web Search | DuckDuckGo |
| Local LLM | Ollama |

---

# 日本語

## プロジェクト概要

**AI-QMS** は、**ISO 13485 医療機器品質マネジメントシステム**の要求事項に基づいて開発された AI 搭載品質管理システムです。医療機器 QMS の実際の運用ニーズを考慮し、AI Agent アーキテクチャを活用して、文書管理、監査証跡、バージョン管理などのコア品質管理機能のインテリジェント化と自動化を実現しています。

本システムは**メイン Agent + サブ Agent** アーキテクチャを採用しており、メイン Agent が品質管理システム全体のモジュールを統括し、文書管理サブ Agent が文書のアップロード、OCR 処理、バージョン検出、署名検証、監査ログなどの業務を担当します。

> **📌 開発状況：Phase 1（文書管理サブ Agent）完了。Phase 2（監査サブ Agent）の開発を開始予定。**

## コア機能

### メイン Agent (Main Agent)
- QMS インテリジェントアシスタント（自然言語対話インターフェース）、20言語 UI 対応
- サブシステム統合オーケストレーションとナビゲーションハブ
- **文書管理サブシステム** — 文書アップロード、OCR、バージョン管理、署名検出、監査証跡、エクスポート
- **監査サブシステム** — CAPA、内部監査、不適合管理（Phase 2 計画中）

### 文書管理サブ Agent (Document Control Sub-Agent) ✅ Phase 1 完了
- **文書アップロードと OCR 処理** — PDF、Word、Excel、PowerPoint、画像に対応
- **MarkItDown-First OCR エンジン** — ローカル処理 約1秒/ファイル、トークン消費ゼロ；スキャン文書は自動的に LLM Vision にフォールバック
- **インテリジェントバージョン検出** — 新規文書 vs バージョン更新を自動識別、OCR によるバージョン番号スキャン
- **多言語署名・印鑑検出** — 15以上の言語、200以上のキーワードによる署名状態の自動検出
- **改ざん防止監査証跡** — SHA-256 ハッシュチェーンによる全文書操作の記録
- **文書廃止管理** — AI チャットによる文書廃止、監査証跡の完全保持
- **相互参照検出** — バージョン更新後に関連文書を自動検索
- **Markdown ストレージ層** — 文書を Markdown 形式に変換し、Agent 間データ抽出に活用
- **原本ファイルダウンロード** — AI チャットコマンドによる原本ファイルのダウンロード
- **文書一覧エクスポート** — 現行正式版文書一覧を Word/Excel でエクスポート
- **全記録エクスポート** — 全文書記録（版更新・廃止含む）を Word/Excel でエクスポート
- **バージョン差分分析** — バージョン更新後に LLM が新旧バージョンの内容差異を自動比較

### 監査サブ Agent (Audit Sub-Agent) 🔜 Phase 2 計画中
- CAPA（是正・予防措置）管理
- 内部監査スケジュールと追跡
- 不適合管理
- 監査報告書の自動生成

### v3.4.0 新機能
- **Arize Phoenix LLM 可観測性** — Phoenix バックエンドを統合し、全 LLM 呼び出しのトークン使用量、レイテンシ、コストをリアルタイム追跡
- **OpenTelemetry 自動計装** — `LiteLLMInstrumentor` によるコード変更ゼロの全 LLM リクエスト自動キャプチャ
- **Phoenix ダッシュボード** — http://localhost:6006 で全 LLM インタラクショントレースを確認可能
- **マルチ Agent トレース分離** — Phoenix Projects により異なるサブ Agent のトレースデータを分離可能
- **ワンクリック Chainlit + Phoenix 起動** — `start.bat` メニューオプション [3] で Chainlit UI と Phoenix 可観測性バックエンドを同時起動
- **自動依存パッケージ更新** — `git pull` 後の起動時に不足パッケージを自動検出・インストール、手動 `pip install` 不要
- **Port 自動切替** — 起動時に Chainlit (3000) と Phoenix (6006) のデフォルトポートの使用状況を自動検出し、使用中の場合は次の空きポートへ自動切替（通知付き）

### v3.3.0 新機能
- **`/web` ウェブ検索コマンド** — `/web キーワード` でウェブを検索して最新情報を取得（例：`/web 最新 ISO 13485 バージョン`）。検索結果をローカル文書データベースと組み合わせて LLM コンテキストとして使用
- **DuckDuckGo 検索エンジン** — 無料、API Key 不要のウェブ検索統合
- **デュアルコンテキスト** — `/web` コマンドでウェブとローカル Markdown DB を同時検索し、完全なソース引用を提供
- **ソース信頼性ランキング (Source Credibility Ranking)** — 検索結果をソースの権威性で自動ランキング。規制産業に最適：
  - 🏛️ Tier 0（最高）：ISO、FDA、EMA、WHO、PMDA、NMPA、TFDA など国際標準・規制当局の公式サイト
  - 🏛️ Tier 1：政府ドメイン（.gov、.go.jp、.gov.tw など）
  - 🎓 Tier 2：学術機関（.edu、.ac.uk など）
  - ✅ Tier 3：認証機関（TÜV、BSI、SGS など）、学術出版社（PubMed、Nature、Lancet など）
  - 🌐 Tier 4：一般的な検索結果
  - ⬇️ Tier 9（最低）：Wikipedia（優先度低）

### v3.2.0 新機能
- **20言語 UI 対応** — 繁体字中国語、簡体字中国語、英語、日本語、韓国語、フランス語、ドイツ語、スペイン語、ポルトガル語、イタリア語、ロシア語、アラビア語、ヒンディー語、タイ語、ベトナム語、インドネシア語、マレー語、トルコ語、オランダ語、ポーランド語に対応。設定でリアルタイム切替可能
- **API Key セキュリティマスク** — API Key 入力後に自動マスク（末尾4文字のみ表示）。スイッチで表示/非表示を切替可能
- **言語セレクター** — ChatSettings パネルに言語セレクターを追加、UI 言語の即時切替に対応

## システムアーキテクチャ

```
┌─────────────────────────────────────────────────────┐
│                  Chainlit UI (Port 3000)             │
│  ┌─────────────────────┐ ┌────────────────────────┐  │
│  │  メイン Agent        │ │  文書管理サブ Agent      │  │
│  │  QMS アシスタント    │ │  Document Control       │  │
│  └─────────────────────┘ └────────────────────────┘  │
│  [ChatSettings: プロバイダー | モデル | API Key]       │
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
│                OCR 処理層                             │
│  [MarkItDown (主)] ──→ [LLM Vision (フォールバック)]   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                  データ層                             │
│  [JSON DB] [Markdown Storage] [Audit Log]            │
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
| **画像** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tiff`, `.bmp` | MarkItDown + LLM Vision |
| **Word** | `.docx`, `.doc` | python-docx / pywin32 |
| **Excel** | `.xlsx`, `.xls` | openpyxl / pywin32 |
| **PowerPoint** | `.pptx`, `.ppt` | python-pptx / pywin32 |
| **テキスト** | `.txt`, `.md`, `.csv`, `.rtf` | 直接読取 |

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

> **API Key の設定：** 起動後、アプリケーション右上の設定パネルで API Key を直接入力できます。環境変数の設定は不要です。

### 4. Phoenix 可観測性の起動（オプション）

LLM 呼び出しトレースとパフォーマンス分析を表示するには：

```bash
start_phoenix.bat
```

または `start.bat` メニューで **[3] Start Chainlit + Phoenix** を選択し、Chainlit と Phoenix を同時に起動します。

Phoenix ダッシュボード：http://localhost:6006

> **旧バージョンからのアップグレード：** `git pull` で更新した場合、手動でのパッケージインストールは不要です。起動時に不足パッケージ（Phoenix など）を自動検出・インストールします。

## チャットコマンド

| コマンド | 説明 |
|----------|------|
| `ヘルプ` / `help` | 使用ガイドを表示 |
| `ステータス` / `status` | システム状態を表示 |
| `文書一覧` | 現行正式版文書 |
| `リスト` / `list` | 全記録（版更新・廃止含む） |
| `検索 <キーワード>` | 文書内容を検索 |
| `ダウンロード <文書ID>` | 原本ファイルをダウンロード（例：ダウンロード QP-852） |
| `廃止 <文書ID>` | 文書を廃止（例：廃止 OTHER-016） |
| `監査証跡` | 監査証跡を表示 |
| `監査証跡ダウンロード word` | 監査ログを .docx でエクスポート |
| `監査証跡ダウンロード excel` | 監査ログを .xlsx でエクスポート |
| `規制リスト` | 引用規格一覧を表示 |
| `規制リストダウンロード word/excel` | 規格リストをエクスポート |
| `引用ダウンロード word/excel` | バージョン引用リストをエクスポート |
| `文書一覧ダウンロード word/excel` | 文書一覧をエクスポート（現行正式版） |
| `全記録ダウンロード word/excel` | 全文書記録をエクスポート（版更新・廃止含む） |
| `/web <キーワード>` | ウェブ検索で最新情報を取得（例：/web 最新 ISO 13485 バージョン） |
| `データベース削除` | 全文書を削除（確認必要） |

## 技術スタック

| カテゴリ | 技術 |
|----------|------|
| プログラミング言語 | Python 3.11 |
| UI フレームワーク | Chainlit 2.9.6 |
| Agent フレームワーク | LangGraph |
| LLM 抽象層 | LiteLLM |
| OCR エンジン | MarkItDown + LLM Vision |
| LLM 可観測性 | Arize Phoenix |
| トレースフレームワーク | OpenTelemetry + OpenInference |
| ウェブ検索 | DuckDuckGo |
| ローカル LLM | Ollama |

---

## Directory Structure / 目錄結構 / ディレクトリ構成

```
AI-QMS/
├── README.md                    # This file (中文/English/日本語)
├── requirements.txt             # Python dependencies
├── start.bat                    # Main launcher / 主啟動腳本
├── start_chainlit.bat           # Chainlit direct launcher (+ Phoenix)
├── start_phoenix.bat            # Phoenix standalone launcher
├── chainlit.md                  # Chainlit welcome message
├── .gitignore
├── .chainlit/                   # Chainlit configuration
│   └── config.toml
├── public/                      # Chainlit public assets
│   ├── main_agent.svg
│   └── doc_control.svg
├── src/                         # Source code
│   ├── chainlit_app/            # Chainlit application
│   │   ├── app.py               # Main app entry point (v3.4.0)
│   │   ├── i18n.py              # 20-language translations
│   │   └── handlers/
│   ├── agents/                  # Agent modules
│   │   └── tools/               # LangGraph tools
│   ├── workflows/               # LangGraph workflows
│   ├── ocr/                     # OCR processing
│   │   └── vision_ocr.py        # MarkItDown + Vision OCR
│   ├── database/                # Database modules
│   │   ├── audit_log.py         # SHA-256 audit trail
│   │   └── document_store.py
│   ├── storage/                 # Markdown storage
│   │   └── markdown_storage.py
│   ├── services/
│   ├── utils/
│   │   ├── audit_export.py      # Audit log Word/Excel export
│   │   ├── regulatory_export.py # Regulatory/Reference list export
│   │   └── doclist_export.py    # Document list Word/Excel export
│   ├── config.py
│   └── llm_providers.py         # 16 LLM provider manager
├── data/                        # Runtime data (auto-generated)
├── uploads/                     # File upload staging
└── markdown_storage/            # Converted Markdown documents
```

## License / 授權 / ライセンス

This project is licensed under the [Apache License 2.0](LICENSE).

Copyright 2026 AI-QMS Project

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
