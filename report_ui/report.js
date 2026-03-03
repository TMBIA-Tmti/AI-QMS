/**
 * AI-QMS Compliance Report — Client-Side Logic
 * ==============================================
 *
 * Vanilla JS — zero dependencies.
 * Communicates with /api/report/ REST endpoints.
 */

(function () {
    "use strict";

    // ── Configuration ──
    const API_BASE = "/api/report";
    const RUN_ID = window.__RUN_ID__ || "";
    const DEBOUNCE_MS = 300;

    // ── i18n ──
    const LANG = window.__LANG__ || "zh-TW";
    let _locale = {};
    let _localeReady = false;

    async function loadLocale() {
        try {
            const resp = await fetch(`/api/report/locales/${LANG}.json`);
            if (resp.ok) _locale = await resp.json();
        } catch (e) { console.warn("Failed to load locale:", e); }
        _localeReady = true;
        applyDataI18n();
    }

    function t(key, params) {
        let text = _locale[key] || key;
        if (params) {
            for (const [k, v] of Object.entries(params)) {
                text = text.replace(`{${k}}`, v);
            }
        }
        return text;
    }

    function applyDataI18n() {
        document.querySelectorAll("[data-i18n]").forEach(el => {
            const key = el.getAttribute("data-i18n");
            const translated = t(key);
            if (translated !== key) {
                if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") el.placeholder = translated;
                else el.textContent = translated;
            }
        });
        document.querySelectorAll("[data-i18n-title]").forEach(el => {
            const key = el.getAttribute("data-i18n-title");
            const translated = t(key);
            if (translated !== key) el.title = translated;
        });
        document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
            const key = el.getAttribute("data-i18n-placeholder");
            const translated = t(key);
            if (translated !== key) el.placeholder = translated;
        });
    }

    loadLocale();

    // ── State ──
    let reportData = null;       // Full report response
    let filteredRows = [];       // Currently displayed rows
    let currentRowId = null;     // Row being edited in a modal
    let filterOptions = null;    // Cached filter options
    let verificationLoaded = false; // Whether verification tab was loaded

    // ── DOM References ──
    const $ = (id) => document.getElementById(id);

    const els = {
        headerRunId: $("headerRunId"),
        headerStatus: $("headerStatus"),
        headerTime: $("headerTime"),
        totalRows: $("totalRows"),
        fullCompliance: $("fullCompliance"),
        partialCompliance: $("partialCompliance"),
        nonCompliance: $("nonCompliance"),
        flaggedCount: $("flaggedCount"),
        tokenUsage: $("tokenUsage"),
        filterDoc: $("filterDoc"),
        filterVerdict: $("filterVerdict"),
        filterRisk: $("filterRisk"),
        filterFlagged: $("filterFlagged"),
        filterSearch: $("filterSearch"),
        btnExportWord: $("btnExportWord"),
        btnExportExcel: $("btnExportExcel"),
        btnRefresh: $("btnRefresh"),
        tableCount: $("tableCount"),
        tableBody: $("reportTableBody"),
        // Detail modal
        detailModal: $("detailModal"),
        detailTitle: $("detailTitle"),
        detailBody: $("detailBody"),
        detailClose: $("detailClose"),
        // Override modal
        overrideModal: $("overrideModal"),
        overrideClose: $("overrideClose"),
        overrideCurrent: $("overrideCurrent"),
        overrideVerdict: $("overrideVerdict"),
        overrideReason: $("overrideReason"),
        overrideCancelBtn: $("overrideCancelBtn"),
        overrideSaveBtn: $("overrideSaveBtn"),
        // Note modal
        noteModal: $("noteModal"),
        noteClose: $("noteClose"),
        noteClauseInfo: $("noteClauseInfo"),
        noteText: $("noteText"),
        noteCancelBtn: $("noteCancelBtn"),
        noteSaveBtn: $("noteSaveBtn"),
        // History modal
        historyModal: $("historyModal"),
        historyClose: $("historyClose"),
        historyBody: $("historyBody"),
        // Toast
        toastContainer: $("toastContainer"),
        // Tab navigation
        tabNav: $("tabNav"),
        // Cross-reference tab
        countryCheckboxes: $("countryCheckboxes"),
        btnLoadCrossref: $("btnLoadCrossref"),
        crossrefSummary: $("crossrefSummary"),
        crossrefSummaryCards: $("crossrefSummaryCards"),
        crossrefTableWrapper: $("crossrefTableWrapper"),
        crossrefTableCount: $("crossrefTableCount"),
        crossrefTableHead: $("crossrefTableHead"),
        crossrefTableBody: $("crossrefTableBody"),
        intercountrySection: $("intercountrySection"),
        intercountryContainer: $("intercountryContainer"),
        deltaSection: $("deltaSection"),
        deltaItemsContainer: $("deltaItemsContainer"),
        // Cross-examination tab
        crossexamStatus: $("crossexamStatus"),
        btnConnectSSE: $("btnConnectSSE"),
        btnPauseExam: $("btnPauseExam"),
        btnResumeExam: $("btnResumeExam"),
        sseRunIdInput: $("sseRunIdInput"),
        crossexamFeed: $("crossexamFeed"),
        humanMessageInput: $("humanMessageInput"),
        btnSendHuman: $("btnSendHuman"),
        phaseFilterBar: $('phaseFilterBar'),
        // Verification tab
        btnReVerify: $("btnReVerify"),
        verPassCount: $("verPassCount"),
        verWarnCount: $("verWarnCount"),
        verFailCount: $("verFailCount"),
        verTotalCount: $("verTotalCount"),
        verTimestamp: $("verTimestamp"),
        verNoData: $("verNoData"),
        verNoDataMsg: $("verNoDataMsg"),
        verCrossChecks: $("verCrossChecks"),
        verCrossChecksList: $("verCrossChecksList"),
        verTableWrapper: $("verTableWrapper"),
        verTableBody: $("verTableBody"),
    };


    // ============================================================
    // API Helpers
    // ============================================================

    async function apiFetch(path, options = {}) {
        const url = `${API_BASE}${path}`;
        try {
            const resp = await fetch(url, {
                headers: { "Content-Type": "application/json", ...options.headers },
                ...options,
            });
            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${resp.status}`);
            }
            return await resp.json();
        } catch (err) {
            console.error(`API error: ${url}`, err);
            throw err;
        }
    }

    async function apiPost(path, body) {
        return apiFetch(path, {
            method: "POST",
            body: JSON.stringify(body),
        });
    }


    // ============================================================
    // Toast Notifications
    // ============================================================

    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        els.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(20px)";
            toast.style.transition = "all 0.3s";
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }


    // ============================================================
    // Modal Helpers
    // ============================================================

    function openModal(modalEl) {
        modalEl.classList.add("active");
        document.body.style.overflow = "hidden";
    }

    function closeModal(modalEl) {
        modalEl.classList.remove("active");
        document.body.style.overflow = "";
    }

    function closeAllModals() {
        document.querySelectorAll(".modal-overlay.active").forEach((m) => closeModal(m));
    }


    // ============================================================
    // Date Formatting
    // ============================================================

    function formatTimestamp(ts) {
        if (!ts) return "—";
        const d = new Date(ts * 1000);
        const pad = (n) => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
               `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }

    function formatDuration(seconds) {
        if (!seconds && seconds !== 0) return "—";
        if (seconds < 60) return t("format.seconds", {value: seconds.toFixed(1)});
        const mins = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return t("format.minutes", {mins, secs});
    }


    // ============================================================
    // Load Report Data
    // ============================================================

    async function loadReport() {
        if (!RUN_ID) {
            els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">${t("table.invalid_id")}</td></tr>`;
            return;
        }

        els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">⏳ ${t("table.loading")}</td></tr>`;

        try {
            const [data, filters] = await Promise.all([
                apiFetch(`/${RUN_ID}`),
                apiFetch(`/${RUN_ID}/filters`),
            ]);

            reportData = data;
            filterOptions = filters;

            renderHeader(data);
            renderSummary(data);
            populateFilters(filters);
            applyFilters();

        } catch (err) {
            els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">${t("table.load_error", {error: escapeHtml(err.message)})}</td></tr>`;
            showToast(t("toast.load_error", {error: err.message}), "error");
        }
    }


    // ============================================================
    // Render Header
    // ============================================================

    function renderHeader(data) {
        els.headerRunId.textContent = data.run_id || "";

        const statusMap = {
            completed: { text: t("status.completed"), cls: "status-completed" },
            running: { text: t("status.running"), cls: "status-running" },
            paused: { text: t("status.paused"), cls: "status-paused" },
            failed: { text: t("status.failed"), cls: "status-failed" },
            pending: { text: t("status.pending"), cls: "status-running" },
        };
        const st = statusMap[data.status] || { text: data.status, cls: "" };
        els.headerStatus.textContent = st.text;
        els.headerStatus.className = `header-status ${st.cls}`;

        els.headerTime.textContent = data.created_at ? formatTimestamp(data.created_at) : "";
    }


    // ============================================================
    // Render Summary Cards
    // ============================================================

    function renderSummary(data) {
        const summary = data.summary || {};
        const vd = summary.verdict_distribution || {};
        const budget = data.llm_budget || {};

        els.totalRows.textContent = summary.total_rows || 0;
        els.fullCompliance.textContent = vd.full_compliance || 0;
        els.partialCompliance.textContent = vd.partial_compliance || 0;
        els.nonCompliance.textContent = vd.non_compliance || 0;
        els.flaggedCount.textContent = summary.flagged_for_ra || 0;

        const used = budget.total_tokens_used || 0;
        const pct = budget.usage_percent || 0;
        els.tokenUsage.textContent = `${pct}%`;
        els.tokenUsage.title = `${used.toLocaleString()} tokens`;
    }


    // ============================================================
    // Populate Filter Dropdowns
    // ============================================================

    function populateFilters(filters) {
        // Documents
        els.filterDoc.innerHTML = `<option value="">${t("filters.all_documents")}</option>`;
        (filters.documents || []).forEach((d) => {
            const opt = document.createElement("option");
            opt.value = d.id;
            opt.textContent = `${d.id} — ${d.title}`;
            els.filterDoc.appendChild(opt);
        });

        // Verdicts
        els.filterVerdict.innerHTML = `<option value="">${t("filters.all_verdicts")}</option>`;
        (filters.verdicts || []).forEach((v) => {
            const opt = document.createElement("option");
            opt.value = v.value;
            opt.textContent = `${v.icon || ""} ${v.label_zh || v.value}`;
            els.filterVerdict.appendChild(opt);
        });

        // Risk levels
        els.filterRisk.innerHTML = `<option value="">${t("filters.all_risk_levels")}</option>`;
        (filters.risk_levels || []).forEach((r) => {
            const opt = document.createElement("option");
            opt.value = r.value;
            opt.textContent = `${r.icon || ""} ${r.label_zh || r.value}`;
            els.filterRisk.appendChild(opt);
        });
    }


    // ============================================================
    // Apply Filters (Client-side)
    // ============================================================

    function applyFilters() {
        if (!reportData || !reportData.rows) return;

        let rows = reportData.rows.slice();

        const docFilter = els.filterDoc.value;
        const verdictFilter = els.filterVerdict.value;
        const riskFilter = els.filterRisk.value;
        const flaggedOnly = els.filterFlagged.checked;
        const searchText = (els.filterSearch.value || "").toLowerCase().trim();

        if (docFilter) rows = rows.filter((r) => r.doc_id === docFilter);
        if (verdictFilter) rows = rows.filter((r) => r.verdict === verdictFilter);
        if (riskFilter) rows = rows.filter((r) => r.risk_level === riskFilter);
        if (flaggedOnly) rows = rows.filter((r) => r.flagged_for_ra);
        if (searchText) {
            rows = rows.filter((r) => {
                const haystack = [
                    r.clause_id, r.clause_title, r.doc_id, r.doc_title,
                    r.audit_question, r.verdict_label_zh, r.risk_label_zh,
                ].join(" ").toLowerCase();
                return haystack.includes(searchText);
            });
        }

        filteredRows = rows;
        renderTable(rows);
        els.tableCount.textContent = t("table.count", {shown: rows.length, total: reportData.rows.length});
    }


    // ============================================================
    // Render Table
    // ============================================================

    function renderTable(rows) {
        if (rows.length === 0) {
            els.tableBody.innerHTML = `
                <tr><td colspan="8" class="loading-cell">
                    <div class="empty-state">
                        <div class="empty-state-icon">🔍</div>
                        <div class="empty-state-text">${t("table.empty")}</div>
                    </div>
                </td></tr>`;
            return;
        }

        els.tableBody.innerHTML = rows.map((r) => renderRow(r)).join("");
    }

    function renderRow(r) {
        const flagged = r.flagged_for_ra;
        const rowClass = flagged ? "row-flagged" : "";

        // Evidence bar
        const evFound = r.evidence_found || 0;
        const evTotal = r.evidence_total || 0;
        const evPct = evTotal > 0 ? Math.round((evFound / evTotal) * 100) : 0;
        const evFillClass = evPct >= 100 ? "fill-full" : evPct > 0 ? "fill-partial" : "fill-none";

        // Verdict badge
        const verdictBadge = getVerdictBadge(r.verdict, r.verdict_icon, r.verdict_label_zh, !!r.ra_override);

        // Risk badge
        const riskBadge = getRiskBadge(r.risk_level, r.risk_icon, r.risk_label_zh);

        return `
        <tr class="${rowClass}" data-row-id="${escapeAttr(r.row_id)}">
            <td class="col-clause">
                <div class="clause-id">${escapeHtml(r.clause_id)}</div>
                <div class="clause-title">${escapeHtml(r.clause_title)}</div>
            </td>
            <td class="col-doc">
                <div class="doc-id">${escapeHtml(r.doc_id)}</div>
                <div class="doc-title" title="${escapeAttr(r.doc_title)}">${escapeHtml(r.doc_title)}</div>
            </td>
            <td class="col-question">
                <div class="audit-question">${escapeHtml(r.audit_question || "—")}</div>
            </td>
            <td class="col-evidence">
                <div class="evidence-bar">
                    <div class="evidence-bar-track">
                        <div class="evidence-bar-fill ${evFillClass}" style="width:${evPct}%"></div>
                    </div>
                    <span class="evidence-text">${evFound}/${evTotal}</span>
                </div>
            </td>
            <td class="col-verdict">${verdictBadge}</td>
            <td class="col-risk">${riskBadge}</td>
            <td class="col-flags">${flagged ? `<span class="flag-icon" title="${t('row.flag_tooltip')}">🚩</span>` : ""}</td>
            <td class="col-actions">
                <div class="action-group">
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openDetail('${escapeAttr(r.row_id)}')" title="${t('row.btn_detail')}">🔍</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openOverride('${escapeAttr(r.row_id)}')" title="${t('row.btn_override')}">✏️</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openNote('${escapeAttr(r.row_id)}')" title="${t('row.btn_note')}">📝</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openHistory('${escapeAttr(r.row_id)}')" title="${t('row.btn_history')}">📜</button>
                    ${r.ra_override ? `<button class="btn btn-sm btn-success" onclick="window.__report.restoreOriginal('${escapeAttr(r.row_id)}')" title="${t('row.btn_restore')}">↩️</button>` : ""}
                    <button class="btn btn-sm btn-primary" onclick="window.__report.rerunRow('${escapeAttr(r.row_id)}')" title="${t('row.btn_rerun')}">🔄</button>
                </div>
            </td>
        </tr>`;
    }

    function getVerdictBadge(verdict, icon, label, hasOverride) {
        if (!verdict) return `<span class="badge badge-insufficient">${t("verdict.undetermined")}</span>`;
        const classMap = {
            full_compliance: "badge-full",
            partial_compliance: "badge-partial",
            non_compliance: "badge-non",
            insufficient_data: "badge-insufficient",
        };
        const cls = classMap[verdict] || "badge-insufficient";
        const overrideClass = hasOverride ? " badge-override" : "";
        return `<span class="badge ${cls}${overrideClass}">${icon || ""} ${label || verdict}</span>`;
    }

    function getRiskBadge(risk, icon, label) {
        if (!risk) return `<span class="badge badge-insufficient">${t("risk.unassessed")}</span>`;
        const classMap = {
            immediate_correction: "badge-risk-immediate",
            deadline_correction: "badge-risk-deadline",
            improvement_plan: "badge-risk-improvement",
            suggested_improvement: "badge-risk-suggested",
            compliant: "badge-risk-compliant",
        };
        const cls = classMap[risk] || "badge-insufficient";
        return `<span class="badge ${cls}">${icon || ""} ${label || risk}</span>`;
    }


    // ============================================================
    // Detail Modal
    // ============================================================

    async function openDetail(rowId) {
        currentRowId = rowId;

        try {
            const data = await apiFetch(`/${RUN_ID}/row/${rowId}`);
            const row = data.row;

            els.detailTitle.textContent = `${row.clause_id} — ${row.clause_title}`;

            let html = "";

            // Basic info
            html += `<div class="detail-section">
                <h3>${t("detail.basic_info")}</h3>
                <div class="detail-grid">
                    <span class="detail-label">${t("detail.clause_id")}</span>
                    <span class="detail-value">${escapeHtml(row.clause_id)}</span>
                    <span class="detail-label">${t("detail.clause_title")}</span>
                    <span class="detail-value">${escapeHtml(row.clause_title)}</span>
                    <span class="detail-label">${t("detail.quality_doc")}</span>
                    <span class="detail-value">${escapeHtml(row.doc_id)} — ${escapeHtml(row.doc_title)}</span>
                    <span class="detail-label">${t("detail.audit_impact")}</span>
                    <span class="detail-value">${escapeHtml(row.audit_impact)}</span>
                    <span class="detail-label">${t("detail.audit_question")}</span>
                    <span class="detail-value">${escapeHtml(row.audit_question || "—")}</span>
                    <span class="detail-label">${t("detail.verdict_result")}</span>
                    <span class="detail-value">${getVerdictBadge(row.verdict, row.verdict_icon, row.verdict_label_zh, !!row.ra_override)}</span>
                    <span class="detail-label">${t("detail.risk_level")}</span>
                    <span class="detail-value">${getRiskBadge(row.risk_level, row.risk_icon, row.risk_label_zh)}</span>
                </div>
            </div>`;

            // RA Override info
            if (row.ra_override) {
                html += `<div class="ra-override-info">
                    <strong>${t("detail.ra_override")}</strong>：${escapeHtml(row.ra_override.verdict)} — ${escapeHtml(row.ra_override.reason || "")}
                    <div style="font-size:0.75rem;color:#64748b;margin-top:4px">
                        ${t("detail.override_by")}: ${escapeHtml(row.ra_override.by || "—")} | 
                        ${t("detail.override_time")}: ${formatTimestamp(row.ra_override.at)}
                    </div>
                </div>`;
            }

            // RA Notes
            if (row.ra_notes) {
                html += `<div class="ra-notes">
                    <strong>${t("detail.ra_notes")}</strong>：${escapeHtml(row.ra_notes)}
                </div>`;
            }

            // Evidence items
            const evidenceItems = row.evidence_items || [];
            if (evidenceItems.length > 0) {
                html += `<div class="detail-section">
                    <h3>${t("detail.evidence_items")} (${evidenceItems.filter(e => e.found).length}/${evidenceItems.length})</h3>
                    <ul class="evidence-list">`;

                for (const ev of evidenceItems) {
                    const evClass = ev.found ? (ev.is_inadequate ? "inadequate" : "found") : "not-found";
                    const statusIcon = ev.found ? (ev.is_inadequate ? "⚠️" : "✅") : "❌";

                    html += `<li class="evidence-item ${evClass}">
                        <div class="evidence-name">${statusIcon} ${escapeHtml(ev.evidence_name || t("detail.unknown_evidence"))}</div>`;

                    if (ev.source_doc_id) {
                        html += `<div class="evidence-source">${t("detail.evidence_source")}: ${escapeHtml(ev.source_doc_id)}${ev.source_section ? ` — ${escapeHtml(ev.source_section)}` : ""}</div>`;
                    }

                    if (ev.source_quote) {
                        html += `<div class="evidence-quote">"${escapeHtml(ev.source_quote)}"</div>`;
                    }

                    if (ev.llm_reasoning) {
                        html += `<div class="evidence-source">${t("detail.llm_reasoning")}: ${escapeHtml(ev.llm_reasoning)}</div>`;
                    }

                    if (ev.relevance_score != null) {
                        html += `<div class="evidence-source">${t("detail.relevance_score")}: ${(ev.relevance_score * 100).toFixed(0)}%</div>`;
                    }

                    html += `</li>`;
                }

                html += `</ul></div>`;
            }

            // Expected evidence (from compliance_rules)
            const expectedEvidence = row.expected_evidence || [];
            if (expectedEvidence.length > 0 && evidenceItems.length === 0) {
                html += `<div class="detail-section">
                    <h3>${t("detail.expected_evidence")}</h3>
                    <ul class="evidence-list">`;
                for (const ev of expectedEvidence) {
                    html += `<li class="evidence-item not-found">
                        <div class="evidence-name">⬜ ${escapeHtml(ev)}</div>
                    </li>`;
                }
                html += `</ul></div>`;
            }

            // Verification rounds
            const rounds = row.verification_rounds || [];
            if (rounds.length > 0) {
                html += `<div class="detail-section">
                    <h3>${t("detail.cross_exam_rounds", {count: rounds.length})}</h3>`;

                for (let i = 0; i < rounds.length; i++) {
                    const round = rounds[i];
                    const agreed = round.agreed;
                    const statusText = agreed ? t("detail.agreed") : t("detail.disagreed");

                    html += `<div class="verification-round">
                        <div class="verification-round-header">
                            <span>${t("detail.round_num", {num: i + 1})}</span>
                            <span>${statusText}</span>
                        </div>
                        <div class="verification-round-body">`;

                    if (round.analyzer_response) {
                        html += `<div class="verification-role analyzer">${t("detail.analyzer")}</div>
                            <div class="verification-text">${escapeHtml(round.analyzer_response)}</div>`;
                    }

                    if (round.verifier_response) {
                        html += `<div class="verification-role verifier">${t("detail.verifier")}</div>
                            <div class="verification-text">${escapeHtml(round.verifier_response)}</div>`;
                    }

                    html += `</div></div>`;
                }

                if (row.flagged_for_ra) {
                    html += `<div class="ra-override-info">
                        <strong>${t("detail.flagged_for_ra")}</strong>：${t("detail.flagged_reason")}
                    </div>`;
                }

                html += `</div>`;
            }

            // Remediation
            if (row.remediation_suggestion) {
                html += `<div class="detail-section">
                    <h3>${t("detail.remediation")}</h3>
                    <div class="remediation-text">${escapeHtml(row.remediation_suggestion)}</div>`;

                if (row.remediation_regulation_cite) {
                    html += `<div style="margin-top:8px;font-size:0.8rem;color:#64748b">
                        ${t("detail.regulation_cite")}: ${escapeHtml(row.remediation_regulation_cite)}
                    </div>`;
                }

                html += `</div>`;
            }

            // Phase results timeline
            const phaseResults = row.phase_results || {};
            const phaseKeys = Object.keys(phaseResults);
            if (phaseKeys.length > 0) {
                html += `<div class="detail-section">
                    <h3>${t("detail.phase_results")}</h3>
                    <div class="detail-grid">`;

                const phaseNames = {
                    phase_0: t("phase.phase_0"),
                    phase_0_5: t("phase.phase_0_5"),
                    phase_1: t("phase.phase_1"),
                    phase_2: t("phase.phase_2"),
                    phase_3: t("phase.phase_3"),
                    phase_4: t("phase.phase_4"),
                    phase_5: t("phase.phase_5"),
                    phase_6: t("phase.phase_6"),
                };

                for (const key of phaseKeys) {
                    const pr = phaseResults[key];
                    const statusIcon = pr.status === "completed" ? "✅" : pr.status === "skipped" ? "⏭️" : pr.status === "failed" ? "❌" : "⏳";
                    const duration = pr.duration_seconds != null ? `${pr.duration_seconds.toFixed(1)}s` : "";

                    html += `<span class="detail-label">${phaseNames[key] || key}</span>
                        <span class="detail-value">${statusIcon} ${pr.status || "—"} ${duration ? `(${duration})` : ""}</span>`;
                }

                html += `</div></div>`;
            }

            els.detailBody.innerHTML = html;
            openModal(els.detailModal);

        } catch (err) {
            showToast(t("detail.load_error", {error: err.message}), "error");
        }
    }


    // ============================================================
    // Override Verdict Modal
    // ============================================================

    function openOverride(rowId) {
        currentRowId = rowId;
        const row = findRow(rowId);
        if (!row) return;

        els.overrideCurrent.innerHTML = getVerdictBadge(row.verdict, row.verdict_icon, row.verdict_label_zh, !!row.ra_override);
        els.overrideVerdict.value = row.verdict || "full_compliance";
        els.overrideReason.value = "";

        openModal(els.overrideModal);
    }

    async function submitOverride() {
        const verdict = els.overrideVerdict.value;
        const reason = els.overrideReason.value.trim();

        if (!reason) {
            showToast(t("override.reason_empty"), "error");
            return;
        }

        els.overrideSaveBtn.disabled = true;
        els.overrideSaveBtn.textContent = t("override.processing");

        try {
            const result = await apiPost(`/${RUN_ID}/row/${currentRowId}/override`, {
                verdict: verdict,
                reason: reason,
            });

            if (result.success) {
                showToast(t("override.success"), "success");
                closeModal(els.overrideModal);
                updateRowInData(currentRowId, result.row);
                applyFilters();
                refreshSummary();

                // Offer to re-run analysis after override
                setTimeout(() => {
                    if (confirm(t("override.rerun_prompt"))) {
                        rerunRow(currentRowId);
                    }
                }, 300);
            }
        } catch (err) {
            showToast(t("override.error", {error: err.message}), "error");
        } finally {
            els.overrideSaveBtn.disabled = false;
            els.overrideSaveBtn.textContent = t("override.confirm");
        }
    }


    // ============================================================
    // Note Modal
    // ============================================================

    function openNote(rowId) {
        currentRowId = rowId;
        const row = findRow(rowId);
        if (!row) return;

        els.noteClauseInfo.textContent = `${row.clause_id} — ${row.clause_title}`;
        els.noteText.value = row.ra_notes || "";

        openModal(els.noteModal);
    }

    async function submitNote() {
        const note = els.noteText.value.trim();

        if (!note) {
            showToast(t("note.empty"), "error");
            return;
        }

        els.noteSaveBtn.disabled = true;
        els.noteSaveBtn.textContent = t("note.saving");

        try {
            const result = await apiPost(`/${RUN_ID}/row/${currentRowId}/note`, {
                note: note,
            });

            if (result.success) {
                showToast(t("note.success"), "success");
                closeModal(els.noteModal);
                updateRowInData(currentRowId, result.row);
                applyFilters();
            }
        } catch (err) {
            showToast(t("note.error", {error: err.message}), "error");
        } finally {
            els.noteSaveBtn.disabled = false;
            els.noteSaveBtn.textContent = t("note.save");
        }
    }


    // ============================================================
    // Version History Modal
    // ============================================================

    async function openHistory(rowId) {
        currentRowId = rowId;

        try {
            const data = await apiFetch(`/${RUN_ID}/row/${rowId}/history`);
            const history = data.version_history || [];

            if (history.length === 0) {
                els.historyBody.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📜</div>
                        <div class="empty-state-text">${t("history.empty")}</div>
                    </div>`;
            } else {
                let html = "";
                // Show in reverse chronological order
                const reversed = history.slice().reverse();
                for (const entry of reversed) {
                    const actionLabels = {
                        override_verdict: t("history.override_verdict"),
                        add_note: t("history.add_note"),
                        restore_original: t("history.restore_original"),
                    };
                    const actionClasses = {
                        override_verdict: "override",
                        add_note: "note",
                        restore_original: "restore",
                    };

                    const label = actionLabels[entry.action] || entry.action;
                    const cls = actionClasses[entry.action] || "";

                    html += `<div class="history-item">
                        <div class="history-action ${cls}">${label}</div>`;

                    if (entry.action === "override_verdict") {
                        html += `<div>${t("history.prev_verdict")}: ${escapeHtml(entry.previous_verdict || "—")} → ${t("history.new_verdict")}: ${escapeHtml(entry.new_verdict || "—")}</div>
                            <div>${t("history.reason")}: ${escapeHtml(entry.reason || "—")}</div>`;
                    } else if (entry.action === "add_note") {
                        html += `<div>${t("history.note_content")}: ${escapeHtml(entry.new_note || "—")}</div>`;
                    } else if (entry.action === "restore_original") {
                        html += `<div>${t("history.override_to_restore", {overridden: escapeHtml(entry.overridden_verdict || "—"), restored: escapeHtml(entry.restored_verdict || "—")})}</div>`;
                    }

                    html += `<div class="history-meta">
                            ${entry.by ? `${t("history.operator")}: ${escapeHtml(entry.by)}` : ""}
                            ${entry.at ? ` | ${formatTimestamp(entry.at)}` : ""}
                        </div>
                    </div>`;
                }

                els.historyBody.innerHTML = html;
            }

            // Also show RA override & notes status
            if (data.ra_override) {
                els.historyBody.insertAdjacentHTML("afterbegin", `
                    <div class="ra-override-info" style="margin-bottom:16px">
                        <strong>${t("history.current_override")}</strong>：${escapeHtml(data.ra_override.verdict || "—")} — ${escapeHtml(data.ra_override.reason || "")}
                    </div>`);
            }

            if (data.ra_notes) {
                els.historyBody.insertAdjacentHTML("afterbegin", `
                    <div class="ra-notes" style="margin-bottom:16px">
                        <strong>${t("history.current_notes")}</strong>：${escapeHtml(data.ra_notes)}
                    </div>`);
            }

            openModal(els.historyModal);

        } catch (err) {
            showToast(t("history.load_error", {error: err.message}), "error");
        }
    }


    // ============================================================
    // Restore LLM Original
    // ============================================================

    async function restoreOriginal(rowId) {
        if (!confirm(t("restore.confirm"))) {
            return;
        }

        try {
            const result = await apiPost(`/${RUN_ID}/row/${rowId}/restore`, {});

            if (result.success) {
                showToast(t("restore.success"), "success");
                updateRowInData(rowId, result.row);
                applyFilters();
                refreshSummary();
            }
        } catch (err) {
            showToast(t("restore.error", {error: err.message}), "error");
        }
    }


    // ============================================================
    // Re-run Single Row
    // ============================================================

    async function rerunRow(rowId) {
        const row = findRow(rowId);
        const clauseLabel = row ? `${row.clause_id} — ${row.clause_title}` : rowId;

        if (!confirm(t("rerun.confirm", {clause: clauseLabel}))) {
            return;
        }

        try {
            const result = await apiPost(`/${RUN_ID}/row/${rowId}/rerun`, {
                from_phase: "phase_1",
            });

            if (result.success) {
                showToast(
                    t("rerun.success", {clause_id: row ? row.clause_id : rowId, message: result.message}),
                    "success"
                );
                // Update the row in local data to reflect pending status
                if (result.row) {
                    updateRowInData(rowId, result.row);
                }
                applyFilters();
                refreshSummary();
            }
        } catch (err) {
            showToast(t("rerun.error", {error: err.message}), "error");
        }
    }


    // ============================================================
    // Export
    // ============================================================

    function exportReport(format) {
        const url = `${API_BASE}/${RUN_ID}/export/${format}`;
        showToast(t("export.progress", {format: format.toUpperCase()}), "info");

        // Use a hidden link to trigger download
        const a = document.createElement("a");
        a.href = url;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }


    // ============================================================
    // Helpers
    // ============================================================

    function findRow(rowId) {
        return (reportData && reportData.rows || []).find((r) => r.row_id === rowId) || null;
    }

    function updateRowInData(rowId, newRowData) {
        if (!reportData || !reportData.rows) return;
        const idx = reportData.rows.findIndex((r) => r.row_id === rowId);
        if (idx >= 0) {
            // Merge display fields
            reportData.rows[idx] = { ...reportData.rows[idx], ...newRowData };
        }
    }

    async function refreshSummary() {
        try {
            const data = await apiFetch(`/${RUN_ID}/summary`);
            if (reportData) {
                reportData.summary = data.summary;
                reportData.llm_budget = data.llm_budget;
            }
            renderSummary({ summary: data.summary, llm_budget: data.llm_budget });
        } catch (_) {
            // Silent fail on summary refresh
        }
    }

    function escapeHtml(str) {
        if (str == null) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function escapeAttr(str) {
        return escapeHtml(str);
    }

    // Debounce helper
    function debounce(fn, ms) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }


    // ============================================================
    // Event Listeners
    // ============================================================

    function bindEvents() {
        // Filters
        els.filterDoc.addEventListener("change", applyFilters);
        els.filterVerdict.addEventListener("change", applyFilters);
        els.filterRisk.addEventListener("change", applyFilters);
        els.filterFlagged.addEventListener("change", applyFilters);
        els.filterSearch.addEventListener("input", debounce(applyFilters, DEBOUNCE_MS));

        // Actions
        els.btnRefresh.addEventListener("click", loadReport);
        els.btnExportWord.addEventListener("click", () => exportReport("word"));
        els.btnExportExcel.addEventListener("click", () => exportReport("excel"));

        // Detail modal
        els.detailClose.addEventListener("click", () => closeModal(els.detailModal));

        // Override modal
        els.overrideClose.addEventListener("click", () => closeModal(els.overrideModal));
        els.overrideCancelBtn.addEventListener("click", () => closeModal(els.overrideModal));
        els.overrideSaveBtn.addEventListener("click", submitOverride);

        // Note modal
        els.noteClose.addEventListener("click", () => closeModal(els.noteModal));
        els.noteCancelBtn.addEventListener("click", () => closeModal(els.noteModal));
        els.noteSaveBtn.addEventListener("click", submitNote);

        // History modal
        els.historyClose.addEventListener("click", () => closeModal(els.historyModal));

        // Close modals on overlay click
        document.querySelectorAll(".modal-overlay").forEach((overlay) => {
            overlay.addEventListener("click", (e) => {
                if (e.target === overlay) closeModal(overlay);
            });
        });

        // Close modals on Escape
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") closeAllModals();
        });

        // Tab navigation
        if (els.tabNav) {
            els.tabNav.addEventListener("click", (e) => {
                const btn = e.target.closest(".tab-btn");
                if (!btn) return;
                const tabId = btn.dataset.tab;
                // Switch active tab button
                els.tabNav.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
                btn.classList.add("active");
                // Switch active tab content
                document.querySelectorAll(".tab-content").forEach((t) => t.classList.remove("active"));
                const targetTab = document.querySelector(`.tab-content[data-tab="${tabId}"]`);
                if (targetTab) targetTab.classList.add("active");
                // Lazy-load cross-ref regulations on first visit
                if (tabId === "crossref" && !crossrefRegulations) {
                    loadCrossrefRegulations();
                }
                // Lazy-load verification on first visit
                if (tabId === "verification" && !verificationLoaded) {
                    loadVerification();
                }
            });
        }

        // Cross-reference controls
        if (els.btnLoadCrossref) {
            els.btnLoadCrossref.addEventListener("click", loadCrossrefTable);
        }

        // Verification controls
        if (els.btnReVerify) {
            els.btnReVerify.addEventListener("click", () => {
                verificationLoaded = false;
                loadVerification();
            });
        }

        // Cross-examination controls
        if (els.btnConnectSSE) {
            els.btnConnectSSE.addEventListener("click", connectSSE);
        }
        if (els.btnPauseExam) {
            els.btnPauseExam.addEventListener("click", pauseExam);
        }
        if (els.btnResumeExam) {
            els.btnResumeExam.addEventListener("click", resumeExam);
        }
        if (els.btnSendHuman) {
            els.btnSendHuman.addEventListener("click", sendHumanMessage);
        }

        // Phase filter buttons
        const phaseFilterBar = document.getElementById('phaseFilterBar');
        if (phaseFilterBar) {
            phaseFilterBar.addEventListener('click', function(e) {
                const btn = e.target.closest('.phase-filter-btn');
                if (!btn) return;
                phaseFilterBar.querySelectorAll('.phase-filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const phase = btn.dataset.phase;
                filterSSEFeedByPhase(phase);
            });
        }
        if (els.humanMessageInput) {
            els.humanMessageInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendHumanMessage();
                }
            });
        }
    }


    // ============================================================
    // Public API (for inline onclick handlers)
    // ============================================================

    window.__report = {
        openDetail,
        openOverride,
        openNote,
        openHistory,
        restoreOriginal,
        rerunRow,
        toggleRationale,
    };


    // ============================================================
    // Cross-Reference Comparison Table
    // ============================================================

    let crossrefRegulations = null;  // cached regulation list
    let crossrefData = null;         // cached cross-ref table data

    const FLAG_EMOJIS = {
        US: "🇺🇸", EU: "🇪🇺", TW: "🇹🇼", JP: "🇯🇵",
        CN: "🇨🇳", KR: "🇰🇷", AU: "🇦🇺", CA: "🇨🇦",
        BR: "🇧🇷", IN: "🇮🇳", GB: "🇬🇧",
    };

    function getMethodLabel(key) {
        return t("method." + key) !== "method." + key ? t("method." + key) : key;
    }

    function getLangLabel(key) {
        return t("lang." + key) !== "lang." + key ? t("lang." + key) : key;
    }

    async function loadCrossrefRegulations() {
        if (!els.countryCheckboxes) return;
        els.countryCheckboxes.innerHTML = `<div class="loading-cell">${t("crossref.loading_regulations")}</div>`;

        try {
            const data = await apiFetch("/crossref/regulations");
            crossrefRegulations = data.regulations || [];

            if (crossrefRegulations.length === 0) {
                els.countryCheckboxes.innerHTML = `<div class="loading-cell">${t("crossref.no_regulations")}</div>`;
                return;
            }

            let html = "";
            for (const reg of crossrefRegulations) {
                const flag = FLAG_EMOJIS[reg.country] || "🏳️";
                const fullCount = reg.status_counts.full || 0;
                const exceedsCount = reg.status_counts.exceeds || 0;
                const uniqueCount = reg.unique_requirements_count || 0;
                html += `
                <label class="country-check-item" data-reg-id="${escapeAttr(reg.regulation_id)}">
                    <input type="checkbox" value="${escapeAttr(reg.regulation_id)}" checked>
                    <span class="country-flag">${flag}</span>
                    <div>
                        <div class="country-name">${escapeHtml(reg.country_name_zh)} (${escapeHtml(reg.country)})</div>
                        <div class="country-meta">${escapeHtml(reg.name_zh)}</div>
                        <div class="country-meta">✅${fullCount} ⬆️${exceedsCount} 🚨${uniqueCount}${t("crossref.unique_count")}</div>
                    </div>
                </label>`;
            }
            els.countryCheckboxes.innerHTML = html;

            // Toggle checked class on click
            els.countryCheckboxes.querySelectorAll(".country-check-item").forEach((item) => {
                const cb = item.querySelector("input[type=checkbox]");
                cb.addEventListener("change", () => {
                    item.classList.toggle("checked", cb.checked);
                });
                item.classList.toggle("checked", cb.checked);
            });
        } catch (err) {
            els.countryCheckboxes.innerHTML = `<div class="loading-cell">${t("crossref.load_error", {error: escapeHtml(err.message)})}</div>`;
        }
    }

    async function loadCrossrefTable() {
        // Gather selected regulations
        const checked = els.countryCheckboxes.querySelectorAll("input[type=checkbox]:checked");
        const regIds = Array.from(checked).map((cb) => cb.value);

        if (regIds.length === 0) {
            showToast(t("crossref.select_at_least_one"), "error");
            return;
        }

        els.btnLoadCrossref.disabled = true;
        els.btnLoadCrossref.textContent = t("crossref.generating");

        try {
            const data = await apiFetch(`/crossref/table?regulations=${regIds.join(",")}`);
            crossrefData = data;

            renderCrossrefSummary(data);
            renderCrossrefTable(data);
            renderInterCountryDiffs(data);
            renderDeltaItems(data);

            els.crossrefSummary.style.display = "";
            els.crossrefTableWrapper.style.display = "";
            els.intercountrySection.style.display = "";
            els.deltaSection.style.display = "";

            showToast(t("crossref.generated", {rows: data.rows.length, countries: regIds.length}), "success");
        } catch (err) {
            showToast(t("crossref.generate_error", {error: err.message}), "error");
        } finally {
            els.btnLoadCrossref.disabled = false;
            els.btnLoadCrossref.textContent = t("crossref.generate_btn");
        }
    }

    function renderCrossrefSummary(data) {
        const meta = data.regulation_meta || {};
        const regIds = data.regulation_ids || [];
        let html = "";

        for (const rid of regIds) {
            const m = meta[rid] || {};
            const flag = FLAG_EMOJIS[m.country] || "🏳️";
            // Count statuses from rows
            let fullCount = 0, partialCount = 0, exceedsCount = 0, naCount = 0;
            for (const row of (data.rows || [])) {
                const regData = (row.regulations || {})[rid];
                if (!regData) continue;
                if (regData.status === "full") fullCount++;
                else if (regData.status === "partial") partialCount++;
                else if (regData.status === "exceeds") exceedsCount++;
                else if (regData.status === "na" || regData.status === "not_mapped") naCount++;
            }
            const uniqueReqs = (data.unique_requirements || {})[rid] || [];

            html += `
            <div class="crossref-stat-card">
                <h4>${flag} ${escapeHtml(m.country_name_zh || rid)}</h4>
                <div class="stat-row"><span>${t("crossref.stat_full")}</span><strong>${fullCount}</strong></div>
                <div class="stat-row"><span>${t("crossref.stat_exceeds")}</span><strong style="color:#2563eb">${exceedsCount}</strong></div>
                <div class="stat-row"><span>${t("crossref.stat_partial")}</span><strong style="color:var(--partial)">${partialCount}</strong></div>
                <div class="stat-row"><span>${t("crossref.stat_na")}</span><strong style="color:var(--insufficient)">${naCount}</strong></div>
                <div class="stat-row"><span>${t("crossref.stat_unique")}</span><strong style="color:var(--non-compliant)">${uniqueReqs.length}</strong></div>
                <div class="stat-bar">
                    <div class="stat-bar-fill" style="width:${Math.round(fullCount / (data.iso_clause_count || 71) * 100)}%;background:var(--compliant)"></div>
                </div>
            </div>`;
        }

        els.crossrefSummaryCards.innerHTML = html;
    }

    function renderCrossrefTable(data) {
        const regIds = data.regulation_ids || [];
        const meta = data.regulation_meta || {};
        const rows = data.rows || [];

        // Build header
        let headHtml = `<tr><th>${t("crossref.iso_clause")}</th>`;
        for (const rid of regIds) {
            const m = meta[rid] || {};
            const flag = FLAG_EMOJIS[m.country] || "";
            headHtml += `<th>${flag} ${escapeHtml(m.country_name_zh || rid)}</th>`;
        }
        headHtml += `</tr>`;
        els.crossrefTableHead.innerHTML = headHtml;

        // Build body rows
        let bodyHtml = "";
        for (const row of rows) {
            const rowId = `cr-${row.clause_id.replace(/\./g, "-")}`;
            bodyHtml += `<tr class="crossref-data-row" data-row-id="${rowId}">`;
            bodyHtml += `<td><div class="clause-id">${escapeHtml(row.clause_id)}</div>
                <div class="clause-title">${escapeHtml(row.clause_title)}</div></td>`;

            for (const rid of regIds) {
                const reg = (row.regulations || {})[rid] || {};
                const status = reg.status || "na";
                const statusLabels = {
                    full: "✅ Full",
                    partial: "⚠️ Partial",
                    exceeds: "⬆️ Exceeds",
                    na: "➖ N/A",
                    not_mapped: "➖ N/A",
                };
                const hasDelta = reg.delta_items && reg.delta_items.length > 0;
                const uniqueClass = hasDelta ? " unique-marker" : "";
                const hasNativeText = reg.original_text || (reg.delta_items || []).some(d => d.original_text);
                bodyHtml += `<td>
                    <span class="status-cell status-${status}${uniqueClass}"
                          onclick="window.__report.toggleRationale('${rowId}')"
                          title="${t('crossref.click_expand')}"
                    >${statusLabels[status] || status}</span>
                </td>`;
            }
            bodyHtml += `</tr>`;

            // Rationale expandable row (hidden by default)
            bodyHtml += `<tr class="rationale-row" id="${rowId}-rationale">`;
            bodyHtml += `<td colspan="${regIds.length + 1}">`;
            for (const rid of regIds) {
                const reg = (row.regulations || {})[rid] || {};
                const m = meta[rid] || {};
                const flag = FLAG_EMOJIS[m.country] || "";
                const conf = reg.confidence || 0;
                const confClass = conf >= 0.9 ? "confidence-high" : conf >= 0.7 ? "confidence-medium" : "confidence-low";
                const methodLabel = getMethodLabel(reg.method);

                bodyHtml += `<div class="rationale-card">
                    <div class="rc-header">${flag} ${escapeHtml(m.country_name_zh || rid)}</div>
                    <div class="rc-field"><span class="rc-label">${t("crossref.rationale_reg_ref")}</span> <span class="rc-value">${escapeHtml(reg.regulation_ref || "—")}</span></div>
                    <div class="rc-field"><span class="rc-label">${t("crossref.rationale_method")}</span> <span class="method-badge">${methodLabel}</span></div>
                    <div class="rc-field"><span class="rc-label">${t("crossref.rationale_confidence")}</span> <span class="rc-confidence ${confClass}">${Math.round(conf * 100)}%</span></div>
                    <div class="rc-field"><span class="rc-label">${t("crossref.rationale_reason_en")}</span> <span class="rc-value">${escapeHtml(reg.rationale_en || "—")}</span></div>
                    <div class="rc-field"><span class="rc-label">${t("crossref.rationale_reason_zh")}</span> <span class="rc-value">${escapeHtml(reg.rationale_zh || "—")}</span></div>`;

                // Native-language regulatory text comparison
                if (reg.original_text) {
                    const langLabel = getLangLabel(reg.original_lang) || reg.original_lang || "—";
                    bodyHtml += `<div class="rc-field" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
                        <span class="rc-label">${t("crossref.original_text")} (${langLabel}):</span>
                        <div class="rc-value" style="font-style:italic;margin-top:4px">${escapeHtml(reg.original_text)}</div>
                    </div>`;
                    if (reg.english_translation) {
                        bodyHtml += `<div class="rc-field">
                            <span class="rc-label">🇬🇧 English Translation:</span>
                            <div class="rc-value" style="margin-top:4px">${escapeHtml(reg.english_translation)}</div>
                        </div>`;
                    }
                    if (reg.semantic_note) {
                        bodyHtml += `<div class="rc-field">
                            <span class="rc-label">${t("crossref.semantic_note")}:</span>
                            <div class="rc-value" style="margin-top:4px;color:var(--primary)">${escapeHtml(reg.semantic_note)}</div>
                        </div>`;
                    }
                }

                // Delta items for this clause
                const deltas = reg.delta_items || [];
                if (deltas.length > 0) {
                    bodyHtml += `<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
                        <span class="rc-label">${t("crossref.unique_requirements")}</span>`;
                    for (const d of deltas) {
                        bodyHtml += `<div style="margin-top:4px;padding:6px;background:var(--non-compliant-bg);border-radius:4px">
                            <strong>${escapeHtml(d.title_zh || d.title_en)}</strong>
                            <div style="font-size:0.72rem;color:var(--text-secondary)">${escapeHtml(d.regulation_ref)}</div>`;
                        // Show native text for delta items too
                        if (d.original_text) {
                            const dLang = getLangLabel(d.original_lang) || d.original_lang || "";
                            bodyHtml += `<div style="margin-top:4px;font-style:italic;font-size:0.75rem">📜 ${dLang}: ${escapeHtml(d.original_text)}</div>`;
                            if (d.english_translation) {
                                bodyHtml += `<div style="font-size:0.75rem">🇬🇧 ${escapeHtml(d.english_translation)}</div>`;
                            }
                            if (d.semantic_note) {
                                bodyHtml += `<div style="font-size:0.75rem;color:var(--primary)">💡 ${escapeHtml(d.semantic_note)}</div>`;
                            }
                        }
                        bodyHtml += `</div>`;
                    }
                    bodyHtml += `</div>`;
                }

                bodyHtml += `</div>`;  // end rationale-card
            }

            // ── Document evidence for this clause (outside per-regulation loop) ──
            const docs = row.doc_evidence || [];
            const relevantDocs = docs.filter(d => d.found_count !== 0 || d.missing_count !== 0 || d.inadequate_count !== 0);
            if (relevantDocs.length > 0) {
                bodyHtml += `<div style="margin-top:12px;padding-top:10px;border-top:2px solid var(--primary)">
                    <span class="rc-label" style="font-size:0.85rem">${t("crossref.doc_evidence")} (${relevantDocs.length}):</span>`;
                for (const doc of relevantDocs) {
                    const isPipeline = doc.source !== 'regex_supplement';
                    const sourceTag = isPipeline
                        ? `<span style="font-size:0.65rem;padding:1px 5px;background:var(--compliant-bg);color:var(--compliant);border-radius:3px;margin-left:6px">Pipeline</span>`
                        : `<span style="font-size:0.65rem;padding:1px 5px;background:var(--surface-alt);color:var(--text-secondary);border-radius:3px;margin-left:6px">對應</span>`;
                    const countsHtml = isPipeline
                        ? `<span style="margin-left:8px;font-size:0.75rem">✅${doc.found_count} ⚠️${doc.inadequate_count} ❌${doc.missing_count}</span>`
                        : '';
                    bodyHtml += `<div style="margin-top:4px;padding:6px 8px;background:var(--surface-alt);border-radius:4px;border-left:3px solid var(--primary)">
                        <strong style="font-size:0.8rem">${escapeHtml(doc.doc_id)}</strong>
                        <span style="font-size:0.75rem;color:var(--text-secondary);margin-left:4px">— ${escapeHtml(doc.doc_title)}</span>
                        ${sourceTag}${countsHtml}
                    </div>`;
                    // Show found evidence details if available
                    if (isPipeline && doc.found && doc.found.length > 0) {
                        bodyHtml += `<div style="margin-left:16px;font-size:0.72rem;color:var(--text-secondary)">`;
                        for (const f of doc.found.slice(0, 3)) {
                            bodyHtml += `<div style="margin-top:2px">✅ ${escapeHtml(f.name)} — <em>${escapeHtml(f.section || '')}</em></div>`;
                        }
                        if (doc.found.length > 3) {
                            bodyHtml += `<div style="margin-top:2px">${t("crossref.more_items", {count: doc.found.length - 3})}</div>`;
                        }
                        bodyHtml += `</div>`;
                    }
                    if (isPipeline && doc.inadequate && doc.inadequate.length > 0) {
                        bodyHtml += `<div style="margin-left:16px;font-size:0.72rem;color:var(--warning-color,orange)">`;
                        for (const f of doc.inadequate.slice(0, 3)) {
                            bodyHtml += `<div style="margin-top:2px">⚠️ ${escapeHtml(f.name)} — <em>${escapeHtml(f.section || '')}</em></div>`;
                        }
                        bodyHtml += `</div>`;
                    }
                    if (isPipeline && doc.missing && doc.missing.length > 0) {
                        bodyHtml += `<div style="margin-left:16px;font-size:0.72rem;color:var(--non-compliant,red)">`;
                        for (const m of doc.missing.slice(0, 3)) {
                            bodyHtml += `<div style="margin-top:2px">❌ ${escapeHtml(m)}</div>`;
                        }
                        if (doc.missing.length > 3) {
                            bodyHtml += `<div style="margin-top:2px">${t("crossref.more_items", {count: doc.missing.length - 3})}</div>`;
                        }
                        bodyHtml += `</div>`;
                    }
                }
                bodyHtml += `</div>`;
            }

            bodyHtml += `</td></tr>`;
        }

        els.crossrefTableBody.innerHTML = bodyHtml;
        els.crossrefTableCount.textContent = t("crossref.table_count", {rows: rows.length, countries: regIds.length});
    }

    function toggleRationale(rowId) {
        const rationaleRow = document.getElementById(`${rowId}-rationale`);
        if (rationaleRow) {
            rationaleRow.classList.toggle("expanded");
        }
    }

    // ============================================================
    // Inter-Country Differences Analysis
    // ============================================================

    function renderInterCountryDiffs(data) {
        const regIds = data.regulation_ids || [];
        const meta = data.regulation_meta || {};
        const rows = data.rows || [];

        if (regIds.length < 2) {
            // Single country selected — show single-country deep-dive instead
            els.intercountrySection.style.display = "none";
            return;
        }

        // For each country, find clauses where IT differs from others
        const diffs = {};  // { regId: { exceeds: [...clauseIds], unique: [...clauseIds] } }
        for (const rid of regIds) {
            diffs[rid] = { exceeds_only: [], unique_only: [] };
        }

        for (const row of rows) {
            const clauseId = row.clause_id;
            const statuses = {};
            for (const rid of regIds) {
                const reg = (row.regulations || {})[rid] || {};
                statuses[rid] = reg.status || "na";
            }

            // Find country-specific differences
            for (const rid of regIds) {
                const myStatus = statuses[rid];
                const otherStatuses = regIds.filter(r => r !== rid).map(r => statuses[r]);

                // This country exceeds but no others do
                if (myStatus === "exceeds" && otherStatuses.every(s => s !== "exceeds")) {
                    diffs[rid].exceeds_only.push(clauseId);
                }
                // This country has na/not_mapped but others have full/partial/exceeds
                if ((myStatus === "na" || myStatus === "not_mapped") &&
                    otherStatuses.some(s => s === "full" || s === "partial" || s === "exceeds")) {
                    diffs[rid].unique_only.push(clauseId);
                }
            }
        }

        // Also include delta items comparison
        const uniqueReqs = data.unique_requirements || {};

        let html = "";
        for (const rid of regIds) {
            const m = meta[rid] || {};
            const flag = FLAG_EMOJIS[m.country] || "";
            const d = diffs[rid];
            const reqs = uniqueReqs[rid] || [];

            if (d.exceeds_only.length === 0 && reqs.length === 0 && d.unique_only.length === 0) continue;

            html += `<div class="intercountry-card">
                <h4>${flag} ${escapeHtml(m.country_name_zh || rid)} ${t("intercountry.unique_diff")}</h4>`;

            if (d.exceeds_only.length > 0) {
                html += `<div style="margin-bottom:8px"><strong>${t("intercountry.exceeds_only")}</strong>
                    <div class="diff-clause-list">
                        ${d.exceeds_only.map(c => `<span class="diff-clause-chip diff-chip-exceeds">${c}</span>`).join("")}            
                    </div>
                </div>`;
            }

            if (reqs.length > 0) {
                html += `<div style="margin-bottom:8px"><strong>${t("intercountry.unique_reqs", {count: reqs.length})}</strong>`;
                for (const req of reqs) {
                    html += `<div style="margin:4px 0;padding:6px 8px;background:var(--bg);border-radius:4px;font-size:0.78rem">
                        <strong>${escapeHtml(req.title_zh)}</strong>
                        <span style="color:var(--text-muted);margin-left:8px">${escapeHtml(req.regulation_ref)}</span>`;
                    // Show native text for inter-country comparison
                    if (req.original_text) {
                        const langLabel = getLangLabel(req.original_lang) || req.original_lang || "";
                        html += `<div style="margin-top:4px;font-size:0.75rem;font-style:italic">📜 ${langLabel}: ${escapeHtml(req.original_text)}</div>`;
                        if (req.english_translation) {
                            html += `<div style="font-size:0.75rem">🇬🇧 ${escapeHtml(req.english_translation)}</div>`;
                        }
                        if (req.semantic_note) {
                            html += `<div style="font-size:0.75rem;color:var(--primary)">💡 ${escapeHtml(req.semantic_note)}</div>`;
                        }
                    }
                    html += `</div>`;
                }
                html += `</div>`;
            }

            if (d.unique_only.length > 0) {
                html += `<div><strong>${t("intercountry.not_covered")}</strong>
                    <div class="diff-clause-list">
                        ${d.unique_only.map(c => `<span class="diff-clause-chip diff-chip-unique">${c}</span>`).join("")}            
                    </div>
                </div>`;
            }

            html += `</div>`;
        }

        if (html) {
            els.intercountryContainer.innerHTML = html;
        } else {
            els.intercountryContainer.innerHTML = `<div class="empty-state"><div class="empty-state-text">${t("intercountry.no_diffs")}</div></div>`;
        }
    }

    // ============================================================
    // Delta Items (Country-Unique Requirements)
    // ============================================================

    function renderDeltaItems(data) {
        const regIds = data.regulation_ids || [];
        const meta = data.regulation_meta || {};
        const uniqueReqs = data.unique_requirements || {};

        let html = "";
        let totalDelta = 0;

        for (const rid of regIds) {
            const reqs = uniqueReqs[rid] || [];
            if (reqs.length === 0) continue;
            totalDelta += reqs.length;

            const m = meta[rid] || {};
            const flag = FLAG_EMOJIS[m.country] || "";

            html += `<div class="delta-country-group">
                <h4>${flag} ${escapeHtml(m.country_name_zh || rid)} — ${t("delta.unique_count", {country: "", count: reqs.length})}</h4>`;

            for (const req of reqs) {
                const confClass = req.confidence >= 0.9 ? "confidence-high" : req.confidence >= 0.7 ? "confidence-medium" : "confidence-low";
                const methodLabel = getMethodLabel(req.method);

                html += `<div class="delta-item">
                    <div class="di-ref">${escapeHtml(req.regulation_ref)}</div>
                    <div class="di-title">${escapeHtml(req.title_zh)} / ${escapeHtml(req.title_en)}</div>
                    <div class="di-req">${escapeHtml(req.requirement_zh)}</div>`;

                // Native text with translation
                if (req.original_text) {
                    const langLabel = getLangLabel(req.original_lang) || req.original_lang || "";
                    html += `<div style="margin:8px 0;padding:8px;background:var(--bg);border-radius:4px;border-left:3px solid var(--primary)">
                        <div style="font-size:0.72rem;font-weight:600;color:var(--text-secondary);margin-bottom:4px">${t("crossref.original_text")} (${langLabel})</div>
                        <div style="font-style:italic;font-size:0.8rem">${escapeHtml(req.original_text)}</div>`;
                    if (req.english_translation) {
                        html += `<div style="margin-top:6px;font-size:0.72rem;font-weight:600;color:var(--text-secondary)">🇬🇧 English Translation</div>
                            <div style="font-size:0.8rem">${escapeHtml(req.english_translation)}</div>`;
                    }
                    if (req.semantic_note) {
                        html += `<div style="margin-top:6px;font-size:0.72rem;font-weight:600;color:var(--primary)">${t("delta.semantic_analysis")}</div>
                            <div style="font-size:0.8rem;color:var(--primary)">${escapeHtml(req.semantic_note)}</div>`;
                    }
                    html += `</div>`;
                }

                html += `<div class="di-question">${t("delta.audit_question")} ${escapeHtml(req.audit_question_zh)}</div>
                    <div class="di-meta">
                        <span>${t("delta.related_iso")} ${(req.related_iso_clauses || []).join(", ")}</span>
                        <span>${t("delta.impact")} ${escapeHtml(req.audit_impact)}</span>
                        <span class="method-badge">${methodLabel}</span>
                        <span class="rc-confidence ${confClass}">${t("delta.confidence", {value: Math.round((req.confidence || 0) * 100)})}</span>
                    </div>
                </div>`;
            }

            html += `</div>`;
        }

        if (totalDelta === 0) {
            html = `<div class="empty-state"><div class="empty-state-text">${t("delta.no_items")}</div></div>`;
        }

        els.deltaItemsContainer.innerHTML = html;
    }


    // ============================================================
    // Real-Time Cross-Examination Viewer (SSE)
    // ============================================================

    let sseSource = null;  // EventSource instance
    let sseConnected = false;

    function connectSSE() {
        const runId = (els.sseRunIdInput && els.sseRunIdInput.value.trim()) || RUN_ID;
        if (!runId) {
            showToast(t("crossexam.enter_run_id"), "error");
            return;
        }

        // Close existing connection
        if (sseSource) {
            sseSource.close();
            sseSource = null;
        }

        // Clear feed
        els.crossexamFeed.innerHTML = "";
        addSystemMessage(t("crossexam.connecting"));

        try {
            sseSource = new EventSource(`${API_BASE}/${encodeURIComponent(runId)}/stream`);

            sseSource.onopen = function () {
                sseConnected = true;
                updateSSEStatus("connected", t("sse.streaming"));
                els.btnConnectSSE.textContent = t("crossexam.disconnect");
                els.btnPauseExam.disabled = false;
                els.humanMessageInput.disabled = false;
                els.btnSendHuman.disabled = false;
            };

            sseSource.onmessage = function (event) {
                try {
                    const data = JSON.parse(event.data);
                    handleSSEEvent(data);
                } catch (e) {
                    console.error("SSE parse error:", e);
                }
            };

            sseSource.onerror = function () {
                if (sseConnected) {
                    addSystemMessage(t("crossexam.reconnecting"));
                    updateSSEStatus("", t("crossexam.reconnect_status"));
                }
            };

        } catch (err) {
            showToast(t("crossexam.sse_error", {error: err.message}), "error");
        }
    }

    function disconnectSSE() {
        if (sseSource) {
            sseSource.close();
            sseSource = null;
        }
        sseConnected = false;
        updateSSEStatus("", t("crossexam.disconnected"));
        els.btnConnectSSE.textContent = t("crossexam.connect");
        els.btnPauseExam.disabled = true;
        els.btnResumeExam.disabled = true;
        els.humanMessageInput.disabled = true;
        els.btnSendHuman.disabled = true;
    }

    // Active phase filter
    let activePhaseFilter = 'all';

    function filterSSEFeedByPhase(phase) {
        activePhaseFilter = phase;
        const cards = els.crossexamFeed.querySelectorAll('.crossexam-card, .exam-message, .msg-round-divider');
        cards.forEach(card => {
            if (phase === 'all') {
                card.style.display = '';
            } else {
                const cardPhase = card.dataset.phase || '';
                card.style.display = (cardPhase === phase) ? '' : 'none';
            }
        });
    }

    function handleSSEEvent(data) {
        const type = data.type;

        switch (type) {
            // ── Pipeline lifecycle ──
            case 'connected':
                addSystemMessage(t("sse.connected"));
                updateSSEStatus('streaming', t("sse.streaming"));
                break;

            case 'pipeline_started':
                addSystemMessage(t("sse.pipeline_started"));
                break;

            case 'pipeline_complete':
                addSystemMessage(t("sse.pipeline_complete"));
                updateSSEStatus('connected', t("sse.complete"));
                break;

            // ── Phase 1: Gap Scan ──
            case 'phase_1_start':
                addPhaseCard('1', 'Gap Scan', data, 'start');
                break;
            case 'phase_1_result':
                addPhaseCard('1', 'Gap Scan', data, 'result');
                break;
            case 'phase_1_error':
                addPhaseCard('1', 'Gap Scan', data, 'error');
                break;

            // ── Phase 2: Checklist Verify ──
            case 'phase_2_start':
                addPhaseCard('2', t("crossexam.phase_verify"), data, 'start');
                break;
            case 'phase_2_result':
                addPhaseCard('2', t("crossexam.phase_verify"), data, 'result');
                break;
            case 'phase_2_error':
                addPhaseCard('2', t("crossexam.phase_verify"), data, 'error');
                break;

            // ── Phase 4: Remediation ──
            case 'phase_4_start':
                addPhaseCard('4', t("crossexam.phase_remediation"), data, 'start');
                break;
            case 'phase_4_result':
                addPhaseCard('4', t("crossexam.phase_remediation"), data, 'result');
                break;
            case 'phase_4_error':
                addPhaseCard('4', t("crossexam.phase_remediation"), data, 'error');
                break;

            // ── Phase 5: Cross-Examination ──
            case 'phase_5_start':
                addPhaseCard('5', t("crossexam.phase_crossexam"), data, 'start');
                break;
            case 'phase_5_result':
                addPhaseCard('5', t("crossexam.phase_crossexam"), data, 'result');
                break;
            case 'phase_5_error':
                addPhaseCard('5', t("crossexam.phase_crossexam"), data, 'error');
                break;

            // ── Phase 5 sub-events (Analyzer/Verifier debate) ──
            case 'verification_start':
                addSystemMessage(t("sse.verification_start", {clause_id: data.clause_id, clause_title: data.clause_title || ''}), '5');
                break;
            case 'round_start':
                addRoundDivider(data.round, '5');
                break;
            case 'analyzer':
                addExamMessage('analyzer', t("sse.analyzer"), data.content, data.clause_id, null, '5');
                break;
            case 'verifier':
                addExamMessage('verifier', t("sse.verifier"), data.content, data.clause_id, null, '5');
                break;
            case 'round_end': {
                const resultText = data.agreed ? t("sse.round_agreed") : t("sse.round_disagreed");
                addSystemMessage(`${resultText} (${data.clause_id})`, '5');
                break;
            }
            case 'verification_complete':
                addSystemMessage(data.agreed ? t("sse.verification_complete_agreed", {clause_id: data.clause_id}) : t("sse.verification_complete_flagged", {clause_id: data.clause_id}), '5');
                break;

            // ── Human intervention ──
            case 'human_injection':
                addExamMessage('human', t("sse.human_label", {user_id: data.user_id || t("sse.human_default")}), data.message, null, data.timestamp);
                break;

            case 'row_reset':
                addSystemMessage(`🔄 ${data.message || t("sse.row_reset_default", {row_id: data.row_id})}`);
                // Refresh table to show updated row status
                loadReport();
                break;

            // ── Control events ──
            case 'complete':
                addSystemMessage(t("sse.complete_verdict", {verdict: data.verdict || '—', flagged: data.flagged ? t("sse.flagged_label") : ''}));
                updateSSEStatus('connected', t("sse.complete"));
                break;
            case 'error':
                addSystemMessage(t("sse.error_msg", {message: data.message || data.error || t("sse.unknown_error")}));
                break;
            case 'pause':
                addSystemMessage(t("sse.paused"));
                updateSSEStatus('connected', t("sse.paused"));
                els.btnPauseExam.disabled = true;
                els.btnResumeExam.disabled = false;
                break;
            case 'resume':
                addSystemMessage(t("sse.resumed"));
                updateSSEStatus('streaming', t("sse.streaming"));
                els.btnPauseExam.disabled = false;
                els.btnResumeExam.disabled = true;
                break;
            case 'heartbeat':
                break;
            default:
                console.log('Unknown SSE event type:', type, data);
        }

        // Auto-scroll to bottom
        els.crossexamFeed.scrollTop = els.crossexamFeed.scrollHeight;
    }

    /**
     * Format raw LLM response JSON into user-friendly HTML.
     * Handles Phase 1 (gap scan), Phase 2 (verify), Phase 4 (remediation) formats.
     */
    function formatLlmResponse(responseText, phaseNum) {
        let parsed = null;
        try {
            // Try to extract JSON from response (may have markdown code fences)
            let jsonStr = responseText;
            const fenceMatch = responseText.match(/```(?:json)?\s*([\s\S]*?)```/);
            if (fenceMatch) jsonStr = fenceMatch[1];
            parsed = JSON.parse(jsonStr);
        } catch (e) {
            // Not valid JSON — show as collapsible raw text
            return `
                <span class="collapsible-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')">${t("llm.view_response")}</span>
                <div class="collapsible-content">
                    <div class="llm-response-preview">${escapeHtml(responseText)}</div>
                </div>`;
        }

        let html = '';

        // Phase 1: Gap Scan — clause_results with evidence_results
        if (parsed.clause_results) {
            const clauses = Object.entries(parsed.clause_results);
            html += `<div class="llm-formatted-results">`;
            for (const [clauseId, clauseData] of clauses) {
                const evidences = clauseData.evidence_results || [];
                const foundCount = evidences.filter(e => e.found && !e.is_inadequate).length;
                const notFoundCount = evidences.filter(e => !e.found).length;
                const inadequateCount = evidences.filter(e => e.found && e.is_inadequate).length;

                html += `<div class="llm-clause-card">`;
                html += `<div class="llm-clause-header">${t("llm.clause_header", {clause_id: escapeHtml(clauseId)})}</div>`;
                html += `<div class="llm-clause-summary">${t("llm.found_count", {found: foundCount, inadequate: inadequateCount, not_found: notFoundCount})}</div>`;

                for (const ev of evidences) {
                    const icon = ev.found ? (ev.is_inadequate ? '⚠️' : '✅') : '❌';
                    const evClass = ev.found ? (ev.is_inadequate ? 'inadequate' : 'found') : 'not-found';
                    html += `<div class="llm-evidence-item ${evClass}">`;
                    html += `<div class="llm-evidence-name">${icon} ${escapeHtml(ev.evidence_name || t("llm.unknown_evidence"))}</div>`;
                    if (ev.source_section) {
                        html += `<div class="llm-evidence-detail">📍 ${escapeHtml(ev.source_section)}</div>`;
                    }
                    if (ev.source_quote) {
                        html += `<div class="llm-evidence-quote">“${escapeHtml(ev.source_quote.substring(0, 150))}${ev.source_quote.length > 150 ? '...' : ''}”</div>`;
                    }
                    if (ev.reasoning) {
                        html += `<div class="llm-evidence-detail">💭 ${escapeHtml(ev.reasoning)}</div>`;
                    }
                    if (ev.relevance_score != null) {
                        const pct = Math.round(ev.relevance_score * 100);
                        html += `<div class="llm-evidence-detail">📊 相關度: ${pct}%</div>`;
                    }
                    html += `</div>`;
                }
                html += `</div>`;
            }
            html += `</div>`;
            // Also keep raw view as collapsible fallback
            html += `<span class="collapsible-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')" style="margin-top:8px;display:inline-block">${t("llm.view_raw")}</span>`;
            html += `<div class="collapsible-content"><div class="llm-response-preview">${escapeHtml(responseText)}</div></div>`;
            return html;
        }

        // Phase 4: Remediation — suggestions
        if (parsed.suggestions || parsed.remediation_suggestions) {
            const suggestions = parsed.suggestions || parsed.remediation_suggestions || [];
            html += `<div class="llm-formatted-results">`;
            for (const s of (Array.isArray(suggestions) ? suggestions : [])) {
                html += `<div class="llm-clause-card">`;
                html += `<div class="llm-clause-header">${t("llm.remediation_header", {title: escapeHtml(s.clause_id || s.title || t("llm.suggestion_default"))})}</div>`;
                if (s.suggestion || s.recommendation) {
                    html += `<div class="llm-evidence-detail">${escapeHtml(s.suggestion || s.recommendation)}</div>`;
                }
                if (s.regulation_cite) {
                    html += `<div class="llm-evidence-detail">📖 ${escapeHtml(s.regulation_cite)}</div>`;
                }
                html += `</div>`;
            }
            html += `</div>`;
            html += `<span class="collapsible-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')" style="margin-top:8px;display:inline-block">${t("llm.view_raw")}</span>`;
            html += `<div class="collapsible-content"><div class="llm-response-preview">${escapeHtml(responseText)}</div></div>`;
            return html;
        }

        // Generic parsed JSON — try to render key-value pairs nicely
        html += `<div class="llm-formatted-results">`;
        for (const [key, value] of Object.entries(parsed)) {
            if (typeof value === 'object' && value !== null) {
                html += `<div class="llm-clause-card">`;
                html += `<div class="llm-clause-header">${escapeHtml(key)}</div>`;
                html += `<div class="llm-evidence-detail">${escapeHtml(JSON.stringify(value, null, 2).substring(0, 500))}</div>`;
                html += `</div>`;
            } else {
                html += `<div class="llm-evidence-detail"><strong>${escapeHtml(key)}</strong>: ${escapeHtml(String(value))}</div>`;
            }
        }
        html += `</div>`;
        html += `<span class="collapsible-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')" style="margin-top:8px;display:inline-block">${t("llm.view_raw")}</span>`;
        html += `<div class="collapsible-content"><div class="llm-response-preview">${escapeHtml(responseText)}</div></div>`;
        return html;
    }


    /**
     * Add a phase card to the SSE feed.
     * @param {string} phaseNum - '1', '2', '4', '5'
     * @param {string} phaseName - Display name
     * @param {object} data - SSE event data
     * @param {string} status - 'start', 'result', 'error'
     */
    function addPhaseCard(phaseNum, phaseName, data, status) {
        const card = document.createElement('div');
        const isError = status === 'error';
        card.className = `crossexam-card phase-${phaseNum}${isError ? ' error' : ''}${status === 'start' ? ' loading' : ''}`;
        card.dataset.phase = phaseNum;

        // Respect active filter
        if (activePhaseFilter !== 'all' && activePhaseFilter !== phaseNum) {
            card.style.display = 'none';
        }

        const now = new Date().toLocaleTimeString();
        const docInfo = data.doc_id ? `${data.doc_id}${data.doc_title ? ' — ' + data.doc_title : ''}` : '';
        const clauseIds = (data.clause_ids || []).join(', ');

        let statusIcon = '🔄';
        let statusText = t("sse.phase_running");
        if (status === 'result') {
            statusIcon = '✅';
            statusText = t("sse.phase_done");
        } else if (status === 'error') {
            statusIcon = '❌';
            statusText = t("sse.phase_error");
        }

        let bodyHtml = '';
        if (status === 'start' && data.prompt_preview) {
            bodyHtml = `
                <span class="collapsible-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')">${t("llm.view_prompt")}</span>
                <div class="collapsible-content">
                    <div class="llm-prompt-preview">${escapeHtml(data.prompt_preview)}</div>
                </div>`;
        } else if (status === 'result') {
            const summary = [];
            if (data.evidence_summary) {
                summary.push(`${t("sse.evidence_found")}: ${data.evidence_summary.found || 0} | ${t("sse.evidence_not_found")}: ${data.evidence_summary.not_found || 0} | ${t("sse.evidence_inadequate")}: ${data.evidence_summary.inadequate || 0}`);
            }
            if (data.total_suggestions !== undefined) {
                summary.push(t("sse.suggestions_count", {count: data.total_suggestions}));
            }
            if (data.total_agreed !== undefined) {
                summary.push(t("sse.agreed_count", {agreed: data.total_agreed, flagged: data.total_flagged || 0}));
            }
            if (data.usage) {
                summary.push(`Token: ${(data.usage.total_tokens || 0).toLocaleString()}`);
            }
            bodyHtml = summary.length > 0 ? `<div style="margin-bottom:6px">${summary.join(' | ')}</div>` : '';
            if (data.llm_response) {
                bodyHtml += formatLlmResponse(data.llm_response, phaseNum);
            }
        } else if (status === 'error') {
            bodyHtml = `<div style="color:#dc2626">${escapeHtml(data.error || t("sse.unknown_error"))}</div>`;
        }

        card.innerHTML = `
            <div class="crossexam-card-header">
                <span class="phase-badge phase-${phaseNum}">P${phaseNum}</span>
                <span style="font-weight:600">${statusIcon} ${phaseName}</span>
                <span class="card-doc-info">${escapeHtml(docInfo)}</span>
                <span class="card-timestamp">${now}</span>
            </div>
            ${clauseIds ? `<div style="font-size:0.8rem;color:#64748b;margin-bottom:4px">${t("sse.clauses")} ${escapeHtml(clauseIds)}</div>` : ''}
            <div class="crossexam-card-body">${bodyHtml}</div>`;

        // If it's a 'start' event, mark previous start card for same doc as done
        if (status === 'start') {
            const prevLoading = els.crossexamFeed.querySelectorAll(`.crossexam-card.loading.phase-${phaseNum}[data-doc="${data.doc_id}"]`);
            prevLoading.forEach(el => el.classList.remove('loading'));
        }
        if (data.doc_id) card.dataset.doc = data.doc_id;

        els.crossexamFeed.appendChild(card);
    }

    function addExamMessage(type, role, content, regulation, timestamp, phase) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `exam-message msg-${type}`;
        if (phase) msgDiv.dataset.phase = phase;

        // Respect active filter
        if (phase && activePhaseFilter !== 'all' && activePhaseFilter !== phase) {
            msgDiv.style.display = 'none';
        }

        const timeStr = timestamp ? new Date(timestamp * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();
        const regBadge = regulation ? `<span class="msg-regulation">${escapeHtml(regulation)}</span>` : '';

        msgDiv.innerHTML = `
            <div class="msg-header">
                <span class="msg-role role-${type}">${role}</span>
                <span>${regBadge} <span class="msg-time">${timeStr}</span></span>
            </div>
            <div class="msg-body">${escapeHtml(content || '')}</div>`;

        els.crossexamFeed.appendChild(msgDiv);
    }

    function addSystemMessage(text, phase) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'exam-message msg-system';
        if (phase) msgDiv.dataset.phase = phase;
        msgDiv.textContent = text;

        // Respect active filter
        if (phase && activePhaseFilter !== 'all' && activePhaseFilter !== phase) {
            msgDiv.style.display = 'none';
        }

        els.crossexamFeed.appendChild(msgDiv);
    }

    function addRoundDivider(round, phase) {
        const div = document.createElement('div');
        div.className = 'msg-round-divider';
        if (phase) div.dataset.phase = phase;
        div.textContent = t("sse.round_divider", {round: round});

        // Respect active filter
        if (phase && activePhaseFilter !== 'all' && activePhaseFilter !== phase) {
            div.style.display = 'none';
        }

        els.crossexamFeed.appendChild(div);
    }

    function updateSSEStatus(className, text) {
        if (els.crossexamStatus) {
            els.crossexamStatus.className = `crossexam-status ${className}`;
            els.crossexamStatus.textContent = text;
        }
    }

    async function pauseExam() {
        const runId = (els.sseRunIdInput && els.sseRunIdInput.value.trim()) || RUN_ID;
        if (!runId) return;
        try {
            await apiPost(`/${runId}/pause`, {});
        } catch (err) {
            showToast(t("crossexam.pause_error", {error: err.message}), "error");
        }
    }

    async function resumeExam() {
        const runId = (els.sseRunIdInput && els.sseRunIdInput.value.trim()) || RUN_ID;
        if (!runId) return;
        try {
            await apiPost(`/${runId}/resume`, {});
        } catch (err) {
            showToast(t("crossexam.resume_error", {error: err.message}), "error");
        }
    }

    async function sendHumanMessage() {
        const message = els.humanMessageInput.value.trim();
        if (!message) return;

        const runId = (els.sseRunIdInput && els.sseRunIdInput.value.trim()) || RUN_ID;
        if (!runId) return;

        // Check for dialog commands before sending as chat
        if (message.startsWith("/")) {
            const handled = await handleDialogCommand(message);
            if (handled) {
                els.humanMessageInput.value = "";
                return;
            }
        }

        els.btnSendHuman.disabled = true;
        try {
            await apiPost(`/${runId}/inject`, { message: message });
            els.humanMessageInput.value = "";
        } catch (err) {
            showToast(t("crossexam.send_error", {error: err.message}), "error");
        } finally {
            els.btnSendHuman.disabled = false;
        }
    }

    /**
     * Handle dialog commands typed in the cross-examination input.
     *
     * Supported commands:
     *   /adjust <standard_id> "<clause_name>" <old_clause> -> <new_clause>
     *     Example: /adjust ISO_14971 "Clause 4 (Risk management process)" 7.1 -> 7.3.3
     *
     *   /standards  — List all supplemental standards and their clause mappings
     *
     *   /help  — Show available commands
     *
     * @param {string} message - The user's input starting with /
     * @returns {boolean} true if command was handled
     */
    async function handleDialogCommand(message) {
        const parts = message.split(/\s+/);
        const cmd = parts[0].toLowerCase();

        if (cmd === "/help") {
            appendSystemMessage(
                `<strong>${t("dialog.help_title")}</strong><br>` +
                `<code>/adjust &lt;standard_id&gt; "&lt;clause_name&gt;" &lt;old&gt; -&gt; &lt;new&gt;</code><br>` +
                `&nbsp;&nbsp;${t("dialog.help_adjust_desc")}<br>` +
                `&nbsp;&nbsp;${t("dialog.help_adjust_example")} <code>/adjust ISO_14971 "Clause 4 (Risk management process)" 7.1 -> 7.3.3</code><br><br>` +
                `<code>/standards</code> — ${t("dialog.help_standards_desc")}<br>` +
                `<code>/help</code> — ${t("dialog.help_help_desc")}`
            );
            return true;
        }

        if (cmd === "/standards") {
            try {
                const resp = await fetch("/api/report/standards/list");
                const data = await resp.json();
                let html = `<strong>${t("dialog.standards_title", {count: data.standards.length})}</strong><br>`;
                for (const std of data.standards) {
                    html += `<br><strong>${std.name_zh}</strong> (${std.standard_id})<br>`;
                    for (const cl of std.clause_links) {
                        html += `&nbsp;&nbsp;${cl.standard_clause} \u2192 ISO 13485 ${cl.iso_13485_clause}<br>`;
                    }
                }
                appendSystemMessage(html);
            } catch (err) {
                showToast(t("dialog.standards_load_error", {error: err.message}), "error");
            }
            return true;
        }

        if (cmd === "/adjust") {
            // Parse: /adjust <standard_id> "<clause_name>" <old> -> <new>
            const adjustMatch = message.match(
                /\/adjust\s+(\S+)\s+"([^"]+)"\s+(\S+)\s*->\s*(\S+)/
            );
            if (!adjustMatch) {
                appendSystemMessage(
                    `<span style="color:#e74c3c">${t("dialog.adjust_format_error")}</span><br>` +
                    `<code>/adjust &lt;standard_id&gt; "&lt;clause_name&gt;" &lt;old_clause&gt; -&gt; &lt;new_clause&gt;</code><br>` +
                    `${t("dialog.adjust_example")} <code>/adjust ISO_14971 "Clause 4 (Risk management process)" 7.1 -> 7.3.3</code>`
                );
                return true;
            }
            const [, standardId, clauseName, oldClause, newClause] = adjustMatch;
            try {
                const resp = await fetch("/api/report/standards/adjust", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        standard_id: standardId,
                        standard_clause: clauseName,
                        old_iso_clause: oldClause,
                        new_iso_clause: newClause,
                    }),
                });
                const result = await resp.json();
                if (result.success) {
                    appendSystemMessage(
                        `<span style="color:#27ae60">✓ ${result.message}</span>`
                    );
                } else {
                    appendSystemMessage(
                        `<span style="color:#e74c3c">✗ ${result.message}</span>`
                    );
                }
            } catch (err) {
                showToast(t("dialog.adjust_error", {error: err.message}), "error");
            }
            return true;
        }

        // Not a recognized command
        return false;
    }

    /**
     * Append a system-level message to the cross-examination log.
     */
    function appendSystemMessage(html) {
        const target = els.crossexamFeed;
        if (!target) return;
        const div = document.createElement("div");
        div.className = "cross-exam-system-msg";
        div.innerHTML = html;
        target.appendChild(div);
        target.scrollTop = target.scrollHeight;
    }


    // ============================================================
    // Verification Tab
    // ============================================================

    /**
     * Load full verification report from the API and render all sections.
     */
    async function loadVerification() {
        // Show loading state
        if (els.verNoData) {
            els.verNoData.style.display = "block";
            if (els.verNoDataMsg) els.verNoDataMsg.textContent = t("verification.verifying");
        }
        if (els.verCrossChecks) els.verCrossChecks.style.display = "none";
        if (els.verTableWrapper) els.verTableWrapper.style.display = "none";

        try {
            const data = await apiFetch("/verification/full");
            verificationLoaded = true;
            renderVerification(data);
        } catch (err) {
            if (els.verNoData) {
                els.verNoData.style.display = "block";
                if (els.verNoDataMsg) {
                    els.verNoDataMsg.textContent = t("verification.verify_error", {error: err.message});
                }
            }
            showToast(t("verification.verify_toast_error", {error: err.message}), "error");
        }
    }

    /**
     * Render the full verification report.
     */
    function renderVerification(data) {
        // Handle no-data state
        if (!data.has_data) {
            renderVerificationNoData(data.no_data_message || t("verification.no_data_default"));
            return;
        }

        // Hide no-data, show results
        if (els.verNoData) els.verNoData.style.display = "none";

        // Summary cards
        renderVerificationSummary(data);

        // Cross checks
        renderVerificationCrossChecks(data.cross_checks || []);

        // Document table
        renderVerificationTable(data.documents || []);

        // Timestamp
        if (els.verTimestamp && data.verified_at) {
            const d = new Date(data.verified_at);
            els.verTimestamp.textContent = t("verification.timestamp", {time: d.toLocaleString()});
        }
    }

    /**
     * Show the no-data empty state.
     */
    function renderVerificationNoData(message) {
        if (els.verNoData) {
            els.verNoData.style.display = "block";
            if (els.verNoDataMsg) els.verNoDataMsg.textContent = message;
        }
        if (els.verCrossChecks) els.verCrossChecks.style.display = "none";
        if (els.verTableWrapper) els.verTableWrapper.style.display = "none";
        // Reset summary cards to dashes
        if (els.verPassCount) els.verPassCount.textContent = "—";
        if (els.verWarnCount) els.verWarnCount.textContent = "—";
        if (els.verFailCount) els.verFailCount.textContent = "—";
        if (els.verTotalCount) els.verTotalCount.textContent = "—";
        if (els.verTimestamp) els.verTimestamp.textContent = "";
    }

    /**
     * Render verification summary cards.
     */
    function renderVerificationSummary(data) {
        if (els.verPassCount) els.verPassCount.textContent = data.passed_count ?? "—";
        if (els.verWarnCount) els.verWarnCount.textContent = data.warning_count ?? "—";
        if (els.verFailCount) els.verFailCount.textContent = data.failed_count ?? "—";
        if (els.verTotalCount) els.verTotalCount.textContent = data.total_documents ?? "—";
    }

    /**
     * Render cross-check results list.
     */
    function renderVerificationCrossChecks(crossChecks) {
        if (!els.verCrossChecks || !els.verCrossChecksList) return;

        if (!crossChecks.length) {
            els.verCrossChecks.style.display = "none";
            return;
        }

        els.verCrossChecks.style.display = "block";
        els.verCrossChecksList.innerHTML = crossChecks.map(function (c) {
            var icon = c.passed ? "✅" : (c.severity === "critical" ? "🔴" : "🟡");
            var cls = c.passed ? "cross-check-pass" : "cross-check-fail";
            return (
                '<div class="cross-check-item ' + cls + '" style="padding:6px 10px;margin-bottom:4px;' +
                'border-radius:6px;background:' + (c.passed ? '#f0fdf4' : '#fef2f2') + '">' +
                '<span style="margin-right:6px">' + icon + '</span>' +
                '<strong>' + escapeHtml(c.check_name) + '</strong>: ' +
                escapeHtml(c.message) +
                '</div>'
            );
        }).join("");
    }

    /**
     * Render the per-document verification table.
     */
    function renderVerificationTable(documents) {
        if (!els.verTableWrapper || !els.verTableBody) return;

        if (!documents.length) {
            els.verTableWrapper.style.display = "none";
            return;
        }

        els.verTableWrapper.style.display = "block";

        els.verTableBody.innerHTML = documents.map(function (doc) {
            var statusIcon = doc.overall_status === "pass" ? "🟢" :
                             doc.overall_status === "warning" ? "🟡" : "🔴";

            // Summarize checks
            var passedChecks = doc.checks.filter(function (c) { return c.passed; }).length;
            var totalChecks = doc.checks.length;
            var checksSummary = t("verification.checks_passed", {passed: passedChecks, total: totalChecks});

            // Collect failed/warning check messages
            var issues = doc.checks
                .filter(function (c) { return !c.passed; })
                .map(function (c) { return escapeHtml(c.message); })
                .join("<br>");
            if (!issues) issues = '<span style="color:#16a34a">' + t("verification.no_issues") + '</span>';

            // Truncate URL for display
            var displayUrl = doc.url || "—";
            if (displayUrl.length > 50) {
                displayUrl = displayUrl.substring(0, 47) + "…";
            }

            return (
                '<tr>' +
                '<td>' + escapeHtml(doc.region || '—') + '</td>' +
                '<td>' + escapeHtml(doc.agency || '—') + '</td>' +
                '<td title="' + escapeHtml(doc.url || '') + '">' + escapeHtml(displayUrl) + '</td>' +
                '<td style="text-align:center">' + statusIcon + '</td>' +
                '<td>' + checksSummary + '</td>' +
                '<td>' + issues + '</td>' +
                '</tr>'
            );
        }).join("");
    }

    // ============================================================
    // Init
    // ============================================================

    async function init() {
        if (!_localeReady) await loadLocale();
        bindEvents();
        loadReport();
        // Pre-fill SSE run ID input
        if (els.sseRunIdInput && RUN_ID) {
            els.sseRunIdInput.value = RUN_ID;
        }
    }

    // Wait for DOM ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

})();
