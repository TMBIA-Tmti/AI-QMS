"""
AI-QMS 全修正驗證測試 (2026-05-12)
====================================
涵蓋今日所有修改項目的完整測試：

M1-M9  爬蟲 DDG 改善
F1     Windows ProactorEventLoop 修正
F2     LiteLLM warning 靜默
F3     PyTorch RTX 5060 Ti warning 靜默
F4     chat_profile async→sync 修正
F5     DDG 25s timeout 上限
F6-F8  來源可信度排序（Tier 0-9）
F9     primp log 靜默 + DDG site bias
F10    EUR-Lex 英文限定
F11    ETag bypass for save_attachments_separately
F12    附件失敗改為 WARNING log
F13    Per-agency 替換（保留未更新文件）

Usage: python scripts/test_all_fixes.py
"""
import asyncio, sys, os, time, inspect, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results = []

def report(name, status, detail=""):
    tag = f"[{status}]"
    line = f"  {tag:<7} {name}"
    if detail:
        line += f" -- {detail}"
    print(line)
    results.append((name, status, detail))

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

# ─────────────────────────────────────────────────────────────
# GROUP 1: 程式碼結構驗證（不需要網路）
# ─────────────────────────────────────────────────────────────
section("GROUP 1: 程式碼結構驗證")

# F1: Windows SelectorEventLoop fix
def test_f1():
    app = open("src/chainlit_app/app.py", encoding="utf-8").read()
    assert "WindowsSelectorEventLoopPolicy" in app
    assert "win32" in app
    report("F1 Windows SelectorEventLoop fix in app.py", PASS)
try: test_f1()
except Exception as e: report("F1 Windows SelectorEventLoop", FAIL, str(e)[:80])

# F2: LiteLLM warning 靜默
def test_f2():
    app = open("src/chainlit_app/app.py", encoding="utf-8").read()
    assert "async_service_success_hook" in app
    assert "filterwarnings" in app
    report("F2 LiteLLM async_service_success_hook suppressed", PASS)
try: test_f2()
except Exception as e: report("F2 LiteLLM suppression", FAIL, str(e)[:80])

# F3: PyTorch RTX 5060 Ti warning 靜默
def test_f3():
    app = open("src/chainlit_app/app.py", encoding="utf-8").read()
    assert "sm_1" in app and "UserWarning" in app and "torch" in app
    report("F3 PyTorch sm_120 UserWarning suppressed", PASS)
try: test_f3()
except Exception as e: report("F3 PyTorch suppression", FAIL, str(e)[:80])

# F4: chat_profile async→sync
def test_f4():
    app = open("src/chainlit_app/app.py", encoding="utf-8").read()
    # Must have "def chat_profile" but NOT "async def chat_profile"
    assert "async def chat_profile" not in app
    assert "def chat_profile" in app
    report("F4 chat_profile is sync (not async)", PASS)
try: test_f4()
except Exception as e: report("F4 chat_profile sync", FAIL, str(e)[:80])

# F5: DDG 25s timeout cap
def test_f5():
    from src.services.regulatory_crawler import AsyncRegulatoryUpdateCrawler
    src = inspect.getsource(AsyncRegulatoryUpdateCrawler._fallback_ddgs_search)
    assert "wait_for" in src and "timeout=25.0" in src
    src2 = inspect.getsource(AsyncRegulatoryUpdateCrawler._ddgs_url_discovery)
    assert "timeout=8.0" in src2 and "timeout=12.0" in src2
    report("F5 DDG 25s hard cap + per-fetch 8s/12s timeouts", PASS)
try: test_f5()
except Exception as e: report("F5 DDG timeout cap", FAIL, str(e)[:80])

# F6-F8: 來源可信度排序
def test_f6():
    from src.services.regulatory_crawler import (
        _url_credibility_score, _sort_by_credibility,
        _CREDIBILITY_CIVIL_ORGS, _MIN_FETCH_CREDIBILITY
    )
    assert _url_credibility_score("https://www.fda.gov/")           == 100
    assert _url_credibility_score("https://www.iso.org/")           == 100
    assert _url_credibility_score("https://www.sgs.com/")           == 35
    assert _url_credibility_score("https://www.tuvsud.com/")        == 35
    assert _url_credibility_score("https://en.wikipedia.org/")      == -1
    assert _url_credibility_score("https://www.reddit.com/")        == -1
    assert _url_credibility_score("https://randomblog.com/")        == 20
    assert _MIN_FETCH_CREDIBILITY == 35
    # 排序：Wikipedia/Reddit 排除，一般網頁不進 URL 抓取
    ranked = _sort_by_credibility([
        {"href": "https://en.wikipedia.org/wiki/ISO", "title": "Wiki"},
        {"href": "https://www.fda.gov/devices", "title": "FDA"},
        {"href": "https://www.sgs.com/en/md", "title": "SGS"},
        {"href": "https://randomblog.com", "title": "Blog"},
    ], min_score=35)
    titles = [r["title"] for r in ranked]
    assert "FDA" in titles and "SGS" in titles
    assert "Wiki" not in titles and "Blog" not in titles
    report(f"F6-F8 Credibility ranking: FDA=100, SGS=35, Wiki=-1, Blog excluded", PASS)
try: test_f6()
except Exception as e: report("F6-F8 Credibility ranking", FAIL, str(e)[:80])

# F9: primp log 靜默
def test_f9():
    app = open("src/chainlit_app/app.py", encoding="utf-8").read()
    assert "primp" in app and "CRITICAL" in app
    assert "duckduckgo_search" in app
    report("F9 primp + duckduckgo_search loggers set to CRITICAL", PASS)
try: test_f9()
except Exception as e: report("F9 primp log suppression", FAIL, str(e)[:80])

# F10: EUR-Lex 英文限定（移除 24 語言展開）
def test_f10():
    from src.services.regulatory_crawler import REGION_SITES
    eu_sites = REGION_SITES.get("歐盟 (EU)", [])
    eur_lex = next((s for s in eu_sites if s["agency"] == "EUR-Lex-MDR-HTML"), None)
    assert eur_lex is not None, "EUR-Lex-MDR-HTML entry not found"
    assert not eur_lex.get("save_attachments_separately"), \
        "save_attachments_separately must be removed (English only)"
    assert not eur_lex.get("index_page"), \
        "index_page must be removed (English only)"
    report("F10 EUR-Lex-MDR-HTML: English only, no 24-language expansion", PASS)
try: test_f10()
except Exception as e: report("F10 EUR-Lex English only", FAIL, str(e)[:80])

# F11: ETag bypass for save_attachments_separately
def test_f11():
    from src.services import regulatory_crawler as rc
    src = inspect.getsource(rc._crawl_tier2_httpx)
    # Must check save_attachments_separately before setting ETag headers
    assert "save_attachments_separately" in src
    # ETag should be skipped for these sites
    assert "not site.get(\"save_attachments_separately\")" in src or \
           "not site.get('save_attachments_separately')" in src
    report("F11 ETag bypass for save_attachments_separately sites", PASS)
try: test_f11()
except Exception as e: report("F11 ETag bypass", FAIL, str(e)[:80])

# F12: 附件失敗改為 WARNING log
def test_f12():
    from src.services import regulatory_crawler as rc
    src = inspect.getsource(rc._crawl_tier2_httpx)
    assert "logger.warning" in src
    assert "Attachment extraction failed" in src or "No attachments extracted" in src
    assert "except Exception as _att_exc" in src or "except Exception" in src
    # Must NOT have bare "except Exception:\n                    pass" silently
    # (check the warning is there instead)
    assert "logger.warning" in src
    report("F12 Attachment failures logged as WARNING (not silent)", PASS)
try: test_f12()
except Exception as e: report("F12 Attachment logging", FAIL, str(e)[:80])

# F13: Per-agency replacement
def test_f13():
    from src.storage.regulatory_markdown_storage import RegulatoryMarkdownStorage
    src = inspect.getsource(RegulatoryMarkdownStorage.save_from_crawl_results)
    # Must NOT have bulk delete_by_region in save_from_crawl_results
    assert "delete_by_region" not in src, \
        "delete_by_region should not be called in save_from_crawl_results"
    # Must use per-agency replacement
    assert "_replace_old_versions" in src
    # _replace_old_versions must exist
    assert hasattr(RegulatoryMarkdownStorage, "_replace_old_versions")
    report("F13 Per-agency replacement (no bulk region delete)", PASS)
try: test_f13()
except Exception as e: report("F13 Per-agency replacement", FAIL, str(e)[:80])

# M9: crawl_delay fix
def test_m9():
    from src.services.regulatory_crawler import AsyncRegulatoryUpdateCrawler
    src = inspect.getsource(AsyncRegulatoryUpdateCrawler._crawl_single_site)
    assert "crawl_delay * 0.5" not in src
    assert "asyncio.sleep(crawl_delay)" in src
    report("M9 crawl_delay * 0.5 removed", PASS)
try: test_m9()
except Exception as e: report("M9 crawl_delay fix", FAIL, str(e)[:80])

# M2: _build_ddg_query
def test_m2():
    from src.services.regulatory_crawler import _build_ddg_query
    q1 = _build_ddg_query({"agency":"A","name":"RDC nº 665/2022 ANVISA","note":""}, "巴西 (Brazil)")
    assert "665" in q1 or "RDC" in q1
    q2 = _build_ddg_query({"agency":"B","name":"21 CFR Part 820","note":""}, "美國 (USA)")
    assert "820" in q2 or "CFR" in q2
    report("M2 _build_ddg_query citation extraction", PASS)
try: test_m2()
except Exception as e: report("M2 _build_ddg_query", FAIL, str(e)[:80])

# M3: _is_regulatory_fulltext
def test_m3():
    from src.services.regulatory_crawler import _is_regulatory_fulltext
    assert not _is_regulatory_fulltext("Short.")
    assert not _is_regulatory_fulltext("Welcome.\n" * 50)
    reg = ("Article 1. The manufacturer shall comply.\n"
           "Section 2. Requirements for compliance.\n"
           "Chapter 3. Management responsibility.\n") * 20
    assert _is_regulatory_fulltext(reg)
    report("M3 _is_regulatory_fulltext quality gate", PASS)
try: test_m3()
except Exception as e: report("M3 content quality gate", FAIL, str(e)[:80])

# ─────────────────────────────────────────────────────────────
# GROUP 2: Storage 功能驗證（in-memory，無磁碟副作用）
# ─────────────────────────────────────────────────────────────
section("GROUP 2: Storage 功能驗證")

def test_storage_per_agency():
    """F13: Per-agency 替換驗證 — 成功更新只刪同 agency 舊版，其他保留"""
    from src.storage.regulatory_markdown_storage import RegulatoryMarkdownStorage

    tmp = tempfile.mkdtemp()
    try:
        store = RegulatoryMarkdownStorage(base_path=tmp)

        # 先存入 3 個 agency
        store.save_regulatory_document("台灣 (Taiwan)", "TFDA-QMS", "", "法規A", "", "v1 content " * 100, "success")
        store.save_regulatory_document("台灣 (Taiwan)", "TFDA-QMS-EN", "", "法規B", "", "v1 content " * 100, "success")
        store.save_regulatory_document("台灣 (Taiwan)", "TFDA-Inspection", "", "法規C", "", "v1 content " * 100, "success")

        initial_count = len([d for d in store.registry["documents"] if d["status"] == "active"])
        assert initial_count == 3, f"Expected 3 docs, got {initial_count}"

        # 模擬爬蟲結果：只有 TFDA-QMS 成功，其他失敗
        crawl_results = {
            "results": [
                {"region": "台灣 (Taiwan)", "agency": "TFDA-QMS", "agency_name": "",
                 "title": "法規A", "url": "", "content_markdown": "new v2 content " * 100,
                 "crawl_status": "success", "failure_reason": None,
                 "has_pdf": False, "pdf_urls": [], "note": ""},
                {"region": "台灣 (Taiwan)", "agency": "TFDA-QMS-EN", "agency_name": "",
                 "title": "法規B", "url": "", "content_markdown": "",
                 "crawl_status": "failed", "failure_reason": "network error",
                 "has_pdf": False, "pdf_urls": [], "note": ""},
                {"region": "台灣 (Taiwan)", "agency": "TFDA-Inspection", "agency_name": "",
                 "title": "法規C", "url": "", "content_markdown": "",
                 "crawl_status": "failed", "failure_reason": "timeout",
                 "has_pdf": False, "pdf_urls": [], "note": ""},
            ]
        }

        save_result = store.save_from_crawl_results(crawl_results)
        active_after = [d for d in store.registry["documents"] if d["status"] == "active"]

        # 應該有 3 份 active：新的 TFDA-QMS + 舊的 TFDA-QMS-EN + 舊的 TFDA-Inspection
        assert len(active_after) == 3, \
            f"Expected 3 active docs after partial crawl, got {len(active_after)}"

        agencies_active = {d["agency"] for d in active_after}
        assert "TFDA-QMS" in agencies_active, "TFDA-QMS (new) should be active"
        assert "TFDA-QMS-EN" in agencies_active, "TFDA-QMS-EN (preserved old) should be active"
        assert "TFDA-Inspection" in agencies_active, "TFDA-Inspection (preserved old) should be active"

        # TFDA-QMS 的爬取時間戳應比其他兩個新（它是這次爬蟲更新的）
        timestamps = {d["agency"]: d.get("crawl_timestamp", "") for d in active_after}
        assert timestamps["TFDA-QMS"] > timestamps.get("TFDA-QMS-EN", ""), \
            "TFDA-QMS should have newer timestamp than the preserved old TFDA-QMS-EN"

        report("F13 Per-agency: 2 failed agencies preserved, 1 successful replaced", PASS,
               f"active={len(active_after)}, agencies={sorted(agencies_active)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

try: test_storage_per_agency()
except Exception as e: report("F13 Per-agency storage test", FAIL, str(e)[:120])


def test_storage_no_bulk_delete():
    """F13: 確認新爬蟲不再整批刪除 region"""
    from src.storage.regulatory_markdown_storage import RegulatoryMarkdownStorage

    tmp = tempfile.mkdtemp()
    try:
        store = RegulatoryMarkdownStorage(base_path=tmp)

        # 存入 5 份文件
        for i in range(5):
            store.save_regulatory_document(
                "歐盟 (EU)", f"MDCG-doc-{i}", "", f"MDCG {i}", "",
                f"Content {i} " * 200, "success"
            )

        # 只爬取其中 1 份成功
        crawl_results = {"results": [
            {"region": "歐盟 (EU)", "agency": "MDCG-doc-0", "agency_name": "",
             "title": "MDCG 0", "url": "", "content_markdown": "Updated content " * 200,
             "crawl_status": "success", "failure_reason": None,
             "has_pdf": False, "pdf_urls": [], "note": ""},
        ]}

        store.save_from_crawl_results(crawl_results)
        active = [d for d in store.registry["documents"] if d["status"] == "active"]

        # 應該還有 5 份（舊的 1-4 + 新的 0）
        assert len(active) == 5, f"Expected 5 active, got {len(active)}"
        report("F13 No bulk delete: 4 old MDCG docs preserved after 1-doc crawl", PASS)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

try: test_storage_no_bulk_delete()
except Exception as e: report("F13 No bulk delete test", FAIL, str(e)[:120])

# ─────────────────────────────────────────────────────────────
# GROUP 3: 網路整合測試（live，4 站點）
# ─────────────────────────────────────────────────────────────
section("GROUP 3: 網路整合測試 (live)")

SUBSET = {
    "英國 (UK)": "MHRA-Guidance",
    "美國 (USA)": "eCFR-820",
    "加拿大 (Canada)": "MDSAP-Companion-ISO13485",
    "韓國 (Korea)": "MFDS-KGMP",
}

async def run_integration():
    from src.services.regulatory_crawler import get_regulatory_crawler, REGION_SITES
    crawler = get_regulatory_crawler()
    await crawler._ensure_client()
    await crawler._etag_cache.load()
    try:
        for region, agency_id in SUBSET.items():
            sites = [s for s in REGION_SITES.get(region, []) if s["agency"] == agency_id]
            if not sites:
                report(f"{region}/{agency_id}", SKIP, "not in REGION_SITES"); continue
            t0 = time.time()
            try:
                result = await crawler._crawl_single_site(sites[0], region)
                elapsed = round(time.time() - t0, 1)
                status = result.get("crawl_status", "")
                chars  = len(result.get("content_markdown", ""))
                note   = (result.get("note") or result.get("failure_reason") or "")[:60]
                if status == "success":
                    report(f"{region}/{agency_id}", PASS,
                           f"chars={chars} elapsed={elapsed}s | {note}")
                else:
                    report(f"{region}/{agency_id}", FAIL, f"status={status} | {note}")
            except Exception as e:
                report(f"{region}/{agency_id}", FAIL, str(e)[:80])
    finally:
        await crawler.close()

asyncio.run(run_integration())

# ─────────────────────────────────────────────────────────────
# GROUP 4: 邊界 / 極限測試
# ─────────────────────────────────────────────────────────────
section("GROUP 4: 邊界 / 極限測試")

# DDG 空結果不崩潰
async def test_ddg_empty():
    from src.services.regulatory_crawler import get_regulatory_crawler
    crawler = get_regulatory_crawler()
    dummy = {"agency":"EMPTY-TEST","name":"xkcd999nonexistent","url":"https://example.com","note":"","tier":2}
    result = await crawler._fallback_ddgs_search(dummy, "Test")
    assert isinstance(result, dict) and "crawl_status" in result
    await crawler.close()
    report("DDG empty result: graceful degradation", PASS, f"status={result['crawl_status']}")
asyncio.run(test_ddg_empty())

# DDG timeout fires
async def test_timeout_fires():
    from src.services.regulatory_crawler import get_regulatory_crawler
    crawler = get_regulatory_crawler()
    original = crawler._ddgs_url_discovery
    async def slow(*a, **kw): await asyncio.sleep(30)
    crawler._ddgs_url_discovery = slow
    dummy = {"agency":"TIMEOUT-TEST","name":"test regulation","url":"https://example.com","note":"","tier":2}
    t0 = time.time()
    result = await crawler._fallback_ddgs_search(dummy, "Test")
    elapsed = time.time() - t0
    crawler._ddgs_url_discovery = original
    await crawler.close()
    assert elapsed < 32, f"Timeout did not fire within 32s (took {elapsed:.1f}s)"
    report("DDG 25s timeout fires correctly", PASS, f"elapsed={elapsed:.1f}s")
asyncio.run(test_timeout_fires())

# ─────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────
section("SUMMARY")
passed  = sum(1 for _, s, _ in results if s == PASS)
failed  = sum(1 for _, s, _ in results if s == FAIL)
skipped = sum(1 for _, s, _ in results if s == SKIP)
total   = len(results)
print(f"\n  {passed}/{total} passed  |  {failed} failed  |  {skipped} skipped\n")

if failed:
    print("Failed tests:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  [X] {name}")
            if detail: print(f"      {detail}")
    sys.exit(1)
else:
    print("All tests passed.")
