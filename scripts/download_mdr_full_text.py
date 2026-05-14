"""Download EU MDR 2017/745 full text, convert to markdown, and save to
regulatory_markdown_storage so the LLM analysis pipeline can use it.

Source priority:
  1a. EUR-Lex CELLAR via SPARQL   — dynamic, always finds latest consolidated
                                    → on success: auto-saves URL to local cache
  1b. URL cache (.cellar_url_cache.json) — previously resolved URLs, newest first
  1c. CELLAR hardcoded DOC_1 URLs — static fallback (always valid, may be older)
  1d. CELEX date scan             — scans last 90 days for new versions, no SPARQL/UUID
  2.  legislation.gov.uk PDF      — latest revised (up to 2020-04-24)

Validation (3 layers):
  Layer 1 — network  : HTTP success, non-empty response
  Layer 2 — content  : magic bytes %PDF, size > 500 KB
  Layer 3 — structure: PyMuPDF extracts > 50 K chars, Article hits >= 80

Output:
  docs/regulations_check/歐盟__EU__MDR_2017_745_OJ_full_text.md  (raw reference)
  regulatory_markdown_storage/documents/歐盟__EU_/EUR-Lex-MDR-CELLAR_*.md  (LLM path)
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("[error] PyMuPDF not installed: pip install pymupdf")

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "docs" / "regulations_check"
OUTPUT_FILE = OUTPUT_DIR / "歐盟__EU__MDR_2017_745_OJ_full_text.md"

# ── thresholds ─────────────────────────────────────────────────────────────────
MIN_PDF_BYTES = 500_000
MIN_CHARS     = 50_000
MIN_ARTICLES  = 80

# ── CELLAR config ───────────────────────────────────────────────────────────────
SPARQL_ENDPOINT  = "https://publications.europa.eu/webapi/rdf/sparql"
CELLAR_CELEX_RE  = r"02017R0745-(\d{8})"

# Local URL cache — auto-written when SPARQL succeeds so other machines can use
# the latest resolved URL without needing SPARQL access.
CELLAR_URL_CACHE = Path(__file__).parent / ".cellar_url_cache.json"

# Hardcoded DOC_1 URLs — valid as long as CELLAR exists (never 404, just older version).
# Newest first.  Update automatically: a successful SPARQL run prints the new URL.
CELLAR_KNOWN_URLS: list[tuple[str, str]] = [
    (
        "http://publications.europa.eu/resource/cellar/"
        "fddb3266-f0ab-11f0-8d3c-01aa75ed71a1.0007.03/DOC_1",
        "02017R0745-20260101",
    ),
    (
        "http://publications.europa.eu/resource/cellar/"
        "c262459f-bcb4-11ef-91ed-01aa75ed71a1.0006.03/DOC_1",
        "02017R0745-20250110",
    ),
]

# CELEX-based URL (no UUID, no SPARQL) — stable chunk ID verified across versions.
# Pattern: 02017R0745-{YYYYMMDD}.ENG.pdfa2a.CL2017R0745EN0050010.0001.pdf
_CELLAR_CELEX_URL_TMPL = (
    "http://publications.europa.eu/resource/celex/"
    "02017R0745-{date}.ENG.pdfa2a.CL2017R0745EN0050010.0001.pdf"
)

# ── legislation.gov.uk ──────────────────────────────────────────────────────────
LEGUK_INDEX    = "https://www.legislation.gov.uk/eur/2017/745"
LEGUK_FALLBACK = "https://www.legislation.gov.uk/eur/2017/745/pdfs/eur_20170745_2020-04-24_en.pdf"

# ── storage agency keys ─────────────────────────────────────────────────────────
AGENCY_CELLAR = "EUR-Lex-MDR-CELLAR"
AGENCY_UK     = "EUR-Lex-MDR-UK"
REGION        = "歐盟 (EU)"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; regulatory-crawler/1.0)",
    "Accept": "application/pdf,*/*",
}


# ══════════════════════════════════════════════════════════════════════════════
# Core helpers
# ══════════════════════════════════════════════════════════════════════════════

def _download(url: str, label: str, timeout: int = 90) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        print(f"  [dl] {label}: {len(data) / 1024 / 1024:.2f} MB")
        return data
    except Exception as exc:
        print(f"  [err] {label}: {type(exc).__name__}: {exc}")
        return None


def _head_ok(url: str, timeout: int = 15) -> bool:
    """HEAD request — True if URL returns 200."""
    try:
        req = urllib.request.Request(url, headers=_HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _validate(data: bytes, label: str) -> bool:
    if not data or len(data) < MIN_PDF_BYTES:
        print(f"  [fail] {label}: too small ({len(data) if data else 0:,} B)")
        return False
    if data[:4] != b"%PDF":
        print(f"  [fail] {label}: not a PDF (magic={data[:4]})")
        return False
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        full_text = "".join(p.get_text("text") for p in doc)
        doc.close()
        chars = len(full_text)
        hits  = len(re.findall(r"Article\s+\d+", full_text))
        if chars < MIN_CHARS:
            print(f"  [fail] {label}: only {chars:,} chars (need {MIN_CHARS:,})")
            return False
        if hits < MIN_ARTICLES:
            print(f"  [fail] {label}: only {hits} Article hits (need {MIN_ARTICLES})")
            return False
    except Exception as exc:
        print(f"  [fail] {label}: PyMuPDF error: {exc}")
        return False
    return True


def _sparql_query(query: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "query": query,
        "format": "application/sparql-results+json",
    })
    req = urllib.request.Request(
        f"{SPARQL_ENDPOINT}?{params}",
        headers={"User-Agent": "Mozilla/5.0",
                 "Accept": "application/sparql-results+json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("results", {}).get("bindings", [])


# ══════════════════════════════════════════════════════════════════════════════
# URL cache — persists latest resolved CELLAR URL across runs / machines
# ══════════════════════════════════════════════════════════════════════════════

def _load_url_cache() -> list[tuple[str, str]]:
    """Load cached CELLAR URLs from .cellar_url_cache.json.

    Returns list of (doc1_url, celex) tuples, newest first.
    Returns [] if cache does not exist or is malformed.
    """
    try:
        if not CELLAR_URL_CACHE.exists():
            return []
        data = json.loads(CELLAR_URL_CACHE.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
        # Sort by celex date descending (newest first)
        entries.sort(key=lambda x: x.get("celex", ""), reverse=True)
        result = [(e["url"], e["celex"]) for e in entries if "url" in e and "celex" in e]
        if result:
            print(f"  [cache] Loaded {len(result)} URL(s) from {CELLAR_URL_CACHE.name}")
        return result
    except Exception as exc:
        print(f"  [cache] Could not load cache: {exc}")
        return []


def _save_url_cache(celex: str, url: str) -> None:
    """Persist a successfully resolved CELLAR URL to .cellar_url_cache.json.

    Keeps the 5 most recent entries.  Called automatically when SPARQL succeeds.
    """
    try:
        entries: list[dict] = []
        if CELLAR_URL_CACHE.exists():
            try:
                entries = json.loads(
                    CELLAR_URL_CACHE.read_text(encoding="utf-8")
                ).get("entries", [])
            except Exception:
                entries = []

        # Deduplicate by celex, insert/update
        entries = [e for e in entries if e.get("celex") != celex]
        entries.append({"celex": celex, "url": url, "saved": time.strftime("%Y-%m-%d")})
        # Keep newest 5 by celex date
        entries.sort(key=lambda x: x.get("celex", ""), reverse=True)
        entries = entries[:5]

        CELLAR_URL_CACHE.write_text(
            json.dumps({"entries": entries, "updated": time.strftime("%Y-%m-%d")},
                       indent=2),
            encoding="utf-8",
        )
        print(f"  [cache] Saved {celex} → {CELLAR_URL_CACHE.name}")
    except Exception as exc:
        print(f"  [cache] Could not save cache: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# CELEX date scan — finds new consolidated versions without SPARQL or UUID
# ══════════════════════════════════════════════════════════════════════════════

def _cellar_date_scan(days: int = 90) -> tuple[bytes, str, str] | None:
    """Scan the last `days` days for a new CELLAR consolidated version.

    Uses the UUID-free CELEX URL pattern.  Stops at the first valid PDF found.
    Saves newly found URL to cache automatically.
    """
    import datetime
    print(f"  [1d] CELEX date scan: checking last {days} days...")
    today = datetime.date.today()
    checked = 0
    for offset in range(days):
        d = (today - datetime.timedelta(days=offset)).strftime("%Y%m%d")
        celex = f"02017R0745-{d}"
        url = _CELLAR_CELEX_URL_TMPL.format(date=d)
        if not _head_ok(url, timeout=5):
            checked += 1
            continue
        # HEAD returned 200 — try full download + validate
        label = f"CELLAR date-scan {celex}"
        data = _download(url, label, timeout=120)
        if data and _validate(data, label):
            _save_url_cache(celex, url)
            return data, celex, f"EUR-Lex CELLAR (date-scan) — CELEX {celex}"
        checked += 1
    print(f"  [1d] Scanned {checked} dates, no valid version found")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CELLAR — step 1a: dynamic SPARQL
# ══════════════════════════════════════════════════════════════════════════════

def _cellar_sparql() -> tuple[str, str] | None:
    """Return (doc1_url, celex) for the newest ENG PDF via SPARQL, or None."""
    print("  [1a] SPARQL: querying consolidated versions...")
    try:
        bindings = _sparql_query("""
            PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
            SELECT ?work ?celex WHERE {
              ?work cdm:resource_legal_id_celex ?celex .
              FILTER(CONTAINS(STR(?celex), "02017R0745-"))
            }
        """)
    except Exception as exc:
        print(f"  [err] SPARQL: {exc}")
        return None

    versions: list[tuple[str, str, str]] = []
    for b in bindings:
        celex = b.get("celex", {}).get("value", "")
        work  = b.get("work",  {}).get("value", "")
        m = re.match(CELLAR_CELEX_RE, celex)
        if m:
            versions.append((m.group(1), celex, work))
    versions.sort(reverse=True)

    if not versions:
        print("  [warn] SPARQL: no consolidated versions found")
        return None

    print(f"  [1a] SPARQL: {len(versions)} versions, trying newest first...")
    for date, celex, work_uri in versions:
        try:
            rows = _sparql_query(f"""
                PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
                SELECT ?manif WHERE {{
                  VALUES ?work {{ <{work_uri}> }}
                  ?expr cdm:expression_belongs_to_work ?work ;
                        cdm:expression_uses_language
                            <http://publications.europa.eu/resource/authority/language/ENG> .
                  ?manif cdm:manifestation_manifests_expression ?expr ;
                         cdm:manifestation_type ?mime .
                  FILTER(CONTAINS(STR(?mime), "pdfa2a"))
                }}
            """)
            if not rows:
                continue
            url = rows[0]["manif"]["value"] + "/DOC_1"
            print(f"  [1a] SPARQL: resolved {celex} → {url[:80]}")
            _save_url_cache(celex, url)   # persist for SPARQL-blocked machines
            return url, celex
        except Exception as exc:
            print(f"    {celex}: {exc}, skipping")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CELLAR — step 1b: hardcoded DOC_1 URLs
# ══════════════════════════════════════════════════════════════════════════════

def _cellar_hardcoded() -> tuple[bytes, str, str] | None:
    """Try hardcoded CELLAR DOC_1 URLs (no SPARQL needed)."""
    for url, celex in CELLAR_KNOWN_URLS:
        # Quick HEAD check — hardcoded URLs should always be 200 on CELLAR
        if not _head_ok(url):
            print(f"  [1b] HEAD failed for {celex}, skipping")
            continue
        label = f"CELLAR {celex} (hardcoded)"
        data = _download(url, label, timeout=120)
        if data and _validate(data, label):
            return data, celex, f"EUR-Lex CELLAR (hardcoded) — CELEX {celex}"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CELLAR — step 1c: CELEX date URL (no UUID, no SPARQL)
# ══════════════════════════════════════════════════════════════════════════════

def _cellar_celex_url(celex: str) -> tuple[bytes, str, str] | None:
    """Try the CELEX-based stable URL pattern (avoids UUID dependency)."""
    date = celex.replace("02017R0745-", "")
    url = _CELLAR_CELEX_URL_TMPL.format(date=date)
    label = f"CELLAR celex-URL {celex}"
    data = _download(url, label, timeout=120)
    if data and _validate(data, label):
        return data, celex, f"EUR-Lex CELLAR (CELEX URL) — CELEX {celex}"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Combined CELLAR fetch (1a → 1b → 1c per known celex)
# ══════════════════════════════════════════════════════════════════════════════

def _try_url_list(
    url_list: list[tuple[str, str]], step_label: str
) -> tuple[bytes, str, str] | None:
    """Try each (url, celex) pair, return first valid result."""
    for url, celex in url_list:
        if not _head_ok(url, timeout=8):
            print(f"  [{step_label}] HEAD failed: {celex}, skip")
            continue
        label = f"CELLAR {celex} ({step_label})"
        data = _download(url, label, timeout=120)
        if data and _validate(data, label):
            return data, celex, f"EUR-Lex CELLAR ({step_label}) — CELEX {celex}"
    return None


def fetch_cellar() -> tuple[bytes, str, str] | None:
    print("\n[source 1] EUR-Lex CELLAR")

    # 1a: SPARQL — dynamic, always finds latest; auto-saves URL to cache on success
    sparql_result = _cellar_sparql()
    if sparql_result:
        url, celex = sparql_result
        data = _download(url, f"CELLAR {celex}", timeout=120)
        if data and _validate(data, f"CELLAR {celex}"):
            return data, celex, f"EUR-Lex CELLAR SPARQL — CELEX {celex}"
        print("  [1a] SPARQL download failed — continuing to cache...")
    else:
        print("  [1a] SPARQL unavailable/blocked — continuing to cache...")

    # 1b: URL cache — previously resolved URLs written by successful SPARQL runs
    #     Works across machines: copy .cellar_url_cache.json to share latest URL
    cached = _load_url_cache()
    if cached:
        result = _try_url_list(cached, "cache")
        if result:
            return result
        print("  [1b] All cached URLs failed — trying hardcoded...")
    else:
        print("  [1b] No cache found — trying hardcoded URLs...")

    # 1c: Hardcoded DOC_1 — static fallback, always valid (CELLAR never removes old versions)
    result = _cellar_hardcoded()
    if result:
        return result

    # 1d: CELEX date scan — scans last 90 days for new versions without SPARQL or UUID
    #     Catches newly published consolidated versions not yet in hardcoded list
    result = _cellar_date_scan(days=90)
    if result:
        return result

    print("  [fail] All CELLAR paths exhausted")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Source 2 — legislation.gov.uk PDF
# ══════════════════════════════════════════════════════════════════════════════

def fetch_legislation_gov_uk() -> tuple[bytes, str, str] | None:
    print("\n[source 2] legislation.gov.uk")
    pdf_url = None
    version = "unknown"

    try:
        req = urllib.request.Request(
            LEGUK_INDEX, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        matches = re.findall(
            r'href="(https://www\.legislation\.gov\.uk/eur/2017/745/pdfs/'
            r'eur_\d+_(\d{4}-\d{2}-\d{2})_en\.pdf)"',
            html,
        )
        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            pdf_url, version = matches[0]
            print(f"  Auto-detected: {version} — {pdf_url}")
    except Exception as exc:
        print(f"  [warn] index parse failed: {exc}")

    if not pdf_url:
        print("  Using hardcoded 2020-04-24 URL")
        pdf_url, version = LEGUK_FALLBACK, "2020-04-24"

    label = f"legislation.gov.uk {version}"
    data = _download(pdf_url, label)
    if data and _validate(data, label):
        return data, version, f"legislation.gov.uk (EU MDR — {version})"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PDF → Markdown
# ══════════════════════════════════════════════════════════════════════════════

def pdf_to_markdown(data: bytes, source_label: str, version: str) -> str:
    doc = fitz.open(stream=data, filetype="pdf")
    n = len(doc)
    header = (
        "# Regulation (EU) 2017/745 — EU Medical Device Regulation (MDR) Full Text\n\n"
        f"**Citation**: Regulation (EU) 2017/745 of the European Parliament "
        f"and of the Council of 5 April 2017  \n"
        f"**Source**: {source_label}  \n"
        f"**Version / CELEX**: {version}  \n"
        f"**Downloaded**: {time.strftime('%Y-%m-%d')}  \n"
        f"**Pages**: {n}  \n\n---\n\n"
    )
    parts = [header]
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        parts.append(f"\n---\n<!-- Page {i + 1}/{n} -->\n\n{text}\n")
        if (i + 1) % 50 == 0:
            print(f"  [convert] {i + 1}/{n} pages...")
    doc.close()
    return "".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Save to regulatory_markdown_storage (LLM path)
# ══════════════════════════════════════════════════════════════════════════════

def save_to_regulatory_storage(
    md_content: str,
    source_label: str,
    version: str,
    source_url: str,
    agency: str,
) -> None:
    """Save converted markdown to regulatory_markdown_storage so LLM can read it."""
    try:
        sys.path.insert(0, str(ROOT))
        from src.storage.regulatory_markdown_storage import get_regulatory_markdown_store

        store = get_regulatory_markdown_store()
        agency_name = (
            f"Regulation (EU) 2017/745 — EU MDR Full Text "
            f"({source_label}, {version})"
        )
        result = store.save_regulatory_document(
            region=REGION,
            agency=agency,
            agency_name=agency_name,
            title=f"EU MDR 2017/745 — {version}",
            url=source_url,
            markdown_content=md_content,
            note=f"Downloaded via download_mdr_full_text.py — {source_label}",
        )
        if result.get("success"):
            # Replace older versions of the same agency so LLM gets the fresh one
            store._replace_old_versions(REGION, agency, result["doc_id"])
            print(f"[storage] Saved → regulatory_markdown_storage: {Path(result['path']).name}")
        else:
            print(f"[storage] Save returned unexpected result: {result}")
    except Exception as exc:
        print(f"[storage] Warning: could not save to regulatory_markdown_storage: {exc}")
        print(f"[storage]   (LLM analysis will use previously stored version)")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = fetch_cellar() or fetch_legislation_gov_uk()

    if result is None:
        print("\n[FAIL] All sources exhausted — cannot download MDR PDF.")
        sys.exit(1)

    data, version, label = result
    print(f"\n[ok] Source: {label}")

    # Determine agency key and source URL
    is_cellar = "CELLAR" in label or "cellar" in label.lower()
    agency     = AGENCY_CELLAR if is_cellar else AGENCY_UK
    source_url = (
        CELLAR_KNOWN_URLS[0][0] if is_cellar
        else LEGUK_FALLBACK
    )

    print("[convert] PDF → Markdown...")
    md = pdf_to_markdown(data, label, version)

    # Write raw reference file (docs/regulations_check/)
    OUTPUT_FILE.write_text(md, encoding="utf-8")
    kb = OUTPUT_FILE.stat().st_size // 1024
    print(f"[write] {OUTPUT_FILE.name} ({kb} KB)")

    # Save to regulatory_markdown_storage (LLM analysis path)
    save_to_regulatory_storage(md, label, version, source_url, agency)

    print("[done]")


if __name__ == "__main__":
    main()
