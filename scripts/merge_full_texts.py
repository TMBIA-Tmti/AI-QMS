"""Merge full-text supplement files into their corresponding regulation check files.

For each region that has a *_full_text.md file, append its content as a new section
into the main regulation check file (overwrites in-place).

Run after export_all_regulations_md.py and after any download_*_full_text.py scripts.
"""
import os
import glob

CHECK_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "regulations_check")

# Map: base check file → list of full-text supplement files to append (in order)
# Paths under CHECK_DIR; use "full_texts/..." for files in that subdirectory.
MERGES = {
    "韓國__Korea_.md": ["韓國__Korea__KGMP_full_text.md"],
    "歐盟__EU_.md": ["歐盟__EU__MDR_2017_745_OJ_full_text.md"],
    # Batch-downloaded PDFs → markdown (in full_texts/ subdirectory)
    "巴西__Brazil_.md": ["full_texts/巴西 (Brazil)__ANVISA-RDC665_full_text.md"],
    "印度__India_.md": ["full_texts/印度 (India)__CDSCO-MDR2017_full_text.md"],
    "新加坡__Singapore_.md": ["full_texts/新加坡 (Singapore)__SSO-HPR-2010-PDF_full_text.md"],
    "沙烏地阿拉伯__Saudi_Arabia_.md": ["full_texts/沙烏地阿拉伯 (Saudi Arabia)__SFDA-MDS-G024_full_text.md"],
    "墨西哥__Mexico_.md": ["full_texts/墨西哥 (Mexico)__NOM241-EN_full_text.md"],
    "土耳其__Turkey_.md": ["full_texts/土耳其 (Turkey)__Resmigazete-TibbCihaz_full_text.md"],
    "馬來西亞__Malaysia_.md": ["full_texts/馬來西亞 (Malaysia)__Act737-PDF_full_text.md"],
    "菲律賓__Philippines_.md": ["full_texts/菲律賓 (Philippines)__RA9711-PDF_full_text.md"],
    "越南__Vietnam_.md": ["full_texts/越南 (Vietnam)__VBHN-BYT-2024_full_text.md"],
    "埃及__Egypt_.md": ["full_texts/埃及 (Egypt)__EDA-Guideline_full_text.md"],
}


def merge_one(base_name: str, supplement_names: list[str]):
    base_path = os.path.join(CHECK_DIR, base_name)
    if not os.path.exists(base_path):
        print(f"[merge] SKIP — base not found: {base_name}")
        return

    with open(base_path, "r", encoding="utf-8") as f:
        base_content = f.read()

    supplements = []
    for sname in supplement_names:
        spath = os.path.join(CHECK_DIR, sname)
        if not os.path.exists(spath):
            print(f"[merge] SKIP supplement not found: {sname}")
            continue
        with open(spath, "r", encoding="utf-8") as f:
            supplements.append((sname, f.read()))
        print(f"[merge] Read supplement: {sname}")

    if not supplements:
        return

    # Strip any previously merged full-text sections (marked by our separator)
    MARKER = "\n\n---\n<!-- FULL TEXT SUPPLEMENT:"
    if MARKER in base_content:
        base_content = base_content[: base_content.index(MARKER)]

    with open(base_path, "w", encoding="utf-8") as f:
        f.write(base_content.rstrip())
        for sname, scontent in supplements:
            f.write(f"\n\n---\n<!-- FULL TEXT SUPPLEMENT: {sname} -->\n\n")
            f.write(scontent)

    size_kb = os.path.getsize(base_path) // 1024
    print(f"[merge] {base_name} → {size_kb} KB (merged {len(supplements)} supplement(s))")


def main():
    for base_name, snames in MERGES.items():
        merge_one(base_name, snames)
    print("[merge] Done.")


if __name__ == "__main__":
    main()
