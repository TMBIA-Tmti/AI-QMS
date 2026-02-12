"""
AI-QMS Phase 1 Document Control - Flask Web Application
文件上傳與版本控制 Prototype
"""
import os
import hashlib
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

# 確保可以導入本地模組
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, MAX_CONTENT_LENGTH
from src.database.audit_log import ImmutableAuditLog
from src.database.document_store import DocumentStore

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# 初始化模組
audit_log = ImmutableAuditLog()
doc_store = DocumentStore()

# 暫存狀態
upload_sessions = {}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def calculate_file_hash(file_path):
    """計算文件 SHA-256 雜湊"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


# ============================================================
# HTML 模板
# ============================================================

UPLOAD_PAGE_HTML = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI-QMS 文件控制系統 - Prototype</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Microsoft JhengHei', sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh; color: #fff; padding: 20px;
        }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 30px; font-size: 2rem; }
        .card { 
            background: rgba(255,255,255,0.1); 
            border-radius: 16px; padding: 30px; 
            backdrop-filter: blur(10px); margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .upload-zone {
            border: 3px dashed rgba(255,255,255,0.3);
            border-radius: 12px; padding: 50px; text-align: center;
            transition: all 0.3s; cursor: pointer;
        }
        .upload-zone:hover { border-color: #4ecdc4; background: rgba(78,205,196,0.1); }
        .upload-zone.dragover { border-color: #4ecdc4; background: rgba(78,205,196,0.2); }
        input[type="file"] { display: none; }
        .btn { 
            padding: 12px 30px; border: none; border-radius: 8px; 
            cursor: pointer; font-size: 1rem; transition: all 0.3s;
            margin: 5px;
        }
        .btn-primary { background: #4ecdc4; color: #1a1a2e; }
        .btn-primary:hover { background: #3db9b1; transform: translateY(-2px); }
        .btn-secondary { background: rgba(255,255,255,0.2); color: #fff; }
        .btn-danger { background: #ff6b6b; color: #fff; }
        .file-list { margin-top: 20px; }
        .file-item { 
            background: rgba(255,255,255,0.05); padding: 15px; 
            border-radius: 8px; margin: 10px 0; display: flex; 
            justify-content: space-between; align-items: center;
        }
        .status { padding: 5px 15px; border-radius: 20px; font-size: 0.85rem; }
        .status-pending { background: #ffc107; color: #000; }
        .status-success { background: #28a745; }
        .status-error { background: #dc3545; }
        .modal { 
            display: none; position: fixed; top: 0; left: 0; 
            width: 100%; height: 100%; background: rgba(0,0,0,0.8);
            justify-content: center; align-items: center; z-index: 1000;
        }
        .modal.show { display: flex; }
        .modal-content { 
            background: #2a2a4a; padding: 30px; border-radius: 16px; 
            max-width: 500px; width: 90%;
        }
        .modal h3 { margin-bottom: 20px; color: #4ecdc4; }
        .checkbox-group { margin: 15px 0; }
        .checkbox-group label { display: flex; align-items: center; cursor: pointer; }
        .checkbox-group input { margin-right: 10px; width: 20px; height: 20px; }
        .audit-log { max-height: 300px; overflow-y: auto; font-family: monospace; font-size: 0.85rem; }
        .log-entry { padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔒 AI-QMS 文件控制系統</h1>
        <p style="text-align:center; margin-bottom:30px; opacity:0.7;">Prototype v0.1 | RTX 5060 Ti (16GB)</p>
        
        <div class="card">
            <h2 style="margin-bottom:20px;">📁 文件上傳</h2>
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="upload-zone" id="dropZone">
                    <p style="font-size:1.2rem; margin-bottom:10px;">拖放文件至此處</p>
                    <p style="opacity:0.7;">或點擊選擇文件 (PDF, DOCX, PNG, JPG)</p>
                    <input type="file" id="fileInput" name="files" multiple accept=".pdf,.docx,.doc,.png,.jpg,.jpeg,.tiff">
                </div>
                <div class="file-list" id="fileList"></div>
                <div style="margin-top:20px; text-align:center;">
                    <button type="button" class="btn btn-primary" onclick="uploadFiles()">📤 上傳文件</button>
                    <button type="button" class="btn btn-secondary" onclick="clearFiles()">🗑️ 清除</button>
                </div>
            </form>
        </div>
        
        <div class="card">
            <h2 style="margin-bottom:20px;">📋 稽核紀錄 (防竄改)</h2>
            <div class="audit-log" id="auditLog">
                <p style="opacity:0.5;">尚無紀錄</p>
            </div>
            <button class="btn btn-secondary" style="margin-top:15px;" onclick="refreshAuditLog()">🔄 重新整理</button>
        </div>
    </div>
    
    <!-- 版本確認彈窗 -->
    <div class="modal" id="versionModal">
        <div class="modal-content">
            <h3>📄 文件類型確認</h3>
            <p id="modalFileName"></p>
            <p style="margin:15px 0;">系統偵測結果: <strong id="detectionResult"></strong></p>
            <p>請確認此文件的處理方式:</p>
            <div class="checkbox-group">
                <label><input type="radio" name="docType" value="new"> 初次輸入 - 設為母版文件</label>
            </div>
            <div class="checkbox-group">
                <label><input type="radio" name="docType" value="update"> 文件進版 - 更新現有文件版本</label>
            </div>
            <div style="margin-top:20px; text-align:right;">
                <button class="btn btn-secondary" onclick="closeModal('versionModal')">取消</button>
                <button class="btn btn-primary" onclick="confirmVersion()">確認</button>
            </div>
        </div>
    </div>
    
    <!-- 簽章確認彈窗 -->
    <div class="modal" id="stampModal">
        <div class="modal-content">
            <h3>⚠️ 進版簽章確認</h3>
            <p id="stampFileName"></p>
            <p style="margin:20px 0;">請確認此文件是否已完成以下程序:</p>
            <div class="checkbox-group">
                <label><input type="checkbox" id="chkSupervisor"> 主管審核簽章</label>
            </div>
            <div class="checkbox-group">
                <label><input type="checkbox" id="chkQA"> 品保確認蓋章</label>
            </div>
            <div class="checkbox-group">
                <label><input type="checkbox" id="chkMR"> 管理代表核准 (若適用)</label>
            </div>
            <p style="margin-top:15px; padding:10px; background:rgba(255,107,107,0.2); border-radius:8px;">
                【重要提醒】確認後將產生不可竄改的稽核紀錄
            </p>
            <div style="margin-top:20px; text-align:right;">
                <button class="btn btn-danger" onclick="closeModal('stampModal')">返回補章</button>
                <button class="btn btn-primary" onclick="confirmStamp()">✓ 確認已完成</button>
            </div>
        </div>
    </div>

    <script>
        let selectedFiles = [];
        let currentSessionId = null;
        
        // 拖放處理
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        
        dropZone.onclick = () => fileInput.click();
        
        dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('dragover'); };
        dropZone.ondragleave = () => dropZone.classList.remove('dragover');
        dropZone.ondrop = (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        };
        
        fileInput.onchange = (e) => handleFiles(e.target.files);
        
        function handleFiles(files) {
            for (let file of files) {
                selectedFiles.push(file);
            }
            updateFileList();
        }
        
        function updateFileList() {
            const list = document.getElementById('fileList');
            list.innerHTML = selectedFiles.map((f, i) => `
                <div class="file-item">
                    <span>📄 ${f.name} (${(f.size/1024/1024).toFixed(2)} MB)</span>
                    <span class="status status-pending">待上傳</span>
                </div>
            `).join('');
        }
        
        function clearFiles() {
            selectedFiles = [];
            updateFileList();
        }
        
        async function uploadFiles() {
            if (selectedFiles.length === 0) {
                alert('請先選擇文件');
                return;
            }
            
            const formData = new FormData();
            selectedFiles.forEach(f => formData.append('files', f));
            
            try {
                const response = await fetch('/upload', { method: 'POST', body: formData });
                const result = await response.json();
                
                if (result.success) {
                    currentSessionId = result.session_id;
                    // 顯示版本確認彈窗
                    document.getElementById('modalFileName').textContent = '文件: ' + selectedFiles[0].name;
                    document.getElementById('detectionResult').textContent = result.detection || '初次輸入';
                    document.getElementById('versionModal').classList.add('show');
                } else {
                    alert('上傳失敗: ' + result.error);
                }
            } catch (err) {
                alert('上傳錯誤: ' + err.message);
            }
        }
        
        function closeModal(id) {
            document.getElementById(id).classList.remove('show');
        }
        
        async function confirmVersion() {
            const docType = document.querySelector('input[name="docType"]:checked');
            if (!docType) {
                alert('請選擇文件類型');
                return;
            }
            
            closeModal('versionModal');
            
            if (docType.value === 'update') {
                // 進版需要確認簽章
                document.getElementById('stampFileName').textContent = '文件: ' + selectedFiles[0].name;
                document.getElementById('stampModal').classList.add('show');
            } else {
                // 初次輸入，直接處理
                await processDocument('new');
            }
        }
        
        async function confirmStamp() {
            const supervisor = document.getElementById('chkSupervisor').checked;
            const qa = document.getElementById('chkQA').checked;
            
            if (!supervisor || !qa) {
                alert('請確認主管審核與品保確認皆已完成');
                return;
            }
            
            closeModal('stampModal');
            await processDocument('update');
        }
        
        async function processDocument(docType) {
            try {
                const response = await fetch('/confirm-version', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: currentSessionId,
                        doc_type: docType,
                        stamp_confirmed: docType === 'update'
                    })
                });
                const result = await response.json();
                
                if (result.success) {
                    alert('✅ 文件處理完成!\\n\\n' + result.message);
                    clearFiles();
                    refreshAuditLog();
                } else {
                    alert('處理失敗: ' + result.error);
                }
            } catch (err) {
                alert('處理錯誤: ' + err.message);
            }
        }
        
        async function refreshAuditLog() {
            try {
                const response = await fetch('/audit-log');
                const result = await response.json();
                
                const logDiv = document.getElementById('auditLog');
                if (result.logs && result.logs.length > 0) {
                    logDiv.innerHTML = result.logs.map(log => `
                        <div class="log-entry">
                            <strong>${log.timestamp}</strong> | ${log.action} | ${log.document_id}<br>
                            <span style="opacity:0.7">Hash: ${log.current_hash ? log.current_hash.substring(0,16) + '...' : 'N/A'}</span>
                        </div>
                    `).join('');
                } else {
                    logDiv.innerHTML = '<p style="opacity:0.5;">尚無紀錄</p>';
                }
            } catch (err) {
                console.error('取得稽核紀錄失敗:', err);
            }
        }
        
        // 初始載入
        refreshAuditLog();
    </script>
</body>
</html>
"""


# ============================================================
# API 路由
# ============================================================

@app.route('/')
def index():
    return render_template_string(UPLOAD_PAGE_HTML)


@app.route('/upload', methods=['POST'])
def upload_files():
    """處理文件上傳"""
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': '未選擇文件'})
    
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({'success': False, 'error': '未選擇文件'})
    
    session_id = datetime.now().strftime('%Y%m%d%H%M%S%f')
    uploaded_files = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # 加上時間戳避免重複
            unique_filename = f"{session_id}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # 確保目錄存在
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(filepath)
            
            # 計算 hash
            file_hash = calculate_file_hash(filepath)
            
            uploaded_files.append({
                'filename': filename,
                'filepath': filepath,
                'hash': file_hash,
                'size': os.path.getsize(filepath)
            })
    
    if not uploaded_files:
        return jsonify({'success': False, 'error': '無有效文件'})
    
    # 儲存 session 狀態
    upload_sessions[session_id] = {
        'files': uploaded_files,
        'status': 'uploaded',
        'timestamp': datetime.now().isoformat()
    }
    
    # 記錄稽核日誌
    audit_log.create_record(
        action="FILE_UPLOADED",
        document_id=uploaded_files[0]['filename'],
        user_id="test_user",
        details={
            'file_count': len(uploaded_files),
            'total_size': sum(f['size'] for f in uploaded_files),
            'file_hash': uploaded_files[0]['hash']
        }
    )
    
    # TODO: 呼叫 LLM 進行文件類型偵測
    detection = "初次輸入"  # 暫時預設
    
    return jsonify({
        'success': True,
        'session_id': session_id,
        'files': [f['filename'] for f in uploaded_files],
        'detection': detection
    })


@app.route('/confirm-version', methods=['POST'])
def confirm_version():
    """確認文件版本類型"""
    data = request.json
    session_id = data.get('session_id')
    doc_type = data.get('doc_type')  # 'new' or 'update'
    stamp_confirmed = data.get('stamp_confirmed', False)
    
    if session_id not in upload_sessions:
        return jsonify({'success': False, 'error': 'Session 不存在'})
    
    session = upload_sessions[session_id]
    
    # 記錄版本確認
    action = "NEW_DOCUMENT_CREATED" if doc_type == 'new' else "VERSION_UPDATE_CONFIRMED"
    
    record = audit_log.create_record(
        action=action,
        document_id=session['files'][0]['filename'],
        user_id="test_user",
        details={
            'doc_type': doc_type,
            'stamp_confirmed': stamp_confirmed,
            'file_hash': session['files'][0]['hash']
        }
    )
    
    # 更新 session 狀態
    session['status'] = 'completed'
    session['doc_type'] = doc_type
    
    # 儲存到文件儲存庫
    doc_store.save_document(
        doc_id=f"DOC-{session_id[:8]}",
        filename=session['files'][0]['filename'],
        filepath=session['files'][0]['filepath'],
        version="1.0" if doc_type == 'new' else "2.0",
        is_new=doc_type == 'new'
    )
    
    message = "新文件已建立，設為母版。" if doc_type == 'new' else "文件進版完成，已產生防竄改紀錄。"
    
    # TODO: 如果是進版，呼叫 AI 搜尋關聯文件
    
    return jsonify({
        'success': True,
        'message': message,
        'audit_hash': record.get('current_hash', '')
    })


@app.route('/audit-log', methods=['GET'])
def get_audit_log():
    """取得稽核紀錄"""
    logs = audit_log.get_all_records()
    return jsonify({'logs': logs})


@app.route('/related-documents', methods=['GET'])
def get_related_documents():
    """取得關聯文件清單"""
    doc_id = request.args.get('doc_id')
    # TODO: 呼叫 AI 搜尋關聯文件
    return jsonify({
        'documents': [],
        'message': '關聯文件搜尋功能開發中'
    })


# ============================================================
# 主程式
# ============================================================

if __name__ == '__main__':
    # 確保上傳目錄存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs('./data/chroma_db', exist_ok=True)
    
    print("=" * 60)
    print("AI-QMS 文件控制系統 - Prototype")
    print("=" * 60)
    print(f"上傳目錄: {UPLOAD_FOLDER}")
    print(f"啟動 Web 伺服器: http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
