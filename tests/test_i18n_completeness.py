"""
Tests to verify all user-visible content respects the selected language.
Run: pytest tests/test_i18n_completeness.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock


# -- Test 1: ISO clause translations -----------------------------------------

def test_all_clauses_have_en_ja_translations():
    """All 71 ISO 13485 clauses must have EN and JA audit questions + evidence."""
    from src.analysis.compliance_rules import ISO_13485_CHECKLIST
    missing = []
    for cid, clause in ISO_13485_CHECKLIST.items():
        for field in ["audit_question_en", "audit_question_ja",
                      "audit_questions_en", "audit_questions_ja",
                      "expected_evidence_en", "expected_evidence_ja"]:
            if not clause.get(field):
                missing.append(f"{cid}: missing {field}")
    assert not missing, f"Missing translations:\n" + "\n".join(missing)


def test_audit_questions_count_matches():
    """audit_questions_en/ja must match count of audit_questions."""
    from src.analysis.compliance_rules import ISO_13485_CHECKLIST
    errors = []
    for cid, clause in ISO_13485_CHECKLIST.items():
        base_count = len(clause.get("audit_questions", []))
        for suffix in ["_en", "_ja"]:
            translated = clause.get(f"audit_questions{suffix}", [])
            if len(translated) != base_count:
                errors.append(f"{cid}: audit_questions has {base_count} items but audit_questions{suffix} has {len(translated)}")
    assert not errors, "\n".join(errors)


def test_expected_evidence_count_matches():
    """expected_evidence_en/ja must match count of expected_evidence."""
    from src.analysis.compliance_rules import ISO_13485_CHECKLIST
    errors = []
    for cid, clause in ISO_13485_CHECKLIST.items():
        base_count = len(clause.get("expected_evidence", []))
        for suffix in ["_en", "_ja"]:
            translated = clause.get(f"expected_evidence{suffix}", [])
            if len(translated) != base_count:
                errors.append(f"{cid}: expected_evidence has {base_count} items but expected_evidence{suffix} has {len(translated)}")
    assert not errors, "\n".join(errors)


# -- Test 2: get_audit_question language routing -----------------------------

def test_get_audit_question_zh():
    """zh-TW returns Chinese content."""
    from src.analysis.compliance_rules import ISO_13485_CHECKLIST, get_audit_question
    clause = ISO_13485_CHECKLIST["4.1"]
    q = get_audit_question(clause, seed=0, lang="zh-TW")
    # Chinese content contains CJK characters
    assert any('\u4e00' <= c <= '\u9fff' for c in q), f"Expected Chinese, got: {q[:50]}"


def test_get_audit_question_en():
    """en-US returns English content (ASCII-heavy, no Chinese chars)."""
    from src.analysis.compliance_rules import ISO_13485_CHECKLIST, get_audit_question
    clause = ISO_13485_CHECKLIST["4.1"]
    q = get_audit_question(clause, seed=0, lang="en-US")
    chinese_chars = sum(1 for c in q if '\u4e00' <= c <= '\u9fff')
    assert chinese_chars == 0, f"Expected English, got Chinese chars in: {q[:80]}"
    assert len(q) > 20, "English question too short"


def test_get_audit_question_ja():
    """ja-JP returns Japanese content (hiragana/katakana present)."""
    from src.analysis.compliance_rules import ISO_13485_CHECKLIST, get_audit_question
    clause = ISO_13485_CHECKLIST["4.1"]
    q = get_audit_question(clause, seed=0, lang="ja-JP")
    # Japanese has hiragana (3040-309F) or katakana (30A0-30FF)
    has_japanese = any('\u3040' <= c <= '\u30ff' for c in q)
    assert has_japanese, f"Expected Japanese (hiragana/katakana), got: {q[:80]}"


def test_get_audit_question_ja_not_english():
    """ja-JP response must differ from en-US response."""
    from src.analysis.compliance_rules import ISO_13485_CHECKLIST, get_audit_question
    clause = ISO_13485_CHECKLIST["4.1"]
    q_en = get_audit_question(clause, seed=0, lang="en-US")
    q_ja = get_audit_question(clause, seed=0, lang="ja-JP")
    assert q_en != q_ja, "Japanese and English questions must be different"


def test_get_audit_question_all_clauses_ja():
    """All 71 clauses return distinct Japanese (not falling back to English)."""
    from src.analysis.compliance_rules import ISO_13485_CHECKLIST, get_audit_question
    non_japanese = []
    for cid, clause in ISO_13485_CHECKLIST.items():
        q = get_audit_question(clause, seed=0, lang="ja-JP")
        has_japanese = any('\u3040' <= c <= '\u30ff' for c in q)
        if not has_japanese:
            non_japanese.append(f"{cid}: {q[:60]}")
    assert not non_japanese, f"Clauses missing Japanese:\n" + "\n".join(non_japanese)


# -- Test 3: get_system_prompt language routing ------------------------------

def test_system_prompt_en_is_english():
    """English lang produces English system prompt."""
    # Mock cl.user_session since we're outside Chainlit
    with patch("chainlit.user_session") as mock_sess:
        mock_sess.get.return_value = "en-US"
        # Import after patching
        import importlib
        import src.chainlit_app.app as app_mod
        prompt = app_mod.get_system_prompt("Main Agent", lang="en-US")
        assert "You are" in prompt or "your" in prompt.lower(), \
            f"Expected English system prompt, got: {prompt[:100]}"
        # Should not contain Chinese characters
        chinese_chars = sum(1 for c in prompt if '\u4e00' <= c <= '\u9fff')
        assert chinese_chars == 0, f"English system prompt contains Chinese: {prompt[:100]}"


def test_system_prompt_ja_is_japanese():
    """Japanese lang produces Japanese system prompt."""
    import src.chainlit_app.app as app_mod
    prompt = app_mod.get_system_prompt("Main Agent", lang="ja-JP")
    has_japanese = any('\u3040' <= c <= '\u30ff' for c in prompt)
    assert has_japanese, f"Expected Japanese system prompt, got: {prompt[:100]}"


def test_system_prompt_zh_is_chinese():
    """zh-TW lang produces Chinese system prompt."""
    import src.chainlit_app.app as app_mod
    prompt = app_mod.get_system_prompt("Main Agent", lang="zh-TW")
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in prompt)
    assert has_chinese, f"Expected Chinese system prompt, got: {prompt[:100]}"


# -- Test 4: i18n locale completeness ----------------------------------------

def test_en_us_locale_has_web_compare_key():
    """en-US.json must have web.compare_local_web key."""
    import json
    path = "src/chainlit_app/locales/en-US.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "web.compare_local_web" in data, "Missing web.compare_local_web in en-US.json"
    assert "Chinese" not in data["web.compare_local_web"]


def test_ja_jp_locale_has_web_compare_key():
    """ja-JP.json must have web.compare_local_web key with Japanese content."""
    import json
    path = "src/chainlit_app/locales/ja-JP.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "web.compare_local_web" in data, "Missing web.compare_local_web in ja-JP.json"
    val = data["web.compare_local_web"]
    has_japanese = any('\u3040' <= c <= '\u30ff' for c in val)
    assert has_japanese, f"ja-JP web.compare_local_web should be Japanese: {val}"


def test_en_us_locale_key_count():
    """en-US and ja-JP locales should have the same number of keys."""
    import json
    with open("src/chainlit_app/locales/en-US.json", encoding="utf-8") as f:
        en = json.load(f)
    with open("src/chainlit_app/locales/ja-JP.json", encoding="utf-8") as f:
        ja = json.load(f)
    en_keys = set(en.keys())
    ja_keys = set(ja.keys())
    missing_in_ja = en_keys - ja_keys
    missing_in_en = ja_keys - en_keys
    assert not missing_in_ja, f"Keys in en-US but not ja-JP: {missing_in_ja}"
    assert not missing_in_en, f"Keys in ja-JP but not en-US: {missing_in_en}"


# -- Test 5: export functions accept lang parameter --------------------------

def test_export_doclist_to_word_accepts_lang():
    """export_doclist_to_word must accept lang parameter."""
    import inspect
    from src.utils.doclist_export import export_doclist_to_word
    sig = inspect.signature(export_doclist_to_word)
    assert "lang" in sig.parameters, "export_doclist_to_word missing lang parameter"


def test_export_doclist_to_excel_accepts_lang():
    """export_doclist_to_excel must accept lang parameter."""
    import inspect
    from src.utils.doclist_export import export_doclist_to_excel
    sig = inspect.signature(export_doclist_to_excel)
    assert "lang" in sig.parameters, "export_doclist_to_excel missing lang parameter"


def test_export_allrecords_to_word_accepts_lang():
    """export_allrecords_to_word must accept lang parameter."""
    import inspect
    from src.utils.doclist_export import export_allrecords_to_word
    sig = inspect.signature(export_allrecords_to_word)
    assert "lang" in sig.parameters, "export_allrecords_to_word missing lang parameter"


# -- Test 6: comparison_table lang threading ---------------------------------

def test_comparison_table_build_initial_rows_accepts_lang():
    """build_initial_rows must accept lang parameter."""
    import inspect
    from src.analysis.comparison_table import ComparisonTable
    # Check if build_initial_rows method accepts lang
    sig = inspect.signature(ComparisonTable.build_initial_rows)
    assert "lang" in sig.parameters, "ComparisonTable.build_initial_rows missing lang parameter"


def test_comparison_table_populate_from_scan_accepts_lang():
    """populate_from_scan must accept lang parameter."""
    import inspect
    from src.analysis.comparison_table import ComparisonTable
    sig = inspect.signature(ComparisonTable.populate_from_scan)
    assert "lang" in sig.parameters, "ComparisonTable.populate_from_scan missing lang parameter"


# -- Test 7: pipeline passes lang --------------------------------------------

def test_pipeline_passes_lang_to_data_quality():
    """AnalysisPipeline._execute_phase_0 must pass lang to run_data_quality_gate."""
    import inspect
    import ast
    with open("src/analysis/pipeline.py", encoding="utf-8") as f:
        source = f.read()
    # Check that run_data_quality_gate is called with lang=
    assert "run_data_quality_gate(self._state, lang=self._lang)" in source or \
           "run_data_quality_gate(self._state,lang=self._lang)" in source, \
        "pipeline.py: run_data_quality_gate not called with lang=self._lang"


# -- Test 8: report_i18n.js reads lang from URL ------------------------------

def test_report_i18n_js_reads_url_param():
    """report_i18n.js must read ?lang= from URL before fetching from API."""
    with open("report_ui/report_i18n.js", encoding="utf-8") as f:
        js = f.read()
    assert "URLSearchParams" in js, "report_i18n.js must use URLSearchParams to read ?lang="
    assert 'get("lang")' in js or "get('lang')" in js, "report_i18n.js must get('lang') from URL params"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
