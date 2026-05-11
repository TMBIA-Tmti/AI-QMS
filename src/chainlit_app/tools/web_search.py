"""
M6: DDG Web Search Tool for Chainlit
=====================================
Provides on-demand regulatory search from the Chainlit UI, mirroring
the experience of Claude CLI / Gemini CLI built-in web search.

Search results are automatically ranked by source credibility:
  🏛️ Tier 0 (score 100) : ISO, FDA, EMA, WHO 等國際標準與法規機構
  🏛️ Tier 1 (score  80) : 政府網域（.gov、.go.jp 等）
  🎓 Tier 2 (score  60) : 學術機構（.edu、.ac.uk 等）
  ✅ Tier 3 (score  40) : 驗證機構與法律資料庫
  🌐 Tier 4 (score  20) : 一般搜尋結果
  ⬇️ Tier 9 (excluded)  : Wikipedia、社群媒體 — 自動排除

Usage in a Chainlit handler:
    from src.chainlit_app.tools.web_search import ddg_web_search, ddg_fetch_regulation

    results = await ddg_web_search("FDA QMSR 21 CFR Part 820 full text 2024")
    content  = await ddg_fetch_regulation(results[0]["href"])
"""

import asyncio
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# ── 來源可信度排序（與 regulatory_crawler.py 一致）────────────────
_CRED_TIER0 = frozenset([
    "iso.org", "who.int", "iec.ch",
    "fda.gov", "federalregister.gov", "ecfr.gov", "hhs.gov",
    "ema.europa.eu", "health.ec.europa.eu", "ec.europa.eu", "eur-lex.europa.eu",
    "pmda.go.jp", "mhlw.go.jp", "nmpa.gov.cn", "english.nmpa.gov.cn",
    "mfds.go.kr", "tga.gov.au", "hsa.gov.sg", "sfda.gov.sa",
    "anvisa.gov.br", "health.gov.il", "swissmedic.ch", "fedlex.admin.ch",
    "mhra.gov.uk", "legislation.gov.uk", "gov.uk",
])
_CRED_GOV = (".gov", ".go.jp", ".go.kr", ".gov.au", ".gov.uk", ".gov.br",
             ".gov.in", ".gov.sg", ".gov.my", ".gov.ph", ".gc.ca",
             ".admin.ch", ".gouv.fr", ".bund.de",
             "laws-lois.justice.gc.ca", "law.moj.gov.tw",
             "laws.e-gov.go.jp", "austlii.edu.au", "mdsap.global")
_CRED_EXCL = frozenset([
    "wikipedia.org", "wikimedia.org", "wikidata.org",
    "reddit.com", "quora.com", "medium.com", "linkedin.com",
    "facebook.com", "twitter.com", "x.com", "youtube.com",
])


def _credibility_score(url: str) -> int:
    """來源可信度分數：100=最高權威，-1=排除。"""
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return 20
    for e in _CRED_EXCL:
        if host == e or host.endswith("." + e):
            return -1
    for t0 in _CRED_TIER0:
        if host == t0 or host.endswith("." + t0):
            return 100
    for g in _CRED_GOV:
        if host.endswith(g) or g in host:
            return 80
    if any(host.endswith(s) for s in (".edu", ".ac.uk", ".ac.jp", ".ac.kr")):
        return 60
    if any(k in host for k in ("legal", "law", "lex", "legis", "regulation",
                                "standard", "luatvietnam", "zakonrf",
                                "medical-device-regulation")):
        return 40
    return 20


def rank_by_credibility(results: list) -> list:
    """依來源可信度排序，自動移除 Wikipedia 等 Tier 9 來源。"""
    scored = [(r, _credibility_score(r.get("href", r.get("link", ""))))
              for r in results]
    return [r for r, s in sorted(scored, key=lambda x: x[1], reverse=True)
            if s >= 0]


# ─────────────────────────────────────────────────────────────────

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
}

_JINA_READER_BASE = "https://r.jina.ai/"
_FETCH_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def ddg_web_search(query: str, max_results: int = 8) -> list[dict]:
    """Search DuckDuckGo and return results ranked by source credibility.

    Each result: {"title": str, "href": str, "body": str}
    Results are sorted: 🏛️ 官方法規機構 > 🏛️ 政府網域 > 🎓 學術 > 🌐 一般
    Wikipedia 及社群媒體（Tier 9）自動排除。
    Returns empty list on any error (never raises).
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        raw = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=max_results))
        )
        return rank_by_credibility(raw) if raw else []
    except Exception as e:
        logger.warning("DDG web search failed: %s", str(e)[:120])
        return []


async def ddg_fetch_regulation(
    url: str,
    use_jina: bool = True,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """Fetch a regulatory page and return its markdown content.

    Tries direct httpx fetch first; falls back to Jina Reader if blocked.
    Returns empty string on complete failure.
    """
    if not url or not url.startswith(("http://", "https://")):
        return ""

    close_client = False
    if client is None:
        client = httpx.AsyncClient(
            http2=True,
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT,
        )
        close_client = True

    content = ""
    try:
        # Try direct fetch with MarkItDown conversion
        try:
            from markitdown import MarkItDown
            import io

            resp = await client.get(url, headers=_DEFAULT_HEADERS, timeout=_FETCH_TIMEOUT)
            if resp.status_code == 200:
                md = MarkItDown()
                result = md.convert_stream(
                    io.BytesIO(resp.content),
                    mime_type=resp.headers.get("content-type", "text/html"),
                )
                content = result.text_content or ""
        except Exception as e:
            logger.debug("Direct fetch failed (%s): %s", url[:60], str(e)[:80])

        # Jina Reader fallback
        if (not content or len(content) < 500) and use_jina:
            try:
                jina_url = f"{_JINA_READER_BASE}{url}"
                resp = await client.get(
                    jina_url,
                    headers={"Accept": "text/markdown"},
                    timeout=httpx.Timeout(45.0, connect=15.0),
                )
                if resp.status_code == 200:
                    content = resp.text
            except Exception as e:
                logger.debug("Jina fetch failed (%s): %s", url[:60], str(e)[:80])

        return content
    finally:
        if close_client:
            await client.aclose()


async def regulatory_web_search_tool(
    query: str,
    fetch_top_n: int = 2,
) -> dict:
    """High-level tool: search DDG, fetch top N results, return consolidated markdown.

    Designed to be called from Chainlit @cl.step handlers.

    Returns:
        {
            "query": str,
            "results": [{"title", "href", "content"}, ...],
            "combined_markdown": str,
        }
    """
    search_results = await ddg_web_search(query, max_results=8)
    if not search_results:
        return {"query": query, "results": [], "combined_markdown": ""}

    async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
        fetch_tasks = [
            ddg_fetch_regulation(
                sr.get("href", sr.get("link", "")),
                use_jina=True,
                client=client,
            )
            for sr in search_results[:fetch_top_n]
            if sr.get("href") or sr.get("link")
        ]
        fetched = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    enriched = []
    for i, sr in enumerate(search_results):
        content = ""
        if i < len(fetched) and isinstance(fetched[i], str):
            content = fetched[i]
        enriched.append({
            "title": sr.get("title", ""),
            "href": sr.get("href", sr.get("link", "")),
            "snippet": sr.get("body", ""),
            "content": content,
        })

    parts = []
    for item in enriched:
        if item["content"]:
            parts.append(f"## {item['title']}\n\n{item['content'][:3000]}\n\n來源: {item['href']}")
        else:
            parts.append(f"## {item['title']}\n\n{item['snippet']}\n\n來源: {item['href']}")

    return {
        "query": query,
        "results": enriched,
        "combined_markdown": "\n\n---\n\n".join(parts),
    }
