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
    };


    // ============================================================
    // Init
    // ============================================================

    function init() {
        bindEvents();
        loadReport();
    }

    // Wait for DOM ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

})();
