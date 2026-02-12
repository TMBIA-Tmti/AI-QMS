# AI-QMS Document Control - 環境設定指南

**Python 版本**: 3.11  
**Conda 環境名稱**: QMS  
**UI 框架**: Chainlit

---

## 1. 建立 Conda 環境

### 方法一：使用 Anaconda Prompt (推薦)

開啟 **Anaconda Prompt** (以系統管理員身分執行)，輸入以下指令：

```bash
# 建立 QMS 環境，指定 Python 3.11
conda create --name QMS python=3.11 --yes

# 確認環境已建立
conda env list
```

### 方法二：使用 PowerShell

```powershell
# 初始化 conda (若尚未初始化)
conda init powershell

# 重新開啟 PowerShell 後
conda create --name QMS python=3.11 --yes
```

---

## 2. 啟動環境

### 在 Anaconda Prompt 中

```bash
# 啟動 QMS 環境
conda activate QMS

# 確認 Python 版本
python --version
# 應顯示: Python 3.11.x
```

### 在 PowerShell 中

```powershell
# 啟動 QMS 環境
conda activate QMS

# 若出現錯誤，先執行
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 3. 安裝依賴套件

啟動 QMS 環境後，進入專案目錄並安裝依賴：

```bash
# 進入專案目錄 (替換為你的實際路徑)
cd path/to/AI-QMS

# 安裝依賴
pip install -r requirements.txt
```

### 主要依賴套件

| 套件 | 用途 |
|------|------|
| chainlit | Chat-based UI 框架 |
| litellm | LLM 統一抽象層 (16+ Provider) |
| markitdown | OCR 引擎 (PDF/Word/Excel → Markdown) |
| python-docx | Word 文件匯出 |
| openpyxl | Excel 文件匯出 |

---

## 4. 啟動系統

### 方法一：使用 start.bat (推薦)

直接雙擊專案根目錄的 `start.bat`，會自動偵測 Conda 環境並啟動系統。

### 方法二：手動啟動

```bash
# 啟動 QMS 環境
conda activate QMS

# 進入專案目錄
cd path/to/AI-QMS

# 啟動 Chainlit App
python -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0
```

### 方法三：使用 start_chainlit.bat

雙擊 `start_chainlit.bat` 快速啟動 Chainlit。

---

## 5. 存取系統

啟動後，開啟瀏覽器訪問：

```
http://localhost:3000
```

系統為 Chainlit Chat 介面，提供兩個 Chat Profile：
- **主系統 (Main Agent)** — LLM 智慧問答
- **文件管制 (Doc Control)** — 文件上傳、版本管理、法規清單

首次使用需透過齒輪按鈕設定 LLM Provider 和 API Key。

---

## 6. 常見問題

### Q1: conda activate 無法使用

```powershell
# 執行初始化
conda init powershell

# 重新開啟 PowerShell
```

### Q2: pip install 失敗

```bash
# 升級 pip
python -m pip install --upgrade pip

# 重新安裝
pip install -r requirements.txt
```

### Q3: 編碼錯誤 (UnicodeDecodeError)

```powershell
# 設定 UTF-8
chcp 65001
$env:PYTHONIOENCODING = "utf-8"
```

### Q4: Port 3000 已被佔用

```powershell
# 檢查佔用 Port 3000 的程序
netstat -ano | findstr :3000

# 找到 PID 後強制結束
taskkill /PID <pid> /F
```

---

## 7. 移除環境

如需重建環境：

```bash
# 停用環境
conda deactivate

# 移除環境
conda env remove --name QMS

# 重新建立
conda create --name QMS python=3.11 --yes
```

---

## 8. 完整指令速查

```bash
# === 一次性設定 ===
conda create --name QMS python=3.11 --yes
conda activate QMS
cd path/to/AI-QMS
pip install -r requirements.txt

# === 每次使用 ===
conda activate QMS
cd path/to/AI-QMS
python -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0

# === 或直接雙擊 start.bat ===
```
