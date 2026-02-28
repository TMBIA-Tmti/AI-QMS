"""One-time script: Extract I18N and COMMANDS dicts from i18n.py into JSON files."""

import sys
import json
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.chainlit_app.i18n import I18N, COMMANDS, SUPPORTED_LANGUAGES, LANG_CODE_MAP

LOCALES_DIR = PROJECT_ROOT / "src" / "chainlit_app" / "locales"
LOCALES_DIR.mkdir(parents=True, exist_ok=True)

# Extract each language's translations + commands into a single JSON
for lang_code, translations in I18N.items():
    data = dict(translations)  # copy
    # Merge commands into the same JSON under cmd.* keys
    if lang_code in COMMANDS:
        for cmd_key, keywords in COMMANDS[lang_code].items():
            data[f"_commands.{cmd_key}"] = keywords

    out_path = LOCALES_DIR / f"{lang_code}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    key_count = len([k for k in data if not k.startswith("_commands.")])
    cmd_count = len([k for k in data if k.startswith("_commands.")])
    print(
        f"  {lang_code}: {key_count} translations + {cmd_count} commands -> {out_path.name}"
    )

print(f"\nDone! {len(I18N)} language files written to {LOCALES_DIR}")
print(f"SUPPORTED_LANGUAGES: {len(SUPPORTED_LANGUAGES)} entries")
print(f"LANG_CODE_MAP: {len(LANG_CODE_MAP)} entries")
