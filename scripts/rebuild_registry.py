"""
Rebuild document_registry.json from existing .md files in markdown_storage/documents/.

Run from the AI-QMS-test root directory:
    python scripts/rebuild_registry.py

Each .md file has YAML frontmatter with doc_id, title, doc_type, etc.
This script reconstructs the registry that was corrupted/reset.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

BASE_PATH = Path("markdown_storage")
DOCUMENTS_PATH = BASE_PATH / "documents"
METADATA_PATH = BASE_PATH / "metadata"
REGISTRY_FILE = METADATA_PATH / "document_registry.json"


def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter between --- delimiters."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    front = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # Parse lists like [FORM, ocr-auto]
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip() for v in val[1:-1].split(",")]
            # Parse floats
            try:
                val = float(val)
            except (ValueError, TypeError):
                pass
            front[key] = val
    return front


def version_from_path(path: Path) -> str:
    """Extract version string from filename like FM-410-01_v1.0.md → v1.0."""
    m = re.search(r"_(v[\d.]+)\.md$", path.name, re.IGNORECASE)
    return m.group(1) if m else "v1.0"


def rebuild():
    if not DOCUMENTS_PATH.exists():
        print(f"ERROR: {DOCUMENTS_PATH} does not exist", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(DOCUMENTS_PATH.rglob("*.md"))
    print(f"Found {len(md_files)} .md files to process")

    # Group files by doc_id so multiple versions collapse into one entry
    doc_map: dict[str, dict] = {}
    skipped = 0

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)

        doc_id = fm.get("doc_id", "")
        if not doc_id:
            doc_id = md_path.stem.split("_")[0] if "_" in md_path.stem else md_path.stem
        doc_id = str(doc_id)

        title = fm.get("title", md_path.stem)
        doc_type = fm.get("doc_type") or md_path.parent.name
        if doc_type not in ("SOP", "WI", "FORM", "DHF", "OTHER"):
            doc_type = "OTHER"

        created_at = fm.get("created_at", datetime.now().isoformat())
        ocr_provider = fm.get("ocr_provider", "unknown")
        ocr_confidence = fm.get("ocr_confidence", 1.0)
        source_file = fm.get("source_file", md_path.name)
        content_hash = fm.get("source_sha256", "")

        version = version_from_path(md_path)
        rel_path = str(md_path.relative_to(BASE_PATH))

        version_entry = {
            "version": version,
            "markdown_path": rel_path,
            "original_file": str(source_file),
            "created_at": str(created_at),
            "created_by": "system",
            "ocr_provider": str(ocr_provider),
            "ocr_confidence": float(ocr_confidence) if ocr_confidence else 1.0,
            "hash": str(content_hash),
        }

        if doc_id not in doc_map:
            doc_map[doc_id] = {
                "doc_id": doc_id,
                "title": str(title),
                "current_version": version,
                "versions": [version_entry],
                "doc_type": doc_type,
                "status": "active",
                "related_documents": [],
            }
            print(f"  + {doc_id} ({doc_type}) {version}")
        else:
            # Add new version; keep the latest as current
            doc_map[doc_id]["versions"].append(version_entry)
            doc_map[doc_id]["current_version"] = version
            doc_map[doc_id]["title"] = str(title)  # use latest title
            print(f"    ↳ {doc_id} added version {version}")

    docs = list(doc_map.values())

    registry = {
        "registry_version": "1.0",
        "last_updated": datetime.now().isoformat(),
        "document_count": len(docs),
        "documents": docs,
    }

    METADATA_PATH.mkdir(parents=True, exist_ok=True)

    # Backup existing registry if non-empty
    if REGISTRY_FILE.exists() and REGISTRY_FILE.stat().st_size > 50:
        backup = REGISTRY_FILE.with_suffix(".json.bak")
        backup.write_bytes(REGISTRY_FILE.read_bytes())
        print(f"Backed up existing registry to {backup}")

    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Registry rebuilt: {len(docs)} documents written to {REGISTRY_FILE}")
    if skipped:
        print(f"   ⚠ Skipped {skipped} files (no doc_id found)")


if __name__ == "__main__":
    rebuild()
