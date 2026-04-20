"""Central language configuration — single source of truth for AI-QMS i18n.

To add a new language:
  1. Create src/chainlit_app/locales/<lang-code>.json with all translation keys
  2. Add the language label to SUPPORTED_LANGUAGES
  3. Add the mapping to LANG_CODE_MAP
  All other files (Python t(), HTML report JS) will automatically use it.
"""

DEFAULT_LANG = "en-US"

# Languages shown in the Chainlit UI selector
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


def lang_key(lang: str) -> str:
    """Normalize a UI language code to a prompt-dict key (zh / en / ja).

    Falls back to 'en' for any language other than zh / ja.
    This is the single source of truth — import from here instead of defining locally.
    """
    if not lang:
        return "en"
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("ja"):
        return "ja"
    return "en"


def display_region(region_key: str, lang: str) -> str:
    """Strip Chinese prefix from bilingual region keys for non-Chinese languages.

    Region keys in the database look like "美國 (USA)" or "歐盟 (EU)".
    For Chinese users, show the full key. For others, show only the English part.
    """
    if lang.startswith("zh"):
        return region_key
    import re
    m = re.search(r'\(([^)]+)\)', region_key)
    return m.group(1) if m else region_key
