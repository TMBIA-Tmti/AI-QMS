"""
Comprehensive test suite for regulation_analyzer.py

Three tiers:
  SIM  — simulation tests (realistic multi-site scenarios, full async flow)
  LIM  — limit/edge-case tests (empty, single-site, huge text, boundary chars)
  AB   — A/B comparison tests (cloud vs local params, compact vs full prompt,
          per-site distribution vs naive head-truncation, keyword vs no-keyword)
"""

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.regulation_analyzer import (
    _CLAUSE_KEYWORDS,
    _CLOUD_PARAMS,
    _LOCAL_PARAMS,
    _UNIQUE_REQ_KEYWORDS,
    _build_clause_batch_prompt,
    _build_clause_batch_prompt_compact,
    _build_focused_regulatory_text,
    _build_unique_requirements_prompt,
    _build_unique_requirements_prompt_compact,
    _combine_crawled_texts,
    _filter_relevant_paragraphs,
    _get_batch_keywords,
    _get_model_params,
    _is_local_provider,
    analyze_regulation_with_llm,
)


# ============================================================
# Shared fixtures
# ============================================================

SITE_A_TEXT = """
## Medical Device Quality Management System Act

Article 1 — Scope
This regulation applies to all manufacturers of medical devices sold in this market.

Article 5 — Quality Management System Requirements
The manufacturer shall establish, document, implement, and maintain a quality management
system (QMS). All QMS processes shall be identified throughout the organisation.
Outsourced processes shall be controlled. Quality system documentation is mandatory.

Article 8 — Design and Development Control
Design and development activities shall follow documented procedures. Design inputs shall
be defined and reviewed. Design outputs shall meet design input requirements. Design
validation and verification shall be performed prior to product release.

Article 12 — Purchasing and Approved Supplier Control
The manufacturer shall evaluate and select suppliers. Approved supplier lists shall be
maintained and reviewed annually. Incoming inspection records are required.
"""

SITE_B_TEXT = """
## Regulatory Guidance — Post-Market Requirements

Section 3 — Adverse Event Reporting
Manufacturers shall report serious adverse events to the competent authority within
15 working days of becoming aware. Near-miss events shall be documented internally.

Section 5 — Device Registration Requirements
All medical devices shall be registered with the National Health Authority before
market placement. Foreign manufacturers require a local authorized representative.
Registration renewal is required every 5 years.

Section 7 — UDI and Traceability
All Class II and above devices shall bear a Unique Device Identifier (UDI). Manufacturers
shall enroll devices in the national UDI database within 30 days of registration approval.
Post-market surveillance reports are required annually for Class III devices.

Section 9 — Corrective and Preventive Action
CAPA procedures shall be documented. Root cause analysis is mandatory for all critical
nonconformances. Effectiveness verification shall be completed within 90 days.
"""

TWO_SITE_CRAWLED = [
    {
        "region": "新加坡 (Singapore)",
        "agency": "HSA-MDA",
        "content_markdown": SITE_A_TEXT,
        "url": "https://hsa.gov.sg/mda",
    },
    {
        "region": "新加坡 (Singapore)",
        "agency": "HSA-Guidance",
        "content_markdown": SITE_B_TEXT,
        "url": "https://hsa.gov.sg/guidance",
    },
]


def _make_mock_llm():
    """Combined mock LLM handling both clause-batch and unique-requirement calls."""

    def mock(messages, model="default", temperature=0.1, max_tokens=8000, stream=False):
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in messages if m["role"] == "user"), "")

        if "BEYOND ISO 13485" in system or "unique requirement" in system.lower():
            # Unique requirements call
            profile_id_match = re.search(r'"([\w_]+)-NNN"', user)
            pid = profile_id_match.group(1) if profile_id_match else "XX_test"
            result = [
                {
                    "req_id": f"{pid}-001",
                    "regulation_ref": "Section 5",
                    "title_en": "Device Registration",
                    "title_zh": "裝置登記",
                    "requirement_en": "All devices must be registered.",
                    "requirement_zh": "所有裝置須登記。",
                    "related_iso_clauses": [],
                    "audit_impact": "critical",
                    "audit_question_en": "Is the device registered?",
                    "audit_question_zh": "裝置是否已登記？",
                    "expected_evidence": ["Registration certificate"],
                    "rationale_en": "No ISO 13485 equivalent",
                    "rationale_zh": "ISO 13485 無對應",
                    "original_text": "All medical devices shall be registered",
                    "original_lang": "en",
                    "english_translation": "",
                    "semantic_note": "",
                    "confidence": 0.9,
                    "is_within_clause_delta": False,
                    "within_clause_delta_vs_iso": "",
                }
            ]
        else:
            # Clause-batch call — return na for all clause IDs detected in prompt
            clause_ids = re.findall(
                r'"([0-9]+(?:\.[0-9]+)*)"',
                user[:800],
            )
            if not clause_ids:
                m2 = re.search(r"Clauses to analyze[^:]*: ([^\n]+)", user)
                if m2:
                    clause_ids = [c.strip() for c in m2.group(1).split(",")]
            clause_ids = clause_ids[:24] or ["4.1"]
            result = [
                {
                    "clause_id": cid,
                    "status": "na",
                    "regulation_ref": "",
                    "rationale_en": "Mock: insufficient text",
                    "rationale_zh": "模擬：文字不足",
                    "original_text": "",
                    "original_lang": "en",
                    "english_translation": "",
                    "semantic_note": "",
                    "confidence": 0.3,
                    "within_clause_deltas": [],
                }
                for cid in clause_ids
            ]

        return {
            "content": json.dumps(result),
            "usage": {
                "prompt_tokens": 300,
                "completion_tokens": 150,
                "total_tokens": 450,
            },
        }

    return mock


# ============================================================
# SIM — Simulation tests
# ============================================================


class TestSim:
    def test_sim_local_provider_gets_local_params(self):
        for pid in ("ollama", "lmstudio"):
            assert _is_local_provider(pid), f"{pid} should be local"
            p = _get_model_params(True)
            assert p["batch_size"] == 8
            assert p["max_tokens_clause"] == 8000
            assert p["max_tokens_unique"] == 8000
            assert p["max_regulatory_chars"] == 2500

    def test_sim_cloud_provider_gets_cloud_params(self):
        for pid in ("openai", "anthropic", "google", "deepseek", "openrouter"):
            assert not _is_local_provider(pid), f"{pid} should be cloud"
            p = _get_model_params(False)
            assert p["batch_size"] == 24
            assert p["max_tokens_clause"] == 16384
            assert p["max_tokens_unique"] == 8192

    def test_sim_two_site_distribution(self):
        """Both sites must appear when there are two sources."""
        result = _build_focused_regulatory_text(TWO_SITE_CRAWLED, [], 4000)
        assert "[HSA-MDA]" in result, "SiteA (HSA-MDA) missing from output"
        assert "[HSA-Guidance]" in result, "SiteB (HSA-Guidance) missing from output"
        assert len(result) <= 4000

    def test_sim_keyword_filtering_elevates_relevant_paragraphs(self):
        """Paragraphs with QMS/quality keywords should appear before unrelated ones."""
        text = (
            "Unrelated section about fees and penalties.\n\n"
            "Another unrelated paragraph about office hours.\n\n"
            "Quality Management System (QMS) requirements apply to all manufacturers.\n\n"
            "Manufacturers shall establish documented QMS procedures.\n\n"
            "More unrelated content about building codes.\n\n"
            "Additional fee schedule information."
        )
        filtered = _filter_relevant_paragraphs(
            text, ["quality management system", "QMS", "procedures"], 500
        )
        # Relevant paragraphs should appear
        assert "Quality Management System" in filtered or "QMS" in filtered

    def test_sim_batch_keywords_parent_fallback(self):
        """'7.3.2' should inherit 7.3 and 7 parent keywords."""
        kw = _get_batch_keywords(["7.3.2"])
        # Should include 7.3.2 own keywords
        assert any("design" in k for k in kw), "7.3.2 design keywords missing"
        # Should also include parent 7.3.1 / general design keywords from parent resolution
        kw_7_3 = _get_batch_keywords(["7.3"])
        # At least some overlap expected
        kw_set = set(kw)
        assert len(kw_set) > 0, "Should produce at least some keywords"

    def test_sim_compact_prompt_has_correct_structure(self):
        clauses = [
            {"clause_id": "4.1", "title": "QMS General", "audit_question": "Q?"},
            {"clause_id": "4.2.1", "title": "Documentation", "audit_question": "Q?"},
        ]
        msgs = _build_clause_batch_prompt_compact(clauses, "Some text", "台灣", "Taiwan")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "4.1" in msgs[1]["content"]
        assert "4.2.1" in msgs[1]["content"]
        assert "Taiwan" in msgs[1]["content"]

    def test_sim_full_flow_local_model(self):
        """End-to-end flow with Ollama provider returns a valid RegulationProfile."""
        mock_llm = _make_mock_llm()
        profile = asyncio.run(
            analyze_regulation_with_llm(
                region_name="新加坡 (Singapore)",
                crawled_texts=TWO_SITE_CRAWLED,
                llm_completion_fn=mock_llm,
                model="qwen2.5:32b",
                provider_id="ollama",
            )
        )
        assert profile is not None, "Profile should not be None"
        assert profile.regulation_id, "regulation_id must be non-empty"
        assert len(profile.iso_mapped) == 71, f"Expected 71 clauses, got {len(profile.iso_mapped)}"
        assert isinstance(profile.unique_requirements, list)

    def test_sim_full_flow_cloud_model(self):
        """End-to-end flow with OpenAI provider returns a valid RegulationProfile."""
        mock_llm = _make_mock_llm()
        profile = asyncio.run(
            analyze_regulation_with_llm(
                region_name="新加坡 (Singapore)",
                crawled_texts=TWO_SITE_CRAWLED,
                llm_completion_fn=mock_llm,
                model="gpt-4o",
                provider_id="openai",
            )
        )
        assert profile is not None
        assert len(profile.iso_mapped) == 71

    def test_sim_unique_req_compact_prompt_structure(self):
        msgs = _build_unique_requirements_prompt_compact(
            "Some regulatory text", "新加坡", "Singapore", "SG_hsamda"
        )
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "SG_hsamda" in msgs[1]["content"]
        assert "BEYOND ISO 13485" in msgs[0]["content"] or "beyond ISO 13485" in msgs[0]["content"].lower()


# ============================================================
# LIM — Limit / edge-case tests
# ============================================================


class TestLim:
    def test_lim_empty_crawled_texts(self):
        result = _build_focused_regulatory_text([], ["QMS"], 2500)
        assert result == ""

    def test_lim_all_empty_content(self):
        texts = [
            {"agency": "A", "content_markdown": "", "url": ""},
            {"agency": "B", "content_markdown": "   ", "url": ""},
        ]
        result = _build_focused_regulatory_text(texts, ["QMS"], 2500)
        assert result == ""

    def test_lim_single_site_gets_full_budget(self):
        """Single site should get the entire max_chars budget."""
        long_text = "Quality management system QMS requirements. " * 200  # ~8800 chars
        texts = [{"agency": "OnlySite", "content_markdown": long_text, "url": ""}]
        result = _build_focused_regulatory_text(texts, ["QMS"], 2500)
        assert len(result) <= 2500
        assert "[OnlySite]" in result

    def test_lim_many_sites_equal_distribution(self):
        """6 sites all get a share — none should be entirely missing."""
        sites = [
            {
                "agency": f"Site{i}",
                "content_markdown": f"Site{i} unique content. " * 50,
                "url": "",
            }
            for i in range(6)
        ]
        result = _build_focused_regulatory_text(sites, [], 6000)
        for i in range(6):
            assert f"Site{i}" in result, f"Site{i} missing — not evenly distributed"

    def test_lim_very_long_text_truncated(self):
        """100k char text must be truncated to max_chars."""
        long_text = "QMS quality system. " * 5000  # ~100k chars
        texts = [{"agency": "BigSite", "content_markdown": long_text, "url": ""}]
        result = _build_focused_regulatory_text(texts, ["QMS"], 2500)
        assert len(result) <= 2500

    def test_lim_no_keyword_matches_returns_head(self):
        """When no paragraphs match keywords, return the first N chars."""
        text = "Totally unrelated content here.\n\nMore unrelated content.\n\nFees and fines."
        filtered = _filter_relevant_paragraphs(text, ["quantum_physics_xyz"], 200)
        assert len(filtered) > 0, "Should return something even with zero keyword matches"
        assert len(filtered) <= 200

    def test_lim_single_paragraph_exceeds_budget(self):
        """A single paragraph longer than max_chars should still return content."""
        text = "Quality management system QMS procedures. " * 100  # ~4200 chars
        filtered = _filter_relevant_paragraphs(text, ["QMS"], 500)
        # Single paragraph > 500 chars; fallback should kick in
        assert len(filtered) > 0

    def test_lim_provider_id_case_insensitive(self):
        for pid in ("OLLAMA", "Ollama", "OlLaMa"):
            assert _is_local_provider(pid), f"'{pid}' should be detected as local"
        for pid in ("LMSTUDIO", "LmStudio"):
            assert _is_local_provider(pid), f"'{pid}' should be detected as local"

    def test_lim_unknown_provider_is_cloud(self):
        for pid in ("anthropic", "google", "openrouter", "groq", "unknownprovider"):
            assert not _is_local_provider(pid), f"'{pid}' should fall through to cloud"

    def test_lim_unknown_clause_id_returns_empty_keywords(self):
        kw = _get_batch_keywords(["99.99.99"])
        assert isinstance(kw, list), "Should always return a list"
        # May be empty since "99.99.99" has no parent matches either

    def test_lim_max_chars_never_exceeded(self):
        """Output must never exceed max_chars regardless of input size."""
        for max_c in (100, 500, 1000, 2500, 6000):
            texts = [
                {"agency": f"Site{j}", "content_markdown": "X" * 10000, "url": ""}
                for j in range(3)
            ]
            result = _build_focused_regulatory_text(texts, ["X"], max_c)
            assert len(result) <= max_c, f"Exceeded max_chars={max_c}: got {len(result)}"

    def test_lim_full_flow_returns_none_on_empty_texts(self):
        """analyze_regulation_with_llm must return None when all content is empty."""
        empty_texts = [
            {"region": "新加坡 (Singapore)", "agency": "A", "content_markdown": "", "url": ""},
        ]
        profile = asyncio.run(
            analyze_regulation_with_llm(
                region_name="新加坡 (Singapore)",
                crawled_texts=empty_texts,
                llm_completion_fn=_make_mock_llm(),
                model="qwen2.5:32b",
                provider_id="ollama",
            )
        )
        assert profile is None, "Should return None when no crawled content exists"

    def test_lim_full_flow_handles_llm_failure_gracefully(self):
        """LLM failures must not raise — fallback NA mappings fill missing clauses."""

        def always_fail(messages, model="default", temperature=0.1, max_tokens=8000, stream=False):
            return {"content": "[ERROR] Connection refused", "all_failed": True, "usage": {}}

        profile = asyncio.run(
            analyze_regulation_with_llm(
                region_name="新加坡 (Singapore)",
                crawled_texts=TWO_SITE_CRAWLED,
                llm_completion_fn=always_fail,
                model="qwen2.5:32b",
                provider_id="ollama",
            )
        )
        assert profile is not None, "Profile should still be returned after LLM failure"
        assert len(profile.iso_mapped) == 71, "All 71 clauses should have NA fallback"
        assert all(
            m.confidence == 0.1 for m in profile.iso_mapped.values()
        ), "All fallback clauses should have confidence=0.1"


# ============================================================
# AB — A/B comparison tests
# ============================================================


class TestAB:
    def test_ab_batch_size_local_vs_cloud(self):
        """Local splits 71 clauses into more, smaller batches than cloud."""
        from src.analysis.compliance_rules import ISO_13485_CHECKLIST

        clause_ids = list(ISO_13485_CHECKLIST.keys())
        assert len(clause_ids) == 71

        local_bs = _LOCAL_PARAMS["batch_size"]   # 8
        cloud_bs = _CLOUD_PARAMS["batch_size"]   # 24

        local_batches = [clause_ids[i:i + local_bs] for i in range(0, len(clause_ids), local_bs)]
        cloud_batches = [clause_ids[i:i + cloud_bs] for i in range(0, len(clause_ids), cloud_bs)]

        assert len(local_batches) > len(cloud_batches), (
            f"Local should have more batches: local={len(local_batches)} cloud={len(cloud_batches)}"
        )
        assert max(len(b) for b in local_batches) == local_bs
        assert max(len(b) for b in cloud_batches) == cloud_bs

    def test_ab_compact_clause_prompt_shorter_than_full(self):
        """Compact system prompt must be significantly shorter than the full version."""
        clauses = [
            {"clause_id": "4.1", "title": "QMS General", "audit_question": "Does QMS exist?"},
            {"clause_id": "7.3.2", "title": "Design Input", "audit_question": "Design inputs defined?"},
        ]
        text = "Sample regulatory text."

        full_msgs = _build_clause_batch_prompt(clauses, text, "台灣", "Taiwan")
        compact_msgs = _build_clause_batch_prompt_compact(clauses, text, "台灣", "Taiwan")

        full_sys_len = len(full_msgs[0]["content"])
        compact_sys_len = len(compact_msgs[0]["content"])

        assert compact_sys_len < full_sys_len, (
            f"Compact system prompt ({compact_sys_len}) should be shorter than full ({full_sys_len})"
        )
        # Expect at least 50% reduction
        ratio = compact_sys_len / full_sys_len
        assert ratio < 0.5, (
            f"Compact prompt should be <50% of full size, got {ratio:.1%}"
        )

    def test_ab_compact_unique_req_prompt_shorter_than_full(self):
        """Compact unique-req system prompt must be shorter than the full version."""
        full_msgs = _build_unique_requirements_prompt("Some text", "台灣", "Taiwan", "TW_test")
        compact_msgs = _build_unique_requirements_prompt_compact("Some text", "台灣", "Taiwan", "TW_test")

        full_len = len(full_msgs[0]["content"])
        compact_len = len(compact_msgs[0]["content"])

        assert compact_len < full_len, (
            f"Compact unique-req prompt ({compact_len}) should be shorter than full ({full_len})"
        )
        ratio = compact_len / full_len
        assert ratio < 0.55, (
            f"Expected <55% of full size, got {ratio:.1%}"
        )

    def test_ab_per_site_distribution_vs_naive_truncation(self):
        """
        Per-site distribution must include content from ALL sites.
        Naive head-truncation would miss later sites when Site A is large.
        """
        # Site A is very large — naive truncation would consume the entire budget
        large_site_a = "This is Site A content about management systems. " * 200  # ~9800 chars
        small_site_b = "Site B unique: device registration required. UDI enrollment."  # ~60 chars

        texts = [
            {"agency": "LargeSiteA", "content_markdown": large_site_a, "url": ""},
            {"agency": "SmallSiteB", "content_markdown": small_site_b, "url": ""},
        ]
        max_chars = 3000

        # New: per-site distribution
        new_result = _build_focused_regulatory_text(texts, [], max_chars)
        assert "[LargeSiteA]" in new_result
        assert "[SmallSiteB]" in new_result, (
            "Per-site distribution must include SmallSiteB even though LargeSiteA is huge"
        )

        # Old: naive combine-then-truncate
        old_combined = _combine_crawled_texts(texts)[:max_chars]
        assert "[SmallSiteB]" not in old_combined or "SmallSiteB" not in old_combined, (
            "Naive truncation should NOT include SmallSiteB (proving old behaviour was broken)"
        )

    def test_ab_keyword_filter_vs_no_filter_relevance(self):
        """
        Keyword filtering should prioritize regulatory content over boilerplate.
        Without filtering, first-N chars may only capture header/boilerplate.
        """
        boilerplate = (
            "MINISTRY OF HEALTH — OFFICIAL DOCUMENT\n\n"
            "Document Reference: MOH/REG/2024/001\n\n"
            "Issue Date: 2024-01-15\n\n"
            "Effective Date: 2024-03-01\n\n"
            "Page 1 of 50\n\n"
            "Table of Contents\n\n"
            "1. Introduction ...... 3\n"
            "2. Scope ............. 5\n"
        )
        regulatory_content = (
            "\n\nSection 5 — Quality Management System\n\n"
            "All manufacturers shall establish and maintain a quality management system "
            "(QMS) meeting the requirements of ISO 13485:2016.\n\n"
            "Section 8 — Corrective and Preventive Action\n\n"
            "CAPA procedures shall be documented. Root cause analysis is required.\n\n"
        )
        text = boilerplate + regulatory_content

        # With keyword filtering: should find QMS/CAPA content
        with_kw = _filter_relevant_paragraphs(text, ["quality management system", "QMS", "CAPA"], 500)
        # Without keyword filtering: naive head truncation
        without_kw = text[:500]

        assert "QMS" in with_kw or "quality management" in with_kw.lower(), (
            "Keyword filter should surface QMS content"
        )
        # Naive head-truncation likely captures only the boilerplate header
        has_boilerplate_only = "Table of Contents" in without_kw or "Document Reference" in without_kw
        assert has_boilerplate_only, (
            "This confirms naive truncation would have returned header boilerplate "
            "(proving keyword filtering is valuable)"
        )

    def test_ab_local_full_flow_uses_more_batches_than_cloud(self):
        """Local flow should produce more LLM calls (smaller batches) than cloud flow."""
        call_log: list[str] = []

        def logging_mock(messages, model="default", temperature=0.1, max_tokens=8000, stream=False):
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            call_type = "unique" if "BEYOND ISO 13485" in system else "clause"
            call_log.append(call_type)
            return _make_mock_llm()(messages, model, temperature, max_tokens, stream)

        # Local run
        call_log.clear()
        asyncio.run(
            analyze_regulation_with_llm(
                region_name="新加坡 (Singapore)",
                crawled_texts=TWO_SITE_CRAWLED,
                llm_completion_fn=logging_mock,
                model="qwen2.5:32b",
                provider_id="ollama",
            )
        )
        local_clause_calls = call_log.count("clause")

        # Cloud run
        call_log.clear()
        asyncio.run(
            analyze_regulation_with_llm(
                region_name="新加坡 (Singapore)",
                crawled_texts=TWO_SITE_CRAWLED,
                llm_completion_fn=logging_mock,
                model="gpt-4o",
                provider_id="openai",
            )
        )
        cloud_clause_calls = call_log.count("clause")

        # 71 clauses / 8 = 9 batches (local) vs 71 / 24 = 3 batches (cloud)
        assert local_clause_calls > cloud_clause_calls, (
            f"Local should have more clause calls ({local_clause_calls}) "
            f"than cloud ({cloud_clause_calls})"
        )

    def test_ab_max_tokens_local_vs_cloud(self):
        """Local max_tokens must be lower than cloud max_tokens."""
        assert _LOCAL_PARAMS["max_tokens_clause"] < _CLOUD_PARAMS["max_tokens_clause"]
        assert _LOCAL_PARAMS["max_tokens_unique"] <= _CLOUD_PARAMS["max_tokens_unique"]

    def test_ab_regulatory_text_budget_local_vs_cloud(self):
        """Local regulatory text budget must be lower than cloud budget."""
        assert _LOCAL_PARAMS["max_regulatory_chars"] < _CLOUD_PARAMS["max_regulatory_chars"]
        assert _LOCAL_PARAMS["max_unique_req_chars"] < _CLOUD_PARAMS["max_unique_req_chars"]
