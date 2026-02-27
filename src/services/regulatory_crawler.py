"""
AI-QMS — Async Regulatory Website Crawler Module (v2.0)
=======================================================

High-performance async crawler for global medical device regulatory websites.

Architecture:
  Tier 0: XML Sitemap pre-scan — detect recently-updated pages via <lastmod>
  Tier 1: API / RSS / JSON   — structured data endpoints (fastest, most reliable)
  Tier 2: httpx async + MarkItDown — HTML fetch → BS4 cleanup → MarkItDown convert
  Tier 3: Jina Reader API    — for anti-scraping / SPA / blocked sites

Features:
  - asyncio.gather parallel crawling across all sites
  - httpx.AsyncClient with HTTP/2, shared connection pool
  - tenacity exponential-backoff retry
  - HTTP ETag / If-Modified-Since conditional caching
  - Per-domain asyncio.Semaphore rate limiting
  - aiofiles async I/O for cache persistence
  - MarkItDown convert_stream for HTML→Markdown (with BS4 pre-strip)
  - Jina Reader API fallback for JS-rendered / anti-bot sites
  - DuckDuckGo supplementary search

Output schema is backward-compatible with v1.0 (sync crawler).
"""

import io
import re
import json
import time
import hashlib
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
import aiofiles
from bs4 import BeautifulSoup

# tenacity retry
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
    )

    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

# DuckDuckGo search (ddgs >= 8.0 or legacy)
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

# MarkItDown for HTML → Markdown conversion
try:
    from markitdown import MarkItDown

    _MD_CONVERTER = MarkItDown()
    MARKITDOWN_AVAILABLE = True
except ImportError:
    _MD_CONVERTER = None
    MARKITDOWN_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================================
# Region & Site Configuration (with Tier assignments)
# ============================================================
#
# Tier 0: Sitemap pre-scan (optional, via sitemap_url field)
# Tier 1: API / RSS / JSON endpoints
# Tier 2: httpx async + BS4 cleanup + MarkItDown
# Tier 3: Jina Reader API (anti-scraping / SPA / blocked)

REGION_SITES = {
    "台灣 (Taiwan)": [
        {
            "agency": "TFDA",
            "name": "衛生福利部食品藥物管理署",
            "url": "https://www.fda.gov.tw/TC/siteList.aspx?sid=11652&scid=791",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "sitemap_url": "https://www.fda.gov.tw/sitemap.xml",
        },
        {
            "agency": "TFDA-Regulations",
            "name": "TFDA 法規專區",
            "url": "https://www.fda.gov.tw/TC/siteList.aspx?sid=310",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "sitemap_url": "https://www.fda.gov.tw/sitemap.xml",
        },
        {
            "agency": "CDE",
            "name": "醫療器材審查中心 (CDE)",
            "url": "https://regulation.cde.org.tw/10254/8725/56201/regPost",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "美國 (USA)": [
        {
            "agency": "FDA-Guidance",
            "name": "FDA Guidance Documents",
            "url": "https://www.fda.gov/regulatory-information/search-fda-guidance-documents",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "sitemap_url": "https://www.fda.gov/sitemap.xml",
        },
        {
            "agency": "FDA-QMSR",
            "name": "FDA QMSR (Quality Management System Regulation)",
            "url": "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/quality-management-system-information-certain-premarket-submission-reviews",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "sitemap_url": "https://www.fda.gov/sitemap.xml",
        },
        {
            "agency": "eCFR",
            "name": "21 CFR Part 820 (eCFR API)",
            "url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-21.json?chapter=I&subchapter=H&part=820",
            "tier": 1,
            "strategy": "api_json",
            "crawl_delay": 3,
        },
        {
            "agency": "Federal-Register",
            "name": "Federal Register - FDA Final Rules",
            "url": "https://www.federalregister.gov/api/v1/documents?conditions[agencies][]=food-and-drug-administration&conditions[type][]=RULE&per_page=20&order=newest",
            "tier": 1,
            "strategy": "api_json",
            "crawl_delay": 3,
        },
    ],
    "歐盟 (EU)": [
        {
            "agency": "MDCG",
            "name": "MDCG Guidance Documents",
            "url": "https://health.ec.europa.eu/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents-and-other-guidance_en",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "sitemap_url": "https://health.ec.europa.eu/sitemap.xml",
        },
        {
            "agency": "EUR-Lex-MDR",
            "name": "EU MDR 2017/745",
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32017R0745",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
        },
        {
            "agency": "EMA",
            "name": "EMA Medical Devices",
            "url": "https://www.ema.europa.eu/en/human-regulatory-overview/medical-devices",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "sitemap_url": "https://www.ema.europa.eu/sitemap.xml",
        },
    ],
    "英國 (UK)": [
        {
            "agency": "MHRA",
            "name": "MHRA Medical Devices Guidance",
            "url": "https://www.gov.uk/api/content/guidance/regulating-medical-devices-in-the-uk",
            "tier": 1,
            "strategy": "api_json",
            "crawl_delay": 3,
        },
        {
            "agency": "UK-Legislation",
            "name": "UK MDR 2002",
            "url": "https://www.legislation.gov.uk/uksi/2002/618/contents/made/data.json",
            "tier": 1,
            "strategy": "api_json",
            "crawl_delay": 3,
        },
    ],
    "日本 (Japan)": [
        {
            "agency": "PMDA",
            "name": "PMDA QMS Inspections",
            "url": "https://www.pmda.go.jp/english/review-services/reviews/0001.html",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "中國 (China)": [
        {
            "agency": "NMPA",
            "name": "NMPA 醫療器械法規",
            "url": "https://www.nmpa.gov.cn/xxgk/fgwj/gzwj/gzwjylqx/index.html",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "High anti-scraping — Jina Reader fallback",
        },
    ],
    "韓國 (Korea)": [
        {
            "agency": "MFDS",
            "name": "MFDS Medical Device Regulations",
            "url": "https://www.mfds.go.kr/eng/wpge/m_37/de0110011001.do",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "加拿大 (Canada)": [
        {
            "agency": "Health-Canada",
            "name": "Health Canada MDALL",
            "url": "https://health-products.canada.ca/api/medical-devices/device/?type=json&state=active&limit=20",
            "tier": 1,
            "strategy": "api_json",
            "crawl_delay": 3,
        },
    ],
    "澳洲 (Australia)": [
        {
            "agency": "TGA",
            "name": "TGA Medical Devices",
            "url": "https://www.tga.gov.au/products/medical-devices/overview/australian-regulatory-guidelines-medical-devices-argmd",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Frequent timeouts — Jina Reader fallback",
        },
    ],
    "瑞士 (Switzerland)": [
        {
            "agency": "Swissmedic",
            "name": "Swissmedic Medical Devices",
            "url": "https://www.swissmedic.ch/swissmedic/en/home/medical-devices.html",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "巴西 (Brazil)": [
        {
            "agency": "ANVISA",
            "name": "ANVISA Medical Devices",
            "url": "https://www.gov.br/anvisa/pt-br/assuntos/produtossaude/produtos-para-a-saude",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Inconsistent availability — Jina Reader fallback",
        },
    ],
    "國際標準 (International)": [
        {
            "agency": "ISO",
            "name": "ISO Medical Equipment Standards (ICS 11.040)",
            "url": "https://www.iso.org/ics/11.040/x/",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Blocks AI bots — metadata only via Jina",
            "sitemap_url": "https://www.iso.org/sitemap.xml",
        },
        {
            "agency": "ICH",
            "name": "ICH Quality Guidelines",
            "url": "https://www.ich.org/page/quality-guidelines",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "SPA site — Jina Reader required",
        },
        {
            "agency": "IMDRF",
            "name": "IMDRF Document Library",
            "url": "https://www.imdrf.org/documents/library",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "403 Forbidden — Jina Reader fallback",
        },
    ],
    # ---------- New regions (v2.0) ----------
    "印度 (India)": [
        {
            "agency": "CDSCO",
            "name": "Central Drugs Standard Control Organization",
            "url": "https://cdsco.gov.in/opencms/opencms/en/Medical-Device-Diagnostics/Medical-Device-Diagnostics/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "新加坡 (Singapore)": [
        {
            "agency": "HSA",
            "name": "Health Sciences Authority",
            "url": "https://www.hsa.gov.sg/medical-devices",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "沙烏地阿拉伯 (Saudi Arabia)": [
        {
            "agency": "SFDA",
            "name": "Saudi Food and Drug Authority",
            "url": "https://www.sfda.gov.sa/en/medical-devices",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "泰國 (Thailand)": [
        {
            "agency": "Thai-FDA",
            "name": "Thai Food and Drug Administration",
            "url": "https://en.fda.moph.go.th/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "紐西蘭 (New Zealand)": [
        {
            "agency": "Medsafe",
            "name": "Medsafe — NZ Medical Devices",
            "url": "https://www.medsafe.govt.nz/regulatory/DevicesNew/2-About.asp",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "墨西哥 (Mexico)": [
        {
            "agency": "COFEPRIS",
            "name": "COFEPRIS — Medical Devices",
            "url": "https://www.gob.mx/cofepris",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "阿根廷 (Argentina)": [
        {
            "agency": "ANMAT",
            "name": "ANMAT — Medical Devices",
            "url": "https://www.argentina.gob.ar/anmat",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "南非 (South Africa)": [
        {
            "agency": "SAHPRA",
            "name": "South African Health Products Regulatory Authority",
            "url": "https://www.sahpra.org.za/medical-devices/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "土耳其 (Turkey)": [
        {
            "agency": "TITCK",
            "name": "Türkiye İlaç ve Tıbbi Cihaz Kurumu",
            "url": "https://www.titck.gov.tr/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "印尼 (Indonesia)": [
        {
            "agency": "BPOM",
            "name": "BPOM — Medical Devices",
            "url": "https://www.pom.go.id/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "馬來西亞 (Malaysia)": [
        {
            "agency": "MDA",
            "name": "Medical Device Authority Malaysia",
            "url": "https://www.mda.gov.my/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "以色列 (Israel)": [
        {
            "agency": "AMAR",
            "name": "Ministry of Health — Medical Device Dept",
            "url": "https://www.health.gov.il/English/Topics/MedicalDevice/Pages/default.aspx",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "菲律賓 (Philippines)": [
        {
            "agency": "FDA-PH",
            "name": "FDA Philippines — Medical Devices",
            "url": "https://www.fda.gov.ph/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "越南 (Vietnam)": [
        {
            "agency": "DAV",
            "name": "Drug Administration of Vietnam",
            "url": "https://dav.gov.vn/en",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "哥倫比亞 (Colombia)": [
        {
            "agency": "INVIMA",
            "name": "INVIMA — Medical Devices",
            "url": "https://www.invima.gov.co/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "俄羅斯 (Russia)": [
        {
            "agency": "RZN",
            "name": "Roszdravnadzor",
            "url": "https://roszdravnadzor.gov.ru/",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Geo-blocking possible — Jina Reader fallback",
        },
    ],
    "埃及 (Egypt)": [
        {
            "agency": "EDA",
            "name": "Egyptian Drug Authority",
            "url": "https://www.edaegypt.gov.eg/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "智利 (Chile)": [
        {
            "agency": "ISP",
            "name": "Instituto de Salud Pública de Chile",
            "url": "https://www.ispch.cl/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    "阿聯酋 (UAE)": [
        {
            "agency": "MOHAP",
            "name": "Ministry of Health and Prevention",
            "url": "https://mohap.gov.ae/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
}


# ============================================================
# Constants
# ============================================================

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
}

_REQUEST_TIMEOUT = 30  # seconds
_JINA_READER_BASE = "https://r.jina.ai/"
_JINA_TIMEOUT = 60  # Jina Reader may be slow
_JINA_DELAY = 3.0  # seconds between Jina requests (20 req/min limit)
_MAX_CONTENT_SIZE = 50_000  # 50KB max markdown content
_DOMAIN_CONCURRENCY = 2  # max concurrent requests per domain
_ETAG_CACHE_PATH = Path("data/etag_cache.json")

# QMS-related keywords for sitemap URL filtering
_QMS_KEYWORDS = [
    "medical-device",
    "medical_device",
    "medicaldevice",
    "guidance",
    "regulation",
    "regulatory",
    "qms",
    "quality-management",
    "quality_management",
    "iso-13485",
    "iso13485",
    "mdr",
    "ivdr",
    "510k",
    "premarket",
    "post-market",
    "device",
    "diagnostic",
]


# ============================================================
# ETag Cache (HTTP conditional request caching)
# ============================================================


class ETagCache:
    """HTTP ETag / Last-Modified conditional cache stored as JSON."""

    def __init__(self, cache_path: Path = _ETAG_CACHE_PATH):
        self._path = cache_path
        self._data: dict = {}
        self._dirty = False

    async def load(self) -> None:
        """Load cache from disk."""
        if self._path.exists():
            try:
                async with aiofiles.open(self._path, "r", encoding="utf-8") as f:
                    raw = await f.read()
                self._data = json.loads(raw) if raw.strip() else {}
            except Exception as e:
                logger.warning(f"ETag cache load failed: {e}")
                self._data = {}
        self._dirty = False

    async def save(self) -> None:
        """Persist cache to disk."""
        if not self._dirty:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self._data, ensure_ascii=False, indent=2)
            async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
                await f.write(content)
            self._dirty = False
        except Exception as e:
            logger.warning(f"ETag cache save failed: {e}")

    def get(self, url: str) -> Optional[dict]:
        """Get cached ETag/Last-Modified for a URL."""
        return self._data.get(url)

    def set(
        self,
        url: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        content_hash: Optional[str] = None,
    ) -> None:
        """Store ETag/Last-Modified/content-hash for a URL."""
        self._data[url] = {
            "etag": etag,
            "last_modified": last_modified,
            "content_hash": content_hash,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dirty = True


# ============================================================
# Sitemap Scanner (Tier 0 pre-scan)
# ============================================================

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class SitemapScanner:
    """Parse XML sitemaps to discover recently-updated regulatory URLs."""

    async def scan(
        self,
        client: httpx.AsyncClient,
        sitemap_url: str,
        last_crawl_time: Optional[str] = None,
        keywords: Optional[list] = None,
    ) -> list:
        """Scan a sitemap for recently-updated URLs matching keywords.

        Args:
            client: shared httpx.AsyncClient
            sitemap_url: URL of sitemap.xml or sitemapindex
            last_crawl_time: ISO timestamp; only return URLs updated after this
            keywords: URL path keywords to filter (default: QMS-related)

        Returns:
            List of URLs that are recently updated and match keywords.
            Empty list on any error (never raises).
        """
        kw = keywords or _QMS_KEYWORDS
        try:
            resp = await client.get(
                sitemap_url,
                headers={"Accept": "application/xml, text/xml"},
                timeout=httpx.Timeout(15.0),
            )
            if resp.status_code != 200:
                return []

            root = ET.fromstring(resp.text)
            tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

            if tag == "sitemapindex":
                return await self._scan_index(client, root, last_crawl_time, kw)
            elif tag == "urlset":
                return self._filter_urls(root, last_crawl_time, kw)
            return []

        except Exception as e:
            logger.debug(f"Sitemap scan failed for {sitemap_url}: {e}")
            return []

    async def _scan_index(
        self,
        client: httpx.AsyncClient,
        root: ET.Element,
        last_crawl_time: Optional[str],
        keywords: list,
    ) -> list:
        """Parse sitemapindex and scan child sitemaps in parallel."""
        child_urls = []
        for sitemap_el in root.findall("sm:sitemap", _SITEMAP_NS):
            loc = sitemap_el.find("sm:loc", _SITEMAP_NS)
            lastmod = sitemap_el.find("sm:lastmod", _SITEMAP_NS)
            if loc is None:
                continue
            # Skip child sitemaps not updated since last crawl
            if last_crawl_time and lastmod is not None and lastmod.text:
                if lastmod.text < last_crawl_time:
                    continue
            child_urls.append(loc.text)

        if not child_urls:
            return []

        # Scan up to 5 child sitemaps in parallel
        all_urls = []
        for batch_start in range(0, len(child_urls), 5):
            batch = child_urls[batch_start : batch_start + 5]
            tasks = []
            for curl in batch:
                tasks.append(
                    self._fetch_and_filter(client, curl, last_crawl_time, keywords)
                )
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    all_urls.extend(r)

        return all_urls[:100]  # cap at 100 URLs

    async def _fetch_and_filter(
        self,
        client: httpx.AsyncClient,
        sitemap_url: str,
        last_crawl_time: Optional[str],
        keywords: list,
    ) -> list:
        """Fetch a single child sitemap and filter URLs."""
        try:
            resp = await client.get(
                sitemap_url,
                headers={"Accept": "application/xml, text/xml"},
                timeout=httpx.Timeout(15.0),
            )
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.text)
            return self._filter_urls(root, last_crawl_time, keywords)
        except Exception:
            return []

    @staticmethod
    def _filter_urls(
        root: ET.Element,
        last_crawl_time: Optional[str],
        keywords: list,
    ) -> list:
        """Extract URLs from <urlset> matching keywords and lastmod filter."""
        matched = []
        for url_el in root.findall("sm:url", _SITEMAP_NS):
            loc = url_el.find("sm:loc", _SITEMAP_NS)
            if loc is None or not loc.text:
                continue
            url_text = loc.text.lower()

            # Keyword filter
            if not any(kw in url_text for kw in keywords):
                continue

            # Lastmod filter
            if last_crawl_time:
                lastmod = url_el.find("sm:lastmod", _SITEMAP_NS)
                if lastmod is not None and lastmod.text:
                    if lastmod.text < last_crawl_time:
                        continue

            matched.append(loc.text)

        return matched


# ============================================================
# Helpers — Content conversion
# ============================================================


def _bs4_strip_boilerplate(html: str) -> str:
    """Remove nav, footer, header, script, style, aside from HTML.

    This is a lightweight pre-processing step before MarkItDown.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(
            ["script", "style", "nav", "footer", "header", "aside", "noscript"]
        ):
            tag.decompose()

        # Try to isolate main content
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", {"role": "main"})
            or soup.find("div", {"id": re.compile(r"content|main", re.I)})
            or soup.find("div", {"class": re.compile(r"content|main", re.I)})
        )
        target = main if main else soup.body if soup.body else soup
        return str(target)
    except Exception:
        return html


def _html_to_markdown(html: str, url: str = "") -> str:
    """Convert HTML to Markdown — MarkItDown primary, BS4 fallback."""
    # First try MarkItDown (higher quality)
    if MARKITDOWN_AVAILABLE and _MD_CONVERTER:
        try:
            stripped = _bs4_strip_boilerplate(html)
            result = _MD_CONVERTER.convert_stream(
                io.BytesIO(stripped.encode("utf-8")),
                file_extension=".html",
            )
            md = result.text_content or ""
            if md.strip() and len(md.strip()) > 50:
                if len(md) > _MAX_CONTENT_SIZE:
                    md = md[:_MAX_CONTENT_SIZE] + "\n\n... (content truncated)"
                return md
        except Exception as e:
            logger.debug(f"MarkItDown failed for {url}: {e}, falling back to BS4")

    # Fallback: manual BS4 extraction
    return _html_to_markdown_bs4(html, url)


def _html_to_markdown_bs4(html: str, url: str = "") -> str:
    """Fallback: Convert HTML to Markdown using BeautifulSoup extraction."""
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(
            ["script", "style", "nav", "footer", "header", "aside", "noscript"]
        ):
            tag.decompose()

        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", {"role": "main"})
            or soup.find("div", {"id": re.compile(r"content|main", re.I)})
            or soup.find("div", {"class": re.compile(r"content|main", re.I)})
        )
        target = main if main else soup.body if soup.body else soup

        lines = []
        title = soup.find("title")
        if title and title.string:
            lines.append(f"# {title.string.strip()}")
            lines.append("")

        for element in target.find_all(
            ["h1", "h2", "h3", "h4", "p", "li", "td", "th", "pre", "blockquote"]
        ):
            text = element.get_text(strip=True)
            if not text:
                continue
            tag_name = element.name
            if tag_name == "h1":
                lines.append(f"# {text}")
            elif tag_name == "h2":
                lines.append(f"## {text}")
            elif tag_name == "h3":
                lines.append(f"### {text}")
            elif tag_name == "h4":
                lines.append(f"#### {text}")
            elif tag_name == "li":
                lines.append(f"- {text}")
            elif tag_name in ("td", "th"):
                continue
            elif tag_name == "pre":
                lines.append(f"```\n{text}\n```")
            elif tag_name == "blockquote":
                lines.append(f"> {text}")
            else:
                lines.append(text)
            lines.append("")

        # Extract tables
        for table in target.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            table_lines = []
            for i, row in enumerate(rows[:50]):
                cells = row.find_all(["th", "td"])
                cell_texts = [c.get_text(strip=True)[:100] for c in cells]
                if cell_texts:
                    table_lines.append("| " + " | ".join(cell_texts) + " |")
                    if i == 0:
                        table_lines.append(
                            "| " + " | ".join(["---"] * len(cell_texts)) + " |"
                        )
            if table_lines:
                lines.extend(table_lines)
                lines.append("")

        markdown = "\n".join(lines)
        if len(markdown) > _MAX_CONTENT_SIZE:
            markdown = markdown[:_MAX_CONTENT_SIZE] + "\n\n... (content truncated)"
        return markdown if markdown.strip() else f"(No extractable content from {url})"

    except Exception as e:
        return f"(HTML parsing failed: {e})"


def _json_to_markdown(data: dict, url: str = "") -> str:
    """Convert API JSON response to readable Markdown."""
    try:
        # eCFR API
        if "meta" in data and "content" in data:
            content = data.get("content", "")
            if isinstance(content, str):
                return _html_to_markdown(content, url)

        # Federal Register API
        if "results" in data and isinstance(data["results"], list):
            lines = ["# Federal Register — FDA Rules\n"]
            for item in data["results"][:20]:
                title = item.get("title", "N/A")
                doc_number = item.get("document_number", "")
                pub_date = item.get("publication_date", "")
                abstract = item.get("abstract", "")[:300]
                html_url = item.get("html_url", "")
                lines.append(f"## {title}")
                lines.append(f"- Document: {doc_number}")
                lines.append(f"- Published: {pub_date}")
                if abstract:
                    lines.append(f"- Abstract: {abstract}")
                if html_url:
                    lines.append(f"- URL: {html_url}")
                lines.append("")
            return "\n".join(lines)

        # GOV.UK Content API
        if "title" in data and "body" in data:
            body = data.get("body", "")
            if isinstance(body, str) and "<" in body:
                return _html_to_markdown(body, url)
            return f"# {data['title']}\n\n{body}"

        if "title" in data and "details" in data:
            details = data.get("details", {})
            body = details.get("body", "")
            if isinstance(body, str) and "<" in body:
                return f"# {data['title']}\n\n" + _html_to_markdown(body, url)
            parts = details.get("parts", [])
            lines = [f"# {data['title']}\n"]
            for part in parts:
                part_title = part.get("title", "")
                part_body = part.get("body", "")
                lines.append(f"## {part_title}")
                if isinstance(part_body, str) and "<" in part_body:
                    lines.append(_html_to_markdown(part_body, url))
                else:
                    lines.append(str(part_body))
                lines.append("")
            return "\n".join(lines)

        # Generic JSON → Markdown
        formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        if len(formatted) > _MAX_CONTENT_SIZE:
            formatted = formatted[:_MAX_CONTENT_SIZE] + "\n... (truncated)"
        return f"# API Response\n\n```json\n{formatted}\n```"

    except Exception as e:
        return f"(JSON parsing failed: {e})"


def _classify_failure(error: Exception, url: str) -> str:
    """Classify the failure reason for user-friendly reporting."""
    err_str = str(error).lower()

    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 403:
            return "HTTP 403 Forbidden — 網站拒絕存取 (可能封鎖爬蟲)"
        elif status == 429:
            return "HTTP 429 Too Many Requests — 請求過於頻繁"
        elif status == 404:
            return "HTTP 404 Not Found — 頁面不存在或已移動"
        elif status == 503:
            return "HTTP 503 Service Unavailable — 伺服器暫時無法使用"
        else:
            return f"HTTP {status} — 伺服器回應錯誤"

    if isinstance(error, httpx.TimeoutException):
        return f"連線逾時 (超過 {_REQUEST_TIMEOUT} 秒) — 網站回應過慢或無法連線"

    if isinstance(error, httpx.ConnectError):
        return "無法連線至伺服器 — DNS 解析失敗或網路問題"

    if "ssl" in err_str or "certificate" in err_str:
        return "SSL 憑證錯誤 — 網站安全憑證問題"

    if "captcha" in err_str:
        return "需要驗證碼 (CAPTCHA) — 無法自動爬取"

    if "javascript" in err_str or "spa" in err_str:
        return "需要 JavaScript 渲染 — 純 HTTP 請求無法取得內容"

    return f"爬取失敗: {type(error).__name__}: {str(error)[:200]}"


# ============================================================
# DuckDuckGo Supplementary Search
# ============================================================


def _ddgs_search(query: str, max_results: int = 5) -> list:
    """Search DuckDuckGo for supplementary regulatory info."""
    if DDGS is None:
        return []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception:
        return []


# ============================================================
# Fetch with retry (tenacity)
# ============================================================


async def _fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: Optional[dict] = None,
    timeout: Optional[httpx.Timeout] = None,
) -> httpx.Response:
    """Fetch a URL with exponential-backoff retry.

    Retries on connection errors, timeouts, and 5xx status codes.
    """
    _timeout = timeout or httpx.Timeout(_REQUEST_TIMEOUT, connect=10.0)
    _headers = dict(_DEFAULT_HEADERS)
    if headers:
        _headers.update(headers)

    if TENACITY_AVAILABLE:

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
            reraise=True,
        )
        async def _inner():
            resp = await client.get(url, headers=_headers, timeout=_timeout)
            # Retry on 5xx
            if resp.status_code >= 500:
                resp.raise_for_status()
            return resp

        return await _inner()
    else:
        # No tenacity: single attempt
        resp = await client.get(url, headers=_headers, timeout=_timeout)
        return resp


# ============================================================
# Tier Handlers
# ============================================================


def _make_result_template(site: dict, region: str) -> dict:
    """Create a result dict template with default values."""
    return {
        "region": region,
        "agency": site.get("agency", "Unknown"),
        "agency_name": site.get("name", site.get("agency", "")),
        "url": site.get("url", ""),
        "title": "",
        "content_markdown": "",
        "crawl_status": "failed",
        "failure_reason": None,
        "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
        "crawl_duration_seconds": 0.0,
        "note": site.get("note", ""),
    }


async def _crawl_tier1_api(
    client: httpx.AsyncClient,
    site: dict,
    region: str,
    etag_cache: ETagCache,
) -> dict:
    """Tier 1: Structured API / RSS / JSON endpoints."""
    result = _make_result_template(site, region)
    url = site["url"]
    start = time.time()

    try:
        # Conditional request headers
        req_headers = {}
        cached = etag_cache.get(url)
        if cached:
            if cached.get("etag"):
                req_headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                req_headers["If-Modified-Since"] = cached["last_modified"]

        response = await _fetch_with_retry(client, url, headers=req_headers)

        # 304 Not Modified
        if response.status_code == 304:
            result["crawl_status"] = "success"
            result["title"] = f"{site['agency']} (cached — not modified)"
            result["content_markdown"] = (
                "(Content unchanged since last crawl — HTTP 304)"
            )
            result["note"] = "HTTP 304 Not Modified — using cached version"
            result["crawl_duration_seconds"] = round(time.time() - start, 2)
            return result

        response.raise_for_status()

        # Update ETag cache
        etag = response.headers.get("ETag")
        last_mod = response.headers.get("Last-Modified")
        content_hash = hashlib.sha256(response.content).hexdigest()[:16]
        etag_cache.set(
            url, etag=etag, last_modified=last_mod, content_hash=content_hash
        )

        # Parse JSON
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type or site.get("strategy") == "api_json":
            try:
                json_data = response.json()
                result["content_markdown"] = _json_to_markdown(json_data, url)
                result["title"] = (
                    json_data.get("title", "")
                    or json_data.get("meta", {}).get("title", "")
                    or f"{site['agency']} API Response"
                )
            except Exception:
                result["content_markdown"] = _html_to_markdown(response.text, url)
                result["title"] = f"{site['agency']} Response"
        else:
            # RSS/XML/HTML fallback
            result["content_markdown"] = _html_to_markdown(response.text, url)
            try:
                soup = BeautifulSoup(response.text, "lxml")
                title_tag = soup.find("title")
                result["title"] = (
                    title_tag.string.strip()
                    if title_tag and title_tag.string
                    else site["agency"]
                )
            except Exception:
                result["title"] = site["agency"]

        if result["content_markdown"] and len(result["content_markdown"].strip()) > 50:
            result["crawl_status"] = "success"
        else:
            result["failure_reason"] = (
                "頁面內容為空或需要 JavaScript 渲染 — "
                "網站可能為 SPA 架構，純 HTTP 請求無法取得實際內容"
            )

    except Exception as e:
        result["failure_reason"] = _classify_failure(e, url)

    result["crawl_duration_seconds"] = round(time.time() - start, 2)
    return result


async def _crawl_tier2_httpx(
    client: httpx.AsyncClient,
    site: dict,
    region: str,
    etag_cache: ETagCache,
) -> dict:
    """Tier 2: HTML fetch → BS4 strip → MarkItDown conversion."""
    result = _make_result_template(site, region)
    url = site["url"]
    start = time.time()

    try:
        # Conditional request headers
        req_headers = {}
        cached = etag_cache.get(url)
        if cached:
            if cached.get("etag"):
                req_headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                req_headers["If-Modified-Since"] = cached["last_modified"]

        response = await _fetch_with_retry(client, url, headers=req_headers)

        # 304 Not Modified
        if response.status_code == 304:
            result["crawl_status"] = "success"
            result["title"] = f"{site['agency']} (cached — not modified)"
            result["content_markdown"] = (
                "(Content unchanged since last crawl — HTTP 304)"
            )
            result["note"] = "HTTP 304 Not Modified — using cached version"
            result["crawl_duration_seconds"] = round(time.time() - start, 2)
            return result

        response.raise_for_status()

        # Update ETag cache
        etag = response.headers.get("ETag")
        last_mod = response.headers.get("Last-Modified")
        content_hash = hashlib.sha256(response.content).hexdigest()[:16]
        etag_cache.set(
            url, etag=etag, last_modified=last_mod, content_hash=content_hash
        )

        content_type = response.headers.get("content-type", "")
        raw_text = response.text

        if "application/json" in content_type:
            # Unexpected JSON from HTML tier — handle gracefully
            try:
                json_data = response.json()
                result["content_markdown"] = _json_to_markdown(json_data, url)
                result["title"] = json_data.get("title", site["agency"])
            except Exception:
                result["content_markdown"] = _html_to_markdown(raw_text, url)
                result["title"] = site["agency"]
        else:
            # HTML → MarkItDown (with BS4 pre-strip)
            result["content_markdown"] = _html_to_markdown(raw_text, url)

            # Extract title
            try:
                soup = BeautifulSoup(raw_text, "lxml")
                title_tag = soup.find("title")
                result["title"] = (
                    title_tag.string.strip()
                    if title_tag and title_tag.string
                    else site["agency"]
                )
            except Exception:
                result["title"] = site["agency"]

        if result["content_markdown"] and len(result["content_markdown"].strip()) > 50:
            result["crawl_status"] = "success"
        else:
            result["failure_reason"] = (
                "頁面內容為空或需要 JavaScript 渲染 — "
                "網站可能為 SPA 架構，純 HTTP 請求無法取得實際內容"
            )

    except Exception as e:
        result["failure_reason"] = _classify_failure(e, url)

    result["crawl_duration_seconds"] = round(time.time() - start, 2)
    return result


async def _crawl_tier3_jina(
    client: httpx.AsyncClient,
    site: dict,
    region: str,
    jina_semaphore: asyncio.Semaphore,
) -> dict:
    """Tier 3: Jina Reader API for anti-scraping / SPA / blocked sites."""
    result = _make_result_template(site, region)
    url = site["url"]
    start = time.time()

    try:
        async with jina_semaphore:
            jina_url = f"{_JINA_READER_BASE}{url}"
            response = await _fetch_with_retry(
                client,
                jina_url,
                headers={"Accept": "text/markdown"},
                timeout=httpx.Timeout(_JINA_TIMEOUT, connect=15.0),
            )

            # Rate limit delay
            await asyncio.sleep(_JINA_DELAY)

        if response.status_code == 200:
            content = response.text.strip()
            if content and len(content) > 50:
                result["content_markdown"] = content
                # Extract title from first heading
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("# "):
                        result["title"] = line[2:].strip()
                        break
                if not result["title"]:
                    result["title"] = site.get("name", site["agency"])
                result["crawl_status"] = "success"
                if len(content) > _MAX_CONTENT_SIZE:
                    result["content_markdown"] = (
                        content[:_MAX_CONTENT_SIZE] + "\n\n... (content truncated)"
                    )
            else:
                result["failure_reason"] = (
                    "Jina Reader 回傳內容為空 — 網站可能完全封鎖爬取"
                )
        else:
            result["failure_reason"] = (
                f"Jina Reader HTTP {response.status_code} — 無法透過 Jina 取得內容"
            )

    except Exception as e:
        result["failure_reason"] = _classify_failure(e, url)

    result["crawl_duration_seconds"] = round(time.time() - start, 2)
    return result


# ============================================================
# Core Async Crawler Class
# ============================================================


class AsyncRegulatoryUpdateCrawler:
    """High-performance async regulatory website crawler for medical device QMS.

    Features:
      - 4-tier crawling strategy (Sitemap → API → httpx+MiD → Jina)
      - Parallel crawling via asyncio.gather
      - HTTP/2 with shared connection pool
      - ETag conditional caching
      - Per-domain rate limiting
      - tenacity exponential-backoff retry
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._etag_cache = ETagCache()
        self._sitemap_scanner = SitemapScanner()
        self._domain_semaphores: dict[str, asyncio.Semaphore] = {}
        self._jina_semaphore = asyncio.Semaphore(2)

    async def _ensure_client(self) -> None:
        """Lazy-init shared AsyncClient with HTTP/2 and connection pool."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=_DEFAULT_HEADERS,
                timeout=httpx.Timeout(_REQUEST_TIMEOUT, connect=10.0),
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                ),
                follow_redirects=True,
                verify=True,
                http2=True,
            )

    def _get_domain_semaphore(self, url: str) -> asyncio.Semaphore:
        """Get or create a per-domain rate-limiting semaphore."""
        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = url
        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = asyncio.Semaphore(_DOMAIN_CONCURRENCY)
        return self._domain_semaphores[domain]

    async def _crawl_single_site(self, site: dict, region: str) -> dict:
        """Crawl a single site with tier dispatch and rate limiting."""
        tier = site.get("tier", 2)
        url = site.get("url", "")
        sem = self._get_domain_semaphore(url)

        async with sem:
            # Small delay to avoid hammering
            crawl_delay = min(site.get("crawl_delay", 3), 5)
            await asyncio.sleep(crawl_delay * 0.5)  # async delay (halved from sync)

            if tier == 1:
                return await _crawl_tier1_api(
                    self._client, site, region, self._etag_cache
                )
            elif tier == 3:
                return await _crawl_tier3_jina(
                    self._client, site, region, self._jina_semaphore
                )
            else:
                # Tier 2 (default) — also handles tier 0 sites that fall through
                return await _crawl_tier2_httpx(
                    self._client, site, region, self._etag_cache
                )

    async def crawl_all_regions(self) -> dict:
        """Crawl all configured regions in parallel.

        Returns structured result dict (same schema as v1.0).
        """
        return await self._crawl_regions(list(REGION_SITES.keys()))

    async def crawl_selected_regions(self, regions: list) -> dict:
        """Crawl only specified regions in parallel.

        Returns structured result dict (same schema as v1.0).
        """
        valid_regions = [r for r in regions if r in REGION_SITES]
        if not valid_regions:
            return {
                "results": [],
                "summary": {
                    "total_sites": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "regions_covered": [],
                    "crawl_duration_seconds": 0.0,
                },
            }
        return await self._crawl_regions(valid_regions)

    async def _crawl_regions(self, regions: list) -> dict:
        """Internal: crawl a list of regions in parallel."""
        await self._ensure_client()
        await self._etag_cache.load()

        start_time = time.time()

        # Build task list
        tasks = []
        for region in regions:
            sites = REGION_SITES.get(region, [])
            for site in sites:
                tasks.append(self._crawl_single_site(site, region))

        # Execute all in parallel
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results — convert exceptions to failed results
        all_results = []
        for i, r in enumerate(raw_results):
            if isinstance(r, Exception):
                # Find which site this corresponds to
                idx = 0
                site_info = {"agency": "Unknown", "url": "", "name": "Unknown"}
                site_region = "Unknown"
                for region in regions:
                    sites = REGION_SITES.get(region, [])
                    for site in sites:
                        if idx == i:
                            site_info = site
                            site_region = region
                        idx += 1

                failed_result = _make_result_template(site_info, site_region)
                failed_result["failure_reason"] = _classify_failure(
                    r, site_info.get("url", "")
                )
                failed_result["crawl_duration_seconds"] = 0.0
                all_results.append(failed_result)
            elif isinstance(r, dict):
                all_results.append(r)

        # Save ETag cache
        await self._etag_cache.save()

        # Build summary
        success_count = sum(
            1 for r in all_results if r.get("crawl_status") == "success"
        )
        failed_count = sum(1 for r in all_results if r.get("crawl_status") == "failed")

        return {
            "results": all_results,
            "summary": {
                "total_sites": len(all_results),
                "success_count": success_count,
                "failed_count": failed_count,
                "regions_covered": regions,
                "crawl_duration_seconds": round(time.time() - start_time, 2),
            },
        }

    def search_supplementary(self, query: str) -> list:
        """Run DuckDuckGo search for supplementary regulatory information."""
        return _ddgs_search(query)

    async def close(self) -> None:
        """Close the HTTP client and persist cache."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        await self._etag_cache.save()


# ============================================================
# Module-level convenience functions (backward-compatible API)
# ============================================================

_crawler_instance: Optional[AsyncRegulatoryUpdateCrawler] = None


def get_regulatory_crawler() -> AsyncRegulatoryUpdateCrawler:
    """Get or create singleton crawler instance."""
    global _crawler_instance
    if _crawler_instance is None:
        _crawler_instance = AsyncRegulatoryUpdateCrawler()
    return _crawler_instance


def get_available_regions() -> list:
    """Return list of all available region names."""
    return list(REGION_SITES.keys())


def get_region_display_info() -> list:
    """Return region info for UI display."""
    info = []
    for region, sites in REGION_SITES.items():
        agencies = [s["agency"] for s in sites]
        info.append(
            {
                "region": region,
                "agencies": agencies,
                "site_count": len(sites),
            }
        )
    return info
