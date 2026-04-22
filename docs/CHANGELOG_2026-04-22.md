# AI-QMS Change Log

**Date**: 2026-04-22
**Version**: v3.7.x
**Author**: Claude Sonnet 4.6 + MDR

---

## Summary of Fixes

### 1. Fix: `report_i18n.js` SyntaxError — `Unexpected identifier 'you'`

**Root cause**: The `BUNDLED_TRANSLATIONS` constant was being regenerated from locale JSON files. String values containing `\n` escape sequences (e.g., `override.rerun_prompt`, `rerun.confirm`) were written as literal newlines into the JS file instead of `\\n`. This split one very long JSON line into multiple physical lines, causing JS to see orphaned text tokens like `Would you like to reset this clause...` on their own lines.

**Fix** (`report_ui/report_i18n.js`): Removed 31 orphaned lines (lines 24–54) that were left over from the broken embedding. Line 23 already contained the complete, valid `BUNDLED_TRANSLATIONS` object with properly escaped `\\n` sequences. The orphaned lines were leftover content that was never cleaned up.

**Effect**: The JS file now passes `node --check` with no errors. All i18n translation keys in the HTML report (`detail.basicInfo`, `detail.clauseId`, `verdict.non_compliance`, etc.) will now resolve to their translated text instead of showing raw key names. All HTML icons that depend on i18n being active will now render correctly.

---

### 2. Fix: Section 0.5 Hardcoded Bilingual Text in Word Reports

**Root cause** (`src/utils/crossexam_export.py`, line ~1137): The "Section 0.5 Risk Priority Summary" heading and table column headers were hardcoded as Chinese-English bilingual strings regardless of the `lang` parameter passed to `export_deep_report_word()`.

**Fix**: Added language-aware translation keys to `_EXPORT_HEADERS` for all three supported languages:
- `deep_s05_heading`: Section 0.5 heading in ZH/EN/JA
- `deep_s05_body`: Body description text in ZH/EN/JA  
- `deep_s05_headers`: Table column headers list in ZH/EN/JA

Replaced hardcoded strings with `dh["deep_s05_heading"]`, `dh["deep_s05_body"].format(n=...)`, and `dh["deep_s05_headers"]`.

**Effect**: When the report language is set to English (`lang=en-US`), Section 0.5 now reads "Chapter 0.5: Risk Priority Summary" with English column headers. Japanese shows Japanese. Chinese shows Chinese.

---

### 3. Fix: Chainlit UI — ⚠️ Partial Crawl Failure Indicator for Region Selection

**Root cause** (`src/chainlit_app/app.py`, around line 5636): The numbered region selection list showed ✅ for any region that had at least one successful crawl, even if other domains within that region failed (e.g., Taiwan shows ✅ because CDE worked, but TFDA failed with SSL error). Users had no way to know some domains in the region were unavailable, leading to potential hallucination risk.

**Fix**: Added a "partial" detection step — if a region is in `success_regions` but also has entries in `region_status[region]["failed"]`, it is classified as `partial`. The numbered list now displays:
- `⚠️ {region} (n/m 個網站爬取失敗)` — ZH: n/m sites failed
- `⚠️ {region} (n/m サイト失敗)` — JA
- `⚠️ {region} (n/m sites failed)` — EN

The `partial_regions` list is also stored in the Chainlit session (`regulatory_partial_regions`) for downstream use.

**Effect**: Users can now see at-a-glance which countries have incomplete crawl data, reducing the risk of hallucination from assuming full data coverage.

---

### 4. Feature: Domain Crawl Status Table in Every Word/Excel Export

**Background**: Previously, the regulatory domain crawl status table (showing which URLs succeeded or failed with SSL errors, timeouts, HTTP 4xx/5xx) only appeared in the deep research report. The user reported that not seeing this information in standard reports was a source of hallucination risk — users couldn't tell whether a country's regulatory data was actually fetched.

**Implementation**:

Added two shared helper functions to `src/utils/crossexam_export.py`:
- `_load_crawl_results()` — loads the last crawl result from `RegulatoryStorage().load_last_results()`
- `_append_crawl_status_word(doc, crawl_results, lang)` — appends a crawl status table as an appendix to any Word document (language-aware heading + column headers)
- `_append_crawl_status_excel(wb, crawl_results, lang)` — appends a crawl status sheet to any Excel workbook

Added new i18n keys to `_EXPORT_HEADERS` (ZH/EN/JA):
- `crawl_appendix_heading`: Appendix section title
- `crawl_appendix_headers`: Table column headers (Status, Agency, Region, URL, HTTP Status, Error)
- `crawl_xl_sheet`: Excel sheet tab name

**Files modified** — all export functions now call the helpers before saving:
- `src/utils/crossexam_export.py`: `export_crossexam_record_word`, `export_crossexam_record_excel`, `export_deep_report_word`, `export_deep_report_excel`
- `src/utils/regulatory_export.py`: `export_regulatory_to_word`, `export_regulatory_to_excel`, `export_reference_to_word`, `export_reference_to_excel`

The table shows:
| Status | Agency | Region | URL | HTTP Status | Error |
|--------|--------|--------|-----|-------------|-------|
| ✓ | CDE | 台灣 | https://... | 200 | |
| ✗ | TFDA | 台灣 | https://... | | SSL error |

Success rows are highlighted green, failure rows red. If no crawl data is available, the section is silently skipped with no error.

---

## Files Changed

| File | Change |
|------|--------|
| `report_ui/report_i18n.js` | Removed 31 orphaned lines that broke JS syntax |
| `src/utils/crossexam_export.py` | Added i18n keys for Section 0.5 + crawl status helpers + integrated into all 4 export functions |
| `src/utils/regulatory_export.py` | Integrated crawl status helpers into all 4 export functions |
| `src/chainlit_app/app.py` | Added ⚠️ partial crawl failure indicator in region selection list |
| `docs/CHANGELOG_2026-04-22.md` | This file |
