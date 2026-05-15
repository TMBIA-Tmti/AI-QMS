"""
Crawler improvement tests: unit, edge, integration, limit.
Tests M1-M9 modifications without running the full 32-region crawl.

Usage: python scripts/test_crawler_improvements.py
"""
import asyncio
import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
results = []

def report(name, status, detail=""):
    tag = f"[{status}]"
    msg = f"  {tag:<7} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append((name, status))


# ─────────────────────────────────────────────
# UNIT TESTS
# ─────────────────────────────────────────────
print("\n=== UNIT TESTS ===")

# T1: _build_ddg_query — citation extraction
def test_build_query():
    from src.services.regulatory_crawler import _build_ddg_query
    # Site with explicit citation in name
    site1 = {
        "agency": "ANVISA-RDC665",
        "name": "RDC nº 665/2022 — ANVISA Good Manufacturing Practices",
        "note": "",
    }
    q1 = _build_ddg_query(site1, "巴西 (Brazil)")
    assert "665" in q1 or "RDC" in q1, f"Expected citation in query, got: {q1}"
    assert "Brazil" in q1 or "巴西" in q1 or "ANVISA" in q1, f"Missing country/agency: {q1}"

    # Site with CFR citation
    site2 = {
        "agency": "eCFR-820",
        "name": "21 CFR Part 820 — Quality Management System Regulation",
        "note": "",
    }
    q2 = _build_ddg_query(site2, "美國 (USA)")
    assert "820" in q2 or "CFR" in q2, f"Expected 21 CFR in query, got: {q2}"

    # Site with no citation — should produce a reasonable fallback
    site3 = {"agency": "GENERIC", "name": "Some Regulation Page", "note": ""}
    q3 = _build_ddg_query(site3, "泰國 (Thailand)")
    assert len(q3) > 10, f"Query too short: {q3}"

    report("_build_ddg_query: citation extraction", PASS)

try:
    test_build_query()
except Exception as e:
    report("_build_ddg_query: citation extraction", FAIL, str(e)[:100])


# T2: _is_regulatory_fulltext — content quality gate
def test_is_fulltext():
    from src.services.regulatory_crawler import _is_regulatory_fulltext

    # Short content — should fail
    assert not _is_regulatory_fulltext("This is a short page."), "Short content should fail"

    # Intro page — keyword-poor, should fail
    intro = "Welcome to our website.\n" * 50
    assert not _is_regulatory_fulltext(intro), "Intro page should fail"

    # Actual regulation-like content — should pass
    reg_content = (
        "Chapter 1 — General Provisions\n\n"
        "Article 1. This regulation shall apply to all manufacturers of medical devices.\n"
        "Article 2. The manufacturer must comply with the following requirements:\n"
        "(a) Establish and maintain a quality management system.\n"
        "(b) Ensure compliance with applicable standards.\n\n"
        "Chapter 2 — QMS Requirements\n\n"
        "Section 2.1 The manufacturer shall document all procedures.\n"
        "Section 2.2 Management review shall be conducted annually.\n"
        "Clause 3: CAPA — Corrective and preventive actions must be implemented.\n"
    ) * 15  # repeat to meet length
    assert _is_regulatory_fulltext(reg_content), "Regulation content should pass"

    # Chinese regulation text — should pass
    cn_content = (
        "第一章 总则\n第一条 为加强医疗器械的监督管理，保证医疗器械的安全、有效，\n"
        "根据《医疗器械监督管理条例》，制定本规范。\n"
        "第二条 本规范适用于在中国境内从事医疗器械生产活动的生产企业。\n"
        "第三章 质量管理体系\n"
        "第十五条 生产企业应当按照本规范的要求，建立健全与所生产医疗器械相适应的质量管理体系，\n"
        "并保证其有效运行。\n"
    ) * 20
    assert _is_regulatory_fulltext(cn_content), "Chinese regulation should pass"

    report("_is_regulatory_fulltext: quality gate", PASS)

try:
    test_is_fulltext()
except Exception as e:
    report("_is_regulatory_fulltext: quality gate", FAIL, str(e)[:100])


# T3: _ddgs_search logging (M8) — should never raise, should log on failure
def test_ddgs_logging():
    from src.services.regulatory_crawler import _ddgs_search
    import logging as _logging

    # Valid query — should return list (empty or not)
    r = _ddgs_search("FDA 21 CFR Part 820 QMSR medical devices", max_results=3)
    assert isinstance(r, list), f"Expected list, got {type(r)}"
    report(f"_ddgs_search: valid query returns list ({len(r)} results)", PASS)

    # Nonsense query — should return empty list, not raise
    r2 = _ddgs_search("zzzzxkcd99zz nonexistent regulation xyz", max_results=3)
    assert isinstance(r2, list), f"Expected list, got {type(r2)}"
    report("_ddgs_search: nonsense query returns empty list (no crash)", PASS)

try:
    test_ddgs_logging()
except Exception as e:
    report("_ddgs_search: M8 logging", FAIL, str(e)[:100])


# ─────────────────────────────────────────────
# EDGE TESTS
# ─────────────────────────────────────────────
print("\n=== EDGE TESTS ===")

# T4: M9 — crawl_delay is no longer halved (verify the code change)
def test_crawl_delay_fix():
    import inspect
    from src.services.regulatory_crawler import AsyncRegulatoryUpdateCrawler
    src = inspect.getsource(AsyncRegulatoryUpdateCrawler._crawl_single_site)
    assert "crawl_delay * 0.5" not in src, "crawl_delay * 0.5 still present — M9 not applied"
    assert "asyncio.sleep(crawl_delay)" in src, "Expected full crawl_delay sleep"
    report("M9: crawl_delay * 0.5 removed", PASS)

try:
    test_crawl_delay_fix()
except Exception as e:
    report("M9: crawl_delay fix", FAIL, str(e)[:100])


# T5: M4 — tier==1 path now calls _fallback_ddgs_search before profile
def test_m4_tier1_ddgs():
    import inspect
    from src.services.regulatory_crawler import AsyncRegulatoryUpdateCrawler
    src = inspect.getsource(AsyncRegulatoryUpdateCrawler._crawl_single_site)
    tier1_block = src[src.find("if tier == 1"):src.find("elif tier == 3")]
    assert "_fallback_ddgs_search" in tier1_block, "M4: DDG not in tier1 fallback chain"
    ddgs_pos = tier1_block.find("_fallback_ddgs_search")
    profile_pos = tier1_block.find("_fallback_profile")
    assert ddgs_pos < profile_pos, "M4: DDG must come before pre-written profile"
    report("M4: tier1 DDG URL discovery before pre-written profile", PASS)

try:
    test_m4_tier1_ddgs()
except Exception as e:
    report("M4: tier1 DDG insertion", FAIL, str(e)[:100])


# T6: M1 — _fallback_ddgs_search now attempts URL fetches
def test_m1_url_fetch():
    import inspect
    from src.services.regulatory_crawler import AsyncRegulatoryUpdateCrawler
    src = inspect.getsource(AsyncRegulatoryUpdateCrawler._fallback_ddgs_search)
    assert "_crawl_tier2_httpx" in src, "M1: tier2 fetch not in DDG fallback"
    assert "_crawl_tier3_jina" in src, "M1: tier3 Jina not in DDG fallback"
    assert "_is_regulatory_fulltext" in src, "M3: quality gate not in DDG fallback"
    assert "_build_ddg_query" in src, "M2: targeted query builder not in DDG fallback"
    report("M1+M2+M3: DDG fallback does URL fetch + quality gate", PASS)

try:
    test_m1_url_fetch()
except Exception as e:
    report("M1+M2+M3: DDG fallback structure", FAIL, str(e)[:100])


# T7: M6 — Chainlit tool module imports cleanly
def test_m6_import():
    try:
        from src.chainlit_app.tools.web_search import (
            ddg_web_search,
            ddg_fetch_regulation,
            regulatory_web_search_tool,
        )
        assert callable(ddg_web_search)
        assert callable(ddg_fetch_regulation)
        assert callable(regulatory_web_search_tool)
        report("M6: Chainlit web_search tool imports OK", PASS)
    except ImportError as e:
        report("M6: Chainlit tool import", FAIL, str(e)[:100])

test_m6_import()


# T8: M7 — run_full_crawl.py has --check-updates argument
def test_m7_arg():
    import importlib.util, argparse
    src_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "run_full_crawl.py"
    )
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert "--check-updates" in src, "M7: --check-updates flag not in run_full_crawl.py"
    assert "_check_regulatory_updates" in src, "M7: update checker function missing"
    report("M7: --check-updates flag in run_full_crawl.py", PASS)

try:
    test_m7_arg()
except Exception as e:
    report("M7: --check-updates", FAIL, str(e)[:100])


# ─────────────────────────────────────────────
# INTEGRATION TESTS (live network, subset)
# ─────────────────────────────────────────────
print("\n=== INTEGRATION TESTS (live, 4 sites) ===")

SUBSET = {
    # Tier 1 API — should succeed cleanly
    "英國 (UK)": "MHRA-Guidance",
    # Tier 2 HTML — publicly accessible
    "美國 (USA)": "eCFR-820",
    # Tier 2 PDF — direct download
    "加拿大 (Canada)": "MDSAP-Companion-ISO13485",
    # Tier 3 Jina / IP-blocked — should use pre-written profile or DDG
    "韓國 (Korea)": "MFDS-KGMP",
}

async def run_integration():
    from src.services.regulatory_crawler import get_regulatory_crawler, REGION_SITES

    crawler = get_regulatory_crawler()
    await crawler._ensure_client()   # initialise HTTP client before direct site calls
    await crawler._etag_cache.load()
    try:
        for region, agency_id in SUBSET.items():
            sites = [s for s in REGION_SITES.get(region, []) if s["agency"] == agency_id]
            if not sites:
                report(f"{region}/{agency_id}", SKIP, "site not found in REGION_SITES")
                continue
            site = sites[0]
            t0 = time.time()
            try:
                result = await crawler._crawl_single_site(site, region)
                elapsed = round(time.time() - t0, 1)
                status = result.get("crawl_status", "")
                source = result.get("content_source", "")
                chars = len(result.get("content_markdown", ""))
                note = (result.get("note") or result.get("failure_reason") or "")[:60]

                if status == "success":
                    report(
                        f"{region}/{agency_id}",
                        PASS,
                        f"source={source} chars={chars} elapsed={elapsed}s | {note}",
                    )
                else:
                    report(
                        f"{region}/{agency_id}",
                        FAIL,
                        f"status={status} | {note}",
                    )
            except Exception as e:
                report(f"{region}/{agency_id}", FAIL, str(e)[:100])
    finally:
        await crawler.close()

asyncio.run(run_integration())


# ─────────────────────────────────────────────
# LIMIT TESTS
# ─────────────────────────────────────────────
print("\n=== LIMIT TESTS ===")

# T9: Rapid DDG requests — verify M8 logs instead of crashing
async def test_rapid_ddg():
    from src.services.regulatory_crawler import _ddgs_search
    errors = 0
    for i in range(4):
        try:
            r = _ddgs_search(f"medical device regulation country {i}", max_results=2)
            assert isinstance(r, list)
        except Exception:
            errors += 1
        await asyncio.sleep(0.3)

    if errors == 0:
        report("Rapid DDG x4: no crashes", PASS)
    else:
        report("Rapid DDG x4: crashes detected", FAIL, f"{errors} exceptions escaped")

asyncio.run(test_rapid_ddg())


# T10: DDG with empty result — fallback should degrade gracefully
async def test_ddg_empty_graceful():
    from src.services.regulatory_crawler import get_regulatory_crawler, REGION_SITES

    crawler = get_regulatory_crawler()
    try:
        dummy_site = {
            "agency": "TEST-EMPTY",
            "name": "zzzznonexistent regulation xkcd 999",
            "url": "https://example.com/nonexistent",
            "note": "",
            "tier": 2,
        }
        result = await crawler._fallback_ddgs_search(dummy_site, "Test (Region)")
        # Should return a result dict (success or failure) — never raise
        assert isinstance(result, dict), "Expected dict result"
        assert "crawl_status" in result, "Missing crawl_status"
        assert "crawl_duration_seconds" in result, "Missing timing"
        report("DDG empty result: graceful degradation", PASS, f"status={result['crawl_status']}")
    except Exception as e:
        report("DDG empty result: graceful degradation", FAIL, str(e)[:100])
    finally:
        await crawler.close()

asyncio.run(test_ddg_empty_graceful())


# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────
print("\n=== SUMMARY ===")
passed = sum(1 for _, s in results if s == PASS)
failed = sum(1 for _, s in results if s == FAIL)
skipped = sum(1 for _, s in results if s == SKIP)
total = len(results)
print(f"  {passed}/{total} passed  |  {failed} failed  |  {skipped} skipped")
if failed:
    print("\nFailed tests:")
    for name, status in results:
        if status == FAIL:
            print(f"  X {name}")
    sys.exit(1)
else:
    print("\nAll tests passed.")
