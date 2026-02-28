"""i18n module for AI-QMS — 20-language translations.

Loads translations and command keywords from JSON files under locales/.
Each JSON file contains both translation keys and command keywords (prefixed with '_commands.').
"""

import json
from pathlib import Path


# ─── Language metadata (unchanged) ──────────────────────────────────────────

SUPPORTED_LANGUAGES = [
    "繁體中文 (zh-TW)",
    "English (en-US)",
    "日本語 (ja-JP)",
    "简体中文 (zh-CN)",
    "한국어 (ko-KR)",
    "Français (fr-FR)",
    "Deutsch (de-DE)",
    "Español (es-ES)",
    "Português (pt-BR)",
    "Italiano (it-IT)",
    "Русский (ru-RU)",
    "العربية (ar-SA)",
    "हिन्दी (hi-IN)",
    "ไทย (th-TH)",
    "Tiếng Việt (vi-VN)",
    "Bahasa Indonesia (id-ID)",
    "Bahasa Melayu (ms-MY)",
    "Türkçe (tr-TR)",
    "Nederlands (nl-NL)",
    "Polski (pl-PL)",
]

LANG_CODE_MAP = {
    "繁體中文 (zh-TW)": "zh-TW",
    "English (en-US)": "en-US",
    "日本語 (ja-JP)": "ja-JP",
    "简体中文 (zh-CN)": "zh-CN",
    "한국어 (ko-KR)": "ko-KR",
    "Français (fr-FR)": "fr-FR",
    "Deutsch (de-DE)": "de-DE",
    "Español (es-ES)": "es-ES",
    "Português (pt-BR)": "pt-BR",
    "Italiano (it-IT)": "it-IT",
    "Русский (ru-RU)": "ru-RU",
    "العربية (ar-SA)": "ar-SA",
    "हिन्दी (hi-IN)": "hi-IN",
    "ไทย (th-TH)": "th-TH",
    "Tiếng Việt (vi-VN)": "vi-VN",
    "Bahasa Indonesia (id-ID)": "id-ID",
    "Bahasa Melayu (ms-MY)": "ms-MY",
    "Türkçe (tr-TR)": "tr-TR",
    "Nederlands (nl-NL)": "nl-NL",
    "Polski (pl-PL)": "pl-PL",
}


# ─── Load translations + commands from JSON files ──────────────────────────

_LOCALES_DIR = Path(__file__).parent / "locales"

_CMD_PREFIX = "_commands."

I18N: dict[str, dict[str, str]] = {}
COMMANDS: dict[str, dict[str, list]] = {}


def _load_locales():
    """Load all locale JSON files, splitting translation keys from command keys."""
    for json_path in sorted(_LOCALES_DIR.glob("*.json")):
        lang_code = json_path.stem  # e.g. "zh-TW"
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        translations = {}
        commands = {}
        for key, value in data.items():
            if key.startswith(_CMD_PREFIX):
                # Strip prefix: "_commands.cmd.help" -> "cmd.help"
                cmd_key = key[len(_CMD_PREFIX) :]
                commands[cmd_key] = value
            else:
                translations[key] = value

        I18N[lang_code] = translations
        if commands:
            COMMANDS[lang_code] = commands


_load_locales()


# ─── Utility functions ─────────────────────────────────────────────────────


def get_all_command_keywords(cmd_key: str) -> set:
    """Get all keywords for a given command key across ALL languages.

    Args:
        cmd_key: Command key like 'cmd.list', 'cmd.search', etc.

    Returns:
        Set of lowercase keyword strings from all 20 languages.
    """
    all_keywords = set()
    for lang_code, cmds in COMMANDS.items():
        if isinstance(cmds, dict) and cmd_key in cmds:
            kws = cmds[cmd_key]
            if isinstance(kws, list):
                all_keywords.update(kw.lower() for kw in kws)
    return all_keywords
