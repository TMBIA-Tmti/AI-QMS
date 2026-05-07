"""Download Korea K-GMP Regulations (Feb 2026) full text from MFDS PDF and write to markdown."""
import os
import io
import requests
import warnings
import fitz  # PyMuPDF

warnings.filterwarnings("ignore")  # suppress InsecureRequestWarning

PDF_URL = "https://www.mfds.go.kr/eng/brd/m_40/down.do?brd_id=eng0011&seq=72638&data_tp=A&file_seq=1"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "regulations_check")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "韓國__Korea__KGMP_full_text.md")
TEMP_PDF = os.path.join(os.path.dirname(__file__), "_kgmp_temp.pdf")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.mfds.go.kr/eng/brd/m_40/view.do?seq=72638",
    "Accept": "application/pdf,application/octet-stream,*/*",
}


def download_pdf():
    print("[download] Downloading K-GMP PDF from MFDS ...")
    try:
        r = requests.get(PDF_URL, headers=HEADERS, verify=True, timeout=60, stream=True)
    except requests.exceptions.SSLError:
        print("[warn] TLS verification failed for MFDS, retrying without verify")
        r = requests.get(PDF_URL, headers=HEADERS, verify=False, timeout=60, stream=True)
    r.raise_for_status()
    with open(TEMP_PDF, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    size_kb = os.path.getsize(TEMP_PDF) // 1024
    print(f"[download] Saved {size_kb} KB → {TEMP_PDF}")


def extract_text():
    doc = fitz.open(TEMP_PDF)
    total = len(doc)
    print(f"[extract] {total} pages")
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        pages.append(text)
        if (i + 1) % 50 == 0:
            print(f"[extract] {i+1}/{total} pages done")
    doc.close()
    return pages


def write_markdown(pages):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    header = (
        "# Korea Medical Device GMP Regulations (의료기기 GMP 규정집) — Full Text\n\n"
        "**Authority**: Ministry of Food and Drug Safety (MFDS), Republic of Korea  \n"
        "**Edition**: February 2026 (latest consolidated compilation)  \n"
        "**Source PDF**: https://www.mfds.go.kr/eng/brd/m_40/down.do?brd_id=eng0011&seq=72638&data_tp=A&file_seq=1  \n"
        "\n"
        "## Contents\n\n"
        "1. Enforcement Rule of the Medical Devices Act (pp. 1–177)\n"
        "2. Standards of GMP for Medical Devices (pp. 178–298)\n"
        "3. Standards of GMP for In Vitro Diagnostic Medical Devices (pp. 299–396)\n"
        "4. Standards of GMP for Digital Medical Devices (pp. 397–501)\n"
        "\n---\n\n"
    )
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        for i, text in enumerate(pages):
            f.write(f"\n---\n<!-- Page {i+1} -->\n\n")
            f.write(text)
            f.write("\n")
    size_kb = os.path.getsize(OUTPUT_FILE) // 1024
    print(f"[write] Written {len(pages)} pages → {OUTPUT_FILE} ({size_kb} KB)")


def main():
    try:
        download_pdf()
        pages = extract_text()
        write_markdown(pages)
    finally:
        if os.path.exists(TEMP_PDF):
            os.remove(TEMP_PDF)
            print("[cleanup] Temp PDF removed")


if __name__ == "__main__":
    main()
