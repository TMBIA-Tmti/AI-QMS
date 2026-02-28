"""Auto-translate missing i18n keys from zh-TW.json to all other languages.

Uses LiteLLM to translate. Reads zh-TW.json as master, finds missing keys
in each target language, and batch-translates them.

Usage:
    python scripts/auto_translate.py
    python scripts/auto_translate.py --provider openrouter --model anthropic/claude-sonnet-4.6 --api-key sk-or-v1-...
    python scripts/auto_translate.py --dry-run   # show what would be translated without calling LLM
"""

import sys
import json
import argparse
from pathlib import Path

# Add project root so we can import litellm if installed
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

LOCALES_DIR = PROJECT_ROOT / "src" / "chainlit_app" / "locales"

# Language display names for translation prompts
LANG_NAMES = {
    "en-US": "English",
    "ja-JP": "Japanese",
    "zh-CN": "Simplified Chinese",
    "ko-KR": "Korean",
    "fr-FR": "French",
    "de-DE": "German",
    "es-ES": "Spanish",
    "pt-BR": "Brazilian Portuguese",
    "it-IT": "Italian",
    "ru-RU": "Russian",
    "ar-SA": "Arabic",
    "hi-IN": "Hindi",
    "th-TH": "Thai",
    "vi-VN": "Vietnamese",
    "id-ID": "Indonesian",
    "ms-MY": "Malay",
    "tr-TR": "Turkish",
    "nl-NL": "Dutch",
    "pl-PL": "Polish",
}

# Terms that must NEVER be translated
DO_NOT_TRANSLATE = ["Eira", "TMBIA-Tmti", "AI-QMS", "ISO 13485", "QMS", "API Key"]


def find_missing_keys(master: dict, target: dict) -> dict:
    """Find keys present in master but missing in target (excluding _commands.* keys)."""
    missing = {}
    for key, value in master.items():
        if key.startswith("_commands."):
            continue  # commands are language-specific, not translated from master
        if key not in target:
            missing[key] = value
    return missing


def build_translate_prompt(missing: dict, target_lang: str) -> str:
    """Build the LLM prompt for translating missing keys."""
    keys_json = json.dumps(missing, ensure_ascii=False, indent=2)
    return f"""You are a professional translator specializing in medical device quality management systems.

Translate the following JSON key-value pairs from Traditional Chinese (zh-TW) to {target_lang}.

RULES:
1. Return ONLY a valid JSON object with the same keys and translated values.
2. Preserve ALL placeholders exactly as-is: {{name}}, {{count}}, {{provider}}, {{model}}, {{error}}, {{total}}, {{added}}, {{removed}}, {{doc_id}}, {{filename}}, {{version}}, {{old_ver}}, {{new_ver}}, {{limit}}, {{step}}, {{time}}, {{icon}}, {{detail}}, {{reason}}, {{hint}}, {{error_type}}, {{error_detail}}, {{msg}}, etc.
3. Preserve ALL markdown formatting: **, *, \\n, •, emojis (📋, ⚙️, 🔄, ✅, ❌, ⚠️, 💡, 📄, 🏥, etc.)
4. NEVER translate these terms — keep them exactly as-is: {", ".join(DO_NOT_TRANSLATE)}
5. Use natural, professional language appropriate for a medical device QMS interface.
6. "Eira" is a proper name (AI assistant) — always keep it as "Eira" in English letters.

JSON to translate:
{keys_json}"""


def translate_batch(missing: dict, target_lang: str, model: str, api_key: str) -> dict:
    """Translate a batch of missing keys using LiteLLM."""
    import litellm

    prompt = build_translate_prompt(missing, target_lang)

    response = litellm.completion(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a JSON translation engine. Return ONLY a raw JSON object. Do NOT wrap in markdown code blocks. No ```json, no ```. Just the raw JSON object.",
            },
            {"role": "user", "content": prompt},
        ],
        api_key=api_key,
        temperature=0.3,
        timeout=120,
    )

    content = response.choices[0].message.content.strip()
    # Strip markdown code blocks if present
    if content.startswith("```"):
        # Remove ```json\n ... \n```
        lines = content.split("\n")
        # Remove first line (```json) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        elif lines[0].startswith("```"):
            lines = lines[1:]
        content = "\n".join(lines)
    return json.loads(content)


def main():
    parser = argparse.ArgumentParser(description="Auto-translate missing i18n keys")
    parser.add_argument(
        "--provider", default="openrouter", help="LLM provider (default: openrouter)"
    )
    parser.add_argument(
        "--model", default="anthropic/claude-sonnet-4.6", help="Model name"
    )
    parser.add_argument(
        "--api-key", default="", help="API key (or set OPENROUTER_API_KEY env var)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be translated without calling LLM",
    )
    args = parser.parse_args()

    # Load master (zh-TW)
    master_path = LOCALES_DIR / "zh-TW.json"
    if not master_path.exists():
        print(f"ERROR: Master file not found: {master_path}")
        sys.exit(1)

    with open(master_path, "r", encoding="utf-8") as f:
        master = json.load(f)

    print(
        f"Master (zh-TW): {len([k for k in master if not k.startswith('_commands.')])} translation keys"
    )

    # Determine model string for litellm
    if args.provider == "openrouter":
        model_str = f"openrouter/{args.model}"
    else:
        model_str = args.model

    # Resolve API key
    import os

    api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY", "")

    total_translated = 0
    total_skipped = 0

    for lang_code, lang_name in LANG_NAMES.items():
        target_path = LOCALES_DIR / f"{lang_code}.json"
        if not target_path.exists():
            print(f"  SKIP {lang_code}: file not found")
            total_skipped += 1
            continue

        with open(target_path, "r", encoding="utf-8") as f:
            target = json.load(f)

        missing = find_missing_keys(master, target)

        if not missing:
            print(f"  ✅ {lang_code} ({lang_name}): up to date")
            continue

        print(
            f"  🔄 {lang_code} ({lang_name}): {len(missing)} missing key(s): {list(missing.keys())}"
        )

        if args.dry_run:
            continue

        if not api_key:
            print(
                "    ERROR: No API key provided. Use --api-key or set OPENROUTER_API_KEY."
            )
            sys.exit(1)

        try:
            translated = translate_batch(missing, lang_name, model_str, api_key)

            # Validate: all keys must be present
            for key in missing:
                if key not in translated:
                    print(
                        f"    WARNING: Key '{key}' not in translation response, using master value"
                    )
                    translated[key] = missing[key]

            # Merge into target
            target.update(translated)

            # Write back (sorted by key for consistency)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(target, f, ensure_ascii=False, indent=2)

            total_translated += len(missing)
            print(f"    ✅ Translated {len(missing)} key(s)")

        except Exception as e:
            print(f"    ❌ Translation failed: {e}")
            total_skipped += 1

    print(
        f"\nDone! Translated {total_translated} key(s), skipped {total_skipped} language(s)"
    )


if __name__ == "__main__":
    main()
