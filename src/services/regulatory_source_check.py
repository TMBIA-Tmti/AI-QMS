"""
Provenance and completeness checks for crawled regulatory documents (no LLM).

For every document in the regulatory registry this answers two questions:

  1. Is it really the regulation (right source, readable text, not a bot-block
     page / search-result stub / raw PDF bytes)?
  2. Is it complete (article numbering continuous, count matches what the
     registry says to expect, not truncated)?

Status per document:  ok | warn | fail
  fail  -> must not be indexed or fed to the LLM (garbage / wrong content)
  warn  -> usable but a human should look (mirror site, unverifiable count)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── source classification ────────────────────────────────────────────────────

# Host suffixes of official regulators / publishers / standards bodies.
_OFFICIAL_SUFFIXES = (
    ".gov", ".gov.uk", ".gov.au", ".gov.sg", ".gov.tw", ".gov.my", ".gov.br",
    ".gov.cn", ".gov.il", ".gov.in", ".gov.sa", ".gov.tr", ".gov.co", ".gov.ae",
    ".gov.ph", ".gov.eg", ".gov.za", ".gov.ar", ".gob.mx", ".gob.ar", ".go.jp",
    ".go.kr", ".go.th", ".go.id", ".govt.nz", ".gc.ca", ".admin.ch", ".europa.eu",
    ".who.int", ".iso.org", ".imdrf.org", ".ich.org", ".swissmedic.ch",
    ".sahpra.org.za", ".bcn.cl", ".minsal.cl", ".luatvietnam.vn",
    ".austlii.edu.au", ".mfds.go.kr", ".pmda.go.jp", ".tga.gov.au", ".chinhphu.vn",
)
# Trade / commercial / third-party mirrors: content may be right but is not primary.
_SECONDARY_SUFFIXES = (
    "medical-device-regulation.eu", "kontur.ru", "zakonrf.info", "consultant.ru",
    "trade.gov", "usembassy.gov", "interamericancoalition-medtech.org",
    "luatvietnam.vn",
)

_BOT_BLOCK_SIGNS = (
    "just a moment", "checking your browser", "enable javascript and cookies",
    "attention required", "access denied", "verify you are human", "captcha",
    "cf-chl", "request blocked", "are you a robot",
)
_PDF_MARKERS = ("/cropbox", "/mediabox", "endobj", "/flatedecode", "%pdf-", "/type /page")
_SEARCH_STUB_SIGNS = ("duckduckgo", "搜尋結果", "搜寻结果")

# Articles the registry promises but whose count the title does not state.
EXPECTED_ARTICLES: dict[str, int] = {
    "TFDA-QMS": 79,
    "EU-MDR-2017-745-PDF": 123,
    "EUR-Lex-MDR-CELLAR": 123,
    "EUR-Lex-MDR-UK": 123,
}

_EN_ARTICLE = re.compile(r"(?m)^\W{0,6}Article\s+(\d{1,3})\s*$", re.IGNORECASE)
_ZH_ARTICLE = re.compile(r"(?m)^\W{0,8}第\s*(\d{1,3})(?:\s*-\s*\d+)?\s*條")
_TITLE_COUNT = re.compile(r"\b(\d{2,3})\s+articles\b", re.IGNORECASE)


def classify_domain(url: str) -> str:
    """official | secondary | unknown"""
    host = (urlparse(url or "").hostname or "").lower()
    if not host:
        return "unknown"
    if any(host == s or host.endswith("." + s) or host.endswith(s) for s in _SECONDARY_SUFFIXES):
        return "secondary"
    if any(host.endswith(s) for s in _OFFICIAL_SUFFIXES):
        return "official"
    return "unknown"


def reject_reason(content: str) -> str:
    """Cheap content-only test: why this text can't be a regulation ('' if fine)."""
    head = content[:3000].lower()
    sample = content[:200000].lower()
    if sum(sample.count(m) for m in _PDF_MARKERS) >= 5:
        return "raw PDF structure (no extracted text)"
    if any(s in head for s in _BOT_BLOCK_SIGNS):
        return "bot-block / challenge page"
    if any(s in content[:1200].lower() for s in _SEARCH_STUB_SIGNS) and len(content) < 20000:
        return "search-result stub, not the document"
    printable = sum(1 for ch in content[:20000] if ch.isprintable() or ch in "\n\t")
    if content[:20000] and printable / len(content[:20000]) < 0.9:
        return "binary / unreadable characters"
    return ""


@dataclass
class DocCheck:
    doc_id: str
    agency: str
    region: str
    url: str
    status: str = "ok"
    issues: list[str] = field(default_factory=list)
    source: str = "unknown"
    chars: int = 0
    articles_found: int = 0
    articles_max: int = 0
    articles_expected: Optional[int] = None
    articles_missing: list[int] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.status = "fail"
        self.issues.append(msg)

    def warn(self, msg: str) -> None:
        if self.status == "ok":
            self.status = "warn"
        self.issues.append(msg)


def _article_numbers(content: str) -> set[int]:
    nums = {int(m) for m in _EN_ARTICLE.findall(content)}
    nums |= {int(m) for m in _ZH_ARTICLE.findall(content)}
    return nums


def verify_document(entry: dict, content: str) -> DocCheck:
    """Check one registry entry against its markdown text."""
    chk = DocCheck(
        doc_id=entry.get("doc_id", ""),
        agency=entry.get("agency", ""),
        region=entry.get("region", ""),
        url=entry.get("url", ""),
        chars=len(content),
    )
    chk.source = classify_domain(chk.url)
    if chk.source == "unknown":
        chk.warn(f"source domain not on the official list: {urlparse(chk.url).hostname}")
    elif chk.source == "secondary":
        chk.warn("third-party mirror, not the official publisher")

    reason = reject_reason(content)
    if reason:
        chk.fail(reason)
        return chk
    if len(content.strip()) < 1500:
        chk.warn(f"very short ({len(content.strip())} chars)")

    nums = _article_numbers(content)
    chk.articles_found = len(nums)
    chk.articles_max = max(nums) if nums else 0

    title = entry.get("title", "") or ""
    expected = EXPECTED_ARTICLES.get(chk.agency)
    if expected is None:
        m = _TITLE_COUNT.search(title)
        expected = int(m.group(1)) if m else None
    chk.articles_expected = expected

    if len(nums) >= 5:
        top = max(nums)
        missing = [n for n in range(1, top + 1) if n not in nums]
        chk.articles_missing = missing[:50]
        # Only treat the numbers as an article sequence when they densely cover
        # 1..top; scattered list numbers (guidance, section lists) are not.
        is_sequence = len(nums) / top >= 0.5
        if is_sequence:
            if len(missing) > max(2, int(top * 0.05)):
                chk.fail(f"article numbering has {len(missing)} gaps in 1..{top}")
            elif missing:
                chk.warn(f"article numbering gaps: {missing[:10]}")
        elif expected:
            chk.warn("article numbers are not a clean sequence (cannot verify completeness)")
        if expected and top < expected:
            chk.fail(f"truncated: found articles up to {top}, expected {expected}")
        elif expected and top > expected + 5:
            chk.warn(f"found article {top} > expected {expected} (annex references?)")
    elif expected:
        chk.warn(f"expected {expected} articles but no article headings detected (cannot verify)")
    return chk


# ── corpus level ─────────────────────────────────────────────────────────────

def _read(store, entry: dict) -> Optional[str]:
    rel = (entry.get("markdown_path") or "").replace("\\", "/")
    if not rel:
        return None
    try:
        return (store.base_path / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def verify_region(region_name: str, store=None) -> list[DocCheck]:
    if store is None:
        from src.storage.regulatory_markdown_storage import get_regulatory_markdown_store

        store = get_regulatory_markdown_store()
    out: list[DocCheck] = []
    for entry in store.list_documents(region=region_name, status="active"):
        content = _read(store, entry)
        if content is None:
            c = DocCheck(entry.get("doc_id", ""), entry.get("agency", ""), region_name, entry.get("url", ""))
            c.fail("markdown file missing on disk")
            out.append(c)
        else:
            out.append(verify_document(entry, content))
    return out


def verify_all(store=None) -> dict[str, list[DocCheck]]:
    if store is None:
        from src.storage.regulatory_markdown_storage import get_regulatory_markdown_store

        store = get_regulatory_markdown_store()
    return {r: verify_region(r, store) for r in store.get_all_regions()}


def render_markdown(results: dict[str, list[DocCheck]], recall: Optional[dict] = None) -> str:
    icon = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
    lines = ["# Regulatory corpus verification", ""]
    total = {"ok": 0, "warn": 0, "fail": 0}
    for checks in results.values():
        for c in checks:
            total[c.status] += 1
    lines += [f"Documents: {sum(total.values())}  |  OK {total['ok']}  |  WARN {total['warn']}  |  FAIL {total['fail']}", ""]
    lines += ["## Failing documents (excluded from LightRAG and from LLM prompts)", ""]
    any_fail = False
    for region, checks in results.items():
        for c in checks:
            if c.status == "fail":
                any_fail = True
                lines.append(f"- **{region}** `{c.doc_id}` {c.agency}: {'; '.join(c.issues)}")
    if not any_fail:
        lines.append("- none")
    lines += ["", "## Per region", "", "| Region | docs | OK | WARN | FAIL | recall |", "|---|---|---|---|---|---|"]
    for region, checks in results.items():
        n = {k: sum(1 for c in checks if c.status == k) for k in total}
        rc = ""
        if recall and region in recall and recall[region].get("probes"):
            rc = f"{recall[region]['hits']}/{recall[region]['probes']}"
        lines.append(f"| {region} | {len(checks)} | {n['ok']} | {n['warn']} | {n['fail']} | {rc} |")
    lines += ["", "## Warnings", ""]
    for region, checks in results.items():
        for c in checks:
            if c.status == "warn":
                lines.append(f"- {region} `{c.doc_id}` {c.agency}: {'; '.join(c.issues)}")
    return "\n".join(lines) + "\n"


def write_report(results: dict[str, list[DocCheck]], out_dir: Path, recall: Optional[dict] = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "verification.json").write_text(
        json.dumps(
            {r: [asdict(c) for c in cs] for r, cs in results.items()}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    md = out_dir / "verification.md"
    md.write_text(render_markdown(results, recall), encoding="utf-8")
    return md
