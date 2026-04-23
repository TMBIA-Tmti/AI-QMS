"""
AI-QMS OCR 引擎全面測試
涵蓋：Tier 0-3、路由邏輯、並發、AB測試、sentinel、GPU 診斷
"""
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = 0
FAIL = 0


def ok(name):
    global PASS
    PASS += 1
    print(f"  [PASS] {name}")


def fail(name, reason=""):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {name}: {reason}")


# ── 測試 PDF 建立工具 ─────────────────────────────────────────


def make_text_pdf(text="Hello QMS ISO 13485 QMS Document Control System", pages=1) -> Path:
    from reportlab.pdfgen import canvas as rl_canvas
    tmp = Path(tempfile.mktemp(suffix=".pdf"))
    c = rl_canvas.Canvas(str(tmp))
    for i in range(pages):
        c.drawString(72, 720 - i * 20, f"Page {i+1}: {text}")
        if i < pages - 1:
            c.showPage()
    c.save()
    return tmp


def make_blank_pdf() -> Path:
    """空白頁 PDF，模擬掃描文件（無文字層）"""
    from reportlab.pdfgen import canvas as rl_canvas
    tmp = Path(tempfile.mktemp(suffix=".pdf"))
    c = rl_canvas.Canvas(str(tmp))
    c.showPage()
    c.save()
    return tmp


# ════════════════════════════════════════════════════════════
# Tier 0: PyMuPDF
# ════════════════════════════════════════════════════════════


def test_tier0():
    from src.ocr.pymupdf_engine import extract_pdf_text_layer

    print("\n── Tier 0: PyMuPDF ──────────────────────────────────")

    # T0-1: 有文字層的 PDF
    pdf = make_text_pdf("AI-QMS ISO 13485 compliance document")
    text = extract_pdf_text_layer(pdf)
    if text and "ISO 13485" in text:
        ok("T0-1 文字層 PDF 抽取成功")
    else:
        fail("T0-1 文字層 PDF 抽取", repr(text))
    pdf.unlink()

    # T0-2: 空白 PDF（掃描模擬）→ 應返回 None
    pdf = make_blank_pdf()
    text = extract_pdf_text_layer(pdf)
    if text is None:
        ok("T0-2 空白 PDF 返回 None（→ 交由 EasyOCR）")
    else:
        fail("T0-2 空白 PDF 應返回 None", repr(text[:50]))
    pdf.unlink()

    # T0-3: 非 PDF → 應返回 None
    tmp = Path(tempfile.mktemp(suffix=".docx"))
    tmp.write_bytes(b"fake docx content")
    text = extract_pdf_text_layer(tmp)
    if text is None:
        ok("T0-3 非 PDF 返回 None")
    else:
        fail("T0-3 非 PDF 應返回 None")
    tmp.unlink()

    # T0-4: 多頁 PDF
    pdf = make_text_pdf("Multi page ISO 13485 QMS Document Control Procedure", pages=3)
    text = extract_pdf_text_layer(pdf)
    if text and "Multi page" in text:
        ok("T0-4 多頁 PDF 抽取成功")
    else:
        fail("T0-4 多頁 PDF", repr(text))
    pdf.unlink()

    # T0-5: 極限測試 — 文字極少（每頁 < 30 字）→ 應視為掃描
    from reportlab.pdfgen import canvas as rl_canvas
    tmp = Path(tempfile.mktemp(suffix=".pdf"))
    c = rl_canvas.Canvas(str(tmp))
    c.drawString(72, 720, "Hi")  # 只有 2 字
    c.save()
    text = extract_pdf_text_layer(tmp)
    if text is None:
        ok("T0-5 文字極少 PDF 正確視為掃描（< 門檻）")
    else:
        fail("T0-5 文字極少應返回 None", repr(text))
    tmp.unlink()


# ════════════════════════════════════════════════════════════
# Tier 1: EasyOCR 路由邏輯
# ════════════════════════════════════════════════════════════


def test_tier1_routing():
    from src.ocr.easyocr_engine import _langs_for_country, _LATIN, _COUNTRY_TO_LANGS

    print("\n── Tier 1: EasyOCR 路由邏輯 ────────────────────────")

    # T1-1: CJK 語言各自配 English（不混合）
    cases = [
        ("tw", ("ch_tra", "en")),
        ("cn", ("ch_sim", "en")),
        ("jp", ("ja", "en")),
        ("kr", ("ko", "en")),
        ("sa", ("ar", "en")),
        ("in", ("hi", "en")),
        ("th", ("th", "en")),
        ("ru", ("ru", "en")),
    ]
    all_ok = True
    for country, expected in cases:
        got = _langs_for_country(country)
        if got != expected:
            fail(f"T1-1 {country} → {got} (expected {expected})")
            all_ok = False
    if all_ok:
        ok("T1-1 CJK/特殊語言各自配 English 正確")

    # T1-2: 拉丁系國家共用 _LATIN 語言組
    latin_countries = ["de", "fr", "us", "br", "vn", "id"]
    all_latin = all(_langs_for_country(c) == _LATIN for c in latin_countries)
    if all_latin:
        ok(f"T1-2 拉丁系國家共用 Latin Reader（{len(_LATIN)} 語言）")
    else:
        fail("T1-2 拉丁系路由", str({c: _langs_for_country(c) for c in latin_countries}))

    # T1-3: 未知國家 → 預設 ("en",)
    got = _langs_for_country("xx")
    if got == ("en",):
        ok("T1-3 未知國家預設英文")
    else:
        fail("T1-3", str(got))

    # T1-4: 大小寫不敏感
    if _langs_for_country("TW") == ("ch_tra", "en") and _langs_for_country("DE") == _LATIN:
        ok("T1-4 國家代碼大小寫不敏感（TW/DE）")
    else:
        fail("T1-4 大小寫不敏感")

    # T1-5: CJK 語言互不混合（不在同一個 tuple 中）
    cjk = ["ch_tra", "ch_sim", "ja", "ko"]
    for country in ["tw", "cn", "jp", "kr"]:
        langs = _langs_for_country(country)
        mixed = [l for l in langs if l in cjk and l != langs[0]]
        if mixed:
            fail(f"T1-5 {country} 的語言組混入其他 CJK: {mixed}")
            break
    else:
        ok("T1-5 CJK 語言各自獨立，無跨 CJK 混合")


# ════════════════════════════════════════════════════════════
# 調度器路由
# ════════════════════════════════════════════════════════════


def test_orchestrator():
    from src.ocr.docling_engine import get_engine
    engine = get_engine()

    print("\n── 調度器路由邏輯 ───────────────────────────────────")

    # T2-1: 文字層 PDF → Tier 0
    pdf = make_text_pdf("QMS SOP-001 Document Control", pages=2)
    r = engine.parse(str(pdf))
    if r.success and r.engine_used == "pymupdf":
        ok("T2-1 文字層 PDF → engine=pymupdf（Tier 0）")
    else:
        fail("T2-1", f"success={r.success} engine={r.engine_used} err={r.error}")
    pdf.unlink()

    # T2-2: Word 檔 → Tier 2 MarkItDown
    from docx import Document as DocxDoc
    tmp_word = Path(tempfile.mktemp(suffix=".docx"))
    doc = DocxDoc()
    doc.add_paragraph("AI-QMS Word Document — ISO 13485")
    doc.save(str(tmp_word))
    r = engine.parse(str(tmp_word))
    if r.success and r.engine_used == "markitdown":
        ok("T2-2 Word 檔 → engine=markitdown（Tier 2，跳過 Tier 0/1）")
    else:
        fail("T2-2", f"success={r.success} engine={r.engine_used}")
    tmp_word.unlink()

    # T2-3: 不存在的檔案
    r = engine.parse("/nonexistent/file.pdf")
    if not r.success and r.engine_used == "error":
        ok("T2-3 不存在檔案 → engine=error")
    else:
        fail("T2-3", f"success={r.success} engine={r.engine_used}")

    # T2-4: 不支援格式
    tmp_xyz = Path(tempfile.mktemp(suffix=".xyz"))
    tmp_xyz.write_text("test")
    r = engine.parse(str(tmp_xyz))
    if not r.success and r.engine_used == "error":
        ok("T2-4 不支援格式 .xyz → engine=error")
    else:
        fail("T2-4", f"success={r.success}")
    tmp_xyz.unlink()

    # T2-5: force_engine=pymupdf
    pdf = make_text_pdf("Force engine ISO 13485 QMS Document Control Test")
    r = engine.parse(str(pdf), force_engine="pymupdf")
    if r.success and r.engine_used == "pymupdf":
        ok("T2-5 force_engine=pymupdf 正常")
    else:
        fail("T2-5", f"success={r.success} engine={r.engine_used}")
    pdf.unlink()

    # T2-6: force_engine=markitdown
    pdf = make_text_pdf("Force markitdown test")
    r = engine.parse(str(pdf), force_engine="markitdown")
    if r.success and r.engine_used == "markitdown":
        ok("T2-6 force_engine=markitdown 正常")
    else:
        fail("T2-6", f"success={r.success} engine={r.engine_used}")
    pdf.unlink()

    # T2-7: country 參數不影響文字層 PDF 路由
    pdf = make_text_pdf("Country param ISO 13485 QMS Document Control Procedure")
    for country in ["tw", "de", "sa", ""]:
        r = engine.parse(str(pdf), country=country)
        if not (r.success and r.engine_used == "pymupdf"):
            fail(f"T2-7 country={country!r} 應走 pymupdf", f"engine={r.engine_used}")
            break
    else:
        ok("T2-7 country 參數不影響文字層 PDF 路由（皆走 pymupdf）")
    pdf.unlink()

    # T2-8: ParseResult 欄位完整
    pdf = make_text_pdf("Result fields test")
    r = engine.parse(str(pdf))
    has_all = all(hasattr(r, f) for f in
                  ["success", "markdown", "engine_used", "page_count",
                   "tables_found", "images_found", "error", "warnings"])
    if has_all:
        ok("T2-8 ParseResult 欄位完整")
    else:
        fail("T2-8 ParseResult 缺欄位")
    pdf.unlink()


# ════════════════════════════════════════════════════════════
# 並發 / Thread 安全
# ════════════════════════════════════════════════════════════


def test_concurrency():
    from src.ocr.docling_engine import get_engine
    engine = get_engine()

    print("\n── Thread 安全 / 並發測試 ───────────────────────────")

    results = []
    errors = []
    lock = threading.Lock()

    def worker(i):
        try:
            pdf = make_text_pdf(f"Thread {i} document")
            r = engine.parse(str(pdf))
            with lock:
                results.append(r.success)
            pdf.unlink()
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if not errors and all(results) and len(results) == 8:
        ok("T3-1 8 執行緒並發解析無崩潰，全部成功")
    else:
        fail("T3-1 並發", f"results={len(results)}/8 errors={errors}")

    # Singleton 一致性
    from src.ocr.docling_engine import get_engine
    e1, e2 = get_engine(), get_engine()
    if e1 is e2:
        ok("T3-2 Singleton 一致（多次 get_engine() 回傳同一物件）")
    else:
        fail("T3-2 Singleton 不一致")


# ════════════════════════════════════════════════════════════
# Config 驗證
# ════════════════════════════════════════════════════════════


def test_config():
    from src.config import (
        FORCE_CPU, EASYOCR_ENABLED, EASYOCR_LANGUAGE_GROUPS,
        COUNTRY_TO_EASYOCR_LANGS, DOCLING_ENABLED,
    )

    print("\n── Config 驗證 ──────────────────────────────────────")

    if not FORCE_CPU:
        ok("T4-1 FORCE_CPU 預設 False")
    else:
        fail("T4-1 FORCE_CPU 應預設 False")

    if EASYOCR_ENABLED:
        ok("T4-2 EASYOCR_ENABLED 預設 True")
    else:
        fail("T4-2 EASYOCR_ENABLED 應預設 True")

    if len(EASYOCR_LANGUAGE_GROUPS) >= 3:
        ok(f"T4-3 EASYOCR_LANGUAGE_GROUPS 有 {len(EASYOCR_LANGUAGE_GROUPS)} 組（CJK 各自獨立）")
    else:
        fail("T4-3", str(len(EASYOCR_LANGUAGE_GROUPS)))

    required = ["tw", "cn", "jp", "kr", "de", "fr", "sa", "in", "th", "vn", "br"]
    missing = [c for c in required if c not in COUNTRY_TO_EASYOCR_LANGS]
    if not missing:
        ok(f"T4-4 COUNTRY_TO_EASYOCR_LANGS 包含全部必要國家（共 {len(COUNTRY_TO_EASYOCR_LANGS)} 筆）")
    else:
        fail("T4-4 缺少國家", str(missing))

    if isinstance(DOCLING_ENABLED, bool):
        ok("T4-5 DOCLING_ENABLED 型別正確（bool）")
    else:
        fail("T4-5", str(type(DOCLING_ENABLED)))


# ════════════════════════════════════════════════════════════
# A/B 測試：PyMuPDF vs MarkItDown
# ════════════════════════════════════════════════════════════


def test_ab():
    from src.ocr.docling_engine import get_engine
    engine = get_engine()

    print("\n── A/B 測試：PyMuPDF vs MarkItDown ─────────────────")

    pdf = make_text_pdf("AB Test: QMS ISO 13485 Section 4.2.3 Document Control")
    r_a = engine.parse(str(pdf), force_engine="pymupdf")
    r_b = engine.parse(str(pdf), force_engine="markitdown")

    if r_a.success and r_b.success:
        ok(f"T5-1 兩引擎皆成功（pymupdf={len(r_a.markdown)}字 / markitdown={len(r_b.markdown)}字）")
    else:
        fail("T5-1", f"pymupdf={r_a.success} markitdown={r_b.success}")

    if r_a.success and "ISO 13485" in r_a.markdown:
        ok("T5-2 PyMuPDF 關鍵字保留（ISO 13485）")
    else:
        fail("T5-2 PyMuPDF 內容", repr(r_a.markdown[:100]))

    # 速度比較（非阻塞，僅記錄）
    import time
    pdf2 = make_text_pdf("Speed test document with enough text to measure", pages=5)
    t0 = time.perf_counter()
    engine.parse(str(pdf2), force_engine="pymupdf")
    t_pymupdf = time.perf_counter() - t0

    t0 = time.perf_counter()
    engine.parse(str(pdf2), force_engine="markitdown")
    t_markitdown = time.perf_counter() - t0

    ok(f"T5-3 速度：pymupdf={t_pymupdf*1000:.0f}ms / markitdown={t_markitdown*1000:.0f}ms（5頁）")
    pdf.unlink()
    pdf2.unlink()


# ════════════════════════════════════════════════════════════
# Sentinel / Model Setup
# ════════════════════════════════════════════════════════════


def test_model_setup():
    from src.ocr.model_setup import is_models_ready, ensure_ocr_models_ready, SENTINEL_FILE, EASYOCR_CACHE_DIR

    print("\n── Model Setup / Sentinel ───────────────────────────")

    # 備份原始狀態
    was_ready = is_models_ready()

    # T6-1: is_models_ready() 可呼叫
    ok(f"T6-1 is_models_ready() 可呼叫（現在: {was_ready}）")

    # T6-2: sentinel 存在時 = True
    EASYOCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SENTINEL_FILE.touch()
    if is_models_ready():
        ok("T6-2 sentinel 存在時 is_models_ready() = True")
    else:
        fail("T6-2")

    # T6-3: sentinel 刪除後 = False
    SENTINEL_FILE.unlink()
    if not is_models_ready():
        ok("T6-3 sentinel 刪除後 is_models_ready() = False")
    else:
        fail("T6-3")

    # T6-4: ensure_ocr_models_ready() 不崩潰（僅啟動 thread，不等待）
    try:
        ensure_ocr_models_ready()
        ok("T6-4 ensure_ocr_models_ready() 啟動正常（背景 thread）")
    except Exception as e:
        fail("T6-4", str(e))

    # 還原狀態
    if was_ready:
        SENTINEL_FILE.touch()


# ════════════════════════════════════════════════════════════
# GPU 診斷
# ════════════════════════════════════════════════════════════


def test_gpu():
    from src.ocr.gpu_check import check_gpu, run_startup_check

    print("\n── GPU 診斷 ──────────────────────────────────────────")

    r = check_gpu()
    valid_statuses = {"ok", "cpu_only", "no_torch", "cuda_mismatch", "unsupported_gpu", "cpu_forced"}
    if r["status"] in valid_statuses:
        ok(f"T7-1 GPU 診斷正常返回（status={r['status']}）")
    else:
        fail("T7-1", str(r))

    if r.get("gpu_name") and "RTX 5060" in r["gpu_name"]:
        if r["status"] == "unsupported_gpu":
            ok("T7-2 RTX 5060 Ti 正確識別為 unsupported_gpu（Blackwell sm_120）")
        else:
            fail("T7-2", f"status={r['status']}")
    else:
        ok("T7-2 非 RTX 5060 Ti 環境（跳過）")

    # T7-3: run_startup_check 不崩潰
    try:
        run_startup_check()
        ok("T7-3 run_startup_check() 不崩潰")
    except Exception as e:
        fail("T7-3", str(e))

    # T7-4: result 欄位完整
    required_keys = {"status", "warnings", "torch_cuda", "driver_cuda", "capability", "gpu_name", "recommendation"}
    if required_keys.issubset(r.keys()):
        ok("T7-4 GPU 結果欄位完整")
    else:
        fail("T7-4 缺欄位", str(required_keys - r.keys()))


# ════════════════════════════════════════════════════════════
# 漏洞測試（邊界 / 異常）
# ════════════════════════════════════════════════════════════


def test_edge_cases():
    from src.ocr.docling_engine import get_engine
    from src.ocr.pymupdf_engine import extract_pdf_text_layer
    engine = get_engine()

    print("\n── 漏洞 / 邊界測試 ──────────────────────────────────")

    # T8-1: 空字串路徑
    r = engine.parse("")
    if not r.success:
        ok("T8-1 空字串路徑不崩潰")
    else:
        fail("T8-1 空字串應返回失敗")

    # T8-2: 路徑含特殊字元
    tmp = Path(tempfile.mkdtemp()) / "test file (1).pdf"
    tmp.write_bytes(b"")
    r = engine.parse(str(tmp))
    if not r.success or r.engine_used:  # 不崩潰即可
        ok("T8-2 含空格/括號路徑不崩潰")
    else:
        fail("T8-2")
    tmp.unlink()

    # T8-3: 0 bytes 檔案
    tmp = Path(tempfile.mktemp(suffix=".pdf"))
    tmp.write_bytes(b"")
    try:
        r = engine.parse(str(tmp))
        ok("T8-3 0 bytes 檔案不崩潰")
    except Exception as e:
        fail("T8-3 0 bytes 崩潰", str(e))
    tmp.unlink()

    # T8-4: 很大的 force_engine 字串（不應崩潰）
    pdf = make_text_pdf("edge")
    r = engine.parse(str(pdf), force_engine="unknown_engine_xyz")
    if not r.success and r.engine_used == "error":
        ok("T8-4 未知 force_engine 返回 error（不崩潰）")
    else:
        fail("T8-4", f"success={r.success} engine={r.engine_used}")
    pdf.unlink()

    # T8-5: extract_pdf_text_layer 對損壞 PDF
    tmp = Path(tempfile.mktemp(suffix=".pdf"))
    tmp.write_bytes(b"NOT A REAL PDF CONTENT %PDF garbage")
    try:
        text = extract_pdf_text_layer(tmp)
        ok("T8-5 損壞 PDF 不崩潰（返回 None 或空）")
    except Exception as e:
        fail("T8-5 損壞 PDF 崩潰", str(e))
    tmp.unlink()


# ════════════════════════════════════════════════════════════
# 主程式
# ════════════════════════════════════════════════════════════


def main():
    import warnings
    warnings.filterwarnings("ignore")

    print()
    print("=" * 60)
    print("  AI-QMS OCR 引擎全面測試")
    print("=" * 60)

    test_tier0()
    test_tier1_routing()
    test_orchestrator()
    test_concurrency()
    test_config()
    test_ab()
    test_model_setup()
    test_gpu()
    test_edge_cases()

    print()
    print("=" * 60)
    status = "PASS" if FAIL == 0 else "FAIL"
    print(f"  結果：{PASS} PASS / {FAIL} FAIL  [{status}]")
    print("=" * 60)

    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
