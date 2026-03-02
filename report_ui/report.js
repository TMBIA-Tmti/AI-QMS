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

    // ── State ──
    let reportData = null;       // Full report response
    let filteredRows = [];       // Currently displayed rows
    let currentRowId = null;     // Row being edited in a modal
    let filterOptions = null;    // Cached filter options

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
        if (seconds < 60) return `${seconds.toFixed(1)} 秒`;
        const mins = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return `${mins} 分 ${secs} 秒`;
    }


    // ============================================================
    // Load Report Data
    // ============================================================

    async function loadReport() {
        if (!RUN_ID) {
            els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">❌ 無效的報告 ID</td></tr>`;
            return;
        }

        els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">⏳ 載入中...</td></tr>`;

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
            els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">❌ 載入失敗: ${escapeHtml(err.message)}</td></tr>`;
            showToast(`載入失敗: ${err.message}`, "error");
        }
    }


    // ============================================================
    // Render Header
    // ============================================================

    function renderHeader(data) {
        els.headerRunId.textContent = data.run_id || "";

        const statusMap = {
            completed: { text: "✅ 已完成", cls: "status-completed" },
            running: { text: "⏳ 執行中", cls: "status-running" },
            paused: { text: "⏸️ 已暫停", cls: "status-paused" },
            failed: { text: "❌ 失敗", cls: "status-failed" },
            pending: { text: "⏳ 等待中", cls: "status-running" },
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
        els.filterDoc.innerHTML = '<option value="">全部文件</option>';
        (filters.documents || []).forEach((d) => {
            const opt = document.createElement("option");
            opt.value = d.id;
            opt.textContent = `${d.id} — ${d.title}`;
            els.filterDoc.appendChild(opt);
        });

        // Verdicts
        els.filterVerdict.innerHTML = '<option value="">全部結果</option>';
        (filters.verdicts || []).forEach((v) => {
            const opt = document.createElement("option");
            opt.value = v.value;
            opt.textContent = `${v.icon || ""} ${v.label_zh || v.value}`;
            els.filterVerdict.appendChild(opt);
        });

        // Risk levels
        els.filterRisk.innerHTML = '<option value="">全部等級</option>';
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
        els.tableCount.textContent = `顯示 ${rows.length} / ${reportData.rows.length} 項`;
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
                        <div class="empty-state-text">無符合條件的項目</div>
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
            <td class="col-flags">${flagged ? '<span class="flag-icon" title="需 RA 審查">🚩</span>' : ""}</td>
            <td class="col-actions">
                <div class="action-group">
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openDetail('${escapeAttr(r.row_id)}')" title="詳情">🔍</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openOverride('${escapeAttr(r.row_id)}')" title="覆寫判定">✏️</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openNote('${escapeAttr(r.row_id)}')" title="備註">📝</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openHistory('${escapeAttr(r.row_id)}')" title="歷史">📜</button>
                    ${r.ra_override ? `<button class="btn btn-sm btn-success" onclick="window.__report.restoreOriginal('${escapeAttr(r.row_id)}')" title="還原 LLM 原始判定">↩️</button>` : ""}
                </div>
            </td>
        </tr>`;
    }

    function getVerdictBadge(verdict, icon, label, hasOverride) {
        if (!verdict) return '<span class="badge badge-insufficient">— 未判定</span>';
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
        if (!risk) return '<span class="badge badge-insufficient">— 未評估</span>';
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
                <h3>📋 基本資訊</h3>
                <div class="detail-grid">
                    <span class="detail-label">條款 ID</span>
                    <span class="detail-value">${escapeHtml(row.clause_id)}</span>
                    <span class="detail-label">條款標題</span>
                    <span class="detail-value">${escapeHtml(row.clause_title)}</span>
                    <span class="detail-label">品質文件</span>
                    <span class="detail-value">${escapeHtml(row.doc_id)} — ${escapeHtml(row.doc_title)}</span>
                    <span class="detail-label">稽核影響</span>
                    <span class="detail-value">${escapeHtml(row.audit_impact)}</span>
                    <span class="detail-label">稽核問題</span>
                    <span class="detail-value">${escapeHtml(row.audit_question || "—")}</span>
                    <span class="detail-label">判定結果</span>
                    <span class="detail-value">${getVerdictBadge(row.verdict, row.verdict_icon, row.verdict_label_zh, !!row.ra_override)}</span>
                    <span class="detail-label">風險等級</span>
                    <span class="detail-value">${getRiskBadge(row.risk_level, row.risk_icon, row.risk_label_zh)}</span>
                </div>
            </div>`;

            // RA Override info
            if (row.ra_override) {
                html += `<div class="ra-override-info">
                    <strong>✏️ RA 已覆寫判定</strong>：${escapeHtml(row.ra_override.verdict)} — ${escapeHtml(row.ra_override.reason || "")}
                    <div style="font-size:0.75rem;color:#64748b;margin-top:4px">
                        覆寫者: ${escapeHtml(row.ra_override.by || "—")} | 
                        時間: ${formatTimestamp(row.ra_override.at)}
                    </div>
                </div>`;
            }

            // RA Notes
            if (row.ra_notes) {
                html += `<div class="ra-notes">
                    <strong>📝 RA 備註</strong>：${escapeHtml(row.ra_notes)}
                </div>`;
            }

            // Evidence items
            const evidenceItems = row.evidence_items || [];
            if (evidenceItems.length > 0) {
                html += `<div class="detail-section">
                    <h3>🔍 證據項目 (${evidenceItems.filter(e => e.found).length}/${evidenceItems.length})</h3>
                    <ul class="evidence-list">`;

                for (const ev of evidenceItems) {
                    const evClass = ev.found ? (ev.is_inadequate ? "inadequate" : "found") : "not-found";
                    const statusIcon = ev.found ? (ev.is_inadequate ? "⚠️" : "✅") : "❌";

                    html += `<li class="evidence-item ${evClass}">
                        <div class="evidence-name">${statusIcon} ${escapeHtml(ev.evidence_name || "未知證據項")}</div>`;

                    if (ev.source_doc_id) {
                        html += `<div class="evidence-source">📄 來源: ${escapeHtml(ev.source_doc_id)}${ev.source_section ? ` — ${escapeHtml(ev.source_section)}` : ""}</div>`;
                    }

                    if (ev.source_quote) {
                        html += `<div class="evidence-quote">"${escapeHtml(ev.source_quote)}"</div>`;
                    }

                    if (ev.llm_reasoning) {
                        html += `<div class="evidence-source">💭 LLM 推理: ${escapeHtml(ev.llm_reasoning)}</div>`;
                    }

                    if (ev.relevance_score != null) {
                        html += `<div class="evidence-source">📊 相關度: ${(ev.relevance_score * 100).toFixed(0)}%</div>`;
                    }

                    html += `</li>`;
                }

                html += `</ul></div>`;
            }

            // Expected evidence (from compliance_rules)
            const expectedEvidence = row.expected_evidence || [];
            if (expectedEvidence.length > 0 && evidenceItems.length === 0) {
                html += `<div class="detail-section">
                    <h3>📋 預期證據</h3>
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
                    <h3>🔄 交叉詰問 (${rounds.length} 輪)</h3>`;

                for (let i = 0; i < rounds.length; i++) {
                    const round = rounds[i];
                    const agreed = round.agreed;
                    const statusText = agreed ? "✅ 一致" : "❌ 不一致";

                    html += `<div class="verification-round">
                        <div class="verification-round-header">
                            <span>第 ${i + 1} 輪</span>
                            <span>${statusText}</span>
                        </div>
                        <div class="verification-round-body">`;

                    if (round.analyzer_response) {
                        html += `<div class="verification-role analyzer">🔍 分析者</div>
                            <div class="verification-text">${escapeHtml(round.analyzer_response)}</div>`;
                    }

                    if (round.verifier_response) {
                        html += `<div class="verification-role verifier">🛡️ 驗證者</div>
                            <div class="verification-text">${escapeHtml(round.verifier_response)}</div>`;
                    }

                    html += `</div></div>`;
                }

                if (row.flagged_for_ra) {
                    html += `<div class="ra-override-info">
                        <strong>🚩 已標記待 RA 審查</strong>：交叉詰問 3 輪後仍有分歧
                    </div>`;
                }

                html += `</div>`;
            }

            // Remediation
            if (row.remediation_suggestion) {
                html += `<div class="detail-section">
                    <h3>🛠️ 改善建議</h3>
                    <div class="remediation-text">${escapeHtml(row.remediation_suggestion)}</div>`;

                if (row.remediation_regulation_cite) {
                    html += `<div style="margin-top:8px;font-size:0.8rem;color:#64748b">
                        📖 法規引用: ${escapeHtml(row.remediation_regulation_cite)}
                    </div>`;
                }

                html += `</div>`;
            }

            // Phase results timeline
            const phaseResults = row.phase_results || {};
            const phaseKeys = Object.keys(phaseResults);
            if (phaseKeys.length > 0) {
                html += `<div class="detail-section">
                    <h3>⏱️ 階段執行記錄</h3>
                    <div class="detail-grid">`;

                const phaseNames = {
                    phase_0: "資料品質檢查",
                    phase_0_5: "法規參照對應",
                    phase_1: "差距掃描",
                    phase_2: "查核表驗證",
                    phase_3: "風險評估",
                    phase_4: "改善建議",
                    phase_5: "獨立驗證",
                    phase_6: "來源驗證",
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
            showToast(`載入詳情失敗: ${err.message}`, "error");
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
            showToast("請填寫覆寫原因", "error");
            return;
        }

        els.overrideSaveBtn.disabled = true;
        els.overrideSaveBtn.textContent = "處理中...";

        try {
            const result = await apiPost(`/${RUN_ID}/row/${currentRowId}/override`, {
                verdict: verdict,
                reason: reason,
            });

            if (result.success) {
                showToast("判定已覆寫", "success");
                closeModal(els.overrideModal);
                updateRowInData(currentRowId, result.row);
                applyFilters();
                refreshSummary();
            }
        } catch (err) {
            showToast(`覆寫失敗: ${err.message}`, "error");
        } finally {
            els.overrideSaveBtn.disabled = false;
            els.overrideSaveBtn.textContent = "確認覆寫";
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
            showToast("請填寫備註內容", "error");
            return;
        }

        els.noteSaveBtn.disabled = true;
        els.noteSaveBtn.textContent = "儲存中...";

        try {
            const result = await apiPost(`/${RUN_ID}/row/${currentRowId}/note`, {
                note: note,
            });

            if (result.success) {
                showToast("備註已儲存", "success");
                closeModal(els.noteModal);
                updateRowInData(currentRowId, result.row);
                applyFilters();
            }
        } catch (err) {
            showToast(`儲存失敗: ${err.message}`, "error");
        } finally {
            els.noteSaveBtn.disabled = false;
            els.noteSaveBtn.textContent = "儲存備註";
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
                        <div class="empty-state-text">此條款尚無修改歷史</div>
                    </div>`;
            } else {
                let html = "";
                // Show in reverse chronological order
                const reversed = history.slice().reverse();
                for (const entry of reversed) {
                    const actionLabels = {
                        override_verdict: "覆寫判定",
                        add_note: "新增備註",
                        restore_original: "還原 LLM 原始判定",
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
                        html += `<div>原判定: ${escapeHtml(entry.previous_verdict || "—")} → 新判定: ${escapeHtml(entry.new_verdict || "—")}</div>
                            <div>原因: ${escapeHtml(entry.reason || "—")}</div>`;
                    } else if (entry.action === "add_note") {
                        html += `<div>備註: ${escapeHtml(entry.new_note || "—")}</div>`;
                    } else if (entry.action === "restore_original") {
                        html += `<div>覆寫判定 ${escapeHtml(entry.overridden_verdict || "—")} → 還原為 ${escapeHtml(entry.restored_verdict || "—")}</div>`;
                    }

                    html += `<div class="history-meta">
                            ${entry.by ? `操作者: ${escapeHtml(entry.by)}` : ""}
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
                        <strong>✏️ 目前覆寫狀態</strong>：${escapeHtml(data.ra_override.verdict || "—")} — ${escapeHtml(data.ra_override.reason || "")}
                    </div>`);
            }

            if (data.ra_notes) {
                els.historyBody.insertAdjacentHTML("afterbegin", `
                    <div class="ra-notes" style="margin-bottom:16px">
                        <strong>📝 目前備註</strong>：${escapeHtml(data.ra_notes)}
                    </div>`);
            }

            openModal(els.historyModal);

        } catch (err) {
            showToast(`載入歷史失敗: ${err.message}`, "error");
        }
    }


    // ============================================================
    // Restore LLM Original
    // ============================================================

    async function restoreOriginal(rowId) {
        if (!confirm("確定要還原為 LLM 原始判定結果嗎？\n（此操作會記錄在版本歷史中）")) {
            return;
        }

        try {
            const result = await apiPost(`/${RUN_ID}/row/${rowId}/restore`, {});

            if (result.success) {
                showToast("已還原 LLM 原始判定", "success");
                updateRowInData(rowId, result.row);
                applyFilters();
                refreshSummary();
            }
        } catch (err) {
            showToast(`還原失敗: ${err.message}`, "error");
        }
    }


    // ============================================================
    // Export
    // ============================================================

    function exportReport(format) {
        const url = `${API_BASE}/${RUN_ID}/export/${format}`;
        showToast(`正在匯出 ${format.toUpperCase()} 報告...`, "info");

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
            });
        }

        // Cross-reference controls
        if (els.btnLoadCrossref) {
            els.btnLoadCrossref.addEventListener("click", loadCrossrefTable);
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

    const METHOD_LABELS = {
        official_crossref: "📜 官方交叉參照",
        clause_structure: "📁 條文結構對應",
        semantic_en: "🇬🇧 英文語意分析",
        semantic_zh: "🇹🇼 中文語意分析",
        keyword_match: "🔑 關鍵字比對",
        expert_judgment: "🧑‍💻 專家判斷",
        llm_analysis: "🤖 LLM 分析",
    };

    const LANG_LABELS = {
        en: "English",
        "zh-TW": "繁體中文",
        "zh-CN": "簡體中文",
        de: "Deutsch",
        fr: "Français",
        ja: "日本語",
        ko: "한국어",
    };

    async function loadCrossrefRegulations() {
        if (!els.countryCheckboxes) return;
        els.countryCheckboxes.innerHTML = '<div class="loading-cell">✨ 載入法規清單中...</div>';

        try {
            const data = await apiFetch("/crossref/regulations");
            crossrefRegulations = data.regulations || [];

            if (crossrefRegulations.length === 0) {
                els.countryCheckboxes.innerHTML = '<div class="loading-cell">❌ 無可用法規</div>';
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
                        <div class="country-meta">✅${fullCount} ⬆️${exceedsCount} 🚨${uniqueCount}獨有</div>
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
            els.countryCheckboxes.innerHTML = `<div class="loading-cell">❌ 載入失敗: ${escapeHtml(err.message)}</div>`;
        }
    }

    async function loadCrossrefTable() {
        // Gather selected regulations
        const checked = els.countryCheckboxes.querySelectorAll("input[type=checkbox]:checked");
        const regIds = Array.from(checked).map((cb) => cb.value);

        if (regIds.length === 0) {
            showToast("請至少選擇一個國家法規", "error");
            return;
        }

        els.btnLoadCrossref.disabled = true;
        els.btnLoadCrossref.textContent = "✨ 產生中...";

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

            showToast(`交叉比對表已產生（${data.rows.length} 條款 × ${regIds.length} 國家）`, "success");
        } catch (err) {
            showToast(`產生失敗: ${err.message}`, "error");
        } finally {
            els.btnLoadCrossref.disabled = false;
            els.btnLoadCrossref.textContent = "📊 產生交叉比對表";
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
                <div class="stat-row"><span>✅ 完全採用</span><strong>${fullCount}</strong></div>
                <div class="stat-row"><span>⬆️ 超越 ISO</span><strong style="color:#2563eb">${exceedsCount}</strong></div>
                <div class="stat-row"><span>⚠️ 部分採用</span><strong style="color:var(--partial)">${partialCount}</strong></div>
                <div class="stat-row"><span>➖ 不適用</span><strong style="color:var(--insufficient)">${naCount}</strong></div>
                <div class="stat-row"><span>🚨 獨有要求</span><strong style="color:var(--non-compliant)">${uniqueReqs.length}</strong></div>
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
        let headHtml = `<tr><th>ISO 13485 條款</th>`;
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
                          title="點擊展開詳情"
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
                const methodLabel = METHOD_LABELS[reg.method] || reg.method || "—";

                bodyHtml += `<div class="rationale-card">
                    <div class="rc-header">${flag} ${escapeHtml(m.country_name_zh || rid)}</div>
                    <div class="rc-field"><span class="rc-label">法規參照:</span> <span class="rc-value">${escapeHtml(reg.regulation_ref || "—")}</span></div>
                    <div class="rc-field"><span class="rc-label">判斷方法:</span> <span class="method-badge">${methodLabel}</span></div>
                    <div class="rc-field"><span class="rc-label">可信度:</span> <span class="rc-confidence ${confClass}">${Math.round(conf * 100)}%</span></div>
                    <div class="rc-field"><span class="rc-label">原因(EN):</span> <span class="rc-value">${escapeHtml(reg.rationale_en || "—")}</span></div>
                    <div class="rc-field"><span class="rc-label">原因(中):</span> <span class="rc-value">${escapeHtml(reg.rationale_zh || "—")}</span></div>`;

                // Native-language regulatory text comparison
                if (reg.original_text) {
                    const langLabel = LANG_LABELS[reg.original_lang] || reg.original_lang || "—";
                    bodyHtml += `<div class="rc-field" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
                        <span class="rc-label">📜 法規原文 (${langLabel}):</span>
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
                            <span class="rc-label">💡 語意解釋 / 跨國差異:</span>
                            <div class="rc-value" style="margin-top:4px;color:var(--primary)">${escapeHtml(reg.semantic_note)}</div>
                        </div>`;
                    }
                }

                // Delta items for this clause
                const deltas = reg.delta_items || [];
                if (deltas.length > 0) {
                    bodyHtml += `<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
                        <span class="rc-label">🚨 獨有要求:</span>`;
                    for (const d of deltas) {
                        bodyHtml += `<div style="margin-top:4px;padding:6px;background:var(--non-compliant-bg);border-radius:4px">
                            <strong>${escapeHtml(d.title_zh || d.title_en)}</strong>
                            <div style="font-size:0.72rem;color:var(--text-secondary)">${escapeHtml(d.regulation_ref)}</div>`;
                        // Show native text for delta items too
                        if (d.original_text) {
                            const dLang = LANG_LABELS[d.original_lang] || d.original_lang || "";
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
            bodyHtml += `</td></tr>`;
        }

        els.crossrefTableBody.innerHTML = bodyHtml;
        els.crossrefTableCount.textContent = `顯示 ${rows.length} 條 ISO 13485 條款 × ${regIds.length} 國家法規`;
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
                <h4>${flag} ${escapeHtml(m.country_name_zh || rid)} 獨有差異</h4>`;

            if (d.exceeds_only.length > 0) {
                html += `<div style="margin-bottom:8px"><strong>⬆️ 只有該國超越 ISO 13485 的條款：</strong>
                    <div class="diff-clause-list">
                        ${d.exceeds_only.map(c => `<span class="diff-clause-chip diff-chip-exceeds">${c}</span>`).join("")}            
                    </div>
                </div>`;
            }

            if (reqs.length > 0) {
                html += `<div style="margin-bottom:8px"><strong>🚨 國家獨有要求 (${reqs.length} 項)：</strong>`;
                for (const req of reqs) {
                    html += `<div style="margin:4px 0;padding:6px 8px;background:var(--bg);border-radius:4px;font-size:0.78rem">
                        <strong>${escapeHtml(req.title_zh)}</strong>
                        <span style="color:var(--text-muted);margin-left:8px">${escapeHtml(req.regulation_ref)}</span>`;
                    // Show native text for inter-country comparison
                    if (req.original_text) {
                        const langLabel = LANG_LABELS[req.original_lang] || req.original_lang || "";
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
                html += `<div><strong>➖ 該國未涵蓋但其他國家有的條款：</strong>
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
            els.intercountryContainer.innerHTML = '<div class="empty-state"><div class="empty-state-text">所選國家法規高度一致，無顯著差異</div></div>';
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
                <h4>${flag} ${escapeHtml(m.country_name_zh || rid)} — ${reqs.length} 項獨有要求</h4>`;

            for (const req of reqs) {
                const confClass = req.confidence >= 0.9 ? "confidence-high" : req.confidence >= 0.7 ? "confidence-medium" : "confidence-low";
                const methodLabel = METHOD_LABELS[req.method] || req.method || "—";

                html += `<div class="delta-item">
                    <div class="di-ref">${escapeHtml(req.regulation_ref)}</div>
                    <div class="di-title">${escapeHtml(req.title_zh)} / ${escapeHtml(req.title_en)}</div>
                    <div class="di-req">${escapeHtml(req.requirement_zh)}</div>`;

                // Native text with translation
                if (req.original_text) {
                    const langLabel = LANG_LABELS[req.original_lang] || req.original_lang || "";
                    html += `<div style="margin:8px 0;padding:8px;background:var(--bg);border-radius:4px;border-left:3px solid var(--primary)">
                        <div style="font-size:0.72rem;font-weight:600;color:var(--text-secondary);margin-bottom:4px">📜 法規原文 (${langLabel})</div>
                        <div style="font-style:italic;font-size:0.8rem">${escapeHtml(req.original_text)}</div>`;
                    if (req.english_translation) {
                        html += `<div style="margin-top:6px;font-size:0.72rem;font-weight:600;color:var(--text-secondary)">🇬🇧 English Translation</div>
                            <div style="font-size:0.8rem">${escapeHtml(req.english_translation)}</div>`;
                    }
                    if (req.semantic_note) {
                        html += `<div style="margin-top:6px;font-size:0.72rem;font-weight:600;color:var(--primary)">💡 語意解釋 / 跨國差異分析</div>
                            <div style="font-size:0.8rem;color:var(--primary)">${escapeHtml(req.semantic_note)}</div>`;
                    }
                    html += `</div>`;
                }

                html += `<div class="di-question">💬 稽核問題: ${escapeHtml(req.audit_question_zh)}</div>
                    <div class="di-meta">
                        <span>📊 相關 ISO: ${(req.related_iso_clauses || []).join(", ")}</span>
                        <span>⚠️ 影響: ${escapeHtml(req.audit_impact)}</span>
                        <span class="method-badge">${methodLabel}</span>
                        <span class="rc-confidence ${confClass}">可信度 ${Math.round((req.confidence || 0) * 100)}%</span>
                    </div>
                </div>`;
            }

            html += `</div>`;
        }

        if (totalDelta === 0) {
            html = '<div class="empty-state"><div class="empty-state-text">所選國家法規無獨有要求</div></div>';
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
            showToast("請輸入 Run ID", "error");
            return;
        }

        // Close existing connection
        if (sseSource) {
            sseSource.close();
            sseSource = null;
        }

        // Clear feed
        els.crossexamFeed.innerHTML = "";
        addSystemMessage("🔌 正在連線...");

        try {
            sseSource = new EventSource(`${API_BASE}/${encodeURIComponent(runId)}/stream`);

            sseSource.onopen = function () {
                sseConnected = true;
                updateSSEStatus("connected", "🟢 已連線");
                els.btnConnectSSE.textContent = "❌ 斷線";
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
                    addSystemMessage("❌ 連線中斷，嘗試重新連線...");
                    updateSSEStatus("", "⚠️ 重連中");
                }
            };

        } catch (err) {
            showToast(`SSE 連線失敗: ${err.message}`, "error");
        }
    }

    function disconnectSSE() {
        if (sseSource) {
            sseSource.close();
            sseSource = null;
        }
        sseConnected = false;
        updateSSEStatus("", "⏹ 未連線");
        els.btnConnectSSE.textContent = "🔌 連線";
        els.btnPauseExam.disabled = true;
        els.btnResumeExam.disabled = true;
        els.humanMessageInput.disabled = true;
        els.btnSendHuman.disabled = true;
    }

    function handleSSEEvent(data) {
        const type = data.type;

        switch (type) {
            case "connected":
                addSystemMessage("✅ 已連線至即時交叉詰問串流");
                updateSSEStatus("streaming", "🟢 串流中");
                break;

            case "round_start":
                addRoundDivider(data.round);
                break;

            case "analyzer":
                addExamMessage("analyzer", "🔍 分析者", data.content, data.regulation, data.timestamp);
                break;

            case "verifier":
                addExamMessage("verifier", "🛡️ 驗證者", data.content, data.regulation, data.timestamp);
                break;

            case "human_injection":
                addExamMessage("human", `🙋 ${data.user_id || "人工"}`, data.message, null, data.timestamp);
                break;

            case "round_end":
                const resultText = data.agreed ? "✅ 本輪結果：一致" : "❌ 本輪結果：不一致";
                addSystemMessage(resultText);
                break;

            case "complete":
                addSystemMessage(`🏁 交叉詰問完成 — 判定: ${data.verdict || "—"} ${data.flagged ? "🚩需RA審查" : ""}`);
                updateSSEStatus("connected", "✅ 完成");
                break;

            case "error":
                addSystemMessage(`❌ 錯誤: ${data.message || "未知錯誤"}`);
                break;

            case "pause":
                addSystemMessage("⏸ 已暫停");
                updateSSEStatus("connected", "⏸ 已暫停");
                els.btnPauseExam.disabled = true;
                els.btnResumeExam.disabled = false;
                break;

            case "resume":
                addSystemMessage("▶️ 已繼續");
                updateSSEStatus("streaming", "🟢 串流中");
                els.btnPauseExam.disabled = false;
                els.btnResumeExam.disabled = true;
                break;

            case "heartbeat":
                // Silent keepalive
                break;

            default:
                console.log("Unknown SSE event type:", type, data);
        }

        // Auto-scroll to bottom
        els.crossexamFeed.scrollTop = els.crossexamFeed.scrollHeight;
    }

    function addExamMessage(type, role, content, regulation, timestamp) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `exam-message msg-${type}`;

        const timeStr = timestamp ? new Date(timestamp * 1000).toLocaleTimeString() : "";
        const regBadge = regulation ? `<span class="msg-regulation">${escapeHtml(regulation)}</span>` : "";

        msgDiv.innerHTML = `
            <div class="msg-header">
                <span class="msg-role role-${type}">${role}</span>
                <span>${regBadge} <span class="msg-time">${timeStr}</span></span>
            </div>
            <div class="msg-body">${escapeHtml(content || "")}</div>`;

        els.crossexamFeed.appendChild(msgDiv);
    }

    function addSystemMessage(text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = "exam-message msg-system";
        msgDiv.textContent = text;
        els.crossexamFeed.appendChild(msgDiv);
    }

    function addRoundDivider(round) {
        const div = document.createElement("div");
        div.className = "msg-round-divider";
        div.textContent = `─── 第 ${round} 輪 ───`;
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
            showToast(`暫停失敗: ${err.message}`, "error");
        }
    }

    async function resumeExam() {
        const runId = (els.sseRunIdInput && els.sseRunIdInput.value.trim()) || RUN_ID;
        if (!runId) return;
        try {
            await apiPost(`/${runId}/resume`, {});
        } catch (err) {
            showToast(`繼續失敗: ${err.message}`, "error");
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
            showToast(`發送失敗: ${err.message}`, "error");
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
                `<strong>可用命令 (Available Commands):</strong><br>` +
                `<code>/adjust &lt;standard_id&gt; "&lt;clause_name&gt;" &lt;old&gt; -&gt; &lt;new&gt;</code><br>` +
                `&nbsp;&nbsp;調整補充標準的 ISO 13485 對應條款<br>` +
                `&nbsp;&nbsp;例: <code>/adjust ISO_14971 "Clause 4 (Risk management process)" 7.1 -> 7.3.3</code><br><br>` +
                `<code>/standards</code> — 列出所有補充標準及其條款對應<br>` +
                `<code>/help</code> — 顯示此幫助訊息`
            );
            return true;
        }

        if (cmd === "/standards") {
            try {
                const resp = await fetch("/api/report/standards/list");
                const data = await resp.json();
                let html = `<strong>補充標準 (${data.standards.length} 項):</strong><br>`;
                for (const std of data.standards) {
                    html += `<br><strong>${std.name_zh}</strong> (${std.standard_id})<br>`;
                    for (const cl of std.clause_links) {
                        html += `&nbsp;&nbsp;${cl.standard_clause} \u2192 ISO 13485 ${cl.iso_13485_clause}<br>`;
                    }
                }
                appendSystemMessage(html);
            } catch (err) {
                showToast(`無法載入標準清單: ${err.message}`, "error");
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
                    `<span style="color:#e74c3c">✗ 格式錯誤。用法:</span><br>` +
                    `<code>/adjust &lt;standard_id&gt; "&lt;clause_name&gt;" &lt;old_clause&gt; -&gt; &lt;new_clause&gt;</code><br>` +
                    `例: <code>/adjust ISO_14971 "Clause 4 (Risk management process)" 7.1 -> 7.3.3</code>`
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
                showToast(`調整失敗: ${err.message}`, "error");
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
    // Init
    // ============================================================

    function init() {
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
