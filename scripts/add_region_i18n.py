"""One-time script: add region.* i18n keys to all 20 Chainlit locale files."""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "src" / "chainlit_app" / "locales"

REGION_KEYS = {
    "region.taiwan":        {"zh-TW": "台灣",          "zh-CN": "台湾",       "ja-JP": "台湾",             "ko-KR": "대만",             "ru-RU": "Тайвань",                "ar-SA": "تايوان",                      "default": "Taiwan"},
    "region.usa":           {"zh-TW": "美國",          "zh-CN": "美国",       "ja-JP": "アメリカ",         "ko-KR": "미국",             "ru-RU": "США",                    "ar-SA": "الولايات المتحدة",            "default": "USA"},
    "region.eu":            {"zh-TW": "歐盟",          "zh-CN": "欧盟",       "ja-JP": "EU",               "ko-KR": "EU",               "ru-RU": "ЕС",                     "ar-SA": "الاتحاد الأوروبي",            "default": "EU"},
    "region.uk":            {"zh-TW": "英國",          "zh-CN": "英国",       "ja-JP": "英国",             "ko-KR": "영국",             "ru-RU": "Великобритания",         "ar-SA": "المملكة المتحدة",             "default": "UK"},
    "region.japan":         {"zh-TW": "日本",          "zh-CN": "日本",       "ja-JP": "日本",             "ko-KR": "일본",             "ru-RU": "Япония",                 "ar-SA": "اليابان",                     "default": "Japan"},
    "region.china":         {"zh-TW": "中國",          "zh-CN": "中国",       "ja-JP": "中国",             "ko-KR": "중국",             "ru-RU": "Китай",                  "ar-SA": "الصين",                       "default": "China"},
    "region.korea":         {"zh-TW": "韓國",          "zh-CN": "韩国",       "ja-JP": "韓国",             "ko-KR": "한국",             "ru-RU": "Корея",                  "ar-SA": "كوريا الجنوبية",              "default": "Korea"},
    "region.canada":        {"zh-TW": "加拿大",        "zh-CN": "加拿大",     "ja-JP": "カナダ",           "ko-KR": "캐나다",           "ru-RU": "Канада",                 "ar-SA": "كندا",                        "default": "Canada"},
    "region.australia":     {"zh-TW": "澳洲",          "zh-CN": "澳大利亚",   "ja-JP": "オーストラリア",   "ko-KR": "호주",             "ru-RU": "Австралия",              "ar-SA": "أستراليا",                    "default": "Australia"},
    "region.switzerland":   {"zh-TW": "瑞士",          "zh-CN": "瑞士",       "ja-JP": "スイス",           "ko-KR": "스위스",           "ru-RU": "Швейцария",              "ar-SA": "سويسرا",                      "default": "Switzerland"},
    "region.brazil":        {"zh-TW": "巴西",          "zh-CN": "巴西",       "ja-JP": "ブラジル",         "ko-KR": "브라질",           "ru-RU": "Бразилия",               "ar-SA": "البرازيل",                    "default": "Brazil"},
    "region.international": {"zh-TW": "國際標準",      "zh-CN": "国际标准",   "ja-JP": "国際標準",         "ko-KR": "국제표준",         "ru-RU": "Международный стандарт", "ar-SA": "المعيار الدولي",              "default": "International Standard"},
    "region.india":         {"zh-TW": "印度",          "zh-CN": "印度",       "ja-JP": "インド",           "ko-KR": "인도",             "ru-RU": "Индия",                  "ar-SA": "الهند",                       "default": "India"},
    "region.singapore":     {"zh-TW": "新加坡",        "zh-CN": "新加坡",     "ja-JP": "シンガポール",     "ko-KR": "싱가포르",         "ru-RU": "Сингапур",               "ar-SA": "سنغافورة",                    "default": "Singapore"},
    "region.saudi_arabia":  {"zh-TW": "沙烏地阿拉伯",  "zh-CN": "沙特阿拉伯", "ja-JP": "サウジアラビア",   "ko-KR": "사우디아라비아",   "ru-RU": "Саудовская Аравия",      "ar-SA": "المملكة العربية السعودية",    "default": "Saudi Arabia"},
    "region.thailand":      {"zh-TW": "泰國",          "zh-CN": "泰国",       "ja-JP": "タイ",             "ko-KR": "태국",             "ru-RU": "Таиланд",                "ar-SA": "تايلاند",                     "default": "Thailand"},
    "region.new_zealand":   {"zh-TW": "紐西蘭",        "zh-CN": "新西兰",     "ja-JP": "ニュージーランド", "ko-KR": "뉴질랜드",         "ru-RU": "Новая Зеландия",         "ar-SA": "نيوزيلندا",                   "default": "New Zealand"},
    "region.mexico":        {"zh-TW": "墨西哥",        "zh-CN": "墨西哥",     "ja-JP": "メキシコ",         "ko-KR": "멕시코",           "ru-RU": "Мексика",                "ar-SA": "المكسيك",                     "default": "Mexico"},
    "region.argentina":     {"zh-TW": "阿根廷",        "zh-CN": "阿根廷",     "ja-JP": "アルゼンチン",     "ko-KR": "아르헨티나",       "ru-RU": "Аргентина",              "ar-SA": "الأرجنتين",                   "default": "Argentina"},
    "region.south_africa":  {"zh-TW": "南非",          "zh-CN": "南非",       "ja-JP": "南アフリカ",       "ko-KR": "남아프리카공화국", "ru-RU": "ЮАР",                    "ar-SA": "جنوب أفريقيا",                "default": "South Africa"},
    "region.turkey":        {"zh-TW": "土耳其",        "zh-CN": "土耳其",     "ja-JP": "トルコ",           "ko-KR": "터키",             "ru-RU": "Турция",                 "ar-SA": "تركيا",                       "default": "Turkey"},
    "region.indonesia":     {"zh-TW": "印尼",          "zh-CN": "印度尼西亚", "ja-JP": "インドネシア",     "ko-KR": "인도네시아",       "ru-RU": "Индонезия",              "ar-SA": "إندونيسيا",                   "default": "Indonesia"},
    "region.malaysia":      {"zh-TW": "馬來西亞",      "zh-CN": "马来西亚",   "ja-JP": "マレーシア",       "ko-KR": "말레이시아",       "ru-RU": "Малайзия",               "ar-SA": "ماليزيا",                     "default": "Malaysia"},
    "region.israel":        {"zh-TW": "以色列",        "zh-CN": "以色列",     "ja-JP": "イスラエル",       "ko-KR": "이스라엘",         "ru-RU": "Израиль",                "ar-SA": "إسرائيل",                     "default": "Israel"},
    "region.philippines":   {"zh-TW": "菲律賓",        "zh-CN": "菲律宾",     "ja-JP": "フィリピン",       "ko-KR": "필리핀",           "ru-RU": "Филиппины",              "ar-SA": "الفلبين",                     "default": "Philippines"},
    "region.vietnam":       {"zh-TW": "越南",          "zh-CN": "越南",       "ja-JP": "ベトナム",         "ko-KR": "베트남",           "ru-RU": "Вьетнам",                "ar-SA": "فيتنام",                      "default": "Vietnam"},
    "region.colombia":      {"zh-TW": "哥倫比亞",      "zh-CN": "哥伦比亚",   "ja-JP": "コロンビア",       "ko-KR": "콜롬비아",         "ru-RU": "Колумбия",               "ar-SA": "كولومبيا",                    "default": "Colombia"},
    "region.russia":        {"zh-TW": "俄羅斯",        "zh-CN": "俄罗斯",     "ja-JP": "ロシア",           "ko-KR": "러시아",           "ru-RU": "Россия",                 "ar-SA": "روسيا",                       "default": "Russia"},
    "region.egypt":         {"zh-TW": "埃及",          "zh-CN": "埃及",       "ja-JP": "エジプト",         "ko-KR": "이집트",           "ru-RU": "Египет",                 "ar-SA": "مصر",                         "default": "Egypt"},
    "region.chile":         {"zh-TW": "智利",          "zh-CN": "智利",       "ja-JP": "チリ",             "ko-KR": "칠레",             "ru-RU": "Чили",                   "ar-SA": "تشيلي",                       "default": "Chile"},
    "region.uae":           {"zh-TW": "阿聯酋",        "zh-CN": "阿联酋",     "ja-JP": "UAE",              "ko-KR": "UAE",              "ru-RU": "ОАЭ",                    "ar-SA": "الإمارات العربية المتحدة",    "default": "UAE"},
}


def pick(key_data: dict, lang_code: str) -> str:
    if lang_code in key_data:
        return key_data[lang_code]
    prefix = lang_code.split("-")[0]
    for k, v in key_data.items():
        if k != "default" and k.split("-")[0] == prefix:
            return v
    return key_data["default"]


updated: list[str] = []
skipped: list[str] = []

for json_file in sorted(BASE.glob("*.json")):
    lang = json_file.stem
    with open(json_file, encoding="utf-8") as f:
        data: dict = json.load(f)

    if "region.taiwan" in data:
        skipped.append(lang)
        continue

    for rk, translations in REGION_KEYS.items():
        data[rk] = pick(translations, lang)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    updated.append(lang)

print("Updated:", updated)
print("Skipped:", skipped)
