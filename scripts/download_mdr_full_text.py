"""Download EU MDR 2017/745 full text from official PDF and write to markdown."""
import sys
import urllib.request
import os
import fitz  # PyMuPDF

PDF_URL = "https://www.legislation.gov.uk/eur/2017/745/pdfs/eur_20170745_adopted_en.pdf"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "regulations_check")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "歐盟__EU__MDR_2017_745_OJ_full_text.md")
TEMP_PDF = os.path.join(os.path.dirname(__file__), "_mdr_temp.pdf")


def download_pdf():
    print(f"[download] Downloading MDR PDF from legislation.gov.uk ...")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; regulatory-crawler/1.0)",
        "Accept": "application/pdf",
    }
    req = urllib.request.Request(PDF_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp, open(TEMP_PDF, "wb") as f:
        data = resp.read()
        f.write(data)
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
        if (i + 1) % 25 == 0:
            print(f"[extract] {i+1}/{total} pages done")

    doc.close()
    return pages


def write_markdown(pages):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    header = (
        "# Regulation (EU) 2017/745 — EU Medical Device Regulation (MDR) Full Text\n\n"
        "**Citation**: Regulation (EU) 2017/745 of the European Parliament and of the Council of 5 April 2017  \n"
        "**Published**: Official Journal of the European Union, L 117, 5.5.2017  \n"
        "**Full Application Date**: 26 May 2021  \n"
        "**Source PDF**: https://www.legislation.gov.uk/eur/2017/745/pdfs/eur_20170745_adopted_en.pdf  \n"
        "**Note**: This is the adopted (original) text. For consolidated/amended text see EUR-Lex CELEX:32017R0745  \n"
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
