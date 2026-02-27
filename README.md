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
- **防竄改偵測稽核紀錄** — SHA-256 雜湊鏈，完整記錄所有文件操作，可偵測未經授權的變更
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

### v3.5.0 新增功能（強烈建議更新）
- **法規地區自動查詢** — 選擇追蹤地區後自動清除非選取地區資料，舊版自動替換為新版

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
| `下載 <文件編號>` | 下載原始文件（如：下載 QP-852） |
| `作廢 <文件編號>` | 作廢文件（如：作廢 OTHER-016） |
| `文件更動紀錄` | 查看文件更動紀錄（附 Word/Excel 匯出按鈕） |
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
- **Tamper-Evident Audit Trail** — SHA-256 hash chain recording all document operations, enabling detection of unauthorized changes
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

### v3.5.0 New Features (Strongly Recommended Update)
- **Regulatory Region Auto-Query** — Auto-cleans non-selected region data, auto-replaces old versions with new

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
| `download <doc_id>` | Download original file (e.g., download QP-852) |
| `obsolete <doc_id>` | Obsolete a document (e.g., obsolete OTHER-016) |
| `audit trail` | View audit trail records (with Word/Excel export buttons) |
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
- **改ざん検出監査証跡** — SHA-256 ハッシュチェーンによる全文書操作の記録、不正な変更の検出が可能
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

### v3.5.0 新機能（強く推奨されるアップデート）
- **法規地域自動照会** — 非選択地域のデータを自動削除、旧バージョンを新バージョンに自動置換

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
│   │   ├── app.py               # Main app entry point (v3.5.0)
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
