"""
fill_i18n_complete.py — Complete all missing i18n keys across 17 locale files.

Two-phase approach:
  Phase 1: Inject the 3 missing _commands.* keys statically (all 17 locales).
  Phase 2: LLM-translate the 976 missing translation keys using en-US as master.
           Uses parallel litellm calls to finish in ~10 minutes with Ollama.

Usage:
  python scripts/fill_i18n_complete.py                        # Ollama default
  python scripts/fill_i18n_complete.py --model qwen-lite:latest
  python scripts/fill_i18n_complete.py --provider openrouter --model anthropic/claude-sonnet-4-6 --api-key sk-...
  python scripts/fill_i18n_complete.py --phase1-only          # only fix command keys
  python scripts/fill_i18n_complete.py --phase2-only          # only do translation
  python scripts/fill_i18n_complete.py --dry-run              # preview without writing
"""

import sys, json, os, time, asyncio, argparse
from pathlib import Path
from copy import deepcopy
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
LOCALES = ROOT / "src" / "chainlit_app" / "locales"

# ─── Language metadata ────────────────────────────────────────────────────────
LANG_NAMES = {
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

# ─── Phase 1: Static command key translations ─────────────────────────────────
# Reference: zh-TW / ja-JP / en-US already complete.
# The 3 missing keys for the 17 locales above.
COMMAND_KEY_TRANSLATIONS: dict[str, dict[str, list[str]]] = {
    "_commands.cmd.download_reference": {
        "zh-CN": ["下载引用清单", "导出引用清单", "下载进版引用", "导出进版引用"],
        "ko-KR": ["참조 목록 다운로드", "참조 목록 내보내기", "인용 다운로드"],
        "fr-FR": ["télécharger références", "exporter références", "télécharger liste références"],
        "de-DE": ["referenzliste herunterladen", "referenzen exportieren"],
        "es-ES": ["descargar referencias", "exportar referencias", "descargar lista referencias"],
        "pt-BR": ["baixar referências", "exportar referências", "baixar lista referências"],
        "it-IT": ["scarica riferimenti", "esporta riferimenti", "scarica lista riferimenti"],
        "ru-RU": ["скачать список ссылок", "экспорт ссылок"],
        "ar-SA": ["تحميل قائمة المراجع", "تصدير قائمة المراجع"],
        "hi-IN": ["संदर्भ सूची डाउनलोड", "संदर्भ सूची निर्यात"],
        "th-TH": ["ดาวน์โหลดรายการอ้างอิง", "ส่งออกรายการอ้างอิง"],
        "vi-VN": ["tải danh sách tài liệu tham khảo", "xuất tài liệu tham khảo"],
        "id-ID": ["unduh daftar referensi", "ekspor referensi"],
        "ms-MY": ["muat turun senarai rujukan", "eksport rujukan"],
        "tr-TR": ["referans listesini indir", "referansları dışa aktar"],
        "nl-NL": ["referentielijst downloaden", "referenties exporteren"],
        "pl-PL": ["pobierz listę referencji", "eksportuj referencje"],
    },
    "_commands.cmd.download_regulatory_update": {
        "zh-CN": ["下载法规更新报告", "导出法规更新报告", "下载法规更新", "导出法规更新"],
        "ko-KR": ["규제 업데이트 보고서 다운로드", "규제 업데이트 내보내기", "법규 업데이트 다운로드"],
        "fr-FR": ["télécharger mise à jour réglementaire", "exporter mise à jour réglementaire"],
        "de-DE": ["regulatorisches update herunterladen", "regulatorisches update exportieren"],
        "es-ES": ["descargar actualización regulatoria", "exportar actualización normativa"],
        "pt-BR": ["baixar atualização regulatória", "exportar atualização regulatória"],
        "it-IT": ["scarica aggiornamento normativo", "esporta aggiornamento normativo"],
        "ru-RU": ["скачать нормативное обновление", "экспорт нормативного обновления"],
        "ar-SA": ["تحميل التحديث التنظيمي", "تصدير التحديث التنظيمي"],
        "hi-IN": ["नियामक अद्यतन रिपोर्ट डाउनलोड", "नियामक अद्यतन निर्यात"],
        "th-TH": ["ดาวน์โหลดรายงานการอัปเดตกฎระเบียบ", "ส่งออกการอัปเดตกฎระเบียบ"],
        "vi-VN": ["tải báo cáo cập nhật quy định", "xuất cập nhật quy định"],
        "id-ID": ["unduh pembaruan regulasi", "ekspor pembaruan regulasi"],
        "ms-MY": ["muat turun kemas kini regulatori", "eksport kemas kini regulatori"],
        "tr-TR": ["düzenleyici güncellemeyi indir", "düzenleyici güncellemeyi dışa aktar"],
        "nl-NL": ["regelgevingsupdate downloaden", "regelgevingsupdate exporteren"],
        "pl-PL": ["pobierz aktualizację regulacyjną", "eksportuj aktualizację regulacyjną"],
    },
    "_commands.cmd.reset_level_range": {
        "zh-CN": ["重置管控范围", "管控范围重置", "更换管控范围"],
        "ko-KR": ["레벨 범위 재설정", "관리 범위 재설정", "제어 범위 변경"],
        "fr-FR": ["réinitialiser plage de niveaux", "changer plage de contrôle"],
        "de-DE": ["steuerungsbereich zurücksetzen", "steuerungsbereich ändern"],
        "es-ES": ["restablecer rango de niveles", "cambiar rango de control"],
        "pt-BR": ["redefinir faixa de nível", "alterar faixa de controle"],
        "it-IT": ["reimposta intervallo livelli", "cambia intervallo di controllo"],
        "ru-RU": ["сбросить диапазон уровней", "изменить диапазон контроля"],
        "ar-SA": ["إعادة تعيين نطاق المستوى", "تغيير نطاق التحكم"],
        "hi-IN": ["स्तर श्रेणी रीसेट", "नियंत्रण श्रेणी बदलें"],
        "th-TH": ["รีเซ็ตช่วงระดับ", "เปลี่ยนช่วงการควบคุม"],
        "vi-VN": ["đặt lại phạm vi cấp độ", "thay đổi phạm vi kiểm soát"],
        "id-ID": ["atur ulang rentang level", "ubah rentang kontrol"],
        "ms-MY": ["tetapkan semula julat tahap", "tukar julat kawalan"],
        "tr-TR": ["seviye aralığını sıfırla", "kontrol aralığını değiştir"],
        "nl-NL": ["niveaubereik herstellen", "controlbereik wijzigen"],
        "pl-PL": ["zresetuj zakres poziomów", "zmień zakres kontroli"],
    },
}

DO_NOT_TRANSLATE = ["Eira", "TMBIA-Tmti", "AI-QMS", "ISO 13485", "QMS", "API Key", "TYPE 1", "TYPE 2"]
BATCH_SIZE = 80  # keys per LLM call — large enough to minimize calls, small enough for local models


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find_missing(master: dict, target: dict) -> dict:
    """Missing translation (non-command) keys in target."""
    return {k: v for k, v in master.items()
            if not k.startswith("_commands.") and k not in target}


# ─── Phase 1 ──────────────────────────────────────────────────────────────────

def phase1_command_keys(dry_run: bool = False) -> None:
    print("\n═══ Phase 1: Command keys ═══")
    for lang_code in LANG_NAMES:
        path = LOCALES / f"{lang_code}.json"
        if not path.exists():
            print(f"  SKIP {lang_code}: file not found")
            continue
        data = load_json(path)
        added = []
        for cmd_key, translations in COMMAND_KEY_TRANSLATIONS.items():
            if cmd_key not in data and lang_code in translations:
                data[cmd_key] = translations[lang_code]
                added.append(cmd_key)
        if added:
            if not dry_run:
                save_json(path, data)
            print(f"  ✅ {lang_code}: added {len(added)} command key(s): {added}")
        else:
            print(f"  ✓  {lang_code}: command keys already complete")
    print()


# ─── Phase 2: LLM translation ─────────────────────────────────────────────────

def build_prompt(batch: dict, target_lang: str) -> list[dict]:
    keys_json = json.dumps(batch, ensure_ascii=False, indent=2)
    system = (
        "You are a professional JSON translation engine for a medical device QMS application.\n"
        "Return ONLY a raw JSON object — no markdown, no code fences, no explanations.\n"
        "Preserve ALL {placeholder} variables exactly. Preserve all emojis and markdown (**, \\n, •).\n"
        f"NEVER translate these terms: {', '.join(DO_NOT_TRANSLATE)}."
    )
    user = (
        f"Translate every value in this JSON from English to {target_lang}.\n"
        f"Keep all keys identical. Return ONLY the translated JSON object.\n\n"
        f"{keys_json}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_json_response(text: str) -> dict | None:
    text = text.strip()
    # Strip code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


def translate_batch_sync(batch: dict, target_lang: str, model: str,
                         api_key: str, api_base: str) -> dict:
    import litellm
    messages = build_prompt(batch, target_lang)
    kwargs: dict = dict(model=model, messages=messages, temperature=0.2, timeout=240)
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    resp = litellm.completion(**kwargs)
    content = resp.choices[0].message.content or ""
    result = parse_json_response(content)
    if result is None:
        raise ValueError(f"Could not parse JSON from response: {content[:300]}")
    # Fill any keys the LLM dropped
    for k, v in batch.items():
        if k not in result:
            result[k] = v
    return result


def translate_lang(lang_code: str, lang_name: str, missing: dict,
                   model: str, api_key: str, api_base: str, dry_run: bool) -> int:
    """Translate all missing keys for one language. Returns count translated."""
    keys = list(missing.keys())
    batches = [dict(list(missing.items())[i:i + BATCH_SIZE])
               for i in range(0, len(keys), BATCH_SIZE)]
    translated: dict = {}

    for idx, batch in enumerate(batches, 1):
        print(f"    [{lang_code}] batch {idx}/{len(batches)} ({len(batch)} keys)…", end=" ", flush=True)
        if dry_run:
            translated.update(batch)
            print("(dry-run)")
            continue
        for attempt in range(3):
            try:
                result = translate_batch_sync(batch, lang_name, model, api_key, api_base)
                translated.update(result)
                print(f"✅")
                break
            except Exception as e:
                wait = 3 * (2 ** attempt)
                if attempt < 2:
                    print(f"⚠️ retry {attempt+1} ({e!s:.60})… wait {wait}s", end=" ", flush=True)
                    time.sleep(wait)
                else:
                    print(f"❌ failed after 3 attempts: {e!s:.80}")
                    translated.update(batch)  # fall back to en-US value

    return len(translated)


def phase2_translations(model: str, api_key: str, api_base: str,
                        dry_run: bool, workers: int = 3) -> None:
    print("═══ Phase 2: Translation keys ═══")
    master = load_json(LOCALES / "en-US.json")

    # Collect work
    tasks: list[tuple[str, str, dict]] = []
    for lang_code, lang_name in LANG_NAMES.items():
        path = LOCALES / f"{lang_code}.json"
        if not path.exists():
            continue
        target = load_json(path)
        missing = find_missing(master, target)
        if not missing:
            print(f"  ✓  {lang_code}: already complete")
            continue
        print(f"  🔄 {lang_code}: {len(missing)} keys to translate")
        tasks.append((lang_code, lang_name, missing))

    if not tasks:
        print("  All languages already complete!")
        return

    print(f"\n  Translating {len(tasks)} language(s), {workers} in parallel…\n")

    def _run(task):
        lang_code, lang_name, missing = task
        count = translate_lang(lang_code, lang_name, missing, model, api_key, api_base, dry_run)
        if not dry_run:
            path = LOCALES / f"{lang_code}.json"
            data = load_json(path)
            # Re-compute missing at write time in case partial runs changed file
            master2 = load_json(LOCALES / "en-US.json")
            fresh_missing = find_missing(master2, data)
            # Only update keys that are still missing
            updates = {k: v for k, v in missing.items() if k in fresh_missing}
            data.update(updates)
            save_json(path, data)
            print(f"  💾 {lang_code}: wrote {count} translations")
        return lang_code, count

    # Use ThreadPoolExecutor for parallel execution
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run, t): t[0] for t in tasks}
        for fut in as_completed(futures):
            lang_code = futures[fut]
            try:
                _, count = fut.result()
            except Exception as e:
                print(f"  ❌ {lang_code} failed: {e}")

    print("\n  Phase 2 complete.")


# ─── Validation ───────────────────────────────────────────────────────────────

def validate() -> bool:
    print("\n═══ Validation ═══")
    master = load_json(LOCALES / "en-US.json")
    en_keys = {k for k in master if not k.startswith("_commands.")}
    all_ok = True
    for lang_code in LANG_NAMES:
        path = LOCALES / f"{lang_code}.json"
        if not path.exists():
            continue
        data = load_json(path)
        t_keys = {k for k in data if not k.startswith("_commands.")}
        missing_t = en_keys - t_keys

        en_cmd = {k for k in master if k.startswith("_commands.")}
        d_cmd = {k for k in data if k.startswith("_commands.")}
        missing_c = en_cmd - d_cmd

        if missing_t or missing_c:
            all_ok = False
            print(f"  ❌ {lang_code}: {len(missing_t)} translation key(s) missing, "
                  f"{len(missing_c)} command key(s) missing")
            if missing_t:
                print(f"      sample: {sorted(missing_t)[:5]}")
        else:
            print(f"  ✅ {lang_code}: complete ({len(t_keys)} translation, {len(d_cmd)} command keys)")
    return all_ok


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fill all missing i18n keys")
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--model", default="qwen-lite:latest")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--api-base", default="")
    parser.add_argument("--workers", type=int, default=3,
                        help="Number of languages to translate in parallel")
    parser.add_argument("--phase1-only", action="store_true")
    parser.add_argument("--phase2-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Build litellm model string
    provider = args.provider.lower()
    model_name = args.model
    if provider == "ollama":
        model_str = f"ollama/{model_name}"
        api_base = args.api_base or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    elif provider == "openrouter":
        model_str = f"openrouter/{model_name}"
        api_base = args.api_base or "https://openrouter.ai/api/v1"
    else:
        model_str = model_name
        api_base = args.api_base
    api_key = args.api_key or os.environ.get(
        {"openrouter": "OPENROUTER_API_KEY", "openai": "OPENAI_API_KEY",
         "anthropic": "ANTHROPIC_API_KEY"}.get(provider, ""), ""
    )

    print(f"AI-QMS i18n Completion Tool")
    print(f"Provider: {provider} | Model: {model_str} | Workers: {args.workers}")
    print(f"Dry-run: {args.dry_run}\n")

    if not args.phase2_only:
        phase1_command_keys(dry_run=args.dry_run)

    if not args.phase1_only:
        phase2_translations(model_str, api_key, api_base, args.dry_run, args.workers)

    validate()


if __name__ == "__main__":
    main()
