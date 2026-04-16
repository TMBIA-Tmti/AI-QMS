"""
AI-QMS — Regulation Analyzer (LLM-Based)
==========================================

Automatically analyzes crawled regulatory text against ISO 13485 clauses
to generate a RegulationProfile for any country.

This is the "8th country" engine — enables dynamic regulation analysis
for countries beyond the predefined 7.

Flow:
  1. Receive crawled markdown text for a country
  2. Batch ISO 13485 clauses (~10 per LLM call)
  3. LLM maps each clause → MappingStatus (full/partial/na/exceeds)
  4. LLM identifies unique/delta requirements beyond ISO 13485
  5. Build RegulationProfile, save to data/regulations/, register in memory
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Callable, Optional

from src.analysis.compliance_rules import (
    ISO_13485_CHECKLIST,
    RegulationProfile,
    ClauseMapping,
    UniqueRequirement,
    MappingStatus,
    MappingMethod,
    save_crawled_regulation,
    generate_profile_id_from_region,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 24  # clauses per LLM call (71 clauses → 3 batches)
_MAX_CONCURRENT_BATCHES = 3
_MAX_REGULATORY_TEXT_CHARS = 6000  # truncate crawled text per LLM call
_MAX_UNIQUE_REQ_TEXT_CHARS = 8000  # more context for unique requirements


# ============================================================
# Public API
# ============================================================


async def analyze_regulation_with_llm(
    region_name: str,
    crawled_texts: list[dict],
    llm_completion_fn: Callable,
    model: str = "default",
    send_progress_fn: Optional[Callable] = None,
) -> Optional[RegulationProfile]:
    """Analyze crawled regulatory text and generate a RegulationProfile.

    Args:
        region_name: REGION_SITES key, e.g., "新加坡 (Singapore)"
        crawled_texts: List of crawl result dicts, each with keys:
            - region: str
            - agency: str (optional)
            - content_markdown: str
            - url: str (optional)
        llm_completion_fn: LLM completion function matching codebase pattern:
            fn(messages, model, temperature, max_tokens, stream) -> dict
        model: LLM model name
        send_progress_fn: Optional async callback for UI progress messages

    Returns:
        RegulationProfile or None if analysis fails completely
    """
    zh_name, en_name = _extract_region_parts(region_name)
    profile_id = generate_profile_id_from_region(region_name)
    country_code = profile_id.split("_")[0] if "_" in profile_id else profile_id[:2]

    # Combine all crawled texts
    combined_text = _combine_crawled_texts(crawled_texts)
    if not combined_text.strip():
        logger.warning(
            f"No crawled text available for {region_name}, skipping analysis"
        )
        return None

    first_url = ""
    for ct in crawled_texts:
        if ct.get("url"):
            first_url = ct["url"]
            break

    if send_progress_fn:
        await send_progress_fn(
            f"🔍 開始分析 {zh_name} ({en_name}) 法規與 ISO 13485 的重疊度..."
        )

    # ── Step 1: Batch clause mapping ──
    clause_ids = list(ISO_13485_CHECKLIST.keys())
    batches = [
        clause_ids[i : i + _BATCH_SIZE] for i in range(0, len(clause_ids), _BATCH_SIZE)
    ]
    total_batches = len(batches)

    iso_mapped: dict[str, ClauseMapping] = {}
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if send_progress_fn:
        await send_progress_fn(
            f"🔍 並行分析 {total_batches} 批 ISO 13485 條款 "
            f"(每批 {_BATCH_SIZE} 條，共 {len(clause_ids)} 條)..."
        )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_BATCHES)

    async def _run_batch(batch_idx: int, batch: list[str]) -> None:
        batch_clauses = [
            {
                "clause_id": cid,
                "title": ISO_13485_CHECKLIST.get(cid, {}).get("title", ""),
                "audit_question": ISO_13485_CHECKLIST.get(cid, {}).get(
                    "audit_question", ""
                ),
            }
            for cid in batch
        ]

        messages = _build_clause_batch_prompt(
            batch_clauses, combined_text[:_MAX_REGULATORY_TEXT_CHARS], zh_name, en_name
        )

        try:
            async with semaphore:
                response = await asyncio.to_thread(
                    llm_completion_fn,
                    messages=messages,
                    model=model,
                    temperature=0.1,
                    max_tokens=16384,
                    stream=False,
                )

            response_text = response.get("content", "")
            usage = response.get("usage", {})
            _accumulate_usage(total_usage, usage)

            if (
                not response_text
                or response_text.startswith("[ERROR]")
                or response.get("all_failed")
            ):
                logger.warning(
                    f"LLM call failed for batch {batch_idx}: "
                    f"{response_text[:200] if response_text else 'empty'}"
                )
                _fill_batch_fallback(iso_mapped, batch)
                return

            parsed = _parse_json_from_response(response_text)
            if parsed and isinstance(parsed, list):
                for item in parsed:
                    cid = item.get("clause_id", "")
                    if cid and cid in ISO_13485_CHECKLIST:
                        iso_mapped[cid] = ClauseMapping(
                            iso_clause=cid,
                            status=_parse_status(item.get("status", "na")),
                            regulation_ref=item.get("regulation_ref", ""),
                            rationale_en=item.get("rationale_en", ""),
                            rationale_zh=item.get("rationale_zh", ""),
                            method=MappingMethod.LLM_ANALYSIS,
                            confidence=min(
                                1.0, max(0.0, float(item.get("confidence", 0.5)))
                            ),
                            notes=item.get("notes", ""),
                            original_text=item.get("original_text", ""),
                            original_lang=item.get("original_lang", ""),
                            english_translation=item.get("english_translation", ""),
                            semantic_note=item.get("semantic_note", ""),
                        )
            else:
                logger.warning(
                    f"Failed to parse JSON for batch {batch_idx}, using fallback"
                )
                _fill_batch_fallback(iso_mapped, batch)

            if send_progress_fn:
                await send_progress_fn(
                    f"✅ 批次 {batch_idx}/{total_batches} 完成 ({batch[0]}–{batch[-1]})"
                )

        except Exception as e:
            logger.error(f"Exception during clause batch {batch_idx}: {e}")
            _fill_batch_fallback(iso_mapped, batch)

    await asyncio.gather(
        *[_run_batch(idx, batch) for idx, batch in enumerate(batches, 1)]
    )

    # Fill any missing clauses with NA
    for cid in clause_ids:
        if cid not in iso_mapped:
            iso_mapped[cid] = ClauseMapping(
                iso_clause=cid,
                status=MappingStatus.NOT_APPLICABLE,
                regulation_ref="",
                rationale_en="No mapping data available",
                rationale_zh="無可用的映射資料",
                method=MappingMethod.LLM_ANALYSIS,
                confidence=0.1,
            )

    # ── Step 2: Identify unique requirements ──
    if send_progress_fn:
        await send_progress_fn(f"🔍 識別 {zh_name} ({en_name}) 獨有的法規要求...")

    unique_reqs: list[UniqueRequirement] = []
    try:
        messages = _build_unique_requirements_prompt(
            combined_text[:_MAX_UNIQUE_REQ_TEXT_CHARS], zh_name, en_name, profile_id
        )
        response = await asyncio.to_thread(
            llm_completion_fn,
            messages=messages,
            model=model,
            temperature=0.1,
            max_tokens=8192,
            stream=False,
        )
        response_text = response.get("content", "")
        usage = response.get("usage", {})
        _accumulate_usage(total_usage, usage)

        if (
            response_text
            and not response_text.startswith("[ERROR]")
            and not response.get("all_failed")
        ):
            parsed = _parse_json_from_response(response_text)
            if parsed and isinstance(parsed, list):
                for idx, item in enumerate(parsed, 1):
                    req_id = item.get("req_id", f"{profile_id}-{idx:03d}")
                    unique_reqs.append(
                        UniqueRequirement(
                            req_id=req_id,
                            regulation_ref=item.get("regulation_ref", ""),
                            title_en=item.get("title_en", ""),
                            title_zh=item.get("title_zh", ""),
                            requirement_en=item.get("requirement_en", ""),
                            requirement_zh=item.get("requirement_zh", ""),
                            related_iso_clauses=item.get("related_iso_clauses", []),
                            audit_impact=item.get("audit_impact", "major"),
                            audit_question_en=item.get("audit_question_en", ""),
                            audit_question_zh=item.get("audit_question_zh", ""),
                            expected_evidence=item.get("expected_evidence", []),
                            rationale_en=item.get("rationale_en", ""),
                            rationale_zh=item.get("rationale_zh", ""),
                            method=MappingMethod.LLM_ANALYSIS,
                            confidence=min(
                                1.0, max(0.0, float(item.get("confidence", 0.5)))
                            ),
                            original_text=item.get("original_text", ""),
                            original_lang=item.get("original_lang", ""),
                            english_translation=item.get("english_translation", ""),
                            semantic_note=item.get("semantic_note", ""),
                        )
                    )
    except Exception as e:
        logger.error(f"Exception during unique requirements analysis: {e}")

    # ── Step 3: Build and save profile ──
    profile = RegulationProfile(
        regulation_id=profile_id,
        name_en=f"{en_name} Medical Device QMS Regulation",
        name_zh=f"{zh_name}醫療器材品質管理法規",
        country=country_code,
        country_name_en=en_name,
        country_name_zh=zh_name,
        source="crawled",
        source_url=first_url,
        last_updated=datetime.now().strftime("%Y-%m-%d"),
        iso_mapped=iso_mapped,
        unique_requirements=unique_reqs,
    )

    try:
        filepath = save_crawled_regulation(profile)
        logger.info(
            f"RegulationProfile saved: {profile_id} → {filepath} "
            f"({len(iso_mapped)} clauses, {len(unique_reqs)} unique reqs, "
            f"{total_usage.get('total_tokens', 0)} tokens used)"
        )
    except Exception as e:
        logger.error(f"Failed to save RegulationProfile for {profile_id}: {e}")

    if send_progress_fn:
        mapped_count = sum(
            1 for m in iso_mapped.values() if m.status != MappingStatus.NOT_APPLICABLE
        )
        await send_progress_fn(
            f"✅ {zh_name} ({en_name}) 法規分析完成：\n"
            f"  • ISO 13485 對應：{mapped_count}/{len(clause_ids)} 條\n"
            f"  • 獨有要求：{len(unique_reqs)} 項\n"
            f"  • Token 用量：{total_usage.get('total_tokens', 0):,}"
        )

    return profile


# ============================================================
# Prompt Builders
# ============================================================


def _build_clause_batch_prompt(
    clauses: list[dict],
    regulatory_text: str,
    country_zh: str,
    country_en: str,
) -> list[dict]:
    """Build LLM messages for analyzing a batch of ISO 13485 clauses."""

    clause_list = "\n".join(f"- {c['clause_id']}: {c['title']}" for c in clauses)
    clause_ids_str = ", ".join(c["clause_id"] for c in clauses)

    system_prompt = (
        "You are a senior medical device regulatory affairs specialist with extensive "
        "experience in ISO 13485:2016 audits, MDSAP (Medical Device Single Audit Program) "
        "multi-country assessments, and cross-jurisdictional QMS comparisons. "
        "You have conducted regulatory audits in Asia-Pacific, EU, and North America.\n\n"
        "Your task: Determine how a country's medical device regulation maps to ISO 13485 "
        "clauses. Apply the MDSAP audit principle: distinguish between regulations that "
        "MENTION a requirement versus those that SUBSTANTIVELY IMPLEMENT it.\n\n"
        "CRITICAL ANALYSIS RULES (from ISO 13485:2016 audit practice):\n"
        "1. Language plausibility ≠ legal correctness: a regulation may use similar "
        "   terminology but differ in scope, applicability threshold, or enforcement.\n"
        "2. Always cite the SPECIFIC article or section from the provided regulatory text.\n"
        "3. If a regulatory concept is functionally equivalent but uses different terminology "
        "   (e.g., 'product dossier' vs 'design history file'), note this as 'full' with a "
        "   semantic_note explaining the terminology difference.\n"
        "4. 'partial' = regulation covers the intent but omits ≥1 substantive sub-requirement.\n"
        "5. Set confidence < 0.4 when the crawled text is insufficient — do NOT infer from "
        "   general regulatory knowledge; base analysis ONLY on the provided text.\n\n"
        "STEP-BY-STEP REASONING for each clause:\n"
        "  Step 1: Search the regulatory text for explicit mention of the clause topic.\n"
        "  Step 2: Check if functionally equivalent requirements exist under different terms.\n"
        "  Step 3: Assess completeness — does it cover all sub-requirements of the clause?\n"
        "  Step 4: Assign status and calibrate confidence based on text evidence quality.\n\n"
        "For each clause, determine the mapping status:\n"
        '- "full": Regulation substantively covers ALL requirements of the ISO 13485 clause\n'
        '- "partial": Covers the main intent but omits ≥1 sub-requirement or has scope gaps\n'
        '- "exceeds": Has STRICTER or ADDITIONAL requirements beyond ISO 13485\n'
        '- "na": No evidence of coverage in the provided regulatory text\n\n'
        "Output ONLY a valid JSON array. No markdown, no explanation outside JSON.\n"
        "Each element must have these fields:\n"
        "{\n"
        '  "clause_id": "4.1",\n'
        '  "status": "full|partial|na|exceeds",\n'
        '  "regulation_ref": "Specific Article/Section reference (e.g., Art. 15, §3.2)",\n'
        '  "rationale_en": "Evidence-based explanation citing specific regulatory text",\n'
        '  "rationale_zh": "中文說明，引用具體法規條文",\n'
        '  "original_text": "Direct quote from regulatory text in native language",\n'
        "  \"original_lang\": \"Language code (e.g., 'en', 'zh', 'ko', 'ms', 'th')\",\n"
        '  "english_translation": "English translation if original is not English",\n'
        '  "semantic_note": "Terminology differences, scope nuances, implementation gaps",\n'
        '  "confidence": 0.8\n'
        "}\n\n"
        "Example output:\n"
        "[\n"
        "  {\n"
        '    "clause_id": "4.1",\n'
        '    "status": "full",\n'
        '    "regulation_ref": "Section 3, Article 5 of Medical Device Act",\n'
        '    "rationale_en": "Article 5 explicitly requires establishment of a QMS covering '
        'all product lifecycle phases, directly equivalent to ISO 13485:2016 Clause 4.1 scope. '
        'All four sub-requirements (processes, interactions, outsourced processes, documentation) '
        'are addressed in Articles 5-7.",\n'
        '    "rationale_zh": "第5條明確要求建立涵蓋產品全生命週期的品質管理系統，直接對應 ISO 13485:2016 第4.1條，'
        '四項子要求均在第5至7條中得到涵蓋。",\n'
        '    "original_text": "제조업자는 품질경영시스템을 수립하고...",\n'
        '    "original_lang": "ko",\n'
        '    "english_translation": "Manufacturers shall establish a quality management system '
        'covering all phases of the product lifecycle...",\n'
        '    "semantic_note": "Uses \'lifecycle QMS\' terminology vs ISO 13485 \'product realization\'; '
        'functionally equivalent. Outsourced process control (4.1.6) confirmed in Article 7.",\n'
        '    "confidence": 0.88\n'
        "  }\n"
        "]"
    )

    user_prompt = (
        f"## Country: {country_zh} ({country_en})\n\n"
        f"## ISO 13485 Clauses to Analyze:\n{clause_list}\n\n"
        f"## Crawled Regulatory Text from {country_en}:\n"
        f"```\n{regulatory_text}\n```\n\n"
        f"Analyze how {country_en}'s regulation substantively covers each of these "
        f"ISO 13485 clauses: {clause_ids_str}\n\n"
        f"IMPORTANT: Base ALL analysis strictly on the regulatory text provided above. "
        f"Do NOT rely on general knowledge about {country_en}'s regulatory system.\n"
        f"For each clause, follow the 4-step reasoning process in your instructions.\n"
        f"If the text lacks sufficient evidence for a clause, "
        f'set status to "na", confidence to 0.25, and note "Insufficient evidence in crawled text".\n\n'
        f"Output the JSON array now:"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_unique_requirements_prompt(
    regulatory_text: str,
    country_zh: str,
    country_en: str,
    profile_id: str,
) -> list[dict]:
    """Build LLM messages for identifying unique/delta requirements."""

    system_prompt = (
        "You are a senior medical device regulatory affairs specialist with MDSAP "
        "multi-country audit experience and deep expertise in identifying country-specific "
        "regulatory delta requirements beyond ISO 13485.\n\n"
        "Your task: Identify requirements in a country's regulation that go BEYOND "
        "what ISO 13485:2016 requires. These are the DELTA items — country-specific "
        "requirements that a manufacturer fully certified to ISO 13485 would STILL need "
        "to satisfy separately for market access in this country.\n\n"
        "CRITICAL ANALYSIS RULES:\n"
        "1. Language plausibility ≠ legal obligation: a country's regulation may "
        "   MENTION a concept (e.g., UDI, PSUR) without imposing a substantive, "
        "   enforceable requirement. Do NOT flag a mention as a unique requirement.\n"
        "2. Base ALL analysis STRICTLY on the regulatory text provided. Do NOT "
        "   infer requirements from general knowledge about this country's regulatory "
        "   system — that knowledge may be outdated or jurisdiction-incorrect.\n"
        "3. Confidence calibration (base on text evidence quality, not assumption):\n"
        "   - 0.8-1.0: Explicit statutory article with clear obligation and penalty\n"
        "   - 0.5-0.7: Implied requirement or indirect reference with partial evidence\n"
        "   - 0.3-0.5: Regulatory intent unclear; text evidence limited\n"
        "   - < 0.3: Very limited crawled text — flag as insufficient evidence\n\n"
        "ANALYSIS APPROACH (apply for each unique requirement found):\n"
        "1. First determine: Is this requirement already covered by ISO 13485?\n"
        "   If YES → skip it (not a delta item).\n"
        "2. Check: Does this requirement impose a specific procedural, documentary, or "
        "   timeline obligation not present in ISO 13485?\n"
        "3. Assess audit_impact: 'critical' = market access blocked without it; "
        "   'major' = audit finding likely; 'minor' = best practice gap.\n"
        "4. Provide specific, auditable expected_evidence — what a MDSAP auditor "
        "   would physically inspect to verify compliance.\n\n"
        "Common categories of unique requirements:\n"
        "- Country-specific device registration/listing/notification requirements\n"
        "- Local authorized representative or agent requirements\n"
        "- Language/labeling requirements (local language mandatory fields)\n"
        "- Unique adverse event/vigilance reporting timelines (e.g., 15 vs 30 days)\n"
        "- Country-specific clinical data or performance study requirements\n"
        "- Post-market surveillance reporting frequency unique to the country\n"
        "- Import/export permits or customs documentation\n"
        "- Unique classification system or risk class mapping differences\n"
        "- Periodic safety update report (PSUR) requirements\n"
        "- Unique UDI/device traceability system requirements\n\n"
        "Output ONLY a valid JSON array. No markdown, no explanation outside JSON.\n"
        "Each element must have these fields:\n"
        "{\n"
        f'  "req_id": "{profile_id}-001",\n'
        '  "regulation_ref": "Article/Section reference",\n'
        '  "title_en": "Short English title",\n'
        '  "title_zh": "中文簡短標題",\n'
        '  "requirement_en": "Full requirement description in English",\n'
        '  "requirement_zh": "完整的中文需求描述",\n'
        '  "related_iso_clauses": ["4.2.3", "7.1"],\n'
        '  "audit_impact": "critical|major|minor",\n'
        '  "audit_question_en": "Audit question to verify compliance",\n'
        '  "audit_question_zh": "用於驗證合規性的稽核問題",\n'
        '  "expected_evidence": ["Document or record expected"],\n'
        '  "rationale_en": "Why this is unique to this country",\n'
        '  "rationale_zh": "為何此要求為該國獨有",\n'
        '  "original_text": "Original regulatory text in native language",\n'
        '  "original_lang": "Language code",\n'
        '  "english_translation": "English translation if not English",\n'
        '  "semantic_note": "Practical impact on manufacturers",\n'
        '  "confidence": 0.75\n'
        "}\n\n"
        "If no unique requirements are found, output an empty array: []\n"
        "Typically, most countries have 3-10 unique requirements beyond ISO 13485.\n"
        "If the crawled text is insufficient to identify requirements confidently, "
        "set confidence < 0.4 and note the limitation in semantic_note."
    )

    user_prompt = (
        f"## Country: {country_zh} ({country_en})\n\n"
        f"## Crawled Regulatory Text:\n"
        f"```\n{regulatory_text}\n```\n\n"
        f"IMPORTANT: Base ALL analysis STRICTLY on the regulatory text provided above. "
        f"Do NOT rely on general knowledge about {country_en}'s regulatory system — "
        f"use only requirements explicitly stated in the crawled text.\n"
        f"If the text lacks sufficient evidence for a specific requirement, "
        f'set confidence below 0.4 and note "Insufficient evidence in crawled text" '
        f"in semantic_note.\n\n"
        f"Identify ALL requirements in {country_en}'s medical device regulation "
        f"that go BEYOND ISO 13485. Focus on country-specific requirements that "
        f"a manufacturer certified to ISO 13485 would still need to address "
        f"separately for {country_en} market access.\n\n"
        f'Use "{profile_id}-NNN" format for req_id (e.g., {profile_id}-001).\n\n'
        f"Output the JSON array now:"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ============================================================
# Parsing Helpers
# ============================================================


def _parse_json_from_response(text: str) -> list | dict | None:
    """Extract and parse JSON from LLM response text.

    Handles:
    - Pure JSON
    - JSON wrapped in ```json ... ``` code blocks
    - JSON preceded/followed by explanatory text
    """
    if not text:
        return None

    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    code_block_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON array in text
    bracket_match = re.search(r"\[[\s\S]*\]", text)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in text
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        try:
            result = json.loads(brace_match.group(0))
            # Wrap single object in list for consistency
            return [result] if isinstance(result, dict) else result
        except json.JSONDecodeError:
            pass

    logger.warning(f"Failed to parse JSON from response: {text[:200]}...")
    return None


def _parse_status(status_str: str) -> MappingStatus:
    """Parse a status string into MappingStatus enum."""
    status_map = {
        "full": MappingStatus.FULL,
        "partial": MappingStatus.PARTIAL,
        "na": MappingStatus.NOT_APPLICABLE,
        "not_applicable": MappingStatus.NOT_APPLICABLE,
        "exceeds": MappingStatus.EXCEEDS,
    }
    return status_map.get(status_str.lower().strip(), MappingStatus.NOT_APPLICABLE)


def _extract_region_parts(region_name: str) -> tuple[str, str]:
    """Extract (zh_name, en_name) from region format like '新加坡 (Singapore)'.

    Returns:
        Tuple of (Chinese name, English name)
    """
    if " (" in region_name and region_name.endswith(")"):
        zh_name = region_name.split(" (")[0]
        en_name = region_name.split("(")[1].rstrip(")")
        return zh_name, en_name
    return region_name, region_name


def _combine_crawled_texts(crawled_texts: list[dict]) -> str:
    """Combine multiple crawled text entries into a single regulatory document."""
    parts = []
    for ct in crawled_texts:
        if not ct.get("content_markdown"):
            continue
        agency = ct.get("agency", "")
        url = ct.get("url", "")
        header = f"### Source: {agency}" if agency else "### Source"
        if url:
            header += f" ({url})"
        parts.append(f"{header}\n{ct['content_markdown']}")
    return "\n\n---\n\n".join(parts)


def _fill_batch_fallback(
    iso_mapped: dict[str, ClauseMapping],
    batch: list[str],
) -> None:
    """Fill a batch of clauses with NA fallback when LLM fails."""
    for cid in batch:
        if cid not in iso_mapped:
            iso_mapped[cid] = ClauseMapping(
                iso_clause=cid,
                status=MappingStatus.NOT_APPLICABLE,
                regulation_ref="",
                rationale_en="LLM analysis failed for this clause",
                rationale_zh="此條款的 LLM 分析失敗",
                method=MappingMethod.LLM_ANALYSIS,
                confidence=0.1,
            )


def _accumulate_usage(total: dict, usage: dict) -> None:
    """Accumulate token usage from an LLM response."""
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        total[key] = total.get(key, 0) + usage.get(key, 0)
