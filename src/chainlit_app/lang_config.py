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


# ── Region name i18n ──────────────────────────────────────────────────────────
# Maps canonical bilingual form (stored in DB) → i18n key used in locale files.

REGION_KEY_MAP: dict[str, str] = {
    "台灣 (Taiwan)":                   "taiwan",
    "美國 (USA)":                       "usa",
    "歐盟 (EU)":                        "eu",
    "英國 (UK)":                        "uk",
    "日本 (Japan)":                     "japan",
    "中國 (China)":                     "china",
    "韓國 (Korea)":                     "korea",
    "加拿大 (Canada)":                  "canada",
    "澳洲 (Australia)":                 "australia",
    "瑞士 (Switzerland)":               "switzerland",
    "巴西 (Brazil)":                    "brazil",
    "國際標準 (International Standard)":"international",
    "印度 (India)":                     "india",
    "新加坡 (Singapore)":               "singapore",
    "沙烏地阿拉伯 (Saudi Arabia)":      "saudi_arabia",
    "泰國 (Thailand)":                  "thailand",
    "紐西蘭 (New Zealand)":             "new_zealand",
    "墨西哥 (Mexico)":                  "mexico",
    "阿根廷 (Argentina)":               "argentina",
    "南非 (South Africa)":              "south_africa",
    "土耳其 (Turkey)":                  "turkey",
    "印尼 (Indonesia)":                 "indonesia",
    "馬來西亞 (Malaysia)":              "malaysia",
    "以色列 (Israel)":                  "israel",
    "菲律賓 (Philippines)":             "philippines",
    "越南 (Vietnam)":                   "vietnam",
    "哥倫比亞 (Colombia)":              "colombia",
    "俄羅斯 (Russia)":                  "russia",
    "埃及 (Egypt)":                     "egypt",
    "智利 (Chile)":                     "chile",
    "阿聯酋 (UAE)":                     "uae",
}

# Embedded translations for zh / en / ja — kept in sync with locale files.
# Other languages fall back to "en" via locale-file fallback in i18n.py.
_REGION_I18N: dict[str, dict[str, str]] = {
    "taiwan":        {"zh": "台灣",          "zh-CN": "台湾",       "ja": "台湾",             "en": "Taiwan"},
    "usa":           {"zh": "美國",          "zh-CN": "美国",       "ja": "アメリカ",         "en": "USA"},
    "eu":            {"zh": "歐盟",          "zh-CN": "欧盟",       "ja": "EU",               "en": "EU"},
    "uk":            {"zh": "英國",          "zh-CN": "英国",       "ja": "英国",             "en": "UK"},
    "japan":         {"zh": "日本",          "zh-CN": "日本",       "ja": "日本",             "en": "Japan"},
    "china":         {"zh": "中國",          "zh-CN": "中国",       "ja": "中国",             "en": "China"},
    "korea":         {"zh": "韓國",          "zh-CN": "韩国",       "ja": "韓国",             "en": "Korea"},
    "canada":        {"zh": "加拿大",        "zh-CN": "加拿大",     "ja": "カナダ",           "en": "Canada"},
    "australia":     {"zh": "澳洲",          "zh-CN": "澳大利亚",   "ja": "オーストラリア",   "en": "Australia"},
    "switzerland":   {"zh": "瑞士",          "zh-CN": "瑞士",       "ja": "スイス",           "en": "Switzerland"},
    "brazil":        {"zh": "巴西",          "zh-CN": "巴西",       "ja": "ブラジル",         "en": "Brazil"},
    "international": {"zh": "國際標準",      "zh-CN": "国际标准",   "ja": "国際標準",         "en": "International Standard"},
    "india":         {"zh": "印度",          "zh-CN": "印度",       "ja": "インド",           "en": "India"},
    "singapore":     {"zh": "新加坡",        "zh-CN": "新加坡",     "ja": "シンガポール",     "en": "Singapore"},
    "saudi_arabia":  {"zh": "沙烏地阿拉伯",  "zh-CN": "沙特阿拉伯", "ja": "サウジアラビア",   "en": "Saudi Arabia"},
    "thailand":      {"zh": "泰國",          "zh-CN": "泰国",       "ja": "タイ",             "en": "Thailand"},
    "new_zealand":   {"zh": "紐西蘭",        "zh-CN": "新西兰",     "ja": "ニュージーランド", "en": "New Zealand"},
    "mexico":        {"zh": "墨西哥",        "zh-CN": "墨西哥",     "ja": "メキシコ",         "en": "Mexico"},
    "argentina":     {"zh": "阿根廷",        "zh-CN": "阿根廷",     "ja": "アルゼンチン",     "en": "Argentina"},
    "south_africa":  {"zh": "南非",          "zh-CN": "南非",       "ja": "南アフリカ",       "en": "South Africa"},
    "turkey":        {"zh": "土耳其",        "zh-CN": "土耳其",     "ja": "トルコ",           "en": "Turkey"},
    "indonesia":     {"zh": "印尼",          "zh-CN": "印度尼西亚", "ja": "インドネシア",     "en": "Indonesia"},
    "malaysia":      {"zh": "馬來西亞",      "zh-CN": "马来西亚",   "ja": "マレーシア",       "en": "Malaysia"},
    "israel":        {"zh": "以色列",        "zh-CN": "以色列",     "ja": "イスラエル",       "en": "Israel"},
    "philippines":   {"zh": "菲律賓",        "zh-CN": "菲律宾",     "ja": "フィリピン",       "en": "Philippines"},
    "vietnam":       {"zh": "越南",          "zh-CN": "越南",       "ja": "ベトナム",         "en": "Vietnam"},
    "colombia":      {"zh": "哥倫比亞",      "zh-CN": "哥伦比亚",   "ja": "コロンビア",       "en": "Colombia"},
    "russia":        {"zh": "俄羅斯",        "zh-CN": "俄罗斯",     "ja": "ロシア",           "en": "Russia"},
    "egypt":         {"zh": "埃及",          "zh-CN": "埃及",       "ja": "エジプト",         "en": "Egypt"},
    "chile":         {"zh": "智利",          "zh-CN": "智利",       "ja": "チリ",             "en": "Chile"},
    "uae":           {"zh": "阿聯酋",        "zh-CN": "阿联酋",     "ja": "UAE",              "en": "UAE"},
}


def display_region(region_key: str, lang: str) -> str:
    """Return the localized name for a canonical bilingual region key.

    Canonical keys stored in the DB look like "美國 (USA)" or "歐盟 (EU)".
    This function maps them to the appropriate display name for the given UI language.

    Language coverage:
      - zh-TW / zh-CN → Traditional / Simplified Chinese
      - ja-JP          → Japanese
      - ko-KR / ru-RU / ar-SA / … → locale file values (set up in region.* i18n keys)
      - all others (en-US, fr-FR, de-DE, …) → English
    """
    rk = REGION_KEY_MAP.get(region_key)
    if rk:
        tr = _REGION_I18N.get(rk, {})
        if lang.startswith("zh-CN") or lang == "zh_CN":
            return tr.get("zh-CN") or tr.get("zh") or tr.get("en", region_key)
        if lang.startswith("zh"):
            return tr.get("zh") or tr.get("en", region_key)
        if lang.startswith("ja"):
            return tr.get("ja") or tr.get("en", region_key)
        # For ko/ru/ar and other non-zh/ja languages: try the locale file first.
        try:
            from src.chainlit_app.i18n import I18N  # lazy import to avoid circular dep
            locale_val = I18N.get(lang, {}).get(f"region.{rk}")
            if locale_val:
                return locale_val
        except Exception:
            pass
        return tr.get("en", region_key)
    # Unknown canonical key — strip Chinese prefix for non-Chinese users (fallback)
    if lang.startswith("zh"):
        return region_key
    import re
    m = re.search(r"\(([^)]+)\)", region_key)
    return m.group(1) if m else region_key
