"""Download EU MDR 2017/745 full text and write to markdown.

Source priority:
  1. EUR-Lex CELLAR via SPARQL   — latest consolidated (e.g. 02017R0745-20250110)
  2. legislation.gov.uk           — latest revised PDF  (up to 2020-04-24)
  3. medical-device-regulation.eu — 2017 original adopted text (fallback)

Validation (3 layers):
  Layer 1 — network  : HTTP success, non-empty response
  Layer 2 — content  : magic bytes %PDF, size > 500 KB
  Layer 3 — structure: PyMuPDF extracts > 50 K chars, Article hits >= 80
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
ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "docs" / "regulations_check"
OUTPUT_FILE = OUTPUT_DIR / "歐盟__EU__MDR_2017_745_OJ_full_text.md"

# ── thresholds ─────────────────────────────────────────────────────────────────
MIN_PDF_BYTES = 500_000   # MDR PDF should be ~1.5–2 MB
MIN_CHARS     = 50_000    # extracted text chars
MIN_ARTICLES  = 80        # "Article N" regex hits

# ── source URLs ────────────────────────────────────────────────────────────────
SPARQL_ENDPOINT  = "https://publications.europa.eu/webapi/rdf/sparql"
CELLAR_CELEX_RE  = r"02017R0745-(\d{8})"   # consolidated version pattern

# Hardcoded CELLAR DOC_1 URLs — used when SPARQL endpoint is blocked/unavailable.
# Update by running this script successfully and noting the printed CELEX + URL.
# Newest version first.
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

LEGUK_INDEX      = "https://www.legislation.gov.uk/eur/2017/745"
LEGUK_FALLBACK   = "https://www.legislation.gov.uk/eur/2017/745/pdfs/eur_20170745_2020-04-24_en.pdf"

# NOTE: medical-device-regulation.eu is now CAPTCHA-protected and will likely fail.
# Kept as last resort in case Cloudflare protection is lifted.
MDR_EU_PDF       = (
    "https://www.medical-device-regulation.eu/wp-content/uploads"
    "/2019/05/CELEX_32017R0745_EN_TXT.pdf"
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; regulatory-crawler/1.0)",
    "Accept": "application/pdf,*/*",
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
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
        hits = len(re.findall(r"Article\s+\d+", full_text))
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
# Source 1 — EUR-Lex CELLAR via SPARQL
# ══════════════════════════════════════════════════════════════════════════════

def _cellar_get_download_url() -> tuple[str, str] | None:
    """
    Query SPARQL for all consolidated MDR versions, try newest → oldest,
    return (download_url, celex) for the first with a valid ENG PDF.
    """
    print("  Querying SPARQL for consolidated versions...")
    try:
        bindings = _sparql_query("""
            PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
            SELECT ?work ?celex WHERE {
              ?work cdm:resource_legal_id_celex ?celex .
              FILTER(CONTAINS(STR(?celex), "02017R0745-"))
            }
        """)
    except Exception as exc:
        print(f"  [err] SPARQL failed: {exc}")
        return None

    versions: list[tuple[str, str, str]] = []
    for b in bindings:
        celex = b.get("celex", {}).get("value", "")
        work  = b.get("work",  {}).get("value", "")
        m = re.match(CELLAR_CELEX_RE, celex)
        if m:
            versions.append((m.group(1), celex, work))
    versions.sort(reverse=True)   # newest date first

    if not versions:
        print("  [warn] No consolidated versions found")
        return None

    print(f"  Found {len(versions)} consolidated versions, trying newest first...")

    for date, celex, work_uri in versions:
        try:
            # Get ENG pdfa2a manifestation URI
            manif_rows = _sparql_query(f"""
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
            if not manif_rows:
                print(f"    {celex}: no ENG PDF manifestation, skip")
                continue

            manif_uri = manif_rows[0]["manif"]["value"]
            download_url = manif_uri + "/DOC_1"
            print(f"    {celex}: {download_url[:90]}")
            return download_url, celex

        except Exception as exc:
            print(f"    {celex}: {type(exc).__name__}: {exc}, skip")
            continue

    return None


def _try_known_cellar_urls() -> tuple[bytes, str, str] | None:
    """Try hardcoded CELLAR DOC_1 URLs — no SPARQL needed."""
    for url, celex in CELLAR_KNOWN_URLS:
        label = f"CELLAR {celex} (hardcoded)"
        data = _download(url, label, timeout=120)
        if data and _validate(data, label):
            return data, celex, f"EUR-Lex CELLAR (hardcoded) — CELEX {celex}"
    return None


def fetch_cellar() -> tuple[bytes, str, str] | None:
    print("\n[source 1] EUR-Lex CELLAR (SPARQL + hardcoded fallback)")

    # 1a: Dynamic SPARQL — finds latest consolidated version automatically
    sparql_result = _cellar_get_download_url()
    if sparql_result:
        url, celex = sparql_result
        data = _download(url, f"CELLAR {celex}", timeout=120)
        if data and _validate(data, f"CELLAR {celex}"):
            return data, celex, f"EUR-Lex CELLAR SPARQL — CELEX {celex}"
        print("  SPARQL URL downloaded but validation failed — trying hardcoded URLs...")
    else:
        print("  SPARQL unavailable/blocked — trying hardcoded CELLAR DOC_1 URLs...")

    # 1b: Hardcoded fallback — works when SPARQL endpoint is blocked on this network
    return _try_known_cellar_urls()


# ══════════════════════════════════════════════════════════════════════════════
# Source 2 — legislation.gov.uk
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
        # Find revised PDF links: eur_20170745_YYYY-MM-DD_en.pdf
        matches = re.findall(
            r'href="(https://www\.legislation\.gov\.uk/eur/2017/745/pdfs/'
            r'eur_\d+_(\d{4}-\d{2}-\d{2})_en\.pdf)"',
            html,
        )
        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            pdf_url, version = matches[0]
            print(f"  Auto-detected latest: {version}")
    except Exception as exc:
        print(f"  [warn] index parse failed: {exc}")

    if not pdf_url:
        print("  Falling back to hardcoded 2020-04-24 URL")
        pdf_url, version = LEGUK_FALLBACK, "2020-04-24"

    label = f"legislation.gov.uk {version}"
    data = _download(pdf_url, label)
    if data and _validate(data, label):
        return data, version, f"legislation.gov.uk (EU MDR — {version})"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Source 3 — medical-device-regulation.eu
# ══════════════════════════════════════════════════════════════════════════════

def fetch_mdr_eu() -> tuple[bytes, str, str] | None:
    print("\n[source 3] medical-device-regulation.eu (2017 original)")
    label = "medical-device-regulation.eu"
    data = _download(MDR_EU_PDF, label)
    if data and _validate(data, label):
        return data, "2017-original", "medical-device-regulation.eu (2017 adopted)"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PDF → Markdown
# ══════════════════════════════════════════════════════════════════════════════

def pdf_to_markdown(data: bytes, source_label: str, version: str) -> str:
    doc = fitz.open(stream=data, filetype="pdf")
    n = len(doc)
    header = (
        "# Regulation (EU) 2017/745 — EU Medical Device Regulation (MDR) Full Text\n\n"
        f"**Citation**: Regulation (EU) 2017/745 of the European Parliament and of the Council of 5 April 2017  \n"
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
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = (
        fetch_cellar()
        or fetch_legislation_gov_uk()
        or fetch_mdr_eu()
    )

    if result is None:
        print("\n[FAIL] All three sources exhausted — cannot download MDR PDF.")
        sys.exit(1)

    data, version, label = result
    print(f"\n[ok] Source: {label}")

    print("[convert] PDF → Markdown...")
    md = pdf_to_markdown(data, label, version)

    OUTPUT_FILE.write_text(md, encoding="utf-8")
    kb = OUTPUT_FILE.stat().st_size // 1024
    print(f"[write] {OUTPUT_FILE.name} ({kb} KB)")
    print("[done]")


if __name__ == "__main__":
    main()
