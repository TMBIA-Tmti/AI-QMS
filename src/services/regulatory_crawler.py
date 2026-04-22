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
import ipaddress as _ipaddress
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

_urlparse = urlparse
import xml.etree.ElementTree as _stdlib_ET
import defusedxml.ElementTree as ET

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


def _is_safe_url(url: str) -> bool:
    """Return False if URL targets private/internal/loopback networks."""
    try:
        parsed = _urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        if hostname.endswith(".internal") or hostname.endswith(".local"):
            return False
        try:
            ip = _ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass  # hostname, not IP — OK
        return True
    except Exception:
        return False


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
            "agency": "TFDA-QMS",
            "name": "醫療器材品質管理系統準則 — 全國法規資料庫 (Taiwan QMS Criteria, 79 articles, ISO 13485 equivalent)",
            "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0030116",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: 醫療器材品質管理系統準則 (TFDA Order, 2021-04-14, effective 2021-05-01) — 79 articles mirroring ISO 13485:2016 — Jina Reader for dynamic content",
        },
        {
            "agency": "TFDA-QMS-EN",
            "name": "Medical Device Quality Management System Guidelines (English) — Taiwan Laws Database",
            "url": "https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=L0030116",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "English version of the QMS Criteria (same pcode L0030116) — ISO 13485:2016 equivalent under Medical Devices Act 2021",
        },
        {
            "agency": "TFDA-QMS-Inspection",
            "name": "醫療器材品質管理系統查核及製造許可證核發辦法 (QMS Inspection & Manufacturing License Issuance Regulations)",
            "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0030112",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "QMS inspection and licence rules under Medical Devices Act — pcode L0030112",
        },
    ],
    "美國 (USA)": [
        {
            "agency": "FDA-QMSR",
            "name": "FDA Quality Management System Regulation (QMSR) — Official Overview",
            "url": "https://www.fda.gov/medical-devices/postmarket-requirements-devices/quality-management-system-regulation-qmsr",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "sitemap_url": "https://www.fda.gov/sitemap.xml",
            "note": "PRIMARY QMS regulation page: 21 CFR Part 820 QMSR, effective 2026-02-02, incorporates ISO 13485:2016 by reference",
        },
        {
            "agency": "eCFR-820",
            "name": "21 CFR Part 820 — Quality Management System Regulation (eCFR full text)",
            "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-820",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "Full regulatory text of 21 CFR Part 820 QMSR on eCFR — current good manufacturing practice (CGMP) for medical devices",
        },
        {
            "agency": "Federal-Register-QMSR",
            "name": "Federal Register — FDA QMSR Final Rule (2024)",
            "url": "https://www.federalregister.gov/api/v1/documents?conditions[agencies][]=food-and-drug-administration&conditions[type][]=RULE&per_page=20&order=newest",
            "tier": 1,
            "strategy": "api_json",
            "crawl_delay": 3,
            "note": "Federal Register API for most-recent FDA rules — monitors QMSR/Part 820 amendments",
        },
    ],
    "歐盟 (EU)": [
        {
            "agency": "EUR-Lex-MDR",
            "name": "Regulation (EU) 2017/745 — EU MDR (full text incl. Annex IX QMS requirements)",
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32017R0745",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "PRIMARY QMS regulation: EU MDR 2017/745 — Annex IX Section 2 specifies QMS requirements for Notified Body audit — EUR-Lex HTML via Jina",
        },
        {
            "agency": "EUR-Lex-MDR-Consolidated",
            "name": "EU MDR 2017/745 — Consolidated version (EUR-Lex PDF)",
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02017R0745-20230320",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Consolidated EU MDR text as of 2023-03-20 — includes all corrigenda amendments",
        },
        {
            "agency": "MDCG",
            "name": "MDCG Guidance Documents (QMS, Annex IX, notified body guidance)",
            "url": "https://health.ec.europa.eu/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents-and-other-guidance_en",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "sitemap_url": "https://health.ec.europa.eu/sitemap.xml",
            "note": "MDCG guidance supporting EU MDR Annex IX/XI QMS conformity assessment",
        },
    ],
    "英國 (UK)": [
        {
            "agency": "UK-MDR-2002",
            "name": "The Medical Devices Regulations 2002 (SI 2002/618) — UK legislation.gov.uk",
            "url": "https://www.legislation.gov.uk/uksi/2002/618/contents/made",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: UK MDR 2002 (SI 618) — Parts II/III/IV specify conformity assessment & QMS requirements; basis for UKCA marking",
        },
        {
            "agency": "MHRA-Guidance",
            "name": "MHRA — Regulating Medical Devices in the UK (GOV.UK Content API)",
            "url": "https://www.gov.uk/api/content/guidance/regulating-medical-devices-in-the-uk",
            "tier": 1,
            "strategy": "api_json",
            "crawl_delay": 3,
            "note": "MHRA official guidance on UK MDR 2002 compliance including QMS requirements for UKCA",
        },
    ],
    "日本 (Japan)": [
        {
            "agency": "eGov-QMS-169",
            "name": "医療機器及び体外診断用医薬品の製造管理及び品質管理の基準に関する省令 (MHLW Ordinance No. 169 — QMS省令 full text)",
            "url": "https://laws.e-gov.go.jp/law/416M60000100169",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: MHLW Ministerial Ordinance No. 169 (2004, revised 2021) — Japanese QMS Ordinance (QMS省令) mirroring ISO 13485:2016 — official e-Gov law database",
        },
        {
            "agency": "PMDA-QMS",
            "name": "PMDA — QMS Compliance Inspection (QMS適合性調査)",
            "url": "https://www.pmda.go.jp/review-services/gmp-qms-gctp/qms/0003.html",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PMDA QMS compliance inspection page — covers QMS省令 requirements and inspection procedures",
        },
        {
            "agency": "PMDA-QMS-EN",
            "name": "PMDA — Revision of Japanese Medical Device QMS Requirements (English)",
            "url": "https://www.pmda.go.jp/english/review-services/regulatory-info/0004.html",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "English-language PMDA page on 2021 QMS Ordinance 169 revision — comparison with ISO 13485:2016 and Chapter translations",
        },
    ],
    "中國 (China)": [
        {
            "agency": "NMPA-GMP-CN",
            "name": "医疗器械生产质量管理规范 — NMPA 公告 2025年第107号 (Chinese, effective 2026-11-01)",
            "url": "https://www.nmpa.gov.cn/xxgk/fgwj/xzhgfxwj/20251104173724174.html",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "PRIMARY (Chinese): NMPA official announcement page for revised GMP (15章132条); actual regulation text is in the Word attachment on this page — anti-bot 412 protection, Jina Reader first",
        },
        {
            "agency": "NMPA-GMP-Announcement",
            "name": "NMPA — GMP Announcement [2025] No. 107 (English, effective 2026-11-01)",
            "url": "https://english.nmpa.gov.cn/2025-12/24/c_1156627.htm",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Official NMPA English announcement releasing the revised Good Manufacturing Practice for Medical Devices (15 chapters, 132 articles) — Jina Reader first",
        },
        {
            "agency": "NMPA-Regulations",
            "name": "NMPA — Regulatory Information (medical devices section)",
            "url": "https://english.nmpa.gov.cn/medicaldevices.html",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "NMPA English portal medical device regulatory page — Jina Reader first",
        },
    ],
    "韓國 (Korea)": [
        {
            "agency": "MFDS-KGMP",
            "name": "MFDS — Medical Device GMP Regulations (K-GMP, English compilation)",
            "url": "https://www.mfds.go.kr/eng/brd/m_40/view.do?seq=72638",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: MFDS K-GMP (의료기기 제조 및 품질관리 기준) — Korean GMP based on ISO 13485:2016, updated 2024/2025 — Jina first",
        },
        {
            "agency": "MFDS-MD-Regulations",
            "name": "MFDS — Medical Device Regulations Listing",
            "url": "https://www.mfds.go.kr/eng/brd/m_40/list.do",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "MFDS English regulations listing — includes GMP/QMS ordinances — Jina first",
        },
    ],
    # Canada QMS is exclusively via MDSAP since Jan 2019 (CMDCAS retired).
    # Primary QMS regulation is CMDR SOR/98-282 Section 32 (requires ISO 13485 certificate).
    # MDSAP sites also included as the operational audit framework.
    "加拿大 (Canada)": [
        {
            "agency": "CMDR-SOR98-282",
            "name": "Medical Devices Regulations SOR/98-282 — Section 32 (ISO 13485 QMS requirement)",
            "url": "https://laws-lois.justice.gc.ca/eng/regulations/SOR-98-282/section-32.html",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: CMDR SOR/98-282 s.32 requires ISO 13485 QMS certificate for Class II–IV device licences — Health Canada Justice Laws",
        },
        {
            "agency": "CMDR-Full",
            "name": "Medical Devices Regulations SOR/98-282 — Full Text",
            "url": "https://laws-lois.justice.gc.ca/eng/regulations/SOR-98-282/FullText.html",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "Full text of CMDR SOR/98-282 — governs QMS, labelling, licensing, post-market for medical devices in Canada",
        },
        {
            "agency": "MDSAP-Global-Audit",
            "name": "MDSAP Audit Procedures and Forms",
            "url": "https://www.mdsap.global/documents/audit-procedures-and-forms",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — Jina Reader first",
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
            "agency": "TGA-Legislation",
            "name": "Therapeutic Goods (Medical Devices) Regulations 2002 — Federal Register of Legislation (current)",
            "url": "https://www.legislation.gov.au/F2002B00237/latest/text",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: TG(MD)R 2002 Schedule 3 requires ISO 13485 QMS for conformity assessment — current consolidated text on legislation.gov.au",
        },
        {
            "agency": "TGA-ARGMD",
            "name": "TGA — Australian Regulatory Guidelines for Medical Devices (ARGMD)",
            "url": "https://www.tga.gov.au/products/medical-devices/overview/australian-regulatory-guidelines-medical-devices-argmd",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "TGA ARGMD — explains Schedule 3 conformity assessment procedures including QMS requirements — Jina Reader fallback",
        },
        {
            "agency": "TGA-MD-Reg",
            "name": "TGA — How We Regulate Medical Devices",
            "url": "https://www.tga.gov.au/how-we-regulate/medical-devices",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Jina Reader first",
        },
    ],
    "瑞士 (Switzerland)": [
        {
            "agency": "MedDO-SR812213",
            "name": "Verordnung über Medizinprodukte (MedDO, SR 812.213) — Medical Devices Ordinance (admin.ch)",
            "url": "https://www.fedlex.admin.ch/eli/cc/2020/552/en",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: Swiss MedDO SR 812.213 (1 July 2020, in force 2021-05-26) aligned with EU MDR 2017/745 — includes Annex IX QMS conformity assessment requirements — fedlex requires JS — Jina Reader first",
        },
        {
            "agency": "Swissmedic-MedDO",
            "name": "Swissmedic — Legal Framework (MedDO / EU MDR alignment)",
            "url": "https://www.swissmedic.ch/swissmedic/en/home/medical-devices/regulation-of-medical-devices/neue-eu-verordnungen-mdr-ivdr.html",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "Swissmedic explanation of MedDO QMS requirements — aligned with EU MDR Annex IX",
        },
    ],
    "巴西 (Brazil)": [
        {
            "agency": "ANVISA-RDC665",
            "name": "RDC nº 665/2022 — ANVISA Good Manufacturing Practices for Medical Devices (BPF/GMP) — English version (PDF)",
            "url": "https://www.gov.br/anvisa/en/regulation-of-companies/arquivos/rdc-665-2022-english-version.pdf",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "PRIMARY QMS regulation: ANVISA RDC 665/2022 (effective 2022-05-02) — Brazilian Good Manufacturing Practices (BGMP) for medical devices and IVDs, replaces RDC 16/2013 — direct ANVISA PDF (confirmed 309KB)",
        },
        {
            "agency": "ANVISA-RDC665-News",
            "name": "ANVISA — RDC 665 de 2022 (Portuguese official news page)",
            "url": "https://www.gov.br/anvisa/pt-br/assuntos/noticias-anvisa/2022/rdc-665-de-2022",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "ANVISA official RDC 665/2022 announcement page in Portuguese — Inconsistent availability — Jina Reader fallback",
        },
    ],
    "MDSAP": [
        {
            "agency": "MDSAP-Global-Audit",
            "name": "MDSAP Audit Procedures and Forms",
            "url": "https://www.mdsap.global/documents/audit-procedures-and-forms",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — Jina Reader first",
        },
        {
            "agency": "MDSAP-Global-QMS",
            "name": "MDSAP Quality Management System",
            "url": "https://www.mdsap.global/documents/quality-management-system",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Akamai protection — Jina Reader first",
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
            "agency": "CDSCO-MDR2017",
            "name": "India Medical Devices Rules 2017 (MDR 2017) — CDSCO official PDF",
            "url": "https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/m_device/Medical%20Devices%20Rules,%202017.pdf",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: India MDR 2017 — Schedule V specifies QMS requirements for medical device manufacturers; ISO 13485 is the referenced standard — CDSCO PDF via Jina",
        },
        {
            "agency": "CDSCO-MD",
            "name": "CDSCO — Medical Devices & Diagnostics portal",
            "url": "https://cdsco.gov.in/opencms/opencms/en/Medical-Device-Diagnostics/Medical-Device-Diagnostics/",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "CDSCO medical device portal — SSL/bot protection — Jina Reader first",
        },
    ],
    "新加坡 (Singapore)": [
        {
            "agency": "SSO-HPR-2010",
            "name": "Health Products (Medical Devices) Regulations 2010 (S 436/2010) — Singapore Statutes Online",
            "url": "https://sso.agc.gov.sg/SL/HPA2007-S436-2010",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: HP(MD)R 2010 — requires ISO 13485 or equivalent QMS for Class B/C/D medical device dealers — Singapore Statutes Online",
        },
        {
            "agency": "HSA-QMS",
            "name": "HSA — Quality Management System (QMS) for Medical Devices",
            "url": "https://www.hsa.gov.sg/medical-devices/dealers-licence/quality-management-system-(qms)-for-medical-devices",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "HSA official QMS requirements page — ISO 13485 / MDSAP mandatory from 1 Jan 2025 for manufacturer licence",
        },
    ],
    "沙烏地阿拉伯 (Saudi Arabia)": [
        {
            "agency": "SFDA-MDS-REQ10",
            "name": "SFDA — Requirements for Inspections and Quality Management System for Medical Devices (MDS-REQ10)",
            "url": "https://www.sfda.gov.sa/en/regulations/87120",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: SFDA MDS-REQ10 — specifies QMS inspection requirements and ISO 13485 alignment for medical device establishments in KSA",
        },
        {
            "agency": "SFDA-ISO13485-Guidance",
            "name": "SFDA — Guidance for ISO 13485 Requirements with SFDA-MDS Regulations (MDS-G-024)",
            "url": "https://www.sfda.gov.sa/sites/default/files/2025-03/MDS-G024.pdf",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "SFDA guidance document mapping ISO 13485:2016 requirements to Saudi MDS regulations (March 2025)",
        },
    ],
    "泰國 (Thailand)": [
        {
            "agency": "Thai-FDA-GMP",
            "name": "Thai FDA — ระบบคุณภาพการผลิตเครื่องมือแพทย์ GMP Medical Device Quality System (B.E. 2566/2023)",
            "url": "https://medical.fda.moph.go.th/situation/category/gmp-gdp/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation source: Thai FDA medical device GMP quality system page — Ministry of Public Health Notification on GMP B.E. 2566 (2023) — medical.fda.moph.go.th subdomain",
        },
        {
            "agency": "Thai-FDA-Laws",
            "name": "Thai FDA — กองควบคุมเครื่องมือแพทย์ Medical Device Laws (relevant-laws)",
            "url": "https://medical.fda.moph.go.th/relevant-laws-and-standards/mdlaw0501",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "Thai FDA Medical Device Division laws and standards page — includes all relevant medical device notifications and GMP requirements",
        },
    ],
    "紐西蘭 (New Zealand)": [
        {
            "agency": "Medsafe-MD-Legislation",
            "name": "Medsafe — Medical Device Legislation",
            "url": "https://www.medsafe.govt.nz/regulatory/devicesnew/2Legislation.asp",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation source: Medsafe medical device legislation page — covers Medicines Act 1981, Medicines (Database of Medical Devices) Regulations 2003, GMP Code",
        },
        {
            "agency": "Medsafe-GMP",
            "name": "Medsafe — NZ Code of GMP (Introduction)",
            "url": "https://www.medsafe.govt.nz/regulatory/guideline/nzgmpcodepart1intro.asp",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "NZ GMP Code Part 1 — applicable to therapeutic goods including medical devices — ISO 13485 referenced standard",
        },
    ],
    "墨西哥 (Mexico)": [
        {
            "agency": "DOF-NOM241-2025",
            "name": "NOM-241-SSA1-2025 — Buenas Prácticas de Fabricación para Dispositivos Médicos (DOF, 11 Nov 2025)",
            "url": "https://dof.gob.mx/nota_detalle.php?codigo=5772517&fecha=11/11/2025",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: NOM-241-SSA1-2025 (supersedes 2021 version) — Mexico official GMP standard for medical devices, ISO 13485 equivalent — published DOF 11/11/2025 — MDSAP recognized as equivalent QMS",
        },
        {
            "agency": "NOM241-EN-PDF",
            "name": "NOM-241-SSA1-2021 (English translation — InterAmerican Coalition MedTech, superseded by 2025 version)",
            "url": "https://www.interamericancoalition-medtech.org/regulatory-convergence/wp-content/uploads/sites/4/2022/03/Norma-Oficial-Mexicana-NOM-241-SSA1-2021-ENG-REV.pdf",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "English version of NOM-241-SSA1-2021 (2021 version, now superseded by 2025 revision) — retained for reference on prior requirements",
        },
    ],
    "阿根廷 (Argentina)": [
        {
            "agency": "ANMAT-MD",
            "name": "ANMAT — Productos Médicos (Medical Products portal, argentina.gob.ar)",
            "url": "https://www.argentina.gob.ar/anmat/regulados/productos-medicos",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation source: ANMAT medical products portal — Disposición 64/25 (Jan 2025) replaced Disposición 2318/2002 for MERCOSUR device registration; BPF (GMP/QMS) certification required for Class II–IV manufacturers",
        },
        {
            "agency": "ANMAT-Disposicion64-25",
            "name": "ANMAT — Disposición 64/2025 — Registro de Productos Médicos (MERCOSUR GMC 25/21)",
            "url": "https://www.argentina.gob.ar/normativa/nacional/disposici%C3%B3n-64-2025-408309/texto",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "Disposición ANMAT 64/25 (in force Jan 2025) — incorporates MERCOSUR Resolution GMC 25/21, replacing prior registration framework; Class III–IV require BPF certificate — official Argentina.gob.ar full text",
        },
    ],
    "南非 (South Africa)": [
        {
            "agency": "SAHPRA-ISO13485",
            "name": "SAHPRA — ISO 13485 Certificate as Prerequisite for Medical Device Establishment Licence",
            "url": "https://www.sahpra.org.za/wp-content/uploads/2025/04/ISO-13485-Certificate-Communication_Signed19.pdf",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation notice: SAHPRA communication (April 2025) requiring ISO 13485:2016 under Medicines Act 101/1965 s.22C — Regulations 5 & 6 for medical device establishment licence from 1 June 2025",
        },
        {
            "agency": "SAHPRA-MD",
            "name": "SAHPRA — Medical Devices",
            "url": "https://www.sahpra.org.za/medical-devices/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "SAHPRA medical device section — licensing, registration, and QMS requirements",
        },
    ],
    "土耳其 (Turkey)": [
        {
            "agency": "TITCK-MD-Legislation",
            "name": "TITCK — Tıbbi Cihaz Mevzuatı (Medical Device Legislation, aligned with EU MDR 2017/745)",
            "url": "https://www.titck.gov.tr/faaliyetalanlari/tibbicihaz/tibbi-cihaz-mevzuati",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation source: TITCK medical device legislation page — Turkey implemented EU MDR 2017/745 aligned regulations in June 2021 including QMS/Annex IX requirements — SSL/CDN protection — Jina Reader first",
        },
        {
            "agency": "TITCK-New-Regs",
            "name": "TITCK — New Medical Device Regulations (2021, EU MDR alignment announcement)",
            "url": "https://titck.gov.tr/duyuru/new-medical-device-regulations-entered-into-force-14062021145923",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "TITCK announcement of June 2021 medical device regulations — EU MDR 2017/745 equivalent — Jina first",
        },
    ],
    "印尼 (Indonesia)": [
        {
            "agency": "Kemkes-CPAKB",
            "name": "Permenkes No. 20 Tahun 2017 — Cara Pembuatan Alat Kesehatan yang Baik (CPAKB) — Farmalkes Kemkes",
            "url": "https://farmalkes.kemkes.go.id/en/unduh/permenkes-20-2017/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: Permenkes No. 20/2017 on Good Manufacturing Practices for Medical Devices (CPAKB) — issued 8 March 2017, effective 18 April 2017 — official Directorate General of Pharmaceutical and Medical Devices (Farmalkes) page",
        },
        {
            "agency": "BPK-Permenkes20",
            "name": "Permenkes No. 20 Tahun 2017 — CPAKB Full Text (BPK Official Indonesian Law Database)",
            "url": "https://peraturan.bpk.go.id/Details/111997/permenkes-no-20-tahun-2017",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "Full text of CPAKB regulation on the official BPK (State Finance Audit Board) law portal — PDF available for download",
        },
    ],
    "馬來西亞 (Malaysia)": [
        {
            "agency": "MDA-Legislation",
            "name": "Medical Device Authority — Legislation Documents (Act 737 & Regulations 2012)",
            "url": "https://www.mda.gov.my/index.php/doc-list/legislation",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation source: Malaysia Medical Device Act 737 (2012) and Medical Device Regulations 2012 — requires ISO 13485/MDSAP/FDA QSR or MHLW 169 QMS certification",
        },
        {
            "agency": "MDA",
            "name": "Medical Device Authority Malaysia — Homepage",
            "url": "https://www.mda.gov.my/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "MDA portal — fallback if legislation page unavailable",
        },
    ],
    "以色列 (Israel)": [
        {
            "agency": "MOH-MD-Division",
            "name": "Israel MOH — Medical Device Division (AMAR)",
            "url": "https://www.health.gov.il/English/MinistryUnits/HealthDivision/MedicalTechnologies/MLD/Pages/default.aspx",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation source: Israel MOH Medical Device Division — requires ISO 13485 compliance statement for registration; Medical Equipment Law 2012 and Medical Devices Regulations 2013 — SSL/CDN issues — Jina Reader first",
        },
    ],
    "菲律賓 (Philippines)": [
        {
            "agency": "FDA-PH-RA9711",
            "name": "Republic Act No. 9711 — FDA Act of 2009 (Philippines QMS legal basis)",
            "url": "https://www.fda.gov.ph/wp-content/uploads/2021/04/Republic-Act-No.-9711.pdf",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: RA 9711 (FDA Act 2009) mandates FDA Philippines to regulate medical devices; ISO 13485 QMS compliance required for CDRRHR registration — official FDA PH PDF",
        },
        {
            "agency": "FDA-PH-MD",
            "name": "Philippines FDA — Medical Devices Homepage (CDRRHR)",
            "url": "https://www.fda.gov.ph/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "Philippines FDA portal — fallback for regulation updates and guidance",
        },
    ],
    "越南 (Vietnam)": [
        {
            "agency": "DMEC-MOH",
            "name": "Vietnam MOH — DMEC Văn bản pháp quy (Legal Documents / Decree 98/2021/ND-CP)",
            "url": "https://dmec.moh.gov.vn/van-ban-phap-quy",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation source: DMEC legal documents listing — Vietnam Decree 98/2021/ND-CP (amended by Decree 96/2023) requires ISO 13485 for medical device registration — Jina Reader first",
        },
        {
            "agency": "DAV",
            "name": "Drug Administration of Vietnam — English",
            "url": "https://dav.gov.vn/en",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "DAV English portal — fallback for regulation updates",
        },
    ],
    "哥倫比亞 (Colombia)": [
        {
            "agency": "INVIMA-Decreto4725",
            "name": "Decreto 4725 de 2005 — Régimen de registros sanitarios de dispositivos médicos (INVIMA Normograma)",
            "url": "https://normograma.invima.gov.co/normograma/compilacion/docs/decreto_4725_2005.htm",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: Decreto 4725/2005 governs medical device registration and GMP (BPM) in Colombia; Article 8 requires BPM compliance; ISO 13485 certificate accepted as QMS evidence — official INVIMA Normograma text",
        },
        {
            "agency": "INVIMA-MD",
            "name": "INVIMA — Dispositivos Médicos y Equipos Biomédicos (Medical Devices portal)",
            "url": "https://www.invima.gov.co/productos-vigilados/dispositivos-medicos/dispositivos-medicos-equipos-biomedicos",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "INVIMA medical device portal — fallback for regulatory updates — SSL/TLS issues — Jina Reader fallback",
        },
    ],
    "俄羅斯 (Russia)": [
        {
            "agency": "RZN-MD",
            "name": "Roszdravnadzor — Medical Devices (Медицинские изделия)",
            "url": "https://roszdravnadzor.gov.ru/medproducts",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "PRIMARY QMS regulation source: Roszdravnadzor — Government Decree No. 1684 (effective 2025-03-01, replaces No. 1416) — mandatory ISO 13485 inspection for Class IIa-sterile/IIb/III from Jan 2024 — Geo-blocking possible — Jina Reader fallback",
        },
        {
            "agency": "Minzdrav-MD",
            "name": "Ministry of Health Russia — Medical Products Policy",
            "url": "https://minzdrav.gov.ru/",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "Minzdrav homepage — covers national medical device policy including GMP framework — Geo-blocking possible — Jina Reader fallback",
        },
    ],
    "埃及 (Egypt)": [
        {
            "agency": "EDA-MD-Guide",
            "name": "EDA — Regulatory Guideline for Registering Medical Devices (ISO 13485 requirement)",
            "url": "https://edaegypt.gov.eg/media/j3hdl0l2/5_regulatory-guideline-for-procedures-of-registering-imported-and-local-medical-devices-holding-international-quali.pdf",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation guideline: EDA Egypt regulatory procedures for medical devices holding international quality certificates (ISO 13485) — official EDA PDF (515KB confirmed)",
        },
        {
            "agency": "EDA",
            "name": "Egyptian Drug Authority — Homepage",
            "url": "https://www.edaegypt.gov.eg/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "EDA portal — fallback for regulation announcements",
        },
    ],
    "智利 (Chile)": [
        {
            "agency": "ISP-Regulations",
            "name": "ISP Chile — Regulaciones (ANAMED — Dispositivos Médicos)",
            "url": "https://www.ispch.gob.cl/anamed/regulaciones/",
            "tier": 3,
            "strategy": "html",
            "crawl_delay": 5,
            "note": "PRIMARY QMS regulation source: ISP Chile ANAMED regulations page — medical device registration requires GMP/ISO 9001 compliance; ISP Resolution N°8209/1999 GMP Guide — Frequent timeouts from Asia — Jina Reader fallback",
        },
    ],
    "阿聯酋 (UAE)": [
        {
            "agency": "MOHAP-FDL38-2024",
            "name": "UAE — Federal Decree-Law No. 38 of 2024 on Medical Products (MOHAP)",
            "url": "https://mohap.gov.ae/en/w/federal-decree-law-no.-38-of-the-year-2024-concerning-medical-products-the-pharmacy-profession-and-pharmaceutical-establishments",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "PRIMARY QMS regulation: Federal Decree-Law No. 38 of 2024 (in force Jan 2025) governs medical products in UAE; ISO 13485:2016 certificate required for manufacturer registration — official MOHAP page",
        },
        {
            "agency": "MOHAP",
            "name": "UAE Ministry of Health and Prevention — Homepage",
            "url": "https://mohap.gov.ae/",
            "tier": 2,
            "strategy": "html",
            "crawl_delay": 3,
            "note": "MOHAP portal — fallback for regulation updates and announcements",
        },
    ],
}


# ============================================================
# Pre-Written Regulatory Profiles (Fallback Content — Source A)
# ============================================================
# Used when all dynamic crawl tiers and DuckDuckGo fail (Source B exhausted).
# Keys: (region_key, agency_key) — must match REGION_SITES entries.
# Results using this source will carry content_source = "pre-written".

REGION_PROFILES: dict[tuple[str, str], str] = {
    ("台灣 (Taiwan)", "TFDA-QMS"): """\
# 醫療器材品質管理系統準則 (Taiwan QMS Criteria)

**主管機關**: 衛生福利部食品藥物管理署 (TFDA)
**法規編號**: pcode L0030116
**發布日期**: 2021-04-14 / **生效日期**: 2021-05-01

## 法規架構（共 79 條）

| 章節 | 條號 | 主題 |
|---|---|---|
| 第一章 | 1–5 | 總則、適用範圍、術語定義 |
| 第二章 | 6–9 | 品質管理系統（文件管制、紀錄管制） |
| 第三章 | 10–16 | 管理責任（品質政策、管理審查） |
| 第四章 | 17–21 | 資源管理（人員、基礎設施） |
| 第五章 | 22–63 | 產品實現（設計管制、採購、製造、滅菌） |
| 第六章 | 64–79 | 量測、分析及改善（CAPA、內稽） |

## 與 ISO 13485:2016 關係

本準則為 ISO 13485:2016 之等效國內轉換；持有效期內之 ISO 13485 認證可作為符合本準則之佐證。

## 適用對象

依醫療器材管理法申請製造許可證之第二至四等級醫療器材製造業者。
""",
    ("台灣 (Taiwan)", "TFDA-QMS-EN"): """\
# Medical Device Quality Management System Guidelines — Taiwan (English)

**Authority**: Taiwan TFDA | **Law Code**: L0030116 | **Effective**: 2021-05-01

Taiwan's QMS Criteria (79 articles) is the national equivalent of ISO 13485:2016,
mandatory for Class II–IV medical device manufacturing licence applications.

## Key Clauses Mapped to ISO 13485:2016

| ISO 13485 Clause | Articles | Topic |
|---|---|---|
| 4 | 6–9 | QMS General Requirements |
| 5 | 10–16 | Management Responsibility |
| 6 | 17–21 | Resource Management |
| 7 | 22–63 | Product Realization |
| 8 | 64–79 | Measurement, Analysis, Improvement |

A valid ISO 13485:2016 certificate from an accredited body is accepted as evidence of compliance.
""",
    ("美國 (USA)", "FDA-QMSR"): """\
# FDA Quality Management System Regulation (QMSR) — 21 CFR Part 820

**Authority**: U.S. Food and Drug Administration (FDA / CDRH)
**Citation**: 21 CFR Part 820
**Final Rule Published**: February 2, 2024 (89 FR 7496)
**Effective Date**: February 2, 2026

## Overview

The QMSR replaces the 1996 Quality System Regulation (QSR) by incorporating
ISO 13485:2016 by reference. Manufacturers must comply with ISO 13485:2016
as interpreted through the QMSR preamble and FDA-specific requirements.

## FDA-Specific Requirements (21 CFR 820)

| Section | Topic |
|---|---|
| 820.10 | Scope — applies to finished device manufacturers |
| 820.20 | Quality Management System — ISO 13485:2016 incorporated by reference |
| 820.30 | Design Controls — design history file (DHF) |
| 820.40 | Complaints — MDR linkage |
| 820.50 | CAPA |
| 820.60 | Records — device master record (DMR), device history record (DHR) |

## Relationship to ISO 13485:2016

FDA QMSR § 820.20 requires conformance with ISO 13485:2016.
Where ISO 13485 is silent, FDA guidance documents supplement requirements.
""",
    ("美國 (USA)", "eCFR-820"): """\
# 21 CFR Part 820 — Quality Management System Regulation (QMSR) Full Text

**Source**: Electronic Code of Federal Regulations (eCFR)
**Effective**: February 2, 2026 | **Replaces**: Former QSR (21 CFR 820, 1996)

The full regulatory text of 21 CFR Part 820 is available on eCFR.gov.
It incorporates ISO 13485:2016 by reference and adds FDA-specific requirements
for device history records, design history files, and complaint handling linked to MDR.
""",
    ("歐盟 (EU)", "EUR-Lex-MDR"): """\
# EU Medical Device Regulation (EU MDR) 2017/745

**Citation**: Regulation (EU) 2017/745 of the European Parliament and of the Council
**Published**: OJ L 117, 5.5.2017 | **Full Application Date**: May 26, 2021

## QMS Requirements — Annex IX, Section 2

Manufacturers of Class IIa, IIb, and III devices must implement and maintain a QMS
assessed by a Notified Body under Annex IX.

### QMS Elements Required (Annex IX, §2.2)

- Regulatory strategy and compliance procedures
- Design and development management (Annex I GSPR compliance)
- Production and post-production activities (PMS, PMCF)
- Risk management per ISO 14971
- Clinical evaluation per Annex XIV
- Document and records control
- Management responsibility and internal audit

## Equivalence to ISO 13485

EU MDR does not directly reference ISO 13485, but ISO 13485:2016 + EN ISO 13485:2016
is widely accepted by Notified Bodies as the harmonised standard covering QMS requirements.

## Class I Self-Declaration

Class I manufacturers self-declare conformity; no Notified Body QMS audit required
(except sterile, measuring, or reusable surgical devices).
""",
    ("英國 (UK)", "UK-MDR-2002"): """\
# The Medical Devices Regulations 2002 (SI 2002/618) — UK QMS Requirements

**Citation**: SI 2002/618 (as amended)
**Authority**: Medicines and Healthcare products Regulatory Agency (MHRA)
**Post-Brexit Basis**: UKCA marking (replacing CE for Great Britain from July 2024)

## QMS Requirements

| Device Class | Conformity Route | QMS Requirement |
|---|---|---|
| Class I | Self-declaration | No Notified Body audit |
| Class IIa | MHRA-approved body (UK Approved Body) | ISO 13485 QMS audit |
| Class IIb/III | Full QA (Schedule 3, Part III) | Full ISO 13485 QMS audit |
| Active Implantables | Full QA (Schedule 2, Part II) | Full ISO 13485 QMS audit |

## Key Provisions

- **Schedule 3, Part III**: Full quality assurance procedure equivalent to EU MDD Annex II
- Manufacturers must maintain a QMS covering design, manufacture, and final inspection
- ISO 13485:2016 is the accepted standard for demonstrating compliance

## MHRA Guidance

MHRA accepts ISO 13485 certification from a UK Approved Body (UKAB) as primary evidence
of QMS compliance for UKCA marking.
""",
    ("日本 (Japan)", "eGov-QMS-169"): """\
# 医療機器 QMS 省令 — MHLW Ministerial Ordinance No. 169 (QMS省令)

**正式名称**: 医療機器及び体外診断用医薬品の製造管理及び品質管理の基準に関する省令
**根拠法**: 医薬品、医療機器等の品質、有効性及び安全性の確保等に関する法律（薬機法）第 23 条の 2 の 5
**省令番号**: 平成 16 年厚生労働省令第 169 号
**最終改正**: 令和 3 年（2021 年）— ISO 13485:2016 対応改正

## 章構成

| 章 | 条 | 内容 |
|---|---|---|
| 第一章 | 1–4 | 総則 |
| 第二章 | 5–8 | 品質管理監督システム（文書管理） |
| 第三章 | 9–14 | 管理監督者の責務 |
| 第四章 | 15–19 | 資源の管理 |
| 第五章 | 20–63 | 製品実現 |
| 第六章 | 64–79 | 測定、分析及び改善 |

## ISO 13485:2016 対応

2021 年改正により、QMS 省令は ISO 13485:2016 と整合化。
第一種・第二種医療機器製造業者は QMS 適合性調査（PMDA 実施）を受ける義務がある。

## 適用対象

薬機法に基づく医療機器製造販売業・製造業の許可要件として適用。
""",
    ("中國 (China)", "NMPA-GMP-CN"): """\
# Good Manufacturing Practice for Medical Devices — China (Revised 2025)

**Authority**: National Medical Products Administration (NMPA)
**Announcement**: NMPA [2025] No. 107 (issued November 2025)
**Effective Date**: November 1, 2026 | **Replaces**: 2014 GMP Regulation

## Structure (15 Chapters, 132 Articles)

| Chapter | Articles | Topic |
|---|---|---|
| 1 | 1–5 | General Provisions |
| 2 | 6–14 | Quality Management System |
| 3 | 15–19 | Organization and Personnel |
| 4 | 20–25 | Infrastructure and Facilities |
| 5 | 26–29 | Equipment |
| 6 | 30–36 | Design and Development |
| 7 | 37–47 | Procurement and Suppliers |
| 8 | 48–62 | Production Management |
| 9 | 63–72 | Quality Control |
| 10 | 73–80 | Sales and After-Sales |
| 11 | 81–87 | Adverse Event Monitoring |
| 12 | 88–94 | Customer Feedback and Complaints |
| 13 | 95–101 | Nonconforming Product |
| 14 | 102–111 | Records and Documents |
| 15 | 112–132 | Supplementary Provisions |

## Relationship to ISO 13485

China GMP is structurally aligned with ISO 13485:2016 but is administered domestically by NMPA.
Foreign manufacturers must obtain NMPA GMP compliance certification for import registration.
""",
    ("韓國 (Korea)", "MFDS-KGMP"): """\
# Korea Good Manufacturing Practice for Medical Devices (K-GMP)

**Korean Name**: 의료기기 제조 및 품질관리 기준
**Authority**: Ministry of Food and Drug Safety (MFDS)
**Legal Basis**: Medical Devices Act Article 6 (Act No. 14330)
**Latest Revision**: 2024 (aligned with ISO 13485:2016 Third Edition)

## Key Requirements

| Clause | Topic |
|---|---|
| Chapter 2 | Quality Management System (ISO 13485 §4) |
| Chapter 3 | Management Responsibility (ISO 13485 §5) |
| Chapter 4 | Resource Management (ISO 13485 §6) |
| Chapter 5 | Product Realization (ISO 13485 §7) |
| Chapter 6 | Measurement, Analysis, and Improvement (ISO 13485 §8) |

## Certification

- Class I: Self-declaration of GMP compliance
- Class II–IV: GMP assessment by MFDS or accredited inspection body required
- ISO 13485:2016 certificate accepted as substitute for foreign manufacturers via MDSAP

## Scope

Applies to all Class I–IV medical device manufacturers in Korea and foreign manufacturers
seeking MFDS registration.
""",
    ("加拿大 (Canada)", "CMDR-SOR98-282"): """\
# Medical Devices Regulations SOR/98-282 — QMS Requirements (Section 32)

**Citation**: SOR/98-282, Medical Devices Regulations
**Authority**: Health Canada
**Administering Act**: Food and Drugs Act (R.S.C. 1985, c. F-27)

## Section 32 — Quality Management System Requirement

Section 32 requires that, as a condition of obtaining a Device Licence for Class II, III, or IV
medical devices, the manufacturer must hold a valid ISO 13485 certificate issued by a
registrar accredited by a member body of the International Accreditation Forum (IAF).

Since January 2019, Canada exclusively uses MDSAP (Medical Device Single Audit Program)
as the audit mechanism. Health Canada no longer accepts CMDCAS certificates.

## Licence Classes and QMS Requirements

| Class | Licence Type | QMS Required |
|---|---|---|
| Class I | No Device Licence | None |
| Class II | Device Licence | ISO 13485 via MDSAP |
| Class III | Device Licence | ISO 13485 via MDSAP |
| Class IV | Device Licence | ISO 13485 via MDSAP |

## MDSAP Audit Structure

MDSAP audits cover: Organization, Device Design, Purchasing/Supplier Controls, Production/Service,
Measurement/Monitoring/Analysis, and Improvement — all mapped to ISO 13485:2016 clauses.
""",
    ("澳洲 (Australia)", "TGA-Legislation"): """\
# Therapeutic Goods (Medical Devices) Regulations 2002 — QMS Requirements

**Citation**: F2002B00237, TG(MD)R 2002 (current consolidated text)
**Authority**: Therapeutic Goods Administration (TGA)
**Administering Act**: Therapeutic Goods Act 1989

## Schedule 3 — Conformity Assessment Procedures

| Device Class | Procedure | QMS Requirement |
|---|---|---|
| Class I (general) | Self-declaration | No third-party QMS audit |
| Class I (sterile/measuring) | Schedule 3, Part 1 | ISO 13485 production QMS audit |
| Class IIa | Schedule 3, Part 2 | ISO 13485 QMS audit |
| Class IIb | Schedule 3, Part 2 | ISO 13485 Full QMS audit |
| Class III / AIMD | Schedule 3, Part 2 | ISO 13485 Full QMS + design audit |

## ISO 13485 as Accepted Standard

TGA accepts ISO 13485:2016 certification from MDSAP-recognised auditing organisations or
accredited certification bodies as evidence of QMS compliance under Schedule 3.

## MDSAP Participation

Australia (TGA) is a full MDSAP participating authority; MDSAP certificates are accepted
in lieu of separate TGA conformity assessment for QMS requirements.
""",
    ("瑞士 (Switzerland)", "MedDO-SR812213"): """\
# Verordnung über Medizinprodukte (MedDO) SR 812.213 — Swiss Medical Devices Ordinance

**Citation**: SR 812.213
**Authority**: Swissmedic
**In Force**: May 26, 2021 (aligned with EU MDR 2017/745)

## QMS Requirements

Switzerland's MedDO is structurally aligned with EU MDR 2017/745 and IVDR 2017/746.
QMS requirements mirror EU MDR Annex IX (conformity assessment via Notified Body / Swiss Approved Body).

| Device Class | Conformity Route | QMS Requirement |
|---|---|---|
| Class I | Self-declaration | No third-party audit |
| Class IIa / IIb | Annex IX (MedDO) | ISO 13485 QMS audit by Swiss Approved Body |
| Class III / AIMD | Annex IX full | Full QMS + Design Dossier |

## Recognition Agreement

Switzerland has a Mutual Recognition Agreement (MRA) with the EU. CE-marked devices can
circulate in Switzerland, and Swiss Approved Bodies can issue CE/CH marks.

## Swissmedic Role

Swissmedic is the market surveillance authority. Manufacturers must register in the
EUDAMED-compatible Swiss registration system and hold Swissmedic-accepted QMS certificates.
""",
    ("巴西 (Brazil)", "ANVISA-RDC665"): """\
# RDC nº 665/2022 — Boas Práticas de Fabricação para Produtos para Saúde (BGMP)

**Citation**: Resolução RDC nº 665, de 30 de março de 2022
**Authority**: ANVISA (Agência Nacional de Vigilância Sanitária)
**Effective Date**: May 2, 2022 | **Replaces**: RDC 16/2013

## Structure (15 Chapters)

| Chapter | Articles | Topic |
|---|---|---|
| 1 | 1–5 | Scope and Definitions |
| 2 | 6–14 | Quality Management System |
| 3 | 15–20 | Management Responsibility |
| 4 | 21–25 | Resource Management |
| 5 | 26–36 | Infrastructure and Work Environment |
| 6 | 37–50 | Product Realization / Design Control |
| 7 | 51–60 | Purchasing and Supplier Management |
| 8 | 61–75 | Production and Service |
| 9 | 76–85 | Quality Control |
| 10 | 86–92 | Nonconforming Product |
| 11 | 93–99 | CAPA |
| 12 | 100–109 | Internal Audit |
| 13 | 110–115 | Post-Market Surveillance |
| 14 | 116–122 | Records |
| 15 | 123–132 | Supplementary Provisions |

## Relationship to ISO 13485

RDC 665/2022 mirrors FDA QSR and ISO 13485:2016. Foreign manufacturers must demonstrate
BGMP compliance as part of ANVISA registration (INMETRO or recognised CB scheme accepted).
""",
    ("印度 (India)", "CDSCO-MDR2017"): """\
# Medical Devices Rules 2017 (MDR 2017) — India QMS Requirements

**Citation**: G.S.R. 78(E), Ministry of Health and Family Welfare, January 31, 2017
**Authority**: Central Drugs Standard Control Organisation (CDSCO)
**Legal Basis**: Drugs and Cosmetics Act 1940 (as amended by Medical Devices Rules 2017)

## Schedule V — Quality Management System

Schedule V of MDR 2017 specifies the essential QMS requirements for medical device manufacturers:

- Design and Development Controls
- Document and Record Control
- Management Review
- Internal Audit
- Risk Management (per ISO 14971)
- Production and Process Controls
- Corrective and Preventive Action (CAPA)
- Post-Market Surveillance

## Device Classes and QMS Requirements

| Class | Risk Level | QMS Audit Required |
|---|---|---|
| Class A | Low | Self-declaration |
| Class B | Low-Moderate | ISO 13485 certificate or Schedule V compliance |
| Class C | Moderate-High | ISO 13485 certificate mandatory |
| Class D | High | ISO 13485 certificate mandatory |

## ISO 13485 Acceptance

CDSCO accepts ISO 13485:2016 certification from NABCB-accredited or IAF MLA member bodies.
Foreign manufacturers must submit ISO 13485 certificate with import licence application.
""",
    ("新加坡 (Singapore)", "SSO-HPR-2010"): """\
# Health Products (Medical Devices) Regulations 2010 (S 436/2010) — Singapore QMS

**Citation**: S 436/2010, made under Health Products Act (HPA) Cap 122D
**Authority**: Health Sciences Authority (HSA)
**In Force**: November 1, 2010 (amended 2021, 2024)

## QMS Requirements

Regulation 23 and Third Schedule require that manufacturers of Class B, C, and D devices
hold a valid ISO 13485:2016 certificate for their manufacturing site(s).

| Device Class | QMS Requirement |
|---|---|
| Class A | No ISO 13485 required (self-declaration) |
| Class B | ISO 13485 certificate (from Jan 1, 2025: MDSAP or equivalent) |
| Class C | ISO 13485 certificate |
| Class D | ISO 13485 certificate |

## From January 1, 2025

HSA requires MDSAP audit certificate OR ISO 13485 certificate from an MDSAP-recognised
auditing organisation for manufacturer licence applications (Class B/C/D).

## ASEAN MDD Alignment

Singapore HP(MD)R is broadly aligned with the ASEAN Medical Device Directive (AMDD)
framework, facilitating mutual recognition across ASEAN member states.
""",
    ("沙烏地阿拉伯 (Saudi Arabia)", "SFDA-MDS-REQ10"): """\
# SFDA Requirements for Inspections and Quality Management System — MDS-REQ10

**Citation**: MDS-REQ10 (SFDA Medical Devices Sector)
**Authority**: Saudi Food and Drug Authority (SFDA)
**Basis**: Medical Devices Law (Royal Decree M/65, 2017)

## Key Requirements

MDS-REQ10 specifies that all medical device establishments (manufacturers, importers, distributors)
must implement a QMS compliant with ISO 13485:2016 as a condition of SFDA establishment licence.

### QMS Scope

- Design and development (for manufacturers)
- Supplier management and purchasing controls
- Production and service controls
- Post-market surveillance and vigilance
- Complaint handling and CAPA
- Document and records management

## ISO 13485 Certification

- Manufacturers must submit ISO 13485:2016 certificate (accredited CB required)
- Foreign manufacturers: certificate must cover the manufacturing site
- MDSAP certificate accepted as equivalent to ISO 13485 certificate

## SFDA Registration Process

1. Establishment Licence (requires ISO 13485 + MDS-REQ10 compliance declaration)
2. Device Licence (product registration via GHAD online system)
3. Periodic inspection by SFDA QMS inspectors
""",
    ("泰國 (Thailand)", "Thai-FDA-GMP"): """\
# Thailand Medical Device QMS — GMP Notification B.E. 2566 (2023)

**Authority**: Thai Food and Drug Administration (Thai FDA), Ministry of Public Health
**Legal Basis**: Medical Devices Act B.E. 2562 (2019)
**GMP Notification**: Notification of Ministry of Public Health on GMP for Medical Devices B.E. 2566 (2023)

## QMS Requirements

Thailand's GMP Notification B.E. 2566 aligns with ISO 13485:2016 and requires:

| Requirement | Scope |
|---|---|
| Quality Management System | Document control, management review |
| Design Controls | DHF, design verification & validation |
| Production Controls | Process validation, traceability |
| CAPA | Root cause analysis, effectiveness verification |
| Post-Market Surveillance | Vigilance reporting, periodic safety updates |

## Device Classes and Compliance

| Class | Registration | QMS Required |
|---|---|---|
| Class 1 | Notification | Basic QMS |
| Class 2 | Licence | ISO 13485 certificate or GMP inspection |
| Class 3 | Licence + pre-market review | ISO 13485 mandatory |

## ISO 13485 Acceptance

Thai FDA accepts ISO 13485:2016 certificates from IAF MLA member accreditation bodies.
MDSAP certificates are accepted from MDSAP-recognised organisations.
""",
    ("紐西蘭 (New Zealand)", "Medsafe-MD-Legislation"): """\
# New Zealand Medical Device Regulation — Medicines Act 1981 & GMP Code

**Authority**: Medsafe (Medicines and Medical Devices Safety Authority)
**Legislation**: Medicines Act 1981 (Part 5A, as amended)
**Regulations**: Medicines (Database of Medical Devices) Regulations 2003

## QMS Requirements

New Zealand requires compliance with the New Zealand Code of Good Manufacturing Practice (NZ GMP Code)
which references ISO 13485:2016 as the applicable standard for medical devices.

### Key Requirements (NZ GMP Code, Part 7 — Medical Devices)

- Quality Management System per ISO 13485:2016
- Design control (for Class IIa and above)
- Document and record management
- Internal audit
- CAPA
- Post-market surveillance

## Device Classes and QMS

| Class | Medsafe Requirement | ISO 13485 |
|---|---|---|
| Class I | WAND registration | Not required |
| Class IIa | WAND + conformity evidence | ISO 13485 recommended |
| Class IIb/III | Full pre-market review | ISO 13485 certificate required |
| AIMD | Full pre-market review | ISO 13485 certificate required |

## Recognition

Medsafe accepts CE marking (EU MDR) or MDSAP certificates as evidence of QMS compliance.
NZ participates in the IMDRF to align with international regulatory frameworks.
""",
    ("墨西哥 (Mexico)", "DOF-NOM241-2025"): """\
# NOM-241-SSA1-2021 — Buenas Prácticas de Fabricación para Dispositivos Médicos

**Citation**: NOM-241-SSA1-2021
**Authority**: COFEPRIS (Comisión Federal para la Protección contra Riesgos Sanitarios)
**Published**: Diario Oficial de la Federación, December 20, 2021
**Effective**: 180 days after publication (June 2022)

## Structure

| Chapter | Topic |
|---|---|
| 1–3 | Scope, References, Definitions |
| 4 | Quality Management System |
| 5 | Management Responsibility |
| 6 | Resource Management |
| 7 | Product Realization |
| 8 | Measurement, Analysis, Improvement |
| Appendix | Medical device-specific supplements |

## Relationship to ISO 13485

NOM-241-SSA1-2021 incorporates ISO 13485:2016 requirements and supplements them with
Mexican-specific requirements for the COFEPRIS registration process.

## Registration Requirements

- Manufacturers must demonstrate NOM-241 compliance as part of Registro Sanitario application
- ISO 13485:2016 certificate from an IAF-accredited body is accepted as evidence
- Foreign manufacturers: certificate must cover the specific manufacturing site

## Scope

Applies to manufacturers of Class I–IV medical devices (dispositivos médicos)
and in vitro diagnostic devices (IVD) in Mexico.
""",
    ("南非 (South Africa)", "SAHPRA-ISO13485"): """\
# SAHPRA — ISO 13485 Certificate Requirement for Medical Device Establishment Licence

**Authority**: South African Health Products Regulatory Authority (SAHPRA)
**Legal Basis**: Medicines and Related Substances Act 101 of 1965, Regulations 5 & 6
**Effective Date**: June 1, 2025 (SAHPRA Communication, April 2025)

## QMS Requirements

From June 1, 2025, SAHPRA requires an ISO 13485:2016 certificate as a prerequisite for:
- New Medical Device Establishment Licence applications
- Renewal of existing establishment licences

### Accepted Certificates

- ISO 13485:2016 certificate from an accredited certification body (SANAS or IAF MLA member)
- MDSAP audit certificate (from MDSAP-recognised auditing organisation)

## Scope

| Establishment Type | Requirement |
|---|---|
| Local Manufacturer | ISO 13485:2016 certificate for manufacturing site |
| Importer | ISO 13485:2016 certificate from manufacturer |
| Distributor | Letter of Authorisation + manufacturer's ISO 13485 |

## Device Registration

SAHPRA device registration requires:
1. Establishment Licence (with ISO 13485 certificate from June 2025)
2. Device registration application under Section 22C

## IMDRF Alignment

South Africa is actively aligning its medical device regulatory framework with IMDRF guidelines,
including adoption of IMDRF's Technical Document on QMS requirements.
""",
    ("土耳其 (Turkey)", "TITCK-MD-Legislation"): """\
# Turkey Medical Device QMS — EU MDR 2017/745 Aligned Regulations (2021)

**Authority**: Türkiye İlaç ve Tıbbi Cihaz Kurumu (TITCK)
**Legal Basis**: Medical Device Regulation published June 2, 2021 (Official Gazette No. 31499)
**EU MDR Alignment**: Substantially mirrors EU MDR 2017/745

## QMS Requirements

Turkey's medical device regulation requires conformity assessment procedures equivalent to
EU MDR 2017/745, including QMS requirements from Annex IX.

| Device Class | EU MDR Equivalent | QMS Requirement |
|---|---|---|
| Class I | Self-declaration | No third-party QMS audit |
| Class IIa | Annex IX Route A | ISO 13485 QMS audit by TITCK Notified Body |
| Class IIb / Class III | Annex IX full | Full QMS audit + Design Dossier |

## CE Marking Acceptance

TITCK accepts CE marking from EU Notified Bodies for medical devices. Manufacturers holding
a valid CE certificate under EU MDR 2017/745 can apply for Turkish registration without
a separate QMS audit.

## Transition Timeline

- Pre-2021 devices under old Medical Device Regulation (2001/8 aligned with MDD 93/42/EEC)
- From June 14, 2021: New MDR-aligned regulation in force
- Transition period for existing CE MDD certificates as agreed with EU Commission
""",
    ("印尼 (Indonesia)", "Kemkes-CPAKB"): """\
# Indonesia Medical Device QMS — CPAKB (Permenkes No. 20 Tahun 2017)

**Authority**: Ministry of Health (Kemenkes), Directorate General of Pharmaceutical and Medical Devices (Farmalkes)
**Legal Basis**: Permenkes No. 20 Tahun 2017 — Cara Pembuatan Alat Kesehatan yang Baik (CPAKB)
**Issued**: 8 March 2017 | **Effective**: 18 April 2017 | BN.2017/No.590

## QMS Requirements

Indonesia requires medical device manufacturers to demonstrate GMP / ISO 13485 compliance
as part of the product registration (Nomor Izin Edar — NIE) application.

| Device Class | Risk Level | QMS Requirement |
|---|---|---|
| Kelas A | Low | Basic quality documentation |
| Kelas B | Low-Moderate | ISO 13485 certificate or GMP inspection |
| Kelas C | Moderate-High | ISO 13485 certificate mandatory |
| Kelas D | High | ISO 13485 certificate mandatory |

## ISO 13485 Acceptance

- Domestic manufacturers: ISO 13485 certificate from KAN-accredited (National Accreditation Body) CB
- Foreign manufacturers: ISO 13485 from IAF MLA member + Certificate of Free Sale (CFS) from home country authority

## Registration Process

1. Manufacturer obtains ISO 13485 certification
2. Apply for NIE through Regalkes online portal
3. Submit technical documentation + ISO 13485 certificate
4. Kemenkes review and NIE issuance (12–24 months for Class C/D)
""",
    ("馬來西亞 (Malaysia)", "MDA-Legislation"): """\
# Malaysia Medical Device Act 737 (2012) — QMS Requirements

**Citation**: Medical Device Act 2012 (Act 737) & Medical Device Regulations 2012
**Authority**: Medical Device Authority (MDA) Malaysia
**Effective**: July 1, 2013

## QMS Requirements

Part III of the Medical Device Regulations 2012 requires conformity assessment,
including QMS certification, for Class B, C, and D devices.

| Device Class | Conformity Route | QMS Requirement |
|---|---|---|
| Class A | Self-declaration | No third-party QMS audit |
| Class B | Conformity assessment | ISO 13485 or equivalent |
| Class C | Full conformity assessment | ISO 13485 certificate mandatory |
| Class D | Full conformity assessment | ISO 13485 certificate mandatory |

## Accepted QMS Certifications

MDA accepts the following as equivalent evidence of QMS compliance:
- ISO 13485:2016 certificate (from DAkkS, UKAS, SAC, or IAF MLA member)
- MDSAP audit certificate
- FDA QSR compliance (for US-based manufacturers)
- MHLW Ordinance 169 compliance (for Japan-based manufacturers)

## Registration Timeline

Malaysia requires product registration (product listing) through the MDA online portal.
QMS certificate must be submitted with initial registration and renewed every 5 years.
""",
    ("以色列 (Israel)", "MOH-MD-Division"): """\
# Israel Medical Device QMS — Medical Equipment Law 5772-2012

**Authority**: Israel Ministry of Health, Medical Technology, Health Informatics & Research Division (AMAR)
**Legal Basis**: Medical Equipment Law 5772-2012; Medical Devices Regulations 5773-2013

## QMS Requirements

Israel's medical device regulatory framework requires ISO 13485:2016 compliance for
medical device manufacturers as a condition of import licence and market authorisation.

| Device Class (Risk) | Regulatory Route | QMS Requirement |
|---|---|---|
| Class I | Technical file + declaration | ISO 13485 not mandatory |
| Class IIa/IIb | Conformity assessment | ISO 13485 certificate required |
| Class III | Full assessment | ISO 13485 certificate + design review |

## CE/FDA Recognition

Israel Ministry of Health accepts:
- CE marking under EU MDR 2017/745 as primary evidence for most device classes
- FDA 510(k) clearance or PMA approval as equivalent evidence
- ISO 13485:2016 certificate from IAF-accredited CB

## Registration Process

Manufacturers submit registration applications to AMAR through the MOH Medical Device Registration System.
Foreign manufacturers must appoint a local Authorised Representative (Israeli agent).
""",
    ("菲律賓 (Philippines)", "FDA-PH-RA9711"): """\
# Philippines FDA — Medical Device QMS Requirements (RA 9711 / FDA Act 2009)

**Authority**: Food and Drug Administration Philippines (FDA-PH)
**Center**: Center for Device Regulation, Radiation Health and Research (CDRRHR)
**Legal Basis**: Republic Act 9711 (FDA Act of 2009); FDA Circular No. 2020-007

## QMS Requirements

FDA-PH requires medical device manufacturers to demonstrate GMP compliance (ISO 13485:2016)
for Certificate of Product Registration (CPR) applications.

| Device Class | Risk | QMS Requirement |
|---|---|---|
| Class A | Exempt/Low | Basic quality documentation |
| Class B | Low-Moderate | ISO 13485 certificate from IAF-accredited CB |
| Class C | Moderate-High | ISO 13485 mandatory |
| Class D | High | ISO 13485 mandatory + premarket evaluation |

## ISO 13485 Acceptance

FDA-PH accepts ISO 13485:2016 certificates from certification bodies accredited by
Philippine Accreditation Bureau (PAB) or IAF MLA member bodies.

Foreign manufacturers must submit:
- ISO 13485 certificate
- Certificate of Free Sale (CFS) / Certificate of Exportation (CE)
- Authorised Philippine Distributor appointment

## ASEAN Alignment

Philippines participates in ASEAN Harmonization of Medical Device Regulations and
the ASEAN MDPQ (Medical Device Product Quality) framework.
""",
    ("越南 (Vietnam)", "DMEC-MOH"): """\
# Vietnam Medical Device QMS — Decree 98/2021/ND-CP & Circular 10/2023/TT-BYT

**Authority**: Ministry of Health (MOH), Department of Medical Equipment and Construction (DMEC)
**Primary Regulation**: Decree No. 98/2021/ND-CP (November 8, 2021)
**Technical Circular**: Circular 10/2023/TT-BYT (May 22, 2023)

## QMS Requirements

Decree 98/2021 requires ISO 13485:2016 QMS certification for all Class B, C, and D medical device
manufacturers as a mandatory condition for product registration (number/declaration).

| Device Class | Vietnamese Classification | QMS Requirement |
|---|---|---|
| Class A | Loại A | No ISO 13485 required |
| Class B | Loại B | ISO 13485 certificate mandatory |
| Class C | Loại C | ISO 13485 certificate mandatory |
| Class D | Loại D | ISO 13485 certificate mandatory |

## ISO 13485 Certification

- Domestic manufacturers: certificate from VILAS (Vietnam Laboratory Accreditation Scheme) or IAF MLA member
- Foreign manufacturers: certificate from IAF MLA member in country of manufacture

## Registration Process (Circular 10/2023)

1. Manufacturer obtains ISO 13485:2016 certificate
2. Vietnam importer/distributor acts as responsible party
3. Submit Declaration of Conformity or Registration Application to MOH/DMEC
4. DMEC issues Registration Number (Số lưu hành)
""",
    ("哥倫比亞 (Colombia)", "INVIMA-Decreto4725"): """\
# Colombia Medical Device QMS — Decreto 4725/2005 (INVIMA)

**Authority**: Instituto Nacional de Vigilancia de Medicamentos y Alimentos (INVIMA)
**Legal Basis**: Decreto 4725 de 2005 (Medical Devices and Diagnostic Equipment)
**Administering Ministry**: Ministry of Health and Social Protection

## QMS Requirements

Decreto 4725/2005 requires medical device manufacturers to demonstrate GMP / ISO 13485
compliance as a condition of INVIMA registration (Registro Sanitario).

| Device Class | INVIMA Class | QMS Requirement |
|---|---|---|
| Class I | Clase I | GMP declaration |
| Class IIa | Clase IIa | ISO 13485 evidence |
| Class IIb | Clase IIb | ISO 13485 certificate |
| Class III | Clase III | ISO 13485 certificate mandatory |

## ISO 13485 Acceptance

INVIMA accepts ISO 13485:2016 certificates from:
- ONAC (Organismo Nacional de Acreditación de Colombia) accredited CBs
- IAF MLA member accreditation bodies internationally

## Registration Process

1. Manufacturer submits technical dossier + ISO 13485 certificate to INVIMA
2. INVIMA issues Registro Sanitario (10-year validity for Class III; 5 years for others)
3. Post-market surveillance obligations apply after registration

## IMDRF/PAHO Alignment

Colombia is working towards alignment with IMDRF guidelines through the PAHO/PANDRH
(Pan American Network on Drug Regulatory Harmonization) medical device working group.
""",
    ("俄羅斯 (Russia)", "RZN-MD"): """\
# Russia Medical Device QMS — Government Decree No. 1684 (2024)

**Authority**: Federal Service for Surveillance in Healthcare (Roszdravnadzor)
**Primary Regulation**: Government Decree No. 1684 (effective March 1, 2025; replaces No. 1416)
**Additional**: Ministry of Health Order No. 972 (2024)

## QMS Requirements

From January 1, 2024 (Class IIa-sterile and above), Roszdravnadzor requires ISO 13485:2016
inspection for medical device state registration (государственная регистрация).

| Device Class (Russian) | Risk | ISO 13485 Inspection |
|---|---|---|
| Class 1 | Low | Not required |
| Class 2a | Moderate (non-sterile) | Not required |
| Class 2a (sterile) | Moderate | Required from Jan 2024 |
| Class 2b | Moderate-High | Required |
| Class 3 | High | Required |

## Regulatory Process

1. Roszdravnadzor GMP inspection of manufacturer's site OR submission of ISO 13485 certificate
2. Technical Specification (ТУ) filing
3. State Registration Certificate issuance

## Eurasian Economic Union (EAEU)

Russia participates in EAEU regulatory harmonization; medical devices may also be
registered under the Common Medical Device Registration Procedure for circulation across
Russia, Belarus, Kazakhstan, Armenia, and Kyrgyzstan.
""",
    ("埃及 (Egypt)", "EDA-MD-Guide"): """\
# Egypt Medical Device QMS — EDA Registration Requirements

**Authority**: Egyptian Drug Authority (EDA), formerly CAPA
**Legal Basis**: Ministerial Decree No. 425/2015; EDA Law 151/2019
**QMS Guidance**: EDA Regulatory Guideline for Registering Medical Devices (2021)

## QMS Requirements

EDA requires medical device manufacturers to submit ISO 13485:2016 certificate as a
mandatory document for product registration.

| Device Class | Risk | QMS Requirement |
|---|---|---|
| Class A | Low | Basic quality declaration |
| Class B | Moderate | ISO 13485 certificate required |
| Class C | High | ISO 13485 certificate mandatory |
| Class D | Critical | ISO 13485 certificate mandatory + clinical data |

## ISO 13485 Acceptance

EDA accepts ISO 13485:2016 certificates from:
- Egyptian Accreditation Council (EGAC) accredited CBs
- IAF MLA member international CBs
- CE marking (under EU MDR/MDD) as alternative evidence for most classes

## Registration Requirements

Foreign manufacturers must:
1. Submit ISO 13485:2016 certificate
2. Submit Certificate of Free Sale from home country authority
3. Appoint EDA-registered local agent
4. Provide technical documentation (product dossier)

## Timeline

EDA registration validity: 3 years (renewable). Manufacturers must notify EDA of
significant changes to QMS or device design.
""",
    ("智利 (Chile)", "ISP-Regulations"): """\
# Chile Medical Device QMS — ISP Chile / ANAMED Regulations

**Authority**: Instituto de Salud Pública de Chile (ISP), División de Dispositivos Médicos (ANAMED)
**Legal Basis**: Decreto Supremo No. 825/1998 (Reglamento de Dispositivos Médicos)
**GMP Guide**: ISP Resolution N°8209/1999 (GMP Guide for Medical Devices)

## QMS Requirements

Chile requires medical device manufacturers to demonstrate GMP compliance as a condition of
ISP registration (Registro Sanitario). ISO 9001 or ISO 13485 compliance is referenced.

| Device Class | Risk | QMS Requirement |
|---|---|---|
| Class I | Exempt | No registration required |
| Class II | Low-Moderate | ISO 13485 or GMP evidence |
| Class III | High | ISO 13485 certificate mandatory |

## ISO 13485 / CE / FDA Acceptance

ISP Chile accepts:
- ISO 13485:2016 certificate from IAF MLA member CB
- CE marking under EU MDR 2017/745
- FDA 510(k) or PMA clearance
- TGA (Australia) approval

## Registration Process

1. Manufacturer prepares technical dossier
2. Chilean importer submits to ISP/ANAMED
3. ISP issues Registro Sanitario
4. Periodic renewal every 5 years

## PANDRH Alignment

Chile participates in PAHO/PANDRH harmonization initiatives and is working towards
adoption of IMDRF-aligned regulatory framework for medical devices.
""",
    ("阿聯酋 (UAE)", "MOHAP-FDL38-2024"): """\
# UAE Medical Device QMS — Federal Decree-Law No. 38 of 2024

**Authority**: Ministry of Health and Prevention (MOHAP) & Emirates Health Authority (EHA)
**Legal Basis**: Federal Decree-Law No. 38 of 2024 (Medical Products, Pharmacy Practice and Pharmaceutical Establishments)
**In Force**: January 2025 | **Replaces**: Federal Law No. 4 of 1983

## QMS Requirements

UAE requires ISO 13485:2016 certificate for medical device manufacturer registration
(Establishment Licence) under the new Federal Decree-Law No. 38 of 2024.

| Entity Type | Requirement |
|---|---|
| Manufacturer (UAE) | ISO 13485:2016 certificate + MOHAP GMP inspection |
| Foreign Manufacturer | ISO 13485:2016 certificate from home country CB |
| Importer | Manufacturer's ISO 13485 + MOHAP importer licence |
| Distributor | Manufacturer's ISO 13485 + distributor licence |

## ISO 13485 Acceptance

MOHAP and Dubai Health Authority (DHA) accept:
- ISO 13485:2016 certificate from DAkkS, UKAS, or IAF MLA member CBs
- CE marking (EU MDR) as alternative for most device classes
- MDSAP certificate from MDSAP-recognised auditing organisations

## Registration Process (MOHAP / UAE REGMED)

1. Obtain Establishment Licence (requires ISO 13485 certificate)
2. Register product in MOHAP/EMAAR system (product registration dossier)
3. MOHAP approval / Certificate of Registration
4. Periodic renewal every 3 years

## Emirates-Specific Requirements

Dubai (DHA) and Abu Dhabi (DOH) may have additional emirate-level requirements
that supplement the federal MOHAP framework.
""",
    ("阿根廷 (Argentina)", "ANMAT-MD"): """\
# Argentina Medical Device QMS — ANMAT Disposición 64/2025 (replaces 2318/2002)

**Authority**: Administración Nacional de Medicamentos, Alimentos y Tecnología Médica (ANMAT)
**Current Regulation**: Disposición ANMAT 64/2025 (in force Jan 2025, incorporates MERCOSUR GMC 25/21)
**Previous**: Disposición ANMAT 2318/2002 (superseded)
**GMP Reference**: Disposición ANMAT 2319/2002 — BPF (Buenas Prácticas de Fabricación) for manufacturers

## QMS Requirements

ANMAT requires GMP/BPF (Buenas Prácticas de Fabricación) compliance for medical device registration.
ISO 13485:2016 is the accepted international standard.

| Device Class (ANMAT) | Risk | QMS Requirement |
|---|---|---|
| Class I | Exempt/Low | Basic declaration |
| Class II | Moderate | ISO 13485 evidence or ANMAT GMP inspection |
| Class III | High | ISO 13485 certificate mandatory |
| Class IV | Critical | ISO 13485 + clinical evidence |

## ISO 13485 Acceptance

ANMAT accepts:
- ISO 13485:2016 certificate from OAA (Organismo Argentino de Acreditación) or IAF MLA member
- CE marking (EU MDR) for most device classes
- FDA clearance/approval

## Registration Process

1. Foreign manufacturer appoints Argentine technical director (director técnico)
2. Technical dossier submission to ANMAT
3. ANMAT issues Certificado de Autorización de Uso (CUA)

## MERCOSUR Harmonization

Argentina participates in MERCOSUR Resolution GMC 40/00 on medical device harmonization,
working towards mutual recognition of registrations across Brazil, Argentina, Uruguay, and Paraguay.
""",
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
            if not _is_safe_url(sitemap_url):
                raise ValueError(f"Blocked unsafe URL: {sitemap_url}")
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
        root: _stdlib_ET.Element,
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
            if not _is_safe_url(sitemap_url):
                raise ValueError(f"Blocked unsafe URL: {sitemap_url}")
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
        root: _stdlib_ET.Element,
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
    if not _is_safe_url(url):
        raise ValueError(f"Blocked unsafe URL: {url}")

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
        "content_source": None,
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
            result["content_source"] = "live"
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
            result["content_source"] = "live"
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
            result["content_source"] = "live"
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
            result["content_source"] = "live"
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
            # Detect Jina "Warning" error pages — e.g. "Warning: Target URL
            # returned error 412" — these are upstream HTTP errors wrapped in
            # a 200 response; treat them as failures so they don't pollute the
            # regulatory markdown DB with useless error text.
            _jina_error = (
                content.startswith("Warning:")
                and "returned error" in content[:200]
            )
            if content and len(content) > 50 and not _jina_error:
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
                result["content_source"] = "live"
                if len(content) > _MAX_CONTENT_SIZE:
                    result["content_markdown"] = (
                        content[:_MAX_CONTENT_SIZE] + "\n\n... (content truncated)"
                    )
            elif _jina_error:
                # Extract the HTTP status from the warning message if possible
                _warn_line = content.split("\n")[0][:120]
                result["failure_reason"] = (
                    f"Jina Reader 回傳上游錯誤 — {_warn_line}"
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
        """Crawl a single site with tier dispatch, fallback chain, and rate limiting.

        Fallback chain: Tier2 (httpx) → Tier3 (Jina) → DuckDuckGo → pre-written profile.
        """
        tier = site.get("tier", 2)
        url = site.get("url", "")
        sem = self._get_domain_semaphore(url)

        async with sem:
            crawl_delay = min(site.get("crawl_delay", 3), 5)
            await asyncio.sleep(crawl_delay * 0.5)

            if tier == 1:
                result = await _crawl_tier1_api(
                    self._client, site, region, self._etag_cache
                )
                if result.get("crawl_status") != "success":
                    profile = self._fallback_profile(site, region)
                    if profile:
                        return profile
                return result
            elif tier == 3:
                result = await _crawl_tier3_jina(
                    self._client, site, region, self._jina_semaphore
                )
                if result.get("crawl_status") != "success":
                    ddgs_result = await self._fallback_ddgs_search(site, region)
                    if ddgs_result.get("crawl_status") == "success":
                        ddgs_result["note"] = (
                            f"Jina 失敗 ({result.get('failure_reason', '未知')})"
                            f" → DuckDuckGo 備援成功"
                        )
                        return ddgs_result
                    profile = self._fallback_profile(site, region)
                    if profile:
                        profile["note"] = (
                            f"Jina 失敗 ({result.get('failure_reason', '未知')})"
                            f" → DuckDuckGo 亦失敗 → 使用預設法規摘要"
                        )
                        return profile
                return result
            else:
                result = await _crawl_tier2_httpx(
                    self._client, site, region, self._etag_cache
                )
                if result.get("crawl_status") != "success":
                    original_reason = result.get("failure_reason", "未知")
                    jina_result = await _crawl_tier3_jina(
                        self._client, site, region, self._jina_semaphore
                    )
                    if jina_result.get("crawl_status") == "success":
                        jina_result["note"] = (
                            f"httpx 失敗 ({original_reason}) → Jina 備援成功"
                        )
                        return jina_result
                    ddgs_result = await self._fallback_ddgs_search(site, region)
                    if ddgs_result.get("crawl_status") == "success":
                        ddgs_result["note"] = (
                            f"httpx 失敗 ({original_reason})"
                            f" → Jina 失敗 ({jina_result.get('failure_reason', '未知')})"
                            f" → DuckDuckGo 備援成功"
                        )
                        return ddgs_result
                    profile = self._fallback_profile(site, region)
                    if profile:
                        profile["note"] = (
                            f"httpx 失敗 ({original_reason})"
                            f" → Jina 失敗 ({jina_result.get('failure_reason', '未知')})"
                            f" → DuckDuckGo 亦失敗 → 使用預設法規摘要"
                        )
                        return profile
                    result["failure_reason"] = (
                        f"{original_reason}"
                        f" → Jina 備援亦失敗 ({jina_result.get('failure_reason', '未知')})"
                        f" → DuckDuckGo 備援亦失敗"
                    )
                return result

    def _fallback_profile(self, site: dict, region: str):
        """Return a pre-written profile result if one exists for this site, else None."""
        key = (region, site.get("agency", ""))
        content = REGION_PROFILES.get(key)
        if not content:
            return None
        result = _make_result_template(site, region)
        result["crawl_status"] = "success"
        result["content_source"] = "pre-written"
        result["content_markdown"] = content
        # Extract title from first heading
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                result["title"] = line[2:].strip()
                break
        if not result["title"]:
            result["title"] = site.get("name", site.get("agency", ""))
        result["crawl_duration_seconds"] = 0.0
        return result

    async def _fallback_ddgs_search(self, site: dict, region: str) -> dict:
        """Fallback: use DuckDuckGo to search for regulation content."""
        result = _make_result_template(site, region)
        start = time.time()
        try:
            agency = site.get("agency", "")
            en_name = region
            if "(" in region and ")" in region:
                en_name = region.split("(")[1].rstrip(")")
            query = f"{en_name} {agency} medical device regulation requirements"
            search_results = await asyncio.to_thread(_ddgs_search, query, 8)
            if not search_results:
                result["failure_reason"] = "DuckDuckGo 搜尋無結果"
                result["crawl_duration_seconds"] = round(time.time() - start, 2)
                return result
            md_parts = [f"# {region} — {agency} (DuckDuckGo 備援搜尋結果)\n"]
            for i, sr in enumerate(search_results, 1):
                title = sr.get("title", "")
                body = sr.get("body", "")
                href = sr.get("href", sr.get("link", ""))
                md_parts.append(f"## {i}. {title}\n\n{body}\n\n來源: {href}\n")
            combined = "\n---\n".join(md_parts)
            if len(combined.strip()) > 100:
                result["crawl_status"] = "success"
                result["content_source"] = "live"
                result["content_markdown"] = combined
                result["title"] = f"{agency} (DuckDuckGo fallback)"
                result["note"] = "透過 DuckDuckGo 搜尋取得替代法規資訊"
            else:
                result["failure_reason"] = "DuckDuckGo 搜尋結果內容不足"
        except Exception as e:
            result["failure_reason"] = f"DuckDuckGo 備援失敗: {str(e)[:200]}"
        result["crawl_duration_seconds"] = round(time.time() - start, 2)
        return result

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
        """Internal: crawl a list of regions in parallel with URL deduplication.

        When multiple regions share the same URL (e.g. Canada and MDSAP both
        reference mdsap.global pages), each unique URL is crawled only once.
        The result is then cloned for every alias region that shares it.
        """
        await self._ensure_client()
        await self._etag_cache.load()

        start_time = time.time()

        # --- URL deduplication ------------------------------------------------
        # url_to_primary: URL -> (primary_region, site_dict)  (first seen wins)
        # url_to_aliases: URL -> [(alias_region, site_dict), ...]
        url_to_primary: dict[str, tuple[str, dict]] = {}
        url_to_aliases: dict[str, list[tuple[str, dict]]] = {}

        for region in regions:
            sites = REGION_SITES.get(region, [])
            for site in sites:
                url = site.get("url", "")
                if url in url_to_primary:
                    url_to_aliases.setdefault(url, []).append((region, site))
                else:
                    url_to_primary[url] = (region, site)

        # Build one task per *unique* URL
        task_keys: list[str] = []  # parallel list of URLs for index lookup
        tasks = []
        for url, (primary_region, site) in url_to_primary.items():
            task_keys.append(url)
            tasks.append(self._crawl_single_site(site, primary_region))

        # Execute all in parallel
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results — convert exceptions to failed results
        all_results = []
        for i, r in enumerate(raw_results):
            url = task_keys[i]
            primary_region, site_info = url_to_primary[url]

            if isinstance(r, Exception):
                failed_result = _make_result_template(site_info, primary_region)
                failed_result["failure_reason"] = _classify_failure(
                    r, site_info.get("url", "")
                )
                failed_result["crawl_duration_seconds"] = 0.0
                all_results.append(failed_result)
                # Clone failure for aliases
                for alias_region, alias_site in url_to_aliases.get(url, []):
                    alias_result = _make_result_template(alias_site, alias_region)
                    alias_result["failure_reason"] = failed_result["failure_reason"]
                    alias_result["crawl_duration_seconds"] = 0.0
                    alias_result["shared_from"] = primary_region
                    all_results.append(alias_result)
            elif isinstance(r, dict):
                all_results.append(r)
                # Clone success for aliases
                for alias_region, alias_site in url_to_aliases.get(url, []):
                    import copy

                    alias_result = copy.deepcopy(r)
                    alias_result["region"] = alias_region
                    alias_result["agency"] = alias_site.get(
                        "agency", r.get("agency", "")
                    )
                    alias_result["agency_name"] = alias_site.get(
                        "name", r.get("agency_name", "")
                    )
                    alias_result["shared_from"] = primary_region
                    all_results.append(alias_result)

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


_MIN_COMPLETE_CONTENT_LEN = 500  # same threshold as _crawl_tier2_httpx


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
