"""Batch download all regulation PDFs for 32 countries + all MDCG guidance documents.

Usage:
    python scripts/download_all_regulation_pdfs.py [--mdcg-only] [--regs-only] [--force]

Downloads PDFs, extracts full text via PyMuPDF, writes per-document markdown files,
then merges them into the corresponding regulation check files.
"""
import os
import re
import sys
import time
import warnings
import argparse
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
import fitz  # PyMuPDF

warnings.filterwarnings("ignore")

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "docs" / "regulations_check"
FULL_TEXT_DIR = ROOT / "docs" / "regulations_check" / "full_texts"
FULL_TEXT_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
})

# ── known PDF targets ────────────────────────────────────────────────────────
# Format: (region_key, agency_key, display_name, pdf_url, extra_headers)
REGULATION_PDFS = [
    ("巴西 (Brazil)", "ANVISA-RDC665",
     "ANVISA RDC 665/2022 — GMP for Medical Devices (English)",
     "https://www.gov.br/anvisa/en/regulation-of-companies/arquivos/rdc-665-2022-english-version.pdf",
     {}),
    ("印度 (India)", "CDSCO-MDR2017",
     "India Medical Devices Rules 2017 (CDSCO)",
     "https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/m_device/Medical%20Devices%20Rules,%202017.pdf",
     {}),
    ("新加坡 (Singapore)", "SSO-HPR-2010-PDF",
     "Singapore HP(MD)R 2010 — Full Text PDF (SSO)",
     "https://sso.agc.gov.sg/SL/HPA2007-S436-2010?DocDate=20231211&ViewType=Pdf",
     {"Referer": "https://sso.agc.gov.sg/SL/HPA2007-S436-2010"}),
    ("沙烏地阿拉伯 (Saudi Arabia)", "SFDA-MDS-G024",
     "SFDA MDS-G024 — QMS Requirements Guidance",
     "https://www.sfda.gov.sa/sites/default/files/2025-03/MDS-G024.pdf",
     {}),
    ("墨西哥 (Mexico)", "NOM241-EN",
     "NOM-241-SSA1-2021 — GMP for Medical Devices (English Translation)",
     "https://www.interamericancoalition-medtech.org/regulatory-convergence/wp-content/uploads/sites/4/2022/03/Norma-Oficial-Mexicana-NOM-241-SSA1-2021-ENG-REV.pdf",
     {}),
    ("土耳其 (Turkey)", "Resmigazete-TibbCihaz",
     "Turkey Medical Device Regulation 2021 — Official Gazette PDF (Turkish)",
     "https://www.resmigazete.gov.tr/eskiler/2021/06/20210602M1-2.pdf",
     {}),
    ("馬來西亞 (Malaysia)", "Act737-PDF",
     "Malaysia Medical Device Act 737 (2012) — Full Text PDF",
     "https://www.ummc.edu.my/files/ethic/Medical%20Device%20Act%202012.pdf",
     {}),
    ("菲律賓 (Philippines)", "RA9711-PDF",
     "Philippines RA 9711 — FDA Act of 2009 Full Text PDF",
     "https://www.fda.gov.ph/wp-content/uploads/2021/04/Republic-Act-No.-9711.pdf",
     {}),
    ("越南 (Vietnam)", "VBHN-BYT-2024",
     "Vietnam Medical Device Law — Consolidated VBHN-BYT 2024 PDF",
     "https://static3.luatvietnam.vn/uploaded/vietlawfile/2024/7/04_vbhn_byt_2024_incom_010724105049.pdf",
     {}),
    ("埃及 (Egypt)", "EDA-Guideline",
     "Egypt EDA Regulatory Guideline for Medical Device Registration (English)",
     "https://edaegypt.gov.eg/media/j3hdl0l2/5_regulatory-guideline-for-procedures-of-registering-imported-and-local-medical-devices-holding-international-quali.pdf",
     {}),
    ("阿聯酋 (UAE)", "FDL38-2024-PDF",
     "UAE Federal Decree-Law No. 38 of 2024 — Medical Products",
     "https://uaelegislation.gov.ae/en/legislations/2751/download",
     {}),
]

# ── MDCG guidance page ────────────────────────────────────────────────────────
MDCG_INDEX_URL = "https://health.ec.europa.eu/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents-and-other-guidance_en"
MDCG_BASE = "https://health.ec.europa.eu"
MDCG_OUT_DIR = FULL_TEXT_DIR / "MDCG"
MDCG_OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── helpers ───────────────────────────────────────────────────────────────────
def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)[:120]


def download_bytes(url: str, extra_headers: dict = None, timeout: int = 60) -> bytes | None:
    headers = dict(SESSION.headers)
    if extra_headers:
        headers.update(extra_headers)
    try:
        try:
            r = SESSION.get(url, headers=headers, verify=True, timeout=timeout, stream=True)
        except requests.exceptions.SSLError:
            print(f"  [warn] TLS verification failed, retrying without verify: {url[:80]}")
            r = SESSION.get(url, headers=headers, verify=False, timeout=timeout, stream=True)
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "")
        data = r.content
        if len(data) < 100:
            print(f"  [warn] Too small ({len(data)} bytes): {url}")
            return None
        # Quick PDF check
        if data[:4] != b"%PDF" and b"%PDF" not in data[:1024]:
            print(f"  [warn] Not a PDF ({ct}): {url[:80]}")
            return None
        return data
    except Exception as e:
        print(f"  [error] {type(e).__name__}: {e} → {url[:80]}")
        return None


def pdf_bytes_to_markdown(pdf_bytes: bytes, display_name: str, source_url: str) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        n = len(doc)
        lines = [
            f"# {display_name}\n",
            f"\n**Source**: {source_url}  \n**Pages**: {n}\n\n---\n",
        ]
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                lines.append(f"\n---\n<!-- Page {i+1}/{n} -->\n\n{text}\n")
        doc.close()
        return "\n".join(lines)
    except Exception as e:
        return f"# {display_name}\n\n**Error extracting text**: {e}\n\n**Source**: {source_url}\n"


def pdf_bytes_to_markdown_docling(pdf_bytes: bytes, display_name: str, source_url: str) -> str:
    """OCR fallback for scanned PDFs using Docling (slow, for offline batch use only)."""
    import os, tempfile, sys
    sys.path.insert(0, str(ROOT))
    try:
        from src.ocr.docling_engine import get_engine
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp = f.name
        print(f"  [docling] OCR starting ({len(pdf_bytes)//1024} KB)…")
        res = get_engine().parse(tmp, force_engine="docling")
        os.unlink(tmp)
        if res.success and res.markdown and len(res.markdown.strip()) > 100:
            header = (
                f"# {display_name}\n\n"
                f"**Source**: {source_url}  \n"
                f"**Pages**: {res.page_count} (OCR via Docling)\n\n---\n\n"
            )
            print(f"  [docling] OCR done — {res.page_count} pages, {len(res.markdown)//1024} KB")
            return header + res.markdown
        print(f"  [docling] OCR returned no content")
    except Exception as e:
        print(f"  [docling] Error: {e}")
    return ""


def write_markdown(path: Path, content: str):
    path.write_text(content, encoding="utf-8")
    kb = path.stat().st_size // 1024
    print(f"  [write] {path.name} ({kb} KB)")


# ── merge into main check file ───────────────────────────────────────────────
def merge_into_check_file(region_key: str, supplement_path: Path):
    region_slug = re.sub(r'[^\w一-鿿]+', "_", region_key).strip("_")
    # Try common name patterns
    for pattern in [f"{region_slug}.md", f"{region_key}.md"]:
        base = OUT_DIR / pattern
        if base.exists():
            break
    else:
        # Find by scanning
        matches = list(OUT_DIR.glob(f"*{region_slug}*.md"))
        matches = [m for m in matches if "full_text" not in m.name and "MDCG" not in m.name]
        if not matches:
            return
        base = matches[0]

    content = base.read_text(encoding="utf-8")
    MARKER = "\n\n---\n<!-- FULL TEXT SUPPLEMENT:"
    # Remove previous merge for this supplement
    supp_marker = f"{MARKER} {supplement_path.name} -->"
    if supp_marker in content:
        idx = content.index(supp_marker)
        next_supp = content.find(MARKER, idx + 1)
        content = content[:idx] + (content[next_supp:] if next_supp > 0 else "")

    supplement_text = supplement_path.read_text(encoding="utf-8")
    content = content.rstrip() + f"\n\n---\n<!-- FULL TEXT SUPPLEMENT: {supplement_path.name} -->\n\n" + supplement_text

    base.write_text(content, encoding="utf-8")
    kb = base.stat().st_size // 1024
    print(f"  [merge] → {base.name} ({kb} KB)")


# ── download all regulation PDFs ─────────────────────────────────────────────
_SCANNED_THRESHOLD = 500  # bytes: full_text files smaller than this are treated as scanned/empty


def run_regulation_pdfs(force: bool = False, country_filter: str = ""):
    print("\n=== Downloading Regulation PDFs ===")
    for region_key, agency_key, display_name, url, extra_h in REGULATION_PDFS:
        if country_filter and country_filter.lower() not in region_key.lower():
            continue
        out_name = safe_filename(f"{region_key}__{agency_key}_full_text") + ".md"
        out_path = FULL_TEXT_DIR / out_name

        # Skip if file exists AND is not essentially empty (scanned → tiny file)
        if out_path.exists() and not force:
            if out_path.stat().st_size >= _SCANNED_THRESHOLD:
                print(f"  [skip] {out_name} already exists")
                merge_into_check_file(region_key, out_path)
                continue
            # File exists but is empty/scanned — re-try with docling
            print(f"  [retry-docling] {out_name} appears scanned ({out_path.stat().st_size}B)")
            data = download_bytes(url, extra_headers=extra_h)
            if not data:
                continue
            md = pdf_bytes_to_markdown_docling(data, display_name, url)
            if md:
                write_markdown(out_path, md)
                merge_into_check_file(region_key, out_path)
            time.sleep(1)
            continue

        print(f"\n[{region_key}] {display_name}")
        data = download_bytes(url, extra_headers=extra_h)
        if not data:
            continue
        md = pdf_bytes_to_markdown(data, display_name, url)
        # Fallback to docling if fitz extracted no meaningful text (scanned PDF)
        if len(md.strip()) < _SCANNED_THRESHOLD:
            print(f"  [fitz] No text layer detected — trying Docling OCR")
            md_docling = pdf_bytes_to_markdown_docling(data, display_name, url)
            if md_docling:
                md = md_docling
        write_markdown(out_path, md)
        merge_into_check_file(region_key, out_path)
        time.sleep(1)


# ── MDCG: discover and download all guidance PDFs ────────────────────────────
def _get_mdcg_pdf_links() -> list[tuple[str, str]]:
    """Scrape the MDCG guidance index page and return [(title, pdf_url)] pairs."""
    print(f"\n[MDCG] Fetching guidance index: {MDCG_INDEX_URL}")
    try:
        try:
            r = SESSION.get(MDCG_INDEX_URL, verify=True, timeout=30)
        except requests.exceptions.SSLError:
            r = SESSION.get(MDCG_INDEX_URL, verify=False, timeout=30)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"  [error] Cannot fetch MDCG index: {e}")
        return []

    # Find PDF links — pattern: href="...mdcg_*.pdf" or href="...system/files/...pdf"
    raw = re.findall(r'href="([^"]+\.pdf)"[^>]*>([^<]+)<', html)
    if not raw:
        # Try broader pattern
        raw_urls = re.findall(r'href="([^"]*(?:system/files|mdcg)[^"]*\.pdf)"', html)
        raw = [(u, Path(urlparse(u).path).stem) for u in raw_urls]

    links = []
    for href, label in raw:
        if not href.startswith("http"):
            href = urljoin(MDCG_BASE, href)
        title = label.strip()[:100] or Path(urlparse(href).path).stem
        links.append((title, href))

    print(f"  [found] {len(links)} PDF links")
    return links


def run_mdcg_pdfs(force: bool = False):
    print("\n=== Downloading MDCG Guidance PDFs ===")
    links = _get_mdcg_pdf_links()
    if not links:
        print("  [warn] No MDCG PDF links found — check if the page structure changed")
        return

    ok, skip, fail = 0, 0, 0
    for title, url in links:
        stem = safe_filename(Path(urlparse(url).path).stem or title)
        out_path = MDCG_OUT_DIR / f"{stem}.md"
        if out_path.exists() and not force:
            skip += 1
            continue

        print(f"  [get] {stem[:60]}")
        data = download_bytes(url)
        if not data:
            fail += 1
            time.sleep(0.5)
            continue
        md = pdf_bytes_to_markdown(data, title, url)
        write_markdown(out_path, md)
        ok += 1
        time.sleep(0.8)

    # Write combined MDCG index markdown
    _write_mdcg_combined()
    print(f"\n[MDCG] Done: {ok} downloaded, {skip} skipped, {fail} failed")


def _write_mdcg_combined():
    """Merge all MDCG individual files into one combined MDCG markdown for the EU check file."""
    files = sorted(MDCG_OUT_DIR.glob("*.md"))
    if not files:
        return
    combined = ["# MDCG Guidance Documents — All Downloads\n\n"]
    for f in files:
        combined.append(f.read_text(encoding="utf-8"))
        combined.append("\n\n")
    combined_path = FULL_TEXT_DIR / "歐盟 (EU)__MDCG_all_guidance_full_text.md"
    combined_path.write_text("\n".join(combined), encoding="utf-8")
    kb = combined_path.stat().st_size // 1024
    print(f"  [combined] MDCG combined → {combined_path.name} ({kb} KB)")
    merge_into_check_file("歐盟 (EU)", combined_path)


# ── entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mdcg-only", action="store_true")
    parser.add_argument("--regs-only", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    parser.add_argument("--country", default="", help="Filter by country name substring (e.g. 'Turkey')")
    args = parser.parse_args()

    if not args.mdcg_only:
        run_regulation_pdfs(force=args.force, country_filter=args.country)
    if not args.regs_only:
        run_mdcg_pdfs(force=args.force)

    print("\n=== All done ===")


if __name__ == "__main__":
    main()
