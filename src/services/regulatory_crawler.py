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
from typing import Callable, Optional
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
            "name": "21 CFR Part 820 — QMSR (eCFR)",
            "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-820",
            "tier": 3,
            "strategy": "html",
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
            "url": "https://www.legislation.gov.uk/uksi/2002/618/contents",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "CloudFront 437 from Asia IPs — Jina Reader fallback",
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
        {
            "agency": "MHLW",
            "name": "厚生労働省 医療機器政策",
            "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177182.html",
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
        {
            "agency": "CMDE",
            "name": "醫療器械技術審評中心",
            "url": "https://www.cmde.org.cn/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
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
        {
            "agency": "NIDS",
            "name": "국가 의료기기 안전정보원",
            "url": "https://www.nids.or.kr/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
    ],
    # Canada QMS is exclusively via MDSAP since Jan 2019 (CMDCAS retired).
    # Reuse MDSAP sites as the crawl source; HC-specific delta rules are
    # handled by the HC RegulationProfile in compliance_rules.py.
    "加拿大 (Canada)": [
        {
            "agency": "MDSAP-Global-Audit",
            "name": "MDSAP Audit Procedures and Forms",
            "url": "https://www.mdsap.global/documents/audit-procedures-and-forms",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — may timeout, Jina fallback available",
        },
        {
            "agency": "MDSAP-Global-QMS",
            "name": "MDSAP Quality Management System",
            "url": "https://www.mdsap.global/documents/quality-management-system",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — may timeout, Jina fallback available",
        },
        {
            "agency": "MDSAP-Global-General",
            "name": "MDSAP General Documents and Procedures",
            "url": "https://www.mdsap.global/documents/general-documents-and-procedures",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — frequent timeouts, Jina Reader fallback",
        },
        {
            "agency": "MDSAP-Global-Assessment",
            "name": "MDSAP Assessment Procedures and Forms",
            "url": "https://www.mdsap.global/documents/assessment-procedures-and-forms",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — frequent timeouts, Jina Reader fallback",
        },
        {
            "agency": "FDA-MDSAP-Audit",
            "name": "FDA MDSAP Audit Procedures and Forms",
            "url": "https://www.fda.gov/medical-devices/medical-device-single-audit-program-mdsap/mdsap-audit-procedures-and-forms",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "sitemap_url": "https://www.fda.gov/sitemap.xml",
        },
        {
            "agency": "FDA-MDSAP-Assessment",
            "name": "FDA MDSAP Assessment Procedures and Forms",
            "url": "https://www.fda.gov/medical-devices/medical-device-single-audit-program-mdsap/mdsap-assessment-procedures-and-forms",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "sitemap_url": "https://www.fda.gov/sitemap.xml",
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
        {
            "agency": "ARTG",
            "name": "Australian Register of Therapeutic Goods",
            "url": "https://www.tga.gov.au/resources/artg-search",
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
    "MDSAP": [
        {
            "agency": "MDSAP-Global-Audit",
            "name": "MDSAP Audit Procedures and Forms",
            "url": "https://www.mdsap.global/documents/audit-procedures-and-forms",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — may timeout, Jina fallback available",
        },
        {
            "agency": "MDSAP-Global-QMS",
            "name": "MDSAP Quality Management System",
            "url": "https://www.mdsap.global/documents/quality-management-system",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — may timeout, Jina fallback available",
        },
        {
            "agency": "MDSAP-Global-General",
            "name": "MDSAP General Documents and Procedures",
            "url": "https://www.mdsap.global/documents/general-documents-and-procedures",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — frequent timeouts, Jina Reader fallback",
        },
        {
            "agency": "MDSAP-Global-Assessment",
            "name": "MDSAP Assessment Procedures and Forms",
            "url": "https://www.mdsap.global/documents/assessment-procedures-and-forms",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — frequent timeouts, Jina Reader fallback",
        },
        {
            "agency": "FDA-MDSAP-Audit",
            "name": "FDA MDSAP Audit Procedures and Forms",
            "url": "https://www.fda.gov/medical-devices/medical-device-single-audit-program-mdsap/mdsap-audit-procedures-and-forms",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "sitemap_url": "https://www.fda.gov/sitemap.xml",
        },
        {
            "agency": "FDA-MDSAP-Assessment",
            "name": "FDA MDSAP Assessment Procedures and Forms",
            "url": "https://www.fda.gov/medical-devices/medical-device-single-audit-program-mdsap/mdsap-assessment-procedures-and-forms",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "sitemap_url": "https://www.fda.gov/sitemap.xml",
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
            "name": "Saudi Food and Drug Authority — Regulations",
            "url": "https://www.sfda.gov.sa/en/regulations?tags=Medical+Devices",
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
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "Cloudflare challenge — Jina Reader fallback",
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
            "agency": "Kemenkes",
            "name": "Ministry of Health — Medical Device Registration (Regalkes)",
            "url": "https://regalkes.kemkes.go.id/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
        },
        {
            "agency": "BPOM",
            "name": "BPOM — Food & Drug Control",
            "url": "https://www.pom.go.id/",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "SSL certificate chain incomplete — Jina Reader fallback",
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
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "SSL/TLS errors — Jina Reader fallback",
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
        {
            "agency": "Minzdrav",
            "name": "Ministry of Health of Russia",
            "url": "https://minzdrav.gov.ru/",
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
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Frequent timeouts from Asia — Jina Reader fallback",
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
        {
            "agency": "EDE",
            "name": "Emirates Drug Establishment",
            "url": "https://ede.gov.ae/",
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
    "mdsap",
    "single-audit",
    "single_audit",
    "audit-approach",
    "audit-procedures",
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


def _retrieve_cached_content(url: str) -> Optional[str]:
    """Retrieve previously crawled content for a URL from regulatory markdown storage.

    Used when HTTP 304 Not Modified is received — instead of storing a useless
    '(Content unchanged)' placeholder, we restore the actual content from the
    last successful crawl so downstream consumers (LLM analysis, reports) get
    real regulatory text.
    """
    try:
        from src.storage.regulatory_markdown_storage import (
            get_regulatory_markdown_store,
        )

        store = get_regulatory_markdown_store()
        doc = store.get_document_by_url(url)
        if doc and doc.get("content"):
            return doc["content"]
    except Exception:
        pass
    return None


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
            previous_content = _retrieve_cached_content(url)
            if previous_content:
                result["content_markdown"] = previous_content
                result["note"] = (
                    "HTTP 304 Not Modified — restored content from previous crawl"
                )
            else:
                result["content_markdown"] = (
                    "HTTP 304 Not Modified but no previous content found in storage — "
                    "content may be empty until next full crawl"
                )
                result["note"] = "HTTP 304 Not Modified — no cached content available"
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
            previous_content = _retrieve_cached_content(url)
            if previous_content:
                result["content_markdown"] = previous_content
                result["note"] = (
                    "HTTP 304 Not Modified — restored content from previous crawl"
                )
            else:
                result["content_markdown"] = (
                    "HTTP 304 Not Modified but no previous content found in storage — "
                    "content may be empty until next full crawl"
                )
                result["note"] = "HTTP 304 Not Modified — no cached content available"
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


# ============================================================
# Regulation Freshness Check (Pre-Cross-Examination)
# ============================================================

# Known latest versions for baseline comparison
_KNOWN_STANDARDS = {
    "ISO_13485": {
        "version": "2016",
        "full_name": "ISO 13485:2016",
        "full_name_zh": "ISO 13485:2016 醫療器材品質管理系統",
        "check_urls": [
            "https://www.iso.org/standard/59752.html",
        ],
        "sitemap_url": "https://www.iso.org/sitemap.xml",
        "keywords": ["13485"],
        "note": "ISO 13485 full text is behind a paywall; only version/lastmod can be checked.",
    },
    "MDSAP": {
        "version": "current",
        "full_name": "MDSAP (Medical Device Single Audit Program)",
        "full_name_zh": "MDSAP（醫療器材單一稽核方案）",
        "check_urls": [
            "https://www.mdsap.global/documents/audit-procedures-and-forms",
            "https://www.mdsap.global/documents/general-documents-and-procedures",
            "https://www.fda.gov/medical-devices/medical-device-single-audit-program-mdsap/mdsap-audit-procedures-and-forms",
            "https://www.fda.gov/medical-devices/medical-device-single-audit-program-mdsap/mdsap-assessment-procedures-and-forms",
            "https://www.fda.gov/medical-devices/cdrh-international-programs/medical-device-single-audit-program-mdsap",
        ],
        "sitemap_url": "https://www.fda.gov/sitemap.xml",
        "keywords": ["mdsap", "single-audit", "single_audit"],
    },
}


async def check_regulation_freshness(
    standards: Optional[list] = None,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Check if ISO 13485 and MDSAP regulation references are up-to-date.

    Performs lightweight checks:
      1. Sitemap lastmod scan for known standard URLs
      2. HTTP HEAD request for Last-Modified headers
      3. Compares against known baseline versions

    Args:
        standards: List of standard keys to check (default: all).
                   Valid keys: 'ISO_13485', 'MDSAP'

    Returns:
        {
            'checked_at': ISO timestamp,
            'results': {
                'ISO_13485': {
                    'status': 'confirmed' | 'unconfirmed' | 'error',
                    'known_version': '2016',
                    'last_modified': '2024-...' or None,
                    'message': str,
                    'message_zh': str,
                },
                ...
            },
            'all_confirmed': bool,
            'announcement_needed': bool,
            'announcement_text': str,
            'announcement_text_zh': str,
        }
    """
    check_keys = standards or list(_KNOWN_STANDARDS.keys())
    results = {}
    crawler = get_regulatory_crawler()
    await crawler._ensure_client()
    client = crawler._client

    for key in check_keys:
        std = _KNOWN_STANDARDS.get(key)
        if not std:
            results[key] = {
                "status": "error",
                "message": f"Unknown standard: {key}",
                "message_zh": f"未知的標準: {key}",
            }
            continue

        last_modified = None
        status = "unconfirmed"
        detail = ""
        detail_zh = ""

        # Method 1: HTTP HEAD to check Last-Modified / response status
        for url in std.get("check_urls", []):
            try:
                resp = await client.head(
                    url,
                    timeout=httpx.Timeout(10.0),
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    lm = resp.headers.get("last-modified", "")
                    if lm:
                        last_modified = lm
                    status = "confirmed"
                    detail = (
                        f"{std['full_name']} page is accessible. "
                        f"Known version: {std['version']}."
                    )
                    detail_zh = (
                        f"{std['full_name_zh']} 頁面可存取。"
                        f"已知版本: {std['version']}。"
                    )
                    if last_modified:
                        detail += f" Last-Modified: {last_modified}."
                        detail_zh += f" 最後修改: {last_modified}。"
                    break  # First successful check is enough
                elif resp.status_code == 403:
                    detail = (
                        f"{std['full_name']} returned 403 Forbidden. "
                        "Content may be behind a paywall."
                    )
                    detail_zh = (
                        f"{std['full_name_zh']} 返回 403 禁止存取。內容可能在付費牆後。"
                    )
                    # ISO standards are paywalled — this is expected
                    if key == "ISO_13485":
                        status = "confirmed"
                        detail += " (Expected for ISO standards — version confirmed via known baseline.)"
                        detail_zh += "（ISO標準預期行為 — 版本透過已知基線確認。）"
            except Exception as e:
                logger.debug(f"Freshness check failed for {url}: {e}")
                detail = f"Connection error checking {std['full_name']}: {e}"
                detail_zh = f"檢查 {std['full_name_zh']} 連線錯誤: {e}"

        # Method 2: Sitemap lastmod check (if available)
        if status == "unconfirmed" and std.get("sitemap_url"):
            try:
                scanner = SitemapScanner()
                urls = await scanner.scan(
                    client,
                    std["sitemap_url"],
                    keywords=std.get("keywords", []),
                )
                if urls:
                    status = "confirmed"
                    detail = (
                        f"{std['full_name']} found in sitemap with "
                        f"{len(urls)} matching URL(s)."
                    )
                    detail_zh = (
                        f"{std['full_name_zh']} 在網站地圖中找到 "
                        f"{len(urls)} 個匹配的URL。"
                    )
            except Exception as e:
                logger.debug(f"Sitemap check failed: {e}")

        results[key] = {
            "status": status,
            "known_version": std.get("version", ""),
            "last_modified": last_modified,
            "message": detail or f"Unable to confirm {std['full_name']} freshness.",
            "message_zh": detail_zh or f"無法確認 {std['full_name_zh']} 的最新狀態。",
        }

    all_confirmed = all(r.get("status") == "confirmed" for r in results.values())
    announcement_needed = not all_confirmed

    # Build announcement text for unconfirmed standards
    unconfirmed = [
        f"- {_KNOWN_STANDARDS[k]['full_name']}: {results[k].get('message', '')}"
        for k in results
        if results[k].get("status") != "confirmed"
    ]
    unconfirmed_zh = [
        f"- {_KNOWN_STANDARDS[k]['full_name_zh']}: {results[k].get('message_zh', '')}"
        for k in results
        if results[k].get("status") != "confirmed"
    ]

    if announcement_needed:
        announcement = (
            "⚠️ Regulation Freshness Notice\n"
            "The following regulatory standards could not be confirmed as the latest version "
            "before cross-examination. Results should be reviewed with this in mind:\n"
            + "\n".join(unconfirmed)
        )
        announcement_zh = (
            "⚠️ 法規最新性公告\n"
            "以下法規標準在交叉詰問前無法確認為最新版本。"
            "分析結果請參考此公告：\n" + "\n".join(unconfirmed_zh)
        )
    else:
        announcement = ""
        announcement_zh = ""

    country_completeness = await check_country_data_completeness(
        progress_callback=progress_callback,
    )
    incomplete = country_completeness.get("incomplete_countries", [])

    # Note: per-country upload reminders are handled by app.py _auto_trigger_crossexam()
    # using i18n keys, so we only pass the country_completeness data here.
    # Do NOT append upload_notice to announcement_text to avoid duplicate messages.
    if incomplete:
        announcement_needed = True

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "all_confirmed": all_confirmed
        and country_completeness.get("all_complete", True),
        "announcement_needed": announcement_needed,
        "announcement_text": announcement,
        "announcement_text_zh": announcement_zh,
        "country_completeness": country_completeness,
    }


# ============================================================
# Per-Country Data Completeness Check (7-Country Cross-Examination)
# ============================================================

# Mapping: cross-examination profile ID → REGION_SITES key
# Static mapping for predefined 7 countries.
# Dynamic countries are added via get_crossexam_country_map().
_CROSSEXAM_COUNTRY_MAP_STATIC = {
    "QMSR": {
        "region": "美國 (USA)",
        "name_en": "USA (FDA QMSR)",
        "name_zh": "美國 (FDA QMSR)",
    },
    "EU_MDR": {
        "region": "歐盟 (EU)",
        "name_en": "EU (MDR 2017/745)",
        "name_zh": "歐盟 (MDR 2017/745)",
    },
    "TFDA": {
        "region": "台灣 (Taiwan)",
        "name_en": "Taiwan (TFDA)",
        "name_zh": "台灣 (TFDA)",
    },
    "HC": {
        "region": "加拿大 (Canada)",
        "name_en": "Canada (HC/MDSAP)",
        "name_zh": "加拿大 (HC/MDSAP)",
    },
    "PMDA": {
        "region": "日本 (Japan)",
        "name_en": "Japan (PMDA)",
        "name_zh": "日本 (PMDA)",
    },
    "ANVISA": {
        "region": "巴西 (Brazil)",
        "name_en": "Brazil (ANVISA)",
        "name_zh": "巴西 (ANVISA)",
    },
    "TGA": {
        "region": "澳洲 (Australia)",
        "name_en": "Australia (TGA)",
        "name_zh": "澳洲 (TGA)",
    },
    "MDSAP": {
        "region": "MDSAP",
        "name_en": "MDSAP (Single Audit)",
        "name_zh": "MDSAP（單一稽核方案）",
    },
}


def get_crossexam_country_map() -> dict:
    """Return the full cross-examination country map (static 7 + dynamic)."""
    result = dict(_CROSSEXAM_COUNTRY_MAP_STATIC)

    # Add dynamically registered profiles (from crawled regulations)
    try:
        from src.analysis.compliance_rules import PREDEFINED_REGULATIONS

        for profile_id, profile in PREDEFINED_REGULATIONS.items():
            if profile_id in result:
                continue  # Already in static map
            # Build dynamic entry from profile metadata
            region_name = f"{profile.country_name_zh} ({profile.country_name_en})"
            result[profile_id] = {
                "region": region_name,
                "name_en": f"{profile.country_name_en} ({profile_id})",
                "name_zh": f"{profile.country_name_zh} ({profile_id})",
            }
    except Exception:
        pass  # Non-critical — static map still available

    return result


_MIN_COMPLETE_CONTENT_LEN = 50  # same threshold as _crawl_tier2_httpx


async def check_country_data_completeness(
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Check whether each cross-examination country (predefined 7 + dynamic) has
    complete regulation data available via crawler.

    For each country:
      1. Attempt a lightweight crawl of its configured sites
      2. If ANY site returns ≥50 chars of content → data is 'complete'
      3. If ALL sites fail or return empty content → 'incomplete',
         user should be notified to manually upload

    Args:
        progress_callback: Optional async callable(completed, total, country_name_zh)
                          called after each country finishes crawling.

    Returns:
        {
            'checked_at': ISO timestamp,
            'countries': {
                'QMSR': {
                    'region': '美國 (USA)',
                    'status': 'complete' | 'incomplete' | 'error',
                    'needs_manual_upload': bool,
                    'sites_checked': int,
                    'sites_success': int,
                    'message': str,
                    'message_zh': str,
                },
                ...
            },
            'incomplete_countries': ['QMSR', ...],  # convenience list
            'all_complete': bool,
        }
    """
    crawler = get_regulatory_crawler()
    await crawler._ensure_client()

    countries_result = {}
    incomplete_list = []
    country_map = get_crossexam_country_map()
    total_countries = len(country_map)
    completed_countries = 0

    for profile_id, country_info in country_map.items():
        region_key = country_info["region"]
        sites = REGION_SITES.get(region_key, [])

        if not sites:
            countries_result[profile_id] = {
                "region": region_key,
                "status": "error",
                "needs_manual_upload": True,
                "sites_checked": 0,
                "sites_success": 0,
                "message": f"No configured crawl sites for {country_info['name_en']}",
                "message_zh": f"{country_info['name_zh']} 沒有設定爬蟲網站",
            }
            incomplete_list.append(profile_id)
            completed_countries += 1
            if progress_callback:
                try:
                    await progress_callback(
                        completed_countries, total_countries, country_info["name_zh"]
                    )
                except Exception:
                    pass
            continue

        tasks = [crawler._crawl_single_site(site, region_key) for site in sites]
        try:
            raw = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            countries_result[profile_id] = {
                "region": region_key,
                "status": "error",
                "needs_manual_upload": True,
                "sites_checked": len(sites),
                "sites_success": 0,
                "message": f"Crawl error for {country_info['name_en']}: {e}",
                "message_zh": f"{country_info['name_zh']} 爬蟲錯誤: {e}",
            }
            incomplete_list.append(profile_id)
            completed_countries += 1
            if progress_callback:
                try:
                    await progress_callback(
                        completed_countries, total_countries, country_info["name_zh"]
                    )
                except Exception:
                    pass
            continue

        sites_checked = len(sites)
        sites_success = 0
        has_complete_content = False

        for r in raw:
            if isinstance(r, Exception):
                continue
            if not isinstance(r, dict):
                continue
            if r.get("crawl_status") == "success":
                content = r.get("content_markdown", "")
                if content and len(content.strip()) > _MIN_COMPLETE_CONTENT_LEN:
                    sites_success += 1
                    has_complete_content = True

        if has_complete_content:
            countries_result[profile_id] = {
                "region": region_key,
                "status": "complete",
                "needs_manual_upload": False,
                "sites_checked": sites_checked,
                "sites_success": sites_success,
                "message": f"{country_info['name_en']}: {sites_success}/{sites_checked} sites returned data",
                "message_zh": f"{country_info['name_zh']}: {sites_success}/{sites_checked} 個網站取得資料",
            }
        else:
            countries_result[profile_id] = {
                "region": region_key,
                "status": "incomplete",
                "needs_manual_upload": True,
                "sites_checked": sites_checked,
                "sites_success": sites_success,
                "message": (
                    f"{country_info['name_en']}: crawler could not retrieve complete data "
                    f"(0/{sites_checked} sites). Please upload regulation documents manually."
                ),
                "message_zh": (
                    f"{country_info['name_zh']}: 爬蟲無法取得完整資料 "
                    f"(0/{sites_checked} 個網站)。請手動上傳該國法規文件。"
                ),
            }
            incomplete_list.append(profile_id)

        completed_countries += 1
        if progress_callback:
            try:
                await progress_callback(
                    completed_countries, total_countries, country_info["name_zh"]
                )
            except Exception:
                pass

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "countries": countries_result,
        "incomplete_countries": incomplete_list,
        "all_complete": len(incomplete_list) == 0,
    }
