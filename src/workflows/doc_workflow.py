
from typing import TypedDict, Literal
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

# 定義狀態
class DocState(TypedDict):
    filename: str
    content: str
    doc_type: str
    is_related: bool
    status: str

# 節點函數
def detect_document_type(state: DocState):
    """偵測文件類型 (模擬/LLM)"""
    print(f"Detecting type for {state['filename']}...")
    # TODO: 實際呼叫 LLM
    # 這裡做簡單模擬
    if "V2" in state['filename'] or "v2" in state['filename']:
        return {"doc_type": "update"}
    return {"doc_type": "new"}

def check_related_documents(state: DocState):
    """檢查關聯文件"""
    print("Checking related documents...")
    if state['doc_type'] == 'update':
        return {"is_related": True}
    return {"is_related": False}

def process_ocr(state: DocState):
    """執行 OCR"""
    print("Running OCR...")
    # TODO: 整合 olmocr
    return {"content": "Simulated OCR Content"}

def update_database(state: DocState):
    """更新資料庫"""
    print("Updating DB...")
    return {"status": "completed"}

# 建立圖形
workflow = StateGraph(DocState)

# 加入節點
workflow.add_node("detect_type", detect_document_type)
workflow.add_node("check_related", check_related_documents)
workflow.add_node("ocr_processing", process_ocr)
workflow.add_node("update_db", update_database)

# 設定邊
workflow.set_entry_point("detect_type")

workflow.add_edge("detect_type", "check_related")

def route_logic(state: DocState):
    if state['is_related']:
        return "ocr_processing"
    return "ocr_processing"  # simplified: always do OCR

workflow.add_conditional_edges(
    "check_related",
    route_logic,
    {
        "ocr_processing": "ocr_processing"
    }
)

workflow.add_edge("ocr_processing", "update_db")
workflow.add_edge("update_db", END)

# 編譯
app = workflow.compile()
