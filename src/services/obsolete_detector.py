"""
AI-QMS - Obsolete Document Detection
=====================================

偵測上傳文件是否為作廢文件，透過以下方式：
- 掃描檔名與標題中的作廢關鍵字
- 掃描 OCR 內容中的作廢句型與關鍵字
- 視覺印章偵測（預留介面，未來整合現有簽章偵測邏輯）

信心度分級：
- >= 0.80: 高信心度（標題/檔名命中）
- 0.40-0.79: 中信心度（內容關鍵字命中）
- < 0.40: 不疑似作廢

重要設計決策：
  僅在內容中命中單一關鍵字時，信心度設為低（0.50），因為文件可能是在
  描述作廢流程（如程序書中提到「作廢文件管制」），而非文件本身已作廢。
  需要使用者二次確認。
"""

from __future__ import annotations

__all__ = [
    "detect_obsolete",
    "OBSOLETE_KEYWORDS_TITLE",
    "OBSOLETE_PHRASES",
]


# ============================================================
# Keyword Constants
# ============================================================

# Title/filename keywords — high confidence when found in title
OBSOLETE_KEYWORDS_TITLE = [
    # 中文繁體
    "作廢",
    "廢止",
    "已作廢",
    "已廢止",
    # 中文簡體
    "作废",
    "废止",
    "已作废",
    "已废止",
    # 英文
    "VOID",
    "VOIDED",
    "OBSOLETE",
    "OBSOLETED",
    "CANCELLED",
    "CANCELED",
    "SUPERSEDED",
    "WITHDRAWN",
    "RETIRED",
    "INVALID",
    # 日文
    "廃止",
    "無効",
]

# Full phrases — very high confidence
OBSOLETE_PHRASES = [
    # 中文
    "本文件已作廢",
    "此文件已作廢",
    "本文件已廢止",
    "此文件已廢止",
    "文件作廢",
    "本文件不再有效",
    "此版本已被取代",
    "此文件不再適用",
    "本文件已失效",
    "此文件已失效",
    # 英文
    "THIS DOCUMENT IS VOID",
    "THIS DOCUMENT HAS BEEN OBSOLETED",
    "THIS DOCUMENT IS NO LONGER VALID",
    "DOCUMENT OBSOLETED",
    "THIS VERSION HAS BEEN SUPERSEDED",
    "DO NOT USE",
    "THIS DOCUMENT IS OBSOLETE",
    "DOCUMENT VOIDED",
    "THIS DOCUMENT HAS BEEN VOIDED",
    "DOCUMENT WITHDRAWN",
    "THIS DOCUMENT IS CANCELLED",
    # 日文
    "本文書は廃止されました",
    "この文書は無効です",
]

# Maximum characters to scan in OCR content
_CONTENT_SCAN_LIMIT = 3000


# ============================================================
# Internal Helpers
# ============================================================


def _scan_text_for_keywords(
    text: str,
    keywords: list[str],
    location: str,
) -> list[dict]:
    """Scan text for keyword matches, returning hits with context.

    Args:
        text: Text to scan.
        keywords: Keywords to search for.
        location: "title", "content", or "filename".

    Returns:
        List of hit dicts with keyword, location, position, context.
    """
    if not text:
        return []

    text_upper = text.upper()
    hits: list[dict] = []
    seen_positions: set[tuple[str, int]] = (
        set()
    )  # Avoid duplicate hits at same position

    for kw in keywords:
        kw_upper = kw.upper()
        start = 0
        while True:
            pos = text_upper.find(kw_upper, start)
            if pos == -1:
                break
            # Avoid overlapping hits at same position
            key = (kw_upper, pos)
            if key not in seen_positions:
                seen_positions.add(key)
                # Extract context (30 chars before and after)
                ctx_start = max(0, pos - 30)
                ctx_end = min(len(text), pos + len(kw) + 30)
                context = text[ctx_start:ctx_end]
                if ctx_start > 0:
                    context = "..." + context
                if ctx_end < len(text):
                    context = context + "..."

                hits.append(
                    {
                        "keyword": kw,
                        "location": location,
                        "position": pos,
                        "context": context,
                    }
                )
            start = pos + 1

    return hits


def _scan_text_for_phrases(text: str, phrases: list[str]) -> list[str]:
    """Scan text for full phrase matches.

    Args:
        text: Text to scan.
        phrases: Phrases to search for.

    Returns:
        List of matched phrase strings.
    """
    if not text:
        return []

    text_upper = text.upper()
    matched: list[str] = []
    for phrase in phrases:
        if phrase.upper() in text_upper:
            matched.append(phrase)
    return matched


def _calculate_confidence(
    title_hits: list[dict],
    filename_hits: list[dict],
    content_hits: list[dict],
    phrase_hits: list[str],
    visual_stamp: bool,
) -> float:
    """Calculate overall obsolete detection confidence.

    Scoring rules:
    - Filename hit: 0.80 base
    - Title hit: 0.80 base
    - Content phrase hit: 0.90 base
    - Content single keyword hit: 0.50 base (low — may describe obsolescence procedure)
    - Title + content: 0.95
    - Title + content + visual: 0.99
    - Visual stamp only: 0.85
    """
    has_title = len(title_hits) > 0
    has_filename = len(filename_hits) > 0
    has_content_kw = len(content_hits) > 0
    has_phrase = len(phrase_hits) > 0
    has_visual = visual_stamp

    # Start from 0 and take the maximum applicable score
    confidence = 0.0

    # Individual scores
    if has_filename:
        confidence = max(confidence, 0.80)
    if has_title:
        confidence = max(confidence, 0.80)
    if has_phrase:
        confidence = max(confidence, 0.90)
    if has_content_kw and not has_phrase:
        confidence = max(confidence, 0.50)
    if has_visual:
        confidence = max(confidence, 0.85)

    # Combination boosts
    if (has_title or has_filename) and (has_content_kw or has_phrase):
        confidence = max(confidence, 0.95)
    if (has_title or has_filename) and (has_content_kw or has_phrase) and has_visual:
        confidence = max(confidence, 0.99)

    # Multiple keyword hits in title boost slightly
    if len(title_hits) >= 2:
        confidence = max(confidence, 0.90)

    return round(confidence, 2)


def _build_reasons(
    title_hits: list[dict],
    filename_hits: list[dict],
    content_hits: list[dict],
    phrase_hits: list[str],
    visual_stamp: bool,
    lang: str = "zh-TW",
) -> list[str]:
    """Build human-readable reason strings for the detection result."""
    reasons: list[str] = []

    if filename_hits:
        kws = ", ".join(f"「{h['keyword']}」" for h in filename_hits)
        reasons.append(f"檔名包含 {kws}")

    if title_hits:
        kws = ", ".join(f"「{h['keyword']}」" for h in title_hits)
        reasons.append(f"標題包含 {kws}")

    if phrase_hits:
        phrases_str = ", ".join(f"「{p}」" for p in phrase_hits[:3])
        reasons.append(f"內容包含作廢句型 {phrases_str}")
    elif content_hits:
        kws = ", ".join(f"「{h['keyword']}」" for h in content_hits[:3])
        reasons.append(f"內容包含 {kws}")
        reasons.append("（注意：可能僅為描述作廢流程，非文件本身已作廢）")

    if visual_stamp:
        reasons.append("偵測到作廢印章（視覺偵測）")

    return reasons


# ============================================================
# Main Detection Function
# ============================================================


def detect_obsolete(
    filename: str,
    title: str,
    ocr_content: str,
    file_path: str = "",
    lang: str = "zh-TW",
) -> dict:
    """偵測文件是否為作廢文件。

    Args:
        filename: 原始檔名。
        title: 從 OCR 偵測到的文件標題。
        ocr_content: OCR 轉出的文字內容。
        file_path: 原始檔案路徑（用於視覺印章偵測，目前為預留）。
        lang: 語言（影響偵測原因文字）。

    Returns:
        {
            "is_suspected_obsolete": bool,     # 是否疑似作廢
            "confidence": float,               # 0.0-1.0 信心度
            "reasons": list[str],              # 人可讀的偵測原因列表
            "keyword_hits": list[dict],        # 關鍵字命中明細
            "phrase_hits": list[str],          # 命中的完整句型
            "visual_stamp_detected": bool,     # 視覺印章偵測結果
        }
    """
    # Scan filename
    filename_hits = _scan_text_for_keywords(
        filename, OBSOLETE_KEYWORDS_TITLE, "filename"
    )

    # Scan title
    title_hits = _scan_text_for_keywords(title, OBSOLETE_KEYWORDS_TITLE, "title")

    # Scan content (limited to first N chars)
    content_to_scan = ocr_content[:_CONTENT_SCAN_LIMIT] if ocr_content else ""

    # Check for full phrases first (higher confidence)
    phrase_hits = _scan_text_for_phrases(content_to_scan, OBSOLETE_PHRASES)

    # Check for individual keywords in content
    content_hits = _scan_text_for_keywords(
        content_to_scan, OBSOLETE_KEYWORDS_TITLE, "content"
    )

    # Visual stamp detection — placeholder for future integration
    # TODO: 整合現有 _detect_stamps_by_color() 邏輯，偵測作廢印章
    visual_stamp_detected = False

    # Calculate confidence
    all_keyword_hits = filename_hits + title_hits + content_hits
    confidence = _calculate_confidence(
        title_hits=title_hits,
        filename_hits=filename_hits,
        content_hits=content_hits,
        phrase_hits=phrase_hits,
        visual_stamp=visual_stamp_detected,
    )

    # Build reasons
    reasons = _build_reasons(
        title_hits=title_hits,
        filename_hits=filename_hits,
        content_hits=content_hits,
        phrase_hits=phrase_hits,
        visual_stamp=visual_stamp_detected,
        lang=lang,
    )

    # Threshold: list ALL non-zero results for user confirmation
    # Requirement: 只要檢測結果機率不為0都列出來讓使用者確認
    is_suspected = confidence > 0.0

    return {
        "is_suspected_obsolete": is_suspected,
        "confidence": confidence,
        "reasons": reasons,
        "keyword_hits": all_keyword_hits,
        "phrase_hits": phrase_hits,
        "visual_stamp_detected": visual_stamp_detected,
    }


# ============================================================
# Module Test
# ============================================================

if __name__ == "__main__":
    print("Obsolete Document Detector — Test Cases")
    print("=" * 60)

    # Test 1: Obsolete in title
    r1 = detect_obsolete(
        "SOP-001_作廢.pdf", "品質手冊（作廢）", "這是一份品質手冊的內容"
    )
    print(f"\nTest 1 — Title hit:")
    print(
        f"  Suspected: {r1['is_suspected_obsolete']} (confidence: {r1['confidence']})"
    )
    print(f"  Reasons: {r1['reasons']}")
    assert r1["is_suspected_obsolete"] is True
    assert r1["confidence"] >= 0.80

    # Test 2: Phrase in content
    r2 = detect_obsolete(
        "DOC-002.pdf", "進料檢驗程序", "注意：本文件已作廢，請參閱最新版本。"
    )
    print(f"\nTest 2 — Phrase hit:")
    print(
        f"  Suspected: {r2['is_suspected_obsolete']} (confidence: {r2['confidence']})"
    )
    print(f"  Reasons: {r2['reasons']}")
    assert r2["is_suspected_obsolete"] is True
    assert r2["confidence"] >= 0.90

    # Test 3: Only content keyword (low confidence — describes process)
    r3 = detect_obsolete(
        "QP-003.pdf",
        "文件管制程序",
        "本程序規定作廢文件的管制方式，包含識別、儲存與銷毀。",
    )
    print(f"\nTest 3 — Content keyword only (describing process):")
    print(
        f"  Suspected: {r3['is_suspected_obsolete']} (confidence: {r3['confidence']})"
    )
    print(f"  Reasons: {r3['reasons']}")
    assert r3["is_suspected_obsolete"] is True  # Still flagged but low confidence
    assert r3["confidence"] <= 0.60  # Should be low

    # Test 4: Clean document
    r4 = detect_obsolete(
        "WI-004.pdf", "焊接作業指導書", "本指導書說明焊接作業的標準步驟與注意事項。"
    )
    print(f"\nTest 4 — Clean document:")
    print(
        f"  Suspected: {r4['is_suspected_obsolete']} (confidence: {r4['confidence']})"
    )
    assert r4["is_suspected_obsolete"] is False
    assert r4["confidence"] == 0.0

    # Test 5: English VOID
    r5 = detect_obsolete(
        "DOC-005.pdf", "VOID - Quality Manual", "This document is no longer valid."
    )
    print(f"\nTest 5 — English VOID:")
    print(
        f"  Suspected: {r5['is_suspected_obsolete']} (confidence: {r5['confidence']})"
    )
    assert r5["is_suspected_obsolete"] is True
    assert r5["confidence"] >= 0.80

    # Test 6: Title + Content combo
    r6 = detect_obsolete(
        "已作廢_SOP-006.pdf",
        "生產管制程序（已作廢）",
        "本文件已作廢，自2024年1月起不再適用。",
    )
    print(f"\nTest 6 — Title + Content combo:")
    print(
        f"  Suspected: {r6['is_suspected_obsolete']} (confidence: {r6['confidence']})"
    )
    assert r6["is_suspected_obsolete"] is True
    assert r6["confidence"] >= 0.95

    print("\n" + "=" * 60)
    print("All tests passed! ✅")
