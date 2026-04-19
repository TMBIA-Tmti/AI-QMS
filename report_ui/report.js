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

    const t = (key, params) => window.__i18n ? window.__i18n.t(key, params) : key;

    // Region display: stored keys are "Chinese (English)" — show English for non-zh
    const displayRegion = (key) => {
        const lang = (window.__i18n && window.__i18n.lang) || "en-US";
        if (lang.startsWith("zh")) return key;
        const m = key && key.match(/\(([^)]+)\)/);
        return m ? m[1] : (key || "");
    };

    // ── State ──
    let reportData = null;       // Full report response
    let filteredRows = [];       // Currently displayed rows
    let currentRowId = null;     // Row being edited in a modal
    let filterOptions = null;    // Cached filter options
    let phaseSkipConfig = [];    // Phases selected to skip (e.g. ["phase_2", "phase_5"])

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
        // Daily Audit tab
        dailyAuditCount: $('dailyAuditCount'),
        btnRunDailyAudit: $('btnRunDailyAudit'),
        btnRunMetaReview: $('btnRunMetaReview'),
        btnLoadAuditHistory: $('btnLoadAuditHistory'),
        dailyAuditSummary: $('dailyAuditSummary'),
        auditOverallScore: $('auditOverallScore'),
        auditDimAScore: $('auditDimAScore'),
        auditDimBScore: $('auditDimBScore'),
        dailyAuditHistory: $('dailyAuditHistory'),
        metaReviewSection: $('metaReviewSection'),
        metaReviewContent: $('metaReviewContent'),
        deviationAlertBanner: $('deviationAlertBanner'),
        deviationAlertTitle: $('deviationAlertTitle'),
        deviationAlertDetails: $('deviationAlertDetails'),
        // Unified command bars
        crossrefCommandInput: $('crossrefCommandInput'),
        btnCrossrefSend: $('btnCrossrefSend'),
        btnCrossrefHelp: $('btnCrossrefHelp'),
        btnCrossrefDownloads: $('btnCrossrefDownloads'),
        crossrefHelpPopup: $('crossrefHelpPopup'),
        crossrefDownloadCatalog: $('crossrefDownloadCatalog'),
        crossrefFeedbackHistory: $('crossrefFeedbackHistory'),
        crossrefFeedbackList: $('crossrefFeedbackList'),
        btnCrossexamHelp: $('btnCrossexamHelp'),
        btnCrossexamDownloads: $('btnCrossexamDownloads'),
        crossexamHelpPopup: $('crossexamHelpPopup'),
        crossexamDownloadCatalog: $('crossexamDownloadCatalog'),
        crossexamFeedbackHistory: $('crossexamFeedbackHistory'),
        crossexamFeedbackList: $('crossexamFeedbackList'),
        // Action dropdown selectors + inline help panels
        crossexamActionSelect: $('crossexamActionSelect'),
        crossexamInlineHelp: $('crossexamInlineHelp'),
        crossrefActionSelect: $('crossrefActionSelect'),
        crossrefInlineHelp: $('crossrefInlineHelp'),
        // Download bar dropdowns + buttons + help panels
        crossrefDlTypeSelect: $('crossrefDlTypeSelect'),
        crossrefDlWord: $('crossrefDlWord'),
        crossrefDlExcel: $('crossrefDlExcel'),
        crossrefDlHelp: $('crossrefDlHelp'),
        crossexamDlTypeSelect: $('crossexamDlTypeSelect'),
        crossexamDlWord: $('crossexamDlWord'),
        crossexamDlExcel: $('crossexamDlExcel'),
        crossexamDlHelp: $('crossexamDlHelp'),
        // Phase config panel
        phaseConfigPanel: $('phaseConfigPanel'),
        btnTogglePhaseConfig: $('btnTogglePhaseConfig'),
        phaseConfigBody: $('phaseConfigBody'),
        phaseConfigGrid: $('phaseConfigGrid'),
        phaseConfigSummary: $('phaseConfigSummary'),
        btnApplyPhaseConfig: $('btnApplyPhaseConfig'),
        btnResetPhaseConfig: $('btnResetPhaseConfig'),
    };

    // ============================================================
    // Action Dropdown — Command Prefixes & Inline Help Data
    // ============================================================

    /** Maps dropdown value → command prefix auto-filled into input */
    const ACTION_CMD_PREFIX = {
        inject:           '',
        download:         '/download ',
        feedback:         '/feedback daily "',
        feedback_history: '/feedback history',
        run:              '/run ',
        downloads:        '/downloads',
        adjust:           '/adjust ',
        standards:        '/standards',
    };

    /** Help content for each action — title, description (30-50+ chars), example input + effect */
    const ACTION_HELP_DATA = {
        inject: {
            icon: '🙋',
            get title() { return t('actionHelp.inject.title'); },
            get desc() { return t('actionHelp.inject.desc'); },
            get examples() { return [
                { input: t('actionHelp.inject.ex1Input'), effect: t('actionHelp.inject.ex1Effect') },
                { input: t('actionHelp.inject.ex2Input'), effect: t('actionHelp.inject.ex2Effect') },
            ]; }
        },
        download: {
            icon: '📥',
            get title() { return t('actionHelp.download.title'); },
            get desc() { return t('actionHelp.download.desc'); },
            get examples() { return [
                { input: '/download crossexam word', effect: t('actionHelp.download.ex1Effect') },
                { input: '/download audit excel', effect: t('actionHelp.download.ex2Effect') },
            ]; }
        },
        feedback: {
            icon: '💬',
            get title() { return t('actionHelp.feedback.title'); },
            get desc() { return t('actionHelp.feedback.desc'); },
            get examples() { return [
                { input: t('actionHelp.feedback.ex1Input'), effect: t('actionHelp.feedback.ex1Effect') },
                { input: t('actionHelp.feedback.ex2Input'), effect: t('actionHelp.feedback.ex2Effect') },
            ]; }
        },
        feedback_history: {
            icon: '📝',
            get title() { return t('actionHelp.feedbackHistory.title'); },
            get desc() { return t('actionHelp.feedbackHistory.desc'); },
            get examples() { return [
                { input: '/feedback history', effect: t('actionHelp.feedbackHistory.ex1Effect') },
            ]; }
        },
        run: {
            icon: '▶️',
            get title() { return t('actionHelp.run.title'); },
            get desc() { return t('actionHelp.run.desc'); },
            get examples() { return [
                { input: '/run audit', effect: t('actionHelp.run.ex1Effect') },
                { input: '/run meta', effect: t('actionHelp.run.ex2Effect') },
            ]; }
        },
        downloads: {
            icon: '📂',
            get title() { return t('actionHelp.downloads.title'); },
            get desc() { return t('actionHelp.downloads.desc'); },
            get examples() { return [
                { input: '/downloads', effect: t('actionHelp.downloads.ex1Effect') },
            ]; }
        },
        adjust: {
            icon: '🔧',
            get title() { return t('actionHelp.adjust.title'); },
            get desc() { return t('actionHelp.adjust.desc'); },
            get examples() { return [
                { input: t('actionHelp.adjust.ex1Input'), effect: t('actionHelp.adjust.ex1Effect') },
            ]; }
        },
        standards: {
            icon: '📜',
            get title() { return t('actionHelp.standards.title'); },
            get desc() { return t('actionHelp.standards.desc'); },
            get examples() { return [
                { input: '/standards', effect: t('actionHelp.standards.ex1Effect') },
            ]; }
        },
    };

    // ============================================================
    // LLM-Assist Help Data — for all 6 intervention points
    // ============================================================

    const LLM_ASSIST_HELP = {
        override: {
            icon: '✏️',
            get title() { return t('llmHelp.override.title'); },
            get desc() { return t('llmHelp.override.desc'); },
            get examples() { return [
                { input: t('llmHelp.override.ex1Input'), effect: t('llmHelp.override.ex1Effect') },
                { input: t('llmHelp.override.ex2Input'), effect: t('llmHelp.override.ex2Effect') },
            ]; }
        },
        note: {
            icon: '📝',
            get title() { return t('llmHelp.note.title'); },
            get desc() { return t('llmHelp.note.desc'); },
            get examples() { return [
                { input: t('llmHelp.note.ex1Input'), effect: t('llmHelp.note.ex1Effect') },
                { input: t('llmHelp.note.ex2Input'), effect: t('llmHelp.note.ex2Effect') },
            ]; }
        },
        evidence: {
            icon: '🔍',
            get title() { return t('llmHelp.evidence.title'); },
            get desc() { return t('llmHelp.evidence.desc'); },
            get examples() { return [
                { input: t('llmHelp.evidence.ex1Input'), effect: t('llmHelp.evidence.ex1Effect') },
                { input: t('llmHelp.evidence.ex2Input'), effect: t('llmHelp.evidence.ex2Effect') },
            ]; }
        },
        inject: {
            icon: '🙋',
            get title() { return t('llmHelp.inject.title'); },
            get desc() { return t('llmHelp.inject.desc'); },
            get examples() { return [
                { input: t('llmHelp.inject.ex1Input'), effect: t('llmHelp.inject.ex1Effect') },
                { input: t('llmHelp.inject.ex2Input'), effect: t('llmHelp.inject.ex2Effect') },
            ]; }
        },
        feedback: {
            icon: '💬',
            get title() { return t('llmHelp.feedback.title'); },
            get desc() { return t('llmHelp.feedback.desc'); },
            get examples() { return [
                { input: t('llmHelp.feedback.ex1Input'), effect: t('llmHelp.feedback.ex1Effect') },
                { input: t('llmHelp.feedback.ex2Input'), effect: t('llmHelp.feedback.ex2Effect') },
            ]; }
        },
        standards: {
            icon: '📜',
            get title() { return t('llmHelp.standards.title'); },
            get desc() { return t('llmHelp.standards.desc'); },
            get examples() { return [
                { input: t('llmHelp.standards.ex1Input'), effect: t('llmHelp.standards.ex1Effect') },
                { input: t('llmHelp.standards.ex2Input'), effect: t('llmHelp.standards.ex2Effect') },
            ]; }
        },
    };

    // ============================================================
    // LLM-Assist Functions — Unified for all intervention points
    // ============================================================

    /**
     * Send user input to LLM for analysis and display suggestion.
     * @param {'override'|'note'|'evidence'|'inject'|'feedback'|'standards'} contextType
     */
    async function llmAssist(contextType) {
        const inputEl = document.getElementById(contextType + 'LlmInput');
        const resultEl = document.getElementById(contextType + 'LlmResult');
        const contentEl = document.getElementById(contextType + 'LlmResultContent');
        const btnEl = document.getElementById(contextType + 'LlmBtn');
        if (!inputEl || !resultEl || !contentEl) return;

        const userInput = inputEl.value.trim();
        if (!userInput) {
            showToast(t('toast.llmAssistEmpty'), 'error');
            return;
        }

        // Get context data from current row
        const row = currentRowId ? findRow(currentRowId) : null;
        const contextData = row ? {
            clause_id: row.clause_id,
            clause_title: row.clause_title,
            current_verdict: row.verdict,
            current_risk: row.risk_level,
            evidence_items: row.evidence_items || [],
            doc_id: row.doc_id,
        } : {};

        if (btnEl) { btnEl.disabled = true; btnEl.textContent = '⚙️ ' + t('ui.analyzing'); }

        try {
            const result = await apiPost('/llm-assist', {
                user_input: userInput,
                context_type: contextType,
                context_data: contextData,
            });

            if (result.success && result.suggestion) {
                contentEl.innerHTML = `<div class="llm-assist-suggestion">${escapeHtml(result.suggestion)}</div>`;
                if (result.sources && result.sources.length > 0) {
                    contentEl.innerHTML += `<div class="llm-assist-sources">📎 ${t('ui.dataSources')}${result.sources.map(s => escapeHtml(s)).join(', ')}</div>`;
                }
                resultEl.style.display = 'block';
                resultEl.dataset.suggestion = result.suggestion;
                resultEl.dataset.contextType = contextType;
            } else {
                showToast(result.message || t('toast.llmAssistFailed'), 'error');
            }
        } catch (err) {
            showToast(t('toast.llmAssistFailed', { msg: err.message }), 'error');
        } finally {
            if (btnEl) { btnEl.disabled = false; btnEl.textContent = '🔍 ' + t('ui.analyze'); }
        }
    }

    /**
     * Apply LLM suggestion to the relevant field.
     * @param {'override'|'note'|'evidence'|'inject'|'feedback'|'standards'} contextType
     */
    function applyLlmResult(contextType) {
        const resultEl = document.getElementById(contextType + 'LlmResult');
        if (!resultEl) return;
        const suggestion = resultEl.dataset.suggestion || '';

        switch (contextType) {
            case 'override':
                if (els.overrideReason) els.overrideReason.value = suggestion;
                break;
            case 'note':
                if (els.noteText) els.noteText.value = suggestion;
                break;
            case 'inject':
                if (els.humanMessageInput) els.humanMessageInput.value = suggestion;
                break;
            case 'feedback': {
                const fbInput = els.crossrefCommandInput || els.crossexamCommandInput;
                if (fbInput) fbInput.value = '/feedback daily "' + suggestion + '"';
                break;
            }
            case 'standards': {
                const adjInput = els.crossrefCommandInput || els.crossexamCommandInput;
                if (adjInput) adjInput.value = suggestion;
                break;
            }
            default:
                break;
        }

        showToast(t('toast.llmAssistApplied'), 'success');
        resultEl.style.display = 'none';
    }

    /**
     * Dismiss LLM suggestion without applying.
     * @param {string} contextType
     */
    function dismissLlmResult(contextType) {
        const resultEl = document.getElementById(contextType + 'LlmResult');
        if (resultEl) resultEl.style.display = 'none';
    }

    // ============================================================
    // Evidence Editor — Human-in-the-loop evidence editing
    // ============================================================

    let evidenceEditorData = null; // { rowId, items: [...] }

    function openEvidenceEditor(rowId) {
        const row = findRow(rowId);
        if (!row) return;

        evidenceEditorData = {
            rowId: rowId,
            items: JSON.parse(JSON.stringify(row.evidence_items || [])),
        };

        // Build editor modal content in detailBody
        renderEvidenceEditor();
    }

    function renderEvidenceEditor() {
        if (!evidenceEditorData) return;
        const row = findRow(evidenceEditorData.rowId);
        if (!row) return;

        let html = `<div class="evidence-editor">
            <div class="evidence-editor-header">
                <h3>✏️ ${t('evidence.editorTitle')} — ${escapeHtml(row.clause_id)}</h3>
                <p class="evidence-editor-desc">${t('evidence.editorDesc')}</p>
            </div>`;

        // Evidence items list
        html += `<div class="evidence-editor-list">`;
        for (let i = 0; i < evidenceEditorData.items.length; i++) {
            html += renderEvidenceEditorItem(i, evidenceEditorData.items[i]);
        }
        html += `</div>`;

        // Add new evidence input
        html += `<div class="evidence-editor-add">
            <textarea id="newEvidenceInput" class="form-textarea" rows="2" 
                      placeholder="${t('evidence.newPlaceholder')}"></textarea>
            <button class="btn btn-assist" onclick="window.__report.addEvidenceItem()">➕ ${t('evidence.addBtn')}</button>
        </div>`;

        // LLM assist section for evidence
        html += `<div class="llm-assist-section" id="evidenceLlmAssist">
            <div class="llm-assist-header">
                <span>🤖 ${t('ui.llmAssist')}</span>
                <span class="llm-assist-hint">${t('ui.llmAssistHint')}</span>
            </div>
            <div class="llm-assist-input-row">
                <textarea id="evidenceLlmInput" class="form-textarea llm-assist-textarea" rows="2"
                          placeholder="${t('ui.llmAssistPlaceholder')}"></textarea>
                <button class="btn btn-assist" onclick="window.__report.llmAssist('evidence')" id="evidenceLlmBtn">🔍 ${t('ui.analyze')}</button>
            </div>
            <div class="llm-assist-result" id="evidenceLlmResult" style="display:none">
                <div class="llm-assist-result-content" id="evidenceLlmResultContent"></div>
                <div class="llm-assist-result-actions">
                    <button class="btn btn-sm btn-primary" onclick="window.__report.applyLlmResult('evidence')">✅ ${t('ui.applySuggestion')}</button>
                    <button class="btn btn-sm btn-cancel" onclick="window.__report.dismissLlmResult('evidence')">✕ ${t('ui.dismiss')}</button>
                </div>
            </div>
        </div>`;

        // Action buttons
        html += `<div class="evidence-editor-actions">
            <button class="btn btn-cancel" onclick="window.__report.cancelEvidenceEditor()">${t('modal.cancel')}</button>
            <button class="btn btn-secondary" onclick="window.__report.previewEvidenceRecalc()">📊 ${t('evidence.previewRecalc')}</button>
            <button class="btn btn-assist" onclick="window.__report.deepRecalcEvidence()" title="${t('evidence.deepRecalcTip')}">🧠 ${t('evidence.deepRecalc')}</button>
            <button class="btn btn-primary" onclick="window.__report.confirmEvidenceUpdate()">✅ ${t('evidence.confirmUpdate')}</button>
        </div>`;

        // Preview result area
        html += `<div class="evidence-editor-preview" id="evidencePreviewResult" style="display:none"></div>`;

        html += `</div>`;

        els.detailBody.innerHTML = html;
        els.detailTitle.textContent = `✏️ ${t('evidence.editTitle')} — ${findRow(evidenceEditorData.rowId)?.clause_id || ''}`;
        openModal(els.detailModal);
    }

    function renderEvidenceEditorItem(index, item) {
        const foundClass = item.found ? 'found' : 'not-found';
        const foundIcon = item.found ? (item.is_inadequate ? '⚠️' : '✅') : '❌';
        return `<div class="evidence-editor-item ${foundClass}" data-index="${index}">
            <div class="evidence-editor-item-header">
                <span>${foundIcon} ${escapeHtml(item.evidence_name || t('evidence.unnamed'))}</span>
                <button class="btn btn-sm btn-danger" onclick="window.__report.deleteEvidenceItem(${index})" title="${t('btn.delete')}">🗑</button>
            </div>
            <div class="evidence-editor-item-controls">
                <label><input type="checkbox" ${item.found ? 'checked' : ''} onchange="window.__report.toggleEvidenceFound(${index}, this.checked)"> ${t('evidence.found')}</label>
                <label><input type="checkbox" ${item.is_inadequate ? 'checked' : ''} onchange="window.__report.toggleEvidenceInadequate(${index}, this.checked)"> ${t('evidence.inadequate')}</label>
                <label><input type="checkbox" ${item.is_outdated ? 'checked' : ''} onchange="window.__report.toggleEvidenceOutdated(${index}, this.checked)"> ${t('evidence.outdated')}</label>
            </div>
            ${item.source_doc_id ? `<div class="evidence-editor-source">📄 ${escapeHtml(item.source_doc_id)}${item.source_section ? ' — ' + escapeHtml(item.source_section) : ''}</div>` : ''}
        </div>`;
    }

    function toggleEvidenceFound(index, checked) {
        if (!evidenceEditorData || !evidenceEditorData.items[index]) return;
        evidenceEditorData.items[index].found = checked;
        renderEvidenceEditor();
    }

    function toggleEvidenceInadequate(index, checked) {
        if (!evidenceEditorData || !evidenceEditorData.items[index]) return;
        evidenceEditorData.items[index].is_inadequate = checked;
        renderEvidenceEditor();
    }

    function toggleEvidenceOutdated(index, checked) {
        if (!evidenceEditorData || !evidenceEditorData.items[index]) return;
        evidenceEditorData.items[index].is_outdated = checked;
        renderEvidenceEditor();
    }

    function addEvidenceItem() {
        if (!evidenceEditorData) return;
        const input = document.getElementById('newEvidenceInput');
        const name = input ? input.value.trim() : '';
        if (!name) {
            showToast(t('toast.evidenceNameEmpty'), 'error');
            return;
        }
        evidenceEditorData.items.push({
            evidence_name: name,
            found: false,
            is_inadequate: false,
            is_outdated: false,
            source_doc_id: '',
            source_section: '',
            source_quote: '',
            llm_reasoning: '',
            relevance_score: null,
            user_added: true,
        });
        renderEvidenceEditor();
    }

    function deleteEvidenceItem(index) {
        if (!evidenceEditorData || !evidenceEditorData.items[index]) return;
        evidenceEditorData.items.splice(index, 1);
        renderEvidenceEditor();
    }

    async function previewEvidenceRecalc() {
        if (!evidenceEditorData) return;
        const previewEl = document.getElementById('evidencePreviewResult');
        if (!previewEl) return;

        try {
            showToast(t('toast.evidencePreviewCalc'), 'info');
            const result = await apiPost(`/${RUN_ID}/row/${evidenceEditorData.rowId}/evidence/preview`, {
                evidence_items: evidenceEditorData.items,
            });

            if (result.success) {
                const orig = result.original || {};
                const proposed = result.proposed || {};
                previewEl.innerHTML = `<h4>📊 ${t('evidence.recalcPreview')}</h4>
                    <div class="evidence-preview-grid">
                        <div class="preview-col">
                            <strong>${t('evidence.original')}</strong>
                            <div>${t('detail.gapSeverity')}: ${escapeHtml(orig.gap_severity || '—')}</div>
                            <div>${t('detail.riskLevel')}: ${escapeHtml(orig.risk_level || '—')}</div>
                            <div>${t('detail.verdict')}: ${escapeHtml(orig.verdict || '—')}</div>
                        </div>
                        <div class="preview-arrow">→</div>
                        <div class="preview-col preview-proposed">
                            <strong>${t('evidence.updated')}</strong>
                            <div>${t('detail.gapSeverity')}: ${escapeHtml(proposed.gap_severity || '—')}</div>
                            <div>${t('detail.riskLevel')}: ${escapeHtml(proposed.risk_level || '—')}</div>
                            <div>${t('detail.verdict')}: ${escapeHtml(proposed.verdict || '—')}</div>
                        </div>
                    </div>`;
                previewEl.style.display = 'block';
            }
        } catch (err) {
            showToast(t('toast.evidencePreviewFailed', { msg: err.message }), 'error');
        }
    }

    async function deepRecalcEvidence() {
        if (!evidenceEditorData) return;
        try {
            showToast(t('toast.evidenceDeepRecalc'), 'info');
            const result = await apiPost(`/${RUN_ID}/row/${evidenceEditorData.rowId}/evidence/deep-recalc`, {
                evidence_items: evidenceEditorData.items,
            });

            if (result.success) {
                showToast(t('toast.evidenceDeepRecalcDone'), 'success');
                // Refresh data
                if (result.row) {
                    updateRowInData(evidenceEditorData.rowId, result.row);
                    applyFilters();
                    refreshSummary();
                }
                closeModal(els.detailModal);
                evidenceEditorData = null;
            }
        } catch (err) {
            showToast(t('toast.evidenceDeepRecalcFailed', { msg: err.message }), 'error');
        }
    }

    async function confirmEvidenceUpdate() {
        if (!evidenceEditorData) return;
        try {
            showToast(t('toast.evidenceConfirming'), 'info');
            const result = await apiPost(`/${RUN_ID}/row/${evidenceEditorData.rowId}/evidence/confirm`, {
                evidence_items: evidenceEditorData.items,
                user_id: 'ra_user',
            });

            if (result.success) {
                showToast(t('toast.evidenceConfirmed'), 'success');
                if (result.row) {
                    updateRowInData(evidenceEditorData.rowId, result.row);
                    applyFilters();
                    refreshSummary();
                }
                closeModal(els.detailModal);
                evidenceEditorData = null;
            }
        } catch (err) {
            showToast(t('toast.evidenceConfirmFailed', { msg: err.message }), 'error');
        }
    }

    function cancelEvidenceEditor() {
        evidenceEditorData = null;
        closeModal(els.detailModal);
    }

    /**
     * Render inline help panel below the command bar when a dropdown option is selected.
     * @param {'crossexam'|'crossref'} tab
     * @param {string} actionValue — dropdown option value
     */
    function showActionInlineHelp(tab, actionValue) {
        const panel = tab === 'crossexam' ? els.crossexamInlineHelp : els.crossrefInlineHelp;
        if (!panel) return;

        if (!actionValue || !ACTION_HELP_DATA[actionValue]) {
            panel.style.display = 'none';
            panel.innerHTML = '';
            return;
        }

        const data = ACTION_HELP_DATA[actionValue];
        let html = `<div class="cmd-inline-help-title">${data.icon} ${data.title}</div>`;
        html += `<div class="cmd-inline-help-desc">${data.desc}</div>`;

        for (const ex of data.examples) {
            html += `<div class="cmd-inline-help-example">`;
            html += `<div class="example-label">${t('ui.example')}</div>`;
            html += `<code>${escapeHtml(ex.input)}</code>`;
            html += `<div class="example-effect">${escapeHtml(ex.effect)}</div>`;
            html += `</div>`;
        }

        panel.innerHTML = html;
        panel.style.display = 'block';
    }

    // ============================================================
    // Download Bar — Report Type Help Data
    // ============================================================

    /** Description for each download report type (30-50 chars) */
    const DL_TYPE_HELP = {
        report: {
            icon: '📊',
            get title() { return t('dlHelp.report.title'); },
            get desc() { return t('dlHelp.report.desc'); },
        },
        deep: {
            icon: '📋',
            get title() { return t('dlHelp.deep.title'); },
            get desc() { return t('dlHelp.deep.desc'); },
        },
        crossexam: {
            icon: '💬',
            get title() { return t('dlHelp.crossexam.title'); },
            get desc() { return t('dlHelp.crossexam.desc'); },
        },
        audit: {
            icon: '📝',
            get title() { return t('dlHelp.audit.title'); },
            get desc() { return t('dlHelp.audit.desc'); },
        },
        meta: {
            icon: '🧠',
            get title() { return t('dlHelp.meta.title'); },
            get desc() { return t('dlHelp.meta.desc'); },
        },
        quality: {
            icon: '🌟',
            get title() { return t('dlHelp.quality.title'); },
            get desc() { return t('dlHelp.quality.desc'); },
        },
        feedback: {
            icon: '💬',
            get title() { return t('dlHelp.feedback.title'); },
            get desc() { return t('dlHelp.feedback.desc'); },
        },
    };

    /**
     * Show inline help for a download type selection.
     * @param {'crossref'|'crossexam'} tab
     * @param {string} typeValue
     */
    function showDlInlineHelp(tab, typeValue) {
        const panel = tab === 'crossref' ? els.crossrefDlHelp : els.crossexamDlHelp;
        const wordBtn = tab === 'crossref' ? els.crossrefDlWord : els.crossexamDlWord;
        const excelBtn = tab === 'crossref' ? els.crossrefDlExcel : els.crossexamDlExcel;
        if (!panel) return;

        if (!typeValue || !DL_TYPE_HELP[typeValue]) {
            panel.style.display = 'none';
            panel.innerHTML = '';
            if (wordBtn) wordBtn.disabled = true;
            if (excelBtn) excelBtn.disabled = true;
            return;
        }

        const data = DL_TYPE_HELP[typeValue];
        panel.innerHTML = `<div class="cmd-inline-help-title">${data.icon} ${data.title}</div><div class="cmd-inline-help-desc">${data.desc}</div>`;
        panel.style.display = 'block';
        if (wordBtn) wordBtn.disabled = false;
        if (excelBtn) excelBtn.disabled = false;
    }


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

    function showToast(message, type = "info", duration = 3000) {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        els.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(20px)";
            toast.style.transition = "all 0.3s";
            setTimeout(() => toast.remove(), 300);
        }, duration);
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
        if (seconds < 60) return `${seconds.toFixed(1)} ${t('ui.seconds')}`;
        const mins = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return `${mins} ${t('ui.minutes')} ${secs} ${t('ui.seconds')}`;
    }


    // ============================================================
    // Load Report Data
    // ============================================================

    async function loadReport() {
        if (!RUN_ID) {
            els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">❌ ${t('ui.invalidReportId')}</td></tr>`;
            return;
        }

        els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">⏳ ${t('table.loading')}</td></tr>`;

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
            els.tableBody.innerHTML = `<tr><td colspan="8" class="loading-cell">❌ ${t('toast.loadFailed', {msg: escapeHtml(err.message)})}</td></tr>`;
            showToast(t('toast.loadFailed', {msg: err.message}), "error");
        }
    }


    // ============================================================
    // Render Header
    // ============================================================

    function renderHeader(data) {
        els.headerRunId.textContent = data.run_id || "";

        const sourceCmd = data.source_command || "regulatory_list";
        const t = window.__i18n ? window.__i18n.t.bind(window.__i18n) : (k) => k;
        const sourceCls = sourceCmd === "regulatory_update" ? "source-update" : "source-list";
        const srcLabel = {
            text: t(`source.${sourceCmd}`) || sourceCmd,
            cls: sourceCls,
        };
        const srcEl = document.getElementById("headerSourceCommand");
        if (srcEl) {
            srcEl.textContent = srcLabel.text;
            srcEl.className = `source-command-badge ${srcLabel.cls}`;
        }

        const statusMap = {
            completed: { get text() { return "✅ " + t("status.completed"); }, cls: "status-completed" },
            running: { get text() { return "⏳ " + t("status.running"); }, cls: "status-running" },
            paused: { get text() { return "⏸️ " + t("status.paused"); }, cls: "status-paused" },
            failed: { get text() { return "❌ " + t("status.failed"); }, cls: "status-failed" },
            pending: { get text() { return "⏳ " + t("status.pending"); }, cls: "status-running" },
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
        const _lang = window.__i18n ? window.__i18n.lang : "en-US";
        const _isEn = _lang && !_lang.startsWith("zh") && !_lang.startsWith("ja");
        const _isJa = _lang && _lang.startsWith("ja");
        // Documents
        els.filterDoc.innerHTML = `<option value="">${window.__i18n ? window.__i18n.t("filter.allDocs") : "All Documents"}</option>`;
        (filters.documents || []).forEach((d) => {
            const opt = document.createElement("option");
            opt.value = d.id;
            opt.textContent = `${d.id} — ${d.title}`;
            els.filterDoc.appendChild(opt);
        });

        // Verdicts
        els.filterVerdict.innerHTML = `<option value="">${window.__i18n ? window.__i18n.t("filter.allVerdicts") : "All Verdicts"}</option>`;
        (filters.verdicts || []).forEach((v) => {
            const opt = document.createElement("option");
            opt.value = v.value;
            const _lbl = _isEn ? (v.label_en || v.label_zh || v.value) : _isJa ? (v.label_ja || v.label_zh || v.value) : (v.label_zh || v.value);
            opt.textContent = `${v.icon || ""} ${_lbl}`;
            els.filterVerdict.appendChild(opt);
        });

        // Risk levels
        els.filterRisk.innerHTML = `<option value="">${window.__i18n ? window.__i18n.t("filter.allRisks") : "All Levels"}</option>`;
        (filters.risk_levels || []).forEach((r) => {
            const opt = document.createElement("option");
            opt.value = r.value;
            const _rlbl = _isEn ? (r.label_en || r.label_zh || r.value) : _isJa ? (r.label_ja || r.label_zh || r.value) : (r.label_zh || r.value);
            opt.textContent = `${r.icon || ""} ${_rlbl}`;
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
        els.tableCount.textContent = t('table.showing', {shown: rows.length, total: reportData.rows.length});
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
                        <div class="empty-state-text">${t('ui.noMatchingItems')}</div>
                    </div>
                </td></tr>`;
            return;
        }

        els.tableBody.innerHTML = rows.map((r) => renderRow(r)).join("");
    }

    function getPhaseStatusIcon(status) {
        const map = {
            completed: "✅",
            skipped: "⏭️",
            failed: "❌",
            pending: "⏳",
            running: "🔄",
        };
        return map[status] || "⏳";
    }

    function renderPipelineIcons(r) {
        const ps = r.phase_status_summary || {};
        const phases = [
            { key: "phase_0",   label: "P0",  get title() { return t("phase.p0"); } },
            { key: "phase_0_5", label: "P0.5", get title() { return t("phase.p05"); } },
            { key: "phase_1",   label: "P1",  get title() { return t("phase.p1"); } },
            { key: "phase_2",   label: "P2",  get title() { return t("phase.p2"); } },
            { key: "phase_3",   label: "P3",  get title() { return t("phase.p3"); } },
            { key: "phase_4",   label: "P4",  get title() { return t("phase.p4"); } },
            { key: "phase_5",   label: "P5",  get title() { return t("phase.p5"); } },
            { key: "phase_6",   label: "P6",  get title() { return t("phase.p6"); } },
        ];
        return phases.map(p => {
            const status = ps[p.key] || "pending";
            const icon = getPhaseStatusIcon(status);
            return `<span class="pipeline-phase phase-${status}" title="${p.title} — ${status}"><span class="phase-label">${p.label}</span>${icon}</span>`;
        }).join("");
    }

    function renderCrossExamBadge(r) {
        const rounds = r.verification_rounds || 0;
        if (rounds === 0) return "";
        const agreed = r.verification_agreed;
        let badge = "";
        if (agreed === true) {
            badge = `<span class="crossexam-badge crossexam-agreed" title="${t('ui.crossexamAgreed', {rounds: rounds})}">✅${rounds}R</span>`;
        } else if (agreed === false) {
            badge = `<span class="crossexam-badge crossexam-disagreed" title="${t('ui.crossexamDisagreed', {rounds: rounds})}">❌${rounds}R</span>`;
        } else {
            badge = `<span class="crossexam-badge crossexam-pending" title="${t('ui.crossexamPending')}">⏳${rounds}R</span>`;
        }
        const qa = r.qa_audit;
        if (qa && qa.score != null) {
            const s = qa.score;
            const cls = s >= 80 ? 'qa-good' : s >= 60 ? 'qa-ok' : 'qa-poor';
            const hIcon = qa.hallucination_detected ? '🚨' : '';
            const titleKey = hIcon ? 'qa.badgeTitleHallucination' : 'qa.badgeTitle';
            badge += `<span class="crossexam-badge ${cls}" title="${t(titleKey, {score: s})}" style="font-size:0.7rem;margin-left:2px">${hIcon}🔎${s}</span>`;
        }
        return badge;
    }

    function renderRow(r) {
        const flagged = r.flagged_for_ra;
        const rowClass = flagged ? "row-flagged" : "";

        const evFound = r.evidence_found || 0;
        const evTotal = r.evidence_total || 0;
        const evPct = evTotal > 0 ? Math.round((evFound / evTotal) * 100) : 0;
        const evFillClass = evPct >= 100 ? "fill-full" : evPct > 0 ? "fill-partial" : "fill-none";

        const verdictBadge = getVerdictBadge(r.verdict, r.verdict_icon, r.verdict_label_zh, !!r.ra_override);

        const riskTooltip = r.risk_level && r.gap_severity && r.audit_impact
            ? `${r.audit_impact} × ${r.gap_severity} → ${r.risk_level}`
            : '';
        const riskBadge = riskTooltip
            ? `<span class="risk-badge-wrapper">${getRiskBadge(r.risk_level, r.risk_icon, r.risk_label_zh)}<span class="risk-tooltip">⚖️ ${escapeHtml(riskTooltip)}</span></span>`
            : getRiskBadge(r.risk_level, r.risk_icon, r.risk_label_zh);

        const pipelineIcons = renderPipelineIcons(r);
        const crossExamBadge = renderCrossExamBadge(r);

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
            <td class="col-pipeline">
                <div class="pipeline-icons">${pipelineIcons}</div>
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
            <td class="col-flags">
                ${flagged ? '<span class="flag-icon" title="${t('ui.raReviewRequired')}">🚩</span>' : ""}
                ${crossExamBadge}
            </td>
            <td class="col-actions">
                <div class="action-group">
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openDetail('${escapeAttr(r.row_id)}')" title="${t('btn.detail')}">🔍</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openOverride('${escapeAttr(r.row_id)}')" title="${t('btn.override')}">✏️</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openNote('${escapeAttr(r.row_id)}')" title="${t('btn.note')}">📝</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.openHistory('${escapeAttr(r.row_id)}')" title="${t('btn.history')}">📜</button>
                    <button class="btn btn-sm btn-outline" onclick="window.__report.rerunRow('${escapeAttr(r.row_id)}')" title="${t('btn.rerun')}">🔄</button>
                    ${r.ra_override ? `<button class="btn btn-sm btn-success" onclick="window.__report.restoreOriginal('${escapeAttr(r.row_id)}')" title="${t('btn.restore')}">↩️</button>` : ""}
                </div>
            </td>
        </tr>`;
    }

    function getVerdictBadge(verdict, icon, label, hasOverride) {
        if (!verdict) return '<span class="badge badge-insufficient">— ' + t('ui.notJudged') + '</span>';
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
        if (!risk) return '<span class="badge badge-insufficient">— ' + t('ui.notAssessed') + '</span>';
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
            const _dLang = window.__i18n ? window.__i18n.lang : "en-US";
            const _dIsEn = _dLang && !_dLang.startsWith("zh") && !_dLang.startsWith("ja");
            const _dIsJa = _dLang && _dLang.startsWith("ja");
            const _i18nT = window.__i18n ? (k) => window.__i18n.t(k) : (k) => k;
            html += `<div class="detail-section">
                <h3>📋 ${_i18nT("detail.basicInfo")}</h3>
                <div class="detail-grid">
                    <span class="detail-label">${_i18nT("detail.clauseId")}</span>
                    <span class="detail-value">${escapeHtml(row.clause_id)}</span>
                    <span class="detail-label">${_i18nT("detail.clauseTitle")}</span>
                    <span class="detail-value">${escapeHtml(row.clause_title)}</span>
                    <span class="detail-label">${_i18nT("detail.qmsDocument")}</span>
                    <span class="detail-value">${escapeHtml(row.doc_id)} — ${escapeHtml(row.doc_title)}</span>
                    <span class="detail-label">${_i18nT("detail.auditImpact")}</span>
                    <span class="detail-value">${escapeHtml(row.audit_impact)}</span>
                    <span class="detail-label">${_i18nT("detail.auditQuestion")}</span>
                    <span class="detail-value">${escapeHtml(row.audit_question || "—")}</span>
                    <span class="detail-label">${_i18nT("detail.verdict")}</span>
                    <span class="detail-value">${getVerdictBadge(row.verdict, row.verdict_icon, row.verdict_label_zh, !!row.ra_override)}</span>
                    <span class="detail-label">${_i18nT("detail.riskLevel")}</span>
                    <span class="detail-value">${getRiskBadge(row.risk_level, row.risk_icon, row.risk_label_zh)}</span>
                </div>
            </div>`;

            // Risk reasoning section — show formula and evidence stats
            if (row.risk_level && row.gap_severity) {
                const formula = `${escapeHtml(row.audit_impact || '?')} × ${escapeHtml(row.gap_severity)} → ${escapeHtml(row.risk_level)}`;
                html += `<div class="risk-reasoning">
                    <h4>⚖️ ${_i18nT('detail.riskReasoning')}</h4>
                    <div class="risk-formula">📊 ${_i18nT('detail.auditImpact')}(${escapeHtml(row.audit_impact || '?')}) × ${_i18nT('detail.gapSeverity')}(${escapeHtml(row.gap_severity)}) → ${_i18nT('detail.riskLevel')}(${escapeHtml(row.risk_level)})</div>`;

                // Extract evidence_stats from phase_3.output if available
                const p3 = (row.phase_results || {}).phase_3;
                const stats = p3 && p3.output ? p3.output.evidence_stats : null;
                if (stats) {
                    html += `<div class="evidence-stats-grid">
                        <div class="evidence-stat-item stat-total"><span class="stat-value">${stats.total || 0}</span>${_i18nT('evidence.total')}</div>
                        <div class="evidence-stat-item stat-adequate"><span class="stat-value">${stats.found_adequate || 0}</span>${_i18nT('evidence.adequate')}</div>
                        <div class="evidence-stat-item stat-inadequate"><span class="stat-value">${stats.inadequate || 0}</span>${_i18nT('evidence.inadequateLabel')}</div>
                        <div class="evidence-stat-item stat-outdated"><span class="stat-value">${stats.outdated || 0}</span>${_i18nT('evidence.outdatedLabel')}</div>
                        <div class="evidence-stat-item stat-missing"><span class="stat-value">${stats.missing || 0}</span>${_i18nT('evidence.missing')}</div>
                    </div>`;
                }

                // Show risk action suggestion if available
                if (row.risk_action_zh) {
                    html += `<div style="margin-top:8px;font-size:0.82rem;color:#78350f">🛠️ ${_i18nT('detail.suggestedAction')}${escapeHtml(row.risk_action_zh)}</div>`;
                }

                // Human intervention button for evidence editing
                html += `<div style="margin-top:10px"><button class="btn btn-assist btn-sm" onclick="window.__report.openEvidenceEditor('${escapeHtml(rowId)}')" title="${_i18nT('evidence.editBtnTip')}">✏️ ${_i18nT('evidence.editBtnLabel')}</button></div>`;

                html += `</div>`;
            }

            // RA Override info
            if (row.ra_override) {
                html += `<div class="ra-override-info">
                    <strong>✏️ ${_i18nT('detail.raOverridden')}</strong>：${escapeHtml(row.ra_override.verdict)} — ${escapeHtml(row.ra_override.reason || "")}
                    <div style="font-size:0.75rem;color:#64748b;margin-top:4px">
                        ${_i18nT('detail.overriddenBy')}: ${escapeHtml(row.ra_override.by || "—")} | 
                        ${_i18nT('detail.time')}: ${formatTimestamp(row.ra_override.at)}
                    </div>
                </div>`;
            }

            // RA Notes
            if (row.ra_notes) {
                html += `<div class="ra-notes">
                    <strong>📝 ${_i18nT('detail.raNotes')}</strong>：${escapeHtml(row.ra_notes)}
                </div>`;
            }

            // Evidence items
            const evidenceItems = row.evidence_items || [];
            if (evidenceItems.length > 0) {
                html += `<div class="detail-section">
                    <h3>🔍 ${_i18nT('detail.evidenceItems')} (${evidenceItems.filter(e => e.found).length}/${evidenceItems.length})</h3>
                    <ul class="evidence-list">`;

                for (const ev of evidenceItems) {
                    const evClass = ev.found ? (ev.is_inadequate ? "inadequate" : "found") : "not-found";
                    const statusIcon = ev.found ? (ev.is_inadequate ? "⚠️" : "✅") : "❌";

                    html += `<li class="evidence-item ${evClass}">
                        <div class="evidence-name">${statusIcon} ${escapeHtml(ev.evidence_name || t("evidence.unknown"))}</div>`;

                    if (ev.source_doc_id) {
                        html += `<div class="evidence-source">📄 ${_i18nT('evidence.source')}: ${escapeHtml(ev.source_doc_id)}${ev.source_section ? ` — ${escapeHtml(ev.source_section)}` : ""}</div>`;
                    }

                    if (ev.source_quote) {
                        html += `<div class="evidence-quote">"${escapeHtml(ev.source_quote)}"</div>`;
                    }

                    if (ev.llm_reasoning) {
                        html += `<div class="evidence-source">💭 ${_i18nT('evidence.llmReasoning')}: ${escapeHtml(ev.llm_reasoning)}</div>`;
                    }

                    if (ev.relevance_score != null) {
                        html += `<div class="evidence-source">📊 ${_i18nT('evidence.relevance')}: ${(ev.relevance_score * 100).toFixed(0)}%</div>`;
                    }

                    html += `</li>`;
                }

                html += `</ul></div>`;
            }

            // Expected evidence (from compliance_rules)
            const expectedEvidence = row.expected_evidence || [];
            if (expectedEvidence.length > 0 && evidenceItems.length === 0) {
                html += `<div class="detail-section">
                    <h3>📋 ${_i18nT('detail.expectedEvidence')}</h3>
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
                    <h3>🔄 ${_i18nT('detail.crossExam')} (${rounds.length} ${_i18nT('ui.rounds')})</h3>`;

                for (let i = 0; i < rounds.length; i++) {
                    const round = rounds[i];
                    const agreed = round.agreed;
                    const statusText = agreed ? "✅ " + t("ui.agreed") : "❌ " + t("ui.disagreed");

                    html += `<div class="verification-round">
                        <div class="verification-round-header">
                            <span>${t('ui.roundN', {n: i + 1})}</span>
                            <span>${statusText}</span>
                        </div>
                        <div class="verification-round-body">`;

                    if (round.analyzer_response) {
                        html += `<div class="verification-role analyzer">🔍 ${_i18nT('ui.analyzer')}</div>
                            <div class="verification-text">${escapeHtml(round.analyzer_response)}</div>`;
                    }

                    if (round.verifier_response) {
                        html += `<div class="verification-role verifier">🛡️ ${_i18nT('ui.verifier')}</div>
                            <div class="verification-text">${escapeHtml(round.verifier_response)}</div>`;
                    }

                    html += `</div></div>`;
                }

                if (row.flagged_for_ra) {
                    html += `<div class="ra-override-info">
                        <strong>🚩 ${_i18nT('detail.flaggedForRA')}</strong>
                    </div>`;
                }

                html += `</div>`;
            }

            // Third-party QA Audit (Phase 5 Step 2)
            const qaAudit = row.qa_audit;
            if (qaAudit) {
                const qaScore = qaAudit.score || 0;
                const qaScoreClass = qaScore >= 80 ? 'qa-good' : qaScore >= 60 ? 'qa-ok' : 'qa-poor';
                html += `<div class="detail-section">
                    <h3>${t('qa.title')}</h3>
                    <div class="qa-audit-summary">
                        <span class="qa-score ${qaScoreClass}">${qaScore}/100</span>
                        <span class="qa-labels">`;

                if (qaAudit.question_quality) {
                    const qqIcon = qaAudit.question_quality === 'good' ? '✅' : qaAudit.question_quality === 'acceptable' ? '⚠️' : '❌';
                    html += `<span class="qa-label" title="${t('qa.questionQuality')}">${qqIcon} ${t('qa.questionQuality')}: ${escapeHtml(qaAudit.question_quality)}</span>`;
                }
                if (qaAudit.answer_accuracy) {
                    const aaIcon = qaAudit.answer_accuracy === 'accurate' ? '✅' : qaAudit.answer_accuracy === 'partially_accurate' ? '⚠️' : '❌';
                    html += `<span class="qa-label" title="${t('qa.answerAccuracy')}">${aaIcon} ${t('qa.answerAccuracy')}: ${escapeHtml(qaAudit.answer_accuracy)}</span>`;
                }
                if (qaAudit.logic_consistency) {
                    const lcIcon = qaAudit.logic_consistency === 'consistent' ? '✅' : qaAudit.logic_consistency === 'minor_issues' ? '⚠️' : '❌';
                    html += `<span class="qa-label" title="${t('qa.logicConsistency')}">${lcIcon} ${t('qa.logicConsistency')}: ${escapeHtml(qaAudit.logic_consistency)}</span>`;
                }
                if (qaAudit.hallucination_detected) {
                    html += `<span class="qa-label qa-hallucination" title="${t('qa.hallucination')}">${t('qa.hallucinationDetected')}</span>`;
                }
                html += `</span></div>`;

                if (qaAudit.hallucination_detected && qaAudit.hallucination_details) {
                    html += `<div class="qa-hallucination-detail">⚠️ ${escapeHtml(qaAudit.hallucination_details)}</div>`;
                }

                if (qaAudit.issues && qaAudit.issues.length > 0) {
                    html += `<div class="qa-issues"><strong>${t('qa.issues')}:</strong><ul>`;
                    for (const issue of qaAudit.issues) {
                        html += `<li>${escapeHtml(issue)}</li>`;
                    }
                    html += `</ul></div>`;
                }

                html += `</div>`;
            }

            // Remediation
            if (row.remediation_suggestion) {
                html += `<div class="detail-section">
                    <h3>🛠️ ${_i18nT('detail.remediation')}</h3>
                    <div class="remediation-text">${escapeHtml(row.remediation_suggestion)}</div>`;

                if (row.remediation_regulation_cite) {
                    html += `<div style="margin-top:8px;font-size:0.8rem;color:#64748b">
                        📖 ${_i18nT('detail.regulationCite')}: ${escapeHtml(row.remediation_regulation_cite)}
                    </div>`;
                }

                html += `</div>`;
            }

            // Phase results timeline
            const phaseResults = row.phase_results || {};
            const phaseKeys = Object.keys(phaseResults);
            if (phaseKeys.length > 0) {
                html += `<div class="detail-section">
                    <h3>⏱️ ${_i18nT('detail.phaseResults')}</h3>
                    <div class="detail-grid">`;

                const phaseNames = {
                    phase_0: t("phase.p0"),
                    phase_0_5: t("phase.p05"),
                    phase_1: t("phase.p1"),
                    phase_2: t("phase.p2"),
                    phase_3: t("phase.p3"),
                    phase_4: t("phase.p4"),
                    phase_5: t("phase.p5"),
                    phase_6: t("phase.p6"),
                };

                for (const key of phaseKeys) {
                    const pr = phaseResults[key];
                    const statusIcon = pr.status === "completed" ? "✅" : pr.status === "skipped" ? "⏭️" : pr.status === "failed" ? "❌" : "⏳";
                    const duration = pr.duration_seconds != null ? `${pr.duration_seconds.toFixed(1)}s` : "";

                    html += `<span class="detail-label">${phaseNames[key] || key}</span>
                        <span class="detail-value">${statusIcon} ${pr.status || "—"} ${duration ? `(${duration})` : ""}</span>`;

                    // For Phase 3 (Risk Assessment), show the output details inline
                    if (key === 'phase_3' && pr.output) {
                        const out = pr.output;
                        const parts = [];
                        if (out.gap_severity) parts.push(`${t('detail.gapSeverity')}: ${out.gap_severity}`);
                        if (out.risk_level) parts.push(`${t('detail.riskLevel')}: ${out.risk_level}`);
                        if (out.verdict) parts.push(`${t('detail.verdict')}: ${out.verdict}`);
                        if (parts.length) {
                            html += `<span class="detail-label"></span>
                                <span class="detail-value" style="font-size:0.78rem;color:#78350f">└─ ${escapeHtml(parts.join(' | '))}</span>`;
                        }
                    }
                }

                html += `</div></div>`;
            }

            els.detailBody.innerHTML = html;
            openModal(els.detailModal);

        } catch (err) {
            showToast(t('toast.detailFailed', {msg: err.message}), "error");
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
            showToast(t('toast.overrideNoReason'), "error");
            return;
        }

        els.overrideSaveBtn.disabled = true;
        els.overrideSaveBtn.textContent = t("ui.processing");

        try {
            const result = await apiPost(`/${RUN_ID}/row/${currentRowId}/override`, {
                verdict: verdict,
                reason: reason,
            });

            if (result.success) {
                showToast(t('toast.overrideSuccess'), "success");
                closeModal(els.overrideModal);
                updateRowInData(currentRowId, result.row);
                applyFilters();
                refreshSummary();
            }
        } catch (err) {
            showToast(t('toast.overrideFailed', {msg: err.message}), "error");
        } finally {
            els.overrideSaveBtn.disabled = false;
            els.overrideSaveBtn.textContent = t("modal.confirmOverride");
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
            showToast(t('toast.noteEmpty'), "error");
            return;
        }

        els.noteSaveBtn.disabled = true;
        els.noteSaveBtn.textContent = t("ui.saving");

        try {
            const result = await apiPost(`/${RUN_ID}/row/${currentRowId}/note`, {
                note: note,
            });

            if (result.success) {
                showToast(t('toast.noteSuccess'), "success");
                closeModal(els.noteModal);
                updateRowInData(currentRowId, result.row);
                applyFilters();
            }
        } catch (err) {
            showToast(t('toast.noteFailed', {msg: err.message}), "error");
        } finally {
            els.noteSaveBtn.disabled = false;
            els.noteSaveBtn.textContent = t("modal.saveNote");
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
                        <div class="empty-state-text">${t('history.noHistory')}</div>
                    </div>`;
            } else {
                let html = "";
                // Show in reverse chronological order
                const reversed = history.slice().reverse();
                for (const entry of reversed) {
                    const actionLabels = {
                        override_verdict: t("history.overrideVerdict"),
                        add_note: t("history.addNote"),
                        restore_original: t("history.restoreOriginal"),
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
                        html += `<div>${t('history.prevVerdict')}: ${escapeHtml(entry.previous_verdict || '—')} → ${t('history.newVerdict')}: ${escapeHtml(entry.new_verdict || '—')}</div>
                            <div>${t('history.reason')}: ${escapeHtml(entry.reason || '—')}</div>`;
                    } else if (entry.action === "add_note") {
                        html += `<div>${t('history.note')}: ${escapeHtml(entry.new_note || '—')}</div>`;
                    } else if (entry.action === "restore_original") {
                        html += `<div>${t('history.overrideVerdict')} ${escapeHtml(entry.overridden_verdict || '—')} → ${t('history.restoredTo')} ${escapeHtml(entry.restored_verdict || '—')}</div>`;
                    }

                    html += `<div class="history-meta">
                            ${entry.by ? `${t('history.operator')}: ${escapeHtml(entry.by)}` : ''}
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
                        <strong>✏️ ${t('history.currentOverride')}</strong>：${escapeHtml(data.ra_override.verdict || "—")} — ${escapeHtml(data.ra_override.reason || "")}
                    </div>`);
            }

            if (data.ra_notes) {
                els.historyBody.insertAdjacentHTML("afterbegin", `
                    <div class="ra-notes" style="margin-bottom:16px">
                        <strong>📝 ${t('history.currentNotes')}</strong>：${escapeHtml(data.ra_notes)}
                    </div>`);
            }

            openModal(els.historyModal);

        } catch (err) {
            showToast(t('toast.historyFailed', {msg: err.message}), "error");
        }
    }


    // ============================================================
    // Restore LLM Original
    // ============================================================

    async function restoreOriginal(rowId) {
        if (!confirm(t("confirm.restore"))) {
            return;
        }

        try {
            const result = await apiPost(`/${RUN_ID}/row/${rowId}/restore`, {});

            if (result.success) {
                showToast(t('toast.restoreSuccess'), "success");
                updateRowInData(rowId, result.row);
                applyFilters();
                refreshSummary();
            }
        } catch (err) {
            showToast(t('toast.restoreFailed', {msg: err.message}), "error");
        }
    }


    // ============================================================
    // Export
    // ============================================================

    async function rerunRow(rowId) {
        if (!confirm(t("confirm.rerun"))) return;
        try {
            const result = await apiPost(`/${RUN_ID}/row/${rowId}/rerun`, { from_phase: "phase_1" });
            if (result.success) {
                showToast(t('toast.rerunSuccess'), "info");
                updateRowInData(rowId, result.row);
                applyFilters();
            }
        } catch (err) {
            showToast(t('toast.rerunFailed', {msg: err.message}), "error");
        }
    }

    function exportReport(format) {
        const url = `${API_BASE}/${RUN_ID}/export/${format}`;
        showToast(t('toast.exporting', {fmt: format.toUpperCase()}), "info");

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

    /**
     * Format LLM cross-examination content into human-readable HTML.
     * Parses JSON responses from analyzer/verifier and renders structured output.
     * Falls back to escaped plain text if content is not valid JSON.
     */
    function formatLLMContent(rawContent, msgType) {
        if (!rawContent) return '';
        const text = String(rawContent).trim();

        // Try to parse JSON (may be wrapped in ```json ... ```)
        let data = null;
        let rawJsonStr = null;
        try {
            let jsonStr = text;
            const fenceMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
            if (fenceMatch) jsonStr = fenceMatch[1].trim();
            data = JSON.parse(jsonStr);
            rawJsonStr = JSON.stringify(data, null, 2);
        } catch (e) {
            // Not JSON — render as readable text
            return `<div class="llm-text">${escapeHtml(text)}</div>`;
        }

        if (!data || typeof data !== 'object') {
            return `<div class="llm-text">${escapeHtml(text)}</div>`;
        }

        // Build human-readable HTML
        let humanHtml = '';
        // ── Analyzer initial position ──
        if (data.position) {
            humanHtml = formatAnalyzerPosition(data);
        }
        // ── Analyzer response to challenge ──
        else if (data.response && !data.agreement_level) {
            humanHtml = formatAnalyzerResponse(data);
        }
        // ── Verifier challenge / follow-up ──
        else if (data.agreement_level) {
            humanHtml = formatVerifierAssessment(data);
        }
        // Fallback: render unknown JSON as labeled key-value pairs
        else {
            humanHtml = formatGenericJSON(data);
        }

        // Append collapsible raw JSON block
        const rawId = 'raw-json-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
        const rawJsonBlock = `
            <details class="llm-raw-json-toggle">
                <summary>🔧 ${t('llm.rawJson')}</summary>
                <pre class="llm-raw-json" id="${rawId}">${escapeHtml(rawJsonStr)}</pre>
            </details>`;

        return humanHtml + rawJsonBlock;
    }

    function formatAnalyzerPosition(d) {
        const conf = d.confidence != null ? `<span class="llm-confidence">${(d.confidence * 100).toFixed(0)}%</span>` : '';
        let html = `<div class="llm-structured">`;
        html += `<div class="llm-section"><span class="llm-label">📝 ${t('llm.position')}</span>${conf}</div>`;
        html += `<div class="llm-content">${escapeHtml(d.position)}</div>`;

        if (d.key_evidence && d.key_evidence.length) {
            html += `<div class="llm-section"><span class="llm-label">📎 ${t('llm.keyEvidence')}</span></div>`;
            html += `<ul class="llm-evidence-list">`;
            d.key_evidence.forEach(e => { html += `<li>${escapeHtml(e)}</li>`; });
            html += `</ul>`;
        }

        if (d.acknowledged_weaknesses && d.acknowledged_weaknesses.length) {
            html += `<div class="llm-section"><span class="llm-label">⚠️ ${t('llm.weaknesses')}</span></div>`;
            html += `<ul class="llm-weakness-list">`;
            d.acknowledged_weaknesses.forEach(w => { html += `<li>${escapeHtml(w)}</li>`; });
            html += `</ul>`;
        }

        html += `</div>`;
        return html;
    }

    function formatAnalyzerResponse(d) {
        const conf = d.revised_confidence != null ? `<span class="llm-confidence">${(d.revised_confidence * 100).toFixed(0)}%</span>` : '';
        let html = `<div class="llm-structured">`;
        html += `<div class="llm-section"><span class="llm-label">💬 ${t('llm.response')}</span>${conf}</div>`;
        html += `<div class="llm-content">${escapeHtml(d.response)}</div>`;

        if (d.additional_evidence && d.additional_evidence.length) {
            html += `<div class="llm-section"><span class="llm-label">📎 ${t('llm.additionalEvidence')}</span></div>`;
            html += `<ul class="llm-evidence-list">`;
            d.additional_evidence.forEach(e => { html += `<li>${escapeHtml(e)}</li>`; });
            html += `</ul>`;
        }

        if (d.concession) {
            html += `<div class="llm-section"><span class="llm-label">✅ ${t('llm.concession')}</span></div>`;
            html += `<div class="llm-content llm-concession">${escapeHtml(d.concession)}</div>`;
        }

        html += `</div>`;
        return html;
    }

    function formatVerifierAssessment(d) {
        const levelIcons = { agree: '✅', partial_agree: '⚠️', disagree: '❌' };
        const levelLabels = { agree: t('llm.agree'), partial_agree: t('llm.partialAgree'), disagree: t('llm.disagree') };
        const icon = levelIcons[d.agreement_level] || '❓';
        const label = levelLabels[d.agreement_level] || d.agreement_level;

        let html = `<div class="llm-structured">`;
        html += `<div class="llm-section"><span class="llm-label">🛡️ ${t('llm.verifierOpinion')}</span> <span class="llm-agreement llm-agreement-${d.agreement_level}">${icon} ${label}</span></div>`;

        // Challenges (initial response)
        if (d.challenges && d.challenges.length) {
            html += `<div class="llm-section"><span class="llm-label">❓ ${t('llm.challenges')}</span></div>`;
            d.challenges.forEach((c, i) => {
                html += `<div class="llm-challenge">`;
                html += `<div class="llm-challenge-point"><strong>${i + 1}.</strong> ${escapeHtml(c.point || '')}</div>`;
                if (c.regulation_basis) html += `<div class="llm-challenge-basis">📜 ${escapeHtml(c.regulation_basis)}</div>`;
                if (c.expected_evidence) html += `<div class="llm-challenge-evidence">📎 ${escapeHtml(c.expected_evidence)}</div>`;
                html += `</div>`;
            });
        }

        // Remaining concerns (follow-up)
        if (d.remaining_concerns && d.remaining_concerns.length) {
            html += `<div class="llm-section"><span class="llm-label">❌ ${t('llm.remainingConcerns')}</span></div>`;
            html += `<ul class="llm-concern-list">`;
            d.remaining_concerns.forEach(c => { html += `<li>${escapeHtml(c)}</li>`; });
            html += `</ul>`;
        }

        // Resolved concerns (follow-up)
        if (d.resolved_concerns && d.resolved_concerns.length) {
            html += `<div class="llm-section"><span class="llm-label">✅ ${t('llm.resolvedConcerns')}</span></div>`;
            html += `<ul class="llm-resolved-list">`;
            d.resolved_concerns.forEach(c => { html += `<li>${escapeHtml(c)}</li>`; });
            html += `</ul>`;
        }

        if (d.overall_assessment) {
            html += `<div class="llm-section"><span class="llm-label">📝 ${t('llm.overallAssessment')}</span></div>`;
            html += `<div class="llm-content llm-overall">${escapeHtml(d.overall_assessment)}</div>`;
        }

        html += `</div>`;
        return html;
    }

    function formatPhaseResultContent(rawText) {
        if (!rawText) return '';
        const text = String(rawText).trim();
        let data = null;
        try {
            let jsonStr = text;
            const fenceMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
            if (fenceMatch) jsonStr = fenceMatch[1].trim();
            data = JSON.parse(jsonStr);
        } catch (e) {
            return `<div class="llm-text">${escapeHtml(text)}</div>`;
        }
        if (!data || typeof data !== 'object') {
            return `<div class="llm-text">${escapeHtml(text)}</div>`;
        }

        let html = '';

        const clauseResults = data.clause_results || data;
        const isClauseMap = Object.keys(clauseResults).some(k => /^\d/.test(k));

        if (isClauseMap) {
            html += '<div class="llm-structured">';
            for (const [clauseId, cData] of Object.entries(clauseResults)) {
                if (!cData || typeof cData !== 'object') continue;
                const vr = cData.verification_results || cData.evidence_results || cData.results || [];
                if (!Array.isArray(vr) || vr.length === 0) {
                    html += `<div class="llm-section"><span class="llm-label">§${escapeHtml(clauseId)}</span></div>`;
                    html += `<div class="llm-content">${escapeHtml(JSON.stringify(cData, null, 2).substring(0, 500))}</div>`;
                    continue;
                }
                html += `<div class="llm-section"><span class="llm-label">§${escapeHtml(clauseId)}</span> <span style="color:#6b7280;font-size:0.85em">${vr.length} ${t('evidence.items')}</span></div>`;
                html += '<table style="width:100%;font-size:0.82rem;border-collapse:collapse;margin:4px 0 10px">';
                html += '<thead><tr style="background:#f1f5f9;text-align:left"><th style="padding:3px 6px">' + t('table.evidence') + '</th><th style="padding:3px 6px">' + t('evidence.adequacy') + '</th><th style="padding:3px 6px">' + t('evidence.score') + '</th><th style="padding:3px 6px">' + t('evidence.explanation') + '</th></tr></thead><tbody>';
                for (const ev of vr) {
                    const adequacy = ev.adequacy || '';
                    const adequacyIcon = adequacy === 'full' ? '✅' : adequacy === 'partial' ? '⚠️' : adequacy === 'irrelevant' ? '❌' : '❓';
                    const adequacyLabel = adequacy === 'full' ? t('evidence.full') : adequacy === 'partial' ? t('evidence.partial') : adequacy === 'irrelevant' ? t('evidence.irrelevant') : adequacy;
                    const score = ev.semantic_score != null ? (ev.semantic_score * 100).toFixed(0) + '%' : '';
                    html += `<tr>
                        <td style="padding:3px 6px;font-weight:500">${escapeHtml(ev.evidence_name || '')}</td>
                        <td style="padding:3px 6px">${adequacyIcon} ${adequacyLabel}</td>
                        <td style="padding:3px 6px">${score}</td>
                        <td style="padding:3px 6px;max-width:400px;word-break:break-word">${escapeHtml((ev.explanation || '').substring(0, 300))}</td>
                    </tr>`;
                }
                html += '</tbody></table>';
            }
            html += '</div>';
        } else {
            html = formatGenericJSON(data);
        }

        const rawId = 'raw-phase-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
        html += `<details class="llm-raw-json-toggle"><summary>🔧 ${t('llm.rawJson')}</summary><pre class="llm-raw-json" id="${rawId}">${escapeHtml(JSON.stringify(data, null, 2))}</pre></details>`;
        return html;
    }

    function formatGenericJSON(obj) {
        let html = `<div class="llm-structured">`;
        for (const [key, val] of Object.entries(obj)) {
            const label = key.replace(/_/g, ' ');
            if (Array.isArray(val)) {
                html += `<div class="llm-section"><span class="llm-label">${escapeHtml(label)}</span></div>`;
                html += `<ul class="llm-evidence-list">`;
                val.forEach(item => {
                    if (typeof item === 'object') html += `<li>${escapeHtml(JSON.stringify(item))}</li>`;
                    else html += `<li>${escapeHtml(String(item))}</li>`;
                });
                html += `</ul>`;
            } else if (typeof val === 'object' && val !== null) {
                html += `<div class="llm-section"><span class="llm-label">${escapeHtml(label)}</span></div>`;
                html += `<div class="llm-content">${escapeHtml(JSON.stringify(val, null, 2))}</div>`;
            } else {
                html += `<div class="llm-section"><span class="llm-label">${escapeHtml(label)}</span> ${escapeHtml(String(val))}</div>`;
            }
        }
        html += `</div>`;
        return html;
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

        // Deep report export
        const btnDeepWord = document.getElementById('btnDeepReportWord');
        const btnDeepExcel = document.getElementById('btnDeepReportExcel');
        if (btnDeepWord) btnDeepWord.addEventListener('click', () => exportDeepReport('word'));
        if (btnDeepExcel) btnDeepExcel.addEventListener('click', () => exportDeepReport('excel'));

        // History tab controls
        const btnLoadHistory = document.getElementById('btnLoadHistory');
        if (btnLoadHistory) btnLoadHistory.addEventListener('click', loadCrossexamHistory);
        const btnRunMeta = document.getElementById('btnRunMetaAnalysis');
        if (btnRunMeta) btnRunMeta.addEventListener('click', loadMetaAnalysis);
        const btnExportMetaWord = document.getElementById('btnExportMetaWord');
        if (btnExportMetaWord) btnExportMetaWord.addEventListener('click', () => exportMetaAnalysis('word'));
        const btnExportMetaExcel = document.getElementById('btnExportMetaExcel');
        if (btnExportMetaExcel) btnExportMetaExcel.addEventListener('click', () => exportMetaAnalysis('excel'));

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
                // Auto-load daily audit history on first visit
                if (tabId === "dailyaudit" && els.dailyAuditHistory) {
                    const isEmpty = !els.dailyAuditHistory.querySelector('.history-records');
                    if (isEmpty) {
                        loadDailyAuditHistory();
                    }
                }
            });
        }

        // Cross-reference controls
        if (els.btnLoadCrossref) {
            els.btnLoadCrossref.addEventListener("click", loadCrossrefTable);
        }
        // Original text toggle for cross-reference
        const toggleOriginalTextCb = document.getElementById("toggleOriginalText");
        if (toggleOriginalTextCb) {
            toggleOriginalTextCb.addEventListener("change", () => {
                showOriginalText = toggleOriginalTextCb.checked;
                // Re-render all crossref sections if data exists
                if (crossrefData) {
                    renderCrossrefTable(crossrefData);
                    renderInterCountryDiffs(crossrefData);
                    renderDeltaItems(crossrefData);
                }
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

        // MDSAP verify toggle — save setting + auto-reload crossref table
        const toggleMdsapVerifyCb = document.getElementById('toggleMdsapVerify');
        if (toggleMdsapVerifyCb) {
            toggleMdsapVerifyCb.addEventListener('change', () => {
                mdsapVerifyEnabled = toggleMdsapVerifyCb.checked;
                apiPost('/crossref/mdsap-verify', { enabled: mdsapVerifyEnabled })
                    .then(() => {
                        showToast(mdsapVerifyEnabled ? t('toast.mdsapEnabled') : t('toast.mdsapDisabled'), 'info');
                        if (crossrefData) {
                            showToast(t('toast.mdsapReloading'), 'info');
                            loadCrossrefTable();
                        } else {
                            showToast(mdsapVerifyEnabled
                                ? t('toast.mdsapSaved7')
                                : t('toast.mdsapSaved2'),
                                'success');
                        }
                    })
                    .catch(e => showToast(t('toast.mdsapFailed', {msg: e.message || e}), 'error'));
            });
        }

        // Daily Audit tab controls
        if (els.btnRunDailyAudit) {
            els.btnRunDailyAudit.addEventListener('click', runDailyAudit);
        }
        if (els.btnRunMetaReview) {
            els.btnRunMetaReview.addEventListener('click', runMetaReview);
        }
        if (els.btnLoadAuditHistory) {
            els.btnLoadAuditHistory.addEventListener('click', loadDailyAuditHistory);
        }
        // Daily audit export buttons
        const btnExportAuditWord = document.getElementById('btnExportAuditWord');
        if (btnExportAuditWord) btnExportAuditWord.addEventListener('click', () => exportDailyAudit('word'));
        const btnExportAuditExcel = document.getElementById('btnExportAuditExcel');
        if (btnExportAuditExcel) btnExportAuditExcel.addEventListener('click', () => exportDailyAudit('excel'));
        const btnExportMetaReviewWord = document.getElementById('btnExportMetaReviewWord');
        if (btnExportMetaReviewWord) btnExportMetaReviewWord.addEventListener('click', () => exportMetaReviewReport('word'));
        const btnExportMetaReviewExcel = document.getElementById('btnExportMetaReviewExcel');
        if (btnExportMetaReviewExcel) btnExportMetaReviewExcel.addEventListener('click', () => exportMetaReviewReport('excel'));
        // Deviation alert dismiss
        const btnDismissDeviation = document.getElementById('btnDismissDeviation');
        if (btnDismissDeviation) {
            btnDismissDeviation.addEventListener('click', () => {
                if (els.deviationAlertBanner) els.deviationAlertBanner.style.display = 'none';
            });
        }

        // === Unified Command Bar: Crossref Tab ===
        if (els.btnCrossrefSend) {
            els.btnCrossrefSend.addEventListener('click', sendCrossrefCommand);
        }
        if (els.crossrefCommandInput) {
            els.crossrefCommandInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendCrossrefCommand();
                }
            });
        }
        if (els.btnCrossrefHelp) {
            els.btnCrossrefHelp.addEventListener('click', () => togglePopup('crossrefHelp'));
        }
        if (els.btnCrossrefDownloads) {
            els.btnCrossrefDownloads.addEventListener('click', () => {
                renderDownloadCatalog('crossref');
                togglePopup('crossrefDownloads');
            });
        }
        const closeCrossrefHelp = document.getElementById('closeCrossrefHelp');
        if (closeCrossrefHelp) closeCrossrefHelp.addEventListener('click', () => closePopup('crossrefHelp'));
        const closeCrossrefDownloads = document.getElementById('closeCrossrefDownloads');
        if (closeCrossrefDownloads) closeCrossrefDownloads.addEventListener('click', () => closePopup('crossrefDownloads'));
        const closeCrossrefFeedback = document.getElementById('closeCrossrefFeedback');
        if (closeCrossrefFeedback) closeCrossrefFeedback.addEventListener('click', () => closePopup('crossrefFeedback'));

        // === Unified Command Bar: Crossexam Tab ===
        if (els.btnCrossexamHelp) {
            els.btnCrossexamHelp.addEventListener('click', () => togglePopup('crossexamHelp'));
        }
        if (els.btnCrossexamDownloads) {
            els.btnCrossexamDownloads.addEventListener('click', () => {
                renderDownloadCatalog('crossexam');
                togglePopup('crossexamDownloads');
            });
        }
        const closeCrossexamHelp = document.getElementById('closeCrossexamHelp');
        if (closeCrossexamHelp) closeCrossexamHelp.addEventListener('click', () => closePopup('crossexamHelp'));
        const closeCrossexamDownloads = document.getElementById('closeCrossexamDownloads');
        if (closeCrossexamDownloads) closeCrossexamDownloads.addEventListener('click', () => closePopup('crossexamDownloads'));
        const closeCrossexamFeedback = document.getElementById('closeCrossexamFeedback');
        if (closeCrossexamFeedback) closeCrossexamFeedback.addEventListener('click', () => closePopup('crossexamFeedback'));

        // === Action Dropdown: Crossexam ===
        if (els.crossexamActionSelect) {
            els.crossexamActionSelect.addEventListener('change', () => {
                showActionInlineHelp('crossexam', els.crossexamActionSelect.value);
                // Auto-fill command prefix into input
                const prefix = ACTION_CMD_PREFIX[els.crossexamActionSelect.value];
                if (prefix && els.humanMessageInput) {
                    els.humanMessageInput.value = prefix;
                    els.humanMessageInput.focus();
                }
            });
        }

        // === Action Dropdown: Crossref ===
        if (els.crossrefActionSelect) {
            els.crossrefActionSelect.addEventListener('change', () => {
                showActionInlineHelp('crossref', els.crossrefActionSelect.value);
                const prefix = ACTION_CMD_PREFIX[els.crossrefActionSelect.value];
                if (prefix && els.crossrefCommandInput) {
                    els.crossrefCommandInput.value = prefix;
                    els.crossrefCommandInput.focus();
                }
            });
        }


        // === Download Bar: Crossref ===
        if (els.crossrefDlTypeSelect) {
            els.crossrefDlTypeSelect.addEventListener('change', () => {
                showDlInlineHelp('crossref', els.crossrefDlTypeSelect.value);
            });
        }
        if (els.crossrefDlWord) {
            els.crossrefDlWord.addEventListener('click', () => {
                const type = els.crossrefDlTypeSelect ? els.crossrefDlTypeSelect.value : '';
                if (type) handleDownloadCommand(['', type, 'word'], 'crossref');
            });
        }
        if (els.crossrefDlExcel) {
            els.crossrefDlExcel.addEventListener('click', () => {
                const type = els.crossrefDlTypeSelect ? els.crossrefDlTypeSelect.value : '';
                if (type) handleDownloadCommand(['', type, 'excel'], 'crossref');
            });
        }

        // === Download Bar: Crossexam ===
        if (els.crossexamDlTypeSelect) {
            els.crossexamDlTypeSelect.addEventListener('change', () => {
                showDlInlineHelp('crossexam', els.crossexamDlTypeSelect.value);
            });
        }
        if (els.crossexamDlWord) {
            els.crossexamDlWord.addEventListener('click', () => {
                const type = els.crossexamDlTypeSelect ? els.crossexamDlTypeSelect.value : '';
                if (type) handleDownloadCommand(['', type, 'word'], 'crossexam');
            });
        }
        if (els.crossexamDlExcel) {
            els.crossexamDlExcel.addEventListener('click', () => {
                const type = els.crossexamDlTypeSelect ? els.crossexamDlTypeSelect.value : '';
                if (type) handleDownloadCommand(['', type, 'excel'], 'crossexam');
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
        exportHistoryRecord,
        exportAuditRecord,
        editFeedback,
        deleteFeedback,
        cmdDownload,
        // LLM-Assist functions
        llmAssist,
        applyLlmResult,
        dismissLlmResult,
        // Evidence Editor functions
        openEvidenceEditor,
        addEvidenceItem,
        deleteEvidenceItem,
        toggleEvidenceFound,
        toggleEvidenceInadequate,
        toggleEvidenceOutdated,
        previewEvidenceRecalc,
        deepRecalcEvidence,
        confirmEvidenceUpdate,
        cancelEvidenceEditor,
    };


    // ============================================================
    // Cross-Reference Comparison Table
    // ============================================================

    let crossrefRegulations = null;  // cached regulation list
    let crossrefData = null;         // cached cross-ref table data
    let showOriginalText = false;   // toggle: show native-language regulatory text
    let mdsapVerifyEnabled = true; // toggle: MDSAP cross-examination verification

    const FLAG_EMOJIS = {
        US: "🇺🇸", EU: "🇪🇺", TW: "🇹🇼", JP: "🇯🇵",
        CN: "🇨🇳", KR: "🇰🇷", AU: "🇦🇺", CA: "🇨🇦",
        BR: "🇧🇷", IN: "🇮🇳", GB: "🇬🇧",
    };

    const METHOD_LABELS = {
        get official_crossref() { return "📜 " + t("method.officialCrossref"); },
        get clause_structure() { return "📁 " + t("method.clauseStructure"); },
        get semantic_en() { return "🇬🇧 " + t("method.semanticEn"); },
        get semantic_zh() { return "🇹🇼 " + t("method.semanticZh"); },
        get keyword_match() { return "🔑 " + t("method.keywordMatch"); },
        get expert_judgment() { return "🧑‍💻 " + t("method.expertJudgment"); },
        get llm_analysis() { return "🤖 " + t("method.llmAnalysis"); },
    };

    const LANG_LABELS = {
        en: "English",
        "zh-TW": "繁體中文",
        "zh-CN": "簡體中文",
        de: "Deutsch",
        fr: "Français",
        ja: "日本語",
        ko: "한국어",
        "pt-BR": "Português (Brasil)",
        pt: "Português",
    };

    async function loadCrossrefRegulations() {
        if (!els.countryCheckboxes) return;
        els.countryCheckboxes.innerHTML = '<div class="loading-cell">✨ ' + t('crossref.loadingRegs') + '</div>';

        try {
            try {
                const mdsapState = await apiFetch("/crossref/mdsap-verify");
                mdsapVerifyEnabled = !!mdsapState.enabled;
                const cb = document.getElementById('toggleMdsapVerify');
                if (cb) cb.checked = mdsapVerifyEnabled;
            } catch (_) {}

            const data = await apiFetch("/crossref/regulations");
            crossrefRegulations = data.regulations || [];

            if (crossrefRegulations.length === 0) {
                els.countryCheckboxes.innerHTML = '<div class="loading-cell">❌ ' + t('ui.noRegsAvailable') + '</div>';
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
                    <input type="checkbox" value="${escapeAttr(reg.regulation_id)}" ${reg.is_user_selected !== false ? 'checked' : ''}>
                    <span class="country-flag">${flag}</span>
                    <div>
                        <div class="country-name">${escapeHtml(reg.country_name_zh)} (${escapeHtml(reg.country)})</div>
                        <div class="country-meta">${escapeHtml(reg.name_zh)}</div>
                        <div class="country-meta">✅${fullCount} ⬆️${exceedsCount} 🚨${uniqueCount} ${t('ui.unique')}</div>
                    </div>
                </label>`;
            }
            const failedRegions = data.failed_regions || [];
            if (failedRegions.length > 0) {
                html += '<div class="crawl-failed-warning">';
                html += `<div class="crawl-failed-title">⚠️ ${t('ui.crawlFailed', {n: failedRegions.length})}</div>`;
                for (const fr of failedRegions) {
                    html += `<div class="crawl-failed-item">❌ ${escapeHtml(displayRegion(fr.region))} (${escapeHtml(fr.agency)}) — ${escapeHtml(fr.reason)}</div>`;
                }
                html += '</div>';
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
            els.countryCheckboxes.innerHTML = `<div class="loading-cell">❌ ${t('toast.loadFailed', {msg: escapeHtml(err.message)})}</div>`;
        }
    }

    async function loadCrossrefTable() {
        // Gather selected regulations
        const checked = els.countryCheckboxes.querySelectorAll("input[type=checkbox]:checked");
        const regIds = Array.from(checked).map((cb) => cb.value);

        if (regIds.length === 0) {
            showToast(t('toast.selectCountry'), "error");
            return;
        }

        els.btnLoadCrossref.disabled = true;
        els.btnLoadCrossref.textContent = '✨ ' + t('ui.generating');

        try {
            const _uiLang = (window.__i18n && window.__i18n.lang) || "en-US";
            const data = await apiFetch(`/crossref/table?regulations=${regIds.join(",")}&lang=${encodeURIComponent(_uiLang)}`);
            crossrefData = data;

            renderCrossrefSummary(data);
            renderCrossrefTable(data);
            renderInterCountryDiffs(data);
            renderDeltaItems(data);

            els.crossrefSummary.style.display = "";
            els.crossrefTableWrapper.style.display = "";
            els.intercountrySection.style.display = "";
            els.deltaSection.style.display = "";

            showToast(t('toast.crossrefGenerated', {rows: data.rows.length, cols: regIds.length}), "success");
        } catch (err) {
            showToast(t('toast.crossrefFailed', {msg: err.message}), "error");
        } finally {
            els.btnLoadCrossref.disabled = false;
            els.btnLoadCrossref.textContent = t('crossref.generateTable');
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
                <div class="stat-row"><span>✅ ${t('crossref.legendFull')}</span><strong>${fullCount}</strong></div>
                <div class="stat-row"><span>⬆️ ${t('crossref.legendExceeds')}</span><strong style="color:#2563eb">${exceedsCount}</strong></div>
                <div class="stat-row"><span>⚠️ ${t('crossref.legendPartial')}</span><strong style="color:var(--partial)">${partialCount}</strong></div>
                <div class="stat-row"><span>➖ ${t('crossref.legendNA')}</span><strong style="color:var(--insufficient)">${naCount}</strong></div>
                <div class="stat-row"><span>🚨 ${t('ui.uniqueReqs')}</span><strong style="color:var(--non-compliant)">${uniqueReqs.length}</strong></div>
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
        let headHtml = `<tr><th>ISO 13485 ${t('table.clause')}</th>`;
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
                          title="${t('ui.clickToExpand')}"
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

                const _cLang = (window.__i18n && window.__i18n.lang) || "en-US";
                const _isEn = !_cLang.startsWith("zh") && !_cLang.startsWith("ja");
                const _countryName = _isEn ? (m.country_name_en || m.country_name_zh || rid) : (m.country_name_zh || rid);
                const _lblRef = t('crossref.lblRef');
                const _lblMethod = t('crossref.lblMethod');
                const _lblConf = t('crossref.lblConfidence');
                // Show primary rationale based on language
                const _primaryRationale = _isEn ? (reg.rationale_en || reg.rationale_zh || "—") : (reg.rationale_zh || reg.rationale_en || "—");
                const _secondaryRationale = _isEn ? (reg.rationale_zh || "—") : (reg.rationale_en || "—");
                const _lblPrimary = t('crossref.lblRationale');
                const _lblSecondary = t('crossref.lblRationaleAlt');

                bodyHtml += `<div class="rationale-card">
                    <div class="rc-header">${flag} ${escapeHtml(_countryName)}</div>
                    <div class="rc-field"><span class="rc-label">${_lblRef}</span> <span class="rc-value">${escapeHtml(reg.regulation_ref || "—")}</span></div>
                    <div class="rc-field"><span class="rc-label">${_lblMethod}</span> <span class="method-badge">${methodLabel}</span></div>
                    <div class="rc-field"><span class="rc-label">${_lblConf}</span> <span class="rc-confidence ${confClass}">${Math.round(conf * 100)}%</span></div>
                    <div class="rc-field"><span class="rc-label">${_lblPrimary}</span> <span class="rc-value">${escapeHtml(_primaryRationale)}</span></div>
                    <div class="rc-field"><span class="rc-label">${_lblSecondary}</span> <span class="rc-value">${escapeHtml(_secondaryRationale)}</span></div>`;

                // Native-language regulatory text comparison
                if (showOriginalText && reg.original_text) {
                    const langLabel = LANG_LABELS[reg.original_lang] || reg.original_lang || "—";
                    const _lblOrig = `📜 ${t('crossref.lblOrigText')} (${langLabel}):`;
                    bodyHtml += `<div class="rc-field" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
                        <span class="rc-label">${_lblOrig}</span>
                        <div class="rc-value" style="font-style:italic;margin-top:4px">${escapeHtml(reg.original_text)}</div>
                    </div>`;
                    if (reg.english_translation) {
                        bodyHtml += `<div class="rc-field">
                            <span class="rc-label">🇬🇧 English Translation:</span>
                            <div class="rc-value" style="margin-top:4px">${escapeHtml(reg.english_translation)}</div>
                        </div>`;
                    }
                    if (reg.semantic_note) {
                        const _lblSemantic = '💡 ' + t('crossref.lblSemantic');
                        bodyHtml += `<div class="rc-field">
                            <span class="rc-label">${_lblSemantic}</span>
                            <div class="rc-value" style="margin-top:4px;color:var(--primary)">${escapeHtml(reg.semantic_note)}</div>
                        </div>`;
                    }
                }

                // Delta items for this clause
                const deltas = reg.delta_items || [];
                if (deltas.length > 0) {
                    const _lblDelta = '🚨 ' + t('crossref.lblUniqueReqs');
                    bodyHtml += `<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
                        <span class="rc-label">${_lblDelta}</span>`;
                    for (const d of deltas) {
                        const _deltaTitle = _isEn ? (d.title_en || d.title_zh) : (d.title_zh || d.title_en);
                        bodyHtml += `<div style="margin-top:4px;padding:6px;background:var(--non-compliant-bg);border-radius:4px">
                            <strong>${escapeHtml(_deltaTitle)}</strong>
                            <div style="font-size:0.72rem;color:var(--text-secondary)">${escapeHtml(d.regulation_ref)}</div>`;
                        // Show native text for delta items too
                        if (showOriginalText && d.original_text) {
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
        const _crLang = window.__i18n ? window.__i18n.lang : "en-US";
        if (_crLang.startsWith("zh")) {
            els.crossrefTableCount.textContent = t('crossref.tableCount', {rows: rows.length, cols: regIds.length});
        } else if (_crLang.startsWith("ja")) {
            els.crossrefTableCount.textContent = t('crossref.tableCount', {rows: rows.length, cols: regIds.length});
        } else {
            els.crossrefTableCount.textContent = `Showing ${rows.length} ISO 13485 clauses × ${regIds.length} country regulations`;
        }
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

            const _icLang = (window.__i18n && window.__i18n.lang) || "en-US";
            const _icEn = !_icLang.startsWith("zh") && !_icLang.startsWith("ja");
            const _icCountry = _icEn ? (m.country_name_en || m.country_name_zh || rid) : (m.country_name_zh || rid);
            html += `<div class="intercountry-card">
                <h4>${flag} ${escapeHtml(_icCountry)} ${t("crossref.uniqueDiffs")}</h4>`;

            if (d.exceeds_only.length > 0) {
                html += `<div style="margin-bottom:8px"><strong>⬆️ ${t("crossref.exceedsOnly")}</strong>
                    <div class="diff-clause-list">
                        ${d.exceeds_only.map(c => `<span class="diff-clause-chip diff-chip-exceeds">${c}</span>`).join("")}
                    </div>
                </div>`;
            }

            if (reqs.length > 0) {
                html += `<div style="margin-bottom:8px"><strong>🚨 ${t("crossref.uniqueReqsCount", {n: reqs.length})}</strong>`;
                for (const req of reqs) {
                    const _reqTitle = _icEn ? (req.title_en || req.title_zh) : (req.title_zh || req.title_en);
                    html += `<div style="margin:4px 0;padding:6px 8px;background:var(--bg);border-radius:4px;font-size:0.78rem">
                        <strong>${escapeHtml(_reqTitle)}</strong>
                        <span style="color:var(--text-muted);margin-left:8px">${escapeHtml(req.regulation_ref)}</span>`;
                    // Show native text for inter-country comparison
                    if (showOriginalText && req.original_text) {
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
                html += `<div><strong>➖ ${t("crossref.notCovered")}</strong>
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
            const _noD = t("crossref.noSignificantDiffs");
            els.intercountryContainer.innerHTML = `<div class="empty-state"><div class="empty-state-text">${_noD}</div></div>`;
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

            const _dlLang = (window.__i18n && window.__i18n.lang) || "en-US";
            const _dlEn = !_dlLang.startsWith("zh") && !_dlLang.startsWith("ja");
            const _dlCountry = _dlEn ? (m.country_name_en || m.country_name_zh || rid) : (m.country_name_zh || rid);
            html += `<div class="delta-country-group">
                <h4>${flag} ${escapeHtml(_dlCountry)} — ${reqs.length} ${t("crossref.uniqueReqsSuffix")}</h4>`;

            for (const req of reqs) {
                const confClass = req.confidence >= 0.9 ? "confidence-high" : req.confidence >= 0.7 ? "confidence-medium" : "confidence-low";
                const methodLabel = METHOD_LABELS[req.method] || req.method || "—";
                const _dlTitle = _dlEn ? `${escapeHtml(req.title_en)} / ${escapeHtml(req.title_zh)}` : `${escapeHtml(req.title_zh)} / ${escapeHtml(req.title_en)}`;
                const _dlReq = _dlEn ? (req.requirement_en || req.requirement_zh) : (req.requirement_zh || req.requirement_en);

                html += `<div class="delta-item">
                    <div class="di-ref">${escapeHtml(req.regulation_ref)}</div>
                    <div class="di-title">${_dlTitle}</div>
                    <div class="di-req">${escapeHtml(_dlReq)}</div>`;

                // Native text with translation
                if (showOriginalText && req.original_text) {
                    const langLabel = LANG_LABELS[req.original_lang] || req.original_lang || "";
                    html += `<div style="margin:8px 0;padding:8px;background:var(--bg);border-radius:4px;border-left:3px solid var(--primary)">
                        <div style="font-size:0.72rem;font-weight:600;color:var(--text-secondary);margin-bottom:4px">📜 ${t('crossref.lblOrigText')} (${langLabel})</div>
                        <div style="font-style:italic;font-size:0.8rem">${escapeHtml(req.original_text)}</div>`;
                    if (req.english_translation) {
                        html += `<div style="margin-top:6px;font-size:0.72rem;font-weight:600;color:var(--text-secondary)">🇬🇧 English Translation</div>
                            <div style="font-size:0.8rem">${escapeHtml(req.english_translation)}</div>`;
                    }
                    if (req.semantic_note) {
                        html += `<div style="margin-top:6px;font-size:0.72rem;font-weight:600;color:var(--primary)">💡 ${t('crossref.lblSemanticFull')}</div>
                            <div style="font-size:0.8rem;color:var(--primary)">${escapeHtml(req.semantic_note)}</div>`;
                    }
                    html += `</div>`;
                }

                const _dlQuestion = _dlEn ? (req.audit_question_en || req.audit_question_zh) : (req.audit_question_zh || req.audit_question_en);
                html += `<div class="di-question">💬 ${t("detail.auditQuestion")}: ${escapeHtml(_dlQuestion)}</div>
                    <div class="di-meta">
                        <span>📊 ${t("crossref.relatedISO")}: ${(req.related_iso_clauses || []).join(", ")}</span>
                        <span>⚠️ ${t("crossref.impact")}: ${escapeHtml(req.audit_impact)}</span>
                        <span class="method-badge">${methodLabel}</span>
                        <span class="rc-confidence ${confClass}">${t("crossref.confidence")} ${Math.round((req.confidence || 0) * 100)}%</span>
                    </div>
                </div>`;
            }

            html += `</div>`;
        }

        if (totalDelta === 0) {
            html = '<div class="empty-state"><div class="empty-state-text">' + t('crossref.noUniqueReqs') + '</div></div>';
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
            showToast(t('toast.enterRunId'), "error");
            return;
        }

        // Close existing connection
        if (sseSource) {
            sseSource.close();
            sseSource = null;
        }

        // Clear feed
        els.crossexamFeed.innerHTML = "";
        addSystemMessage("🔌 " + t("sse.connecting"));

        try {
            sseSource = new EventSource(`${API_BASE}/${encodeURIComponent(runId)}/stream`);

            sseSource.onopen = function () {
                sseConnected = true;
                updateSSEStatus("connected", "🟢 " + t("sse.connected"));
                els.btnConnectSSE.textContent = "❌ " + t("sse.disconnect");
                els.btnPauseExam.disabled = false;
                els.humanMessageInput.disabled = false;
                els.btnSendHuman.disabled = false;
            };
                window.__sseReconnectAttempts = 0;  // Reset reconnect counter on successful connect

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
                    sseConnected = false;
                    addSystemMessage("❌ " + t("sse.disconnected"));
                    updateSSEStatus("", "⚠️ " + t("sse.reconnecting"));
                    // Auto-reconnect with exponential backoff
                    if (!window.__sseReconnectAttempts) window.__sseReconnectAttempts = 0;
                    window.__sseReconnectAttempts++;
                    const delay = Math.min(1000 * Math.pow(2, window.__sseReconnectAttempts - 1), 30000);
                    setTimeout(() => {
                        if (!sseConnected) {
                            addSystemMessage(`🔄 ${t('sse.reconnectAttempt', {n: window.__sseReconnectAttempts})}`);
                            connectSSE();
                        }
                    }, delay);
                }
            };

        } catch (err) {
            showToast(t('toast.sseFailed', {msg: err.message}), "error");
        }
    }

    function disconnectSSE() {
        if (sseSource) {
            sseSource.close();
            sseSource = null;
        }
        sseConnected = false;
        updateSSEStatus("", t("crossexam.notConnected"));
        els.btnConnectSSE.textContent = t("crossexam.connect");
        els.btnPauseExam.disabled = true;
        els.btnResumeExam.disabled = true;
        els.humanMessageInput.disabled = true;
        els.btnSendHuman.disabled = true;
    }

    // Active phase filter
    let activePhaseFilter = 'all';

    // Cache clause context from verification_start events
    // Maps clause_id → { clause_title, doc_id, selected_regulations }
    const clauseContextCache = {};

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
                addSystemMessage('✅ ' + t('sse.connectedToStream'));
                updateSSEStatus('streaming', '🟢 ' + t('sse.streaming'));
                break;

            case 'pipeline_started':
                addSystemMessage('🚀 ' + t('sse.pipelineStarted'));
                break;

            case 'pipeline_complete':
                addSystemMessage('🏁 ' + t('sse.pipelineComplete'));
                updateSSEStatus('connected', '✅ ' + t('sse.done'));
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
                addPhaseCard('2', t('phase.p2'), data, 'start');
                break;
            case 'phase_2_result':
                addPhaseCard('2', t('phase.p2'), data, 'result');
                break;
            case 'phase_2_error':
                addPhaseCard('2', t('phase.p2'), data, 'error');
                break;

            // ── Phase 3: Risk Assessment ──
            case 'phase_3_start':
                addPhaseCard('3', t('phase.p3'), data, 'start');
                break;
            case 'phase_3_result':
                addPhaseCard('3', t('phase.p3'), data, 'result');
                break;
            case 'phase_3_error':
                addPhaseCard('3', t('phase.p3'), data, 'error');
                break;

            // ── Phase 4: Remediation ──
            case 'phase_4_start':
                addPhaseCard('4', t('phase.p4'), data, 'start');
                break;
            case 'phase_4_result':
                addPhaseCard('4', t('phase.p4'), data, 'result');
                break;
            case 'phase_4_error':
                addPhaseCard('4', t('phase.p4'), data, 'error');
                break;

            // ── Phase 1/2/4 conversation-style events ──
            case 'phase_1_conversation':
                renderPhaseConversation('1', 'Gap Scan', data);
                break;
            case 'phase_2_conversation':
                renderPhaseConversation('2', t('phase.p2'), data);
                break;
            case 'phase_4_conversation':
                renderPhaseConversation('4', t('phase.p4'), data);
                break;

            // ── Phase 5: Cross-Examination ──
            case 'phase_5_start':
                addPhaseCard('5', t('phase.p5'), data, 'start');
                break;
            case 'phase_5_result':
                addPhaseCard('5', t('phase.p5'), data, 'result');
                break;
            case 'phase_5_error':
                addPhaseCard('5', t('phase.p5'), data, 'error');
                break;

            // ── Phase 5 sub-events (Analyzer/Verifier debate) ──
            case 'verification_start':
                // Cache clause context for enriching analyzer/verifier messages
                if (data.clause_id) {
                    clauseContextCache[data.clause_id] = {
                        clause_title: data.clause_title || '',
                        doc_id: data.doc_id || '',
                        selected_regulations: data.selected_regulations || []
                    };
                }
                addSystemMessage(`🔄 ${t('sse.startCrossExam')}: ${data.clause_id} — ${data.clause_title || ''}`, '5');
                break;
            case 'round_start':
                addRoundDivider(data.round, '5');
                break;
            case 'analyzer':
                addExamMessage('analyzer', '🔍 ' + t('ui.analyzer'), data.content, data.clause_id, null, '5');
                break;
            case 'verifier':
                addExamMessage('verifier', '🛡️ ' + t('ui.verifier'), data.content, data.clause_id, null, '5');
                break;
            case 'round_end': {
                const resultText = data.agreed ? '✅ ' + t('sse.roundAgreed') : '❌ ' + t('sse.roundDisagreed');
                addSystemMessage(`${resultText} (${data.clause_id})`, '5');
                break;
            }
            case 'verification_complete':
                addSystemMessage(`🏁 ${t('sse.clauseComplete', {id: data.clause_id})} — ${data.agreed ? '✅ ' + t('ui.agreed') : '🚩 ' + t('ui.raReviewRequired')}`, '5');
                break;

            case 'verification_skipped':
                addSystemMessage(`⏭ ${t('sse.clauseSkipped', {id: data.clause_id})} (${data.reason === 'time_budget' ? t('sse.timeBudgetExhausted') : t('sse.tokenBudgetExhausted')})`, '5');
                break;
            case 'human_ack':
                addSystemMessage(`✅ ${t('sse.humanAck', {round: data.consumed_at_round, id: data.clause_id})}`, '5');
                break;
            // ── Human intervention ──
            case 'human_injection':
                addExamMessage('human', `🙋 ${data.user_id || t('ui.human')}`, data.message, null, data.timestamp);
                break;
            case 'human_injection_applied': {
                const clauseId = data.clause_id ? ` (${t('table.clause')} ${data.clause_id})` : '';
                const msgCount = Array.isArray(data.messages) ? data.messages.length : 1;
                addSystemMessage(`✅ ${t('sse.humanApplied', {clauseId: clauseId, count: msgCount})}`);
                break;
            }

            // ── Control events ──
            case 'complete':
                addSystemMessage(`🏁 ${t('sse.complete')} — ${t('detail.verdict')}: ${data.verdict || '—'} ${data.flagged ? '🚩' + t('ui.raReviewRequired') : ''}`);
                updateSSEStatus('connected', '✅ ' + t('sse.complete'));
                break;
            case 'error':
                addSystemMessage(`❌ ${t('sse.error')}: ${data.message || data.error || t('ui.unknownError')}`);
                break;
            case 'pause':
                addSystemMessage('⏸ ' + t('sse.paused'));
                updateSSEStatus('connected', '⏸ ' + t('sse.paused'));
                els.btnPauseExam.disabled = true;
                els.btnResumeExam.disabled = false;
                break;
            case 'resume':
                addSystemMessage('▶️ ' + t('sse.resumed'));
                updateSSEStatus('streaming', '🟢 ' + t('sse.streaming'));
                els.btnPauseExam.disabled = false;
                els.btnResumeExam.disabled = true;
                break;
            case 'heartbeat':
                break;
            default:
                console.warn('Unknown SSE event type:', type, data);
        }

        // Auto-scroll to bottom
        els.crossexamFeed.scrollTop = els.crossexamFeed.scrollHeight;
    }

    /**
     * Add a phase card to the SSE feed.
     * @param {string} phaseNum - '1', '2', '3', '4', '5'
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
        let statusText = t('ui.running');
        if (status === 'result') {
            statusIcon = '✅';
            statusText = t('sse.done');
        } else if (status === 'error') {
            statusIcon = '❌';
            statusText = t('sse.errorLabel');
        }

        let bodyHtml = '';
        if (status === 'start' && data.prompt_preview) {
            bodyHtml = `
                <span class="collapsible-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')">📄 ${t('sse.viewPrompt')}</span>
                <div class="collapsible-content">
                    <div class="llm-prompt-preview">${escapeHtml(data.prompt_preview)}</div>
                </div>`;
        } else if (status === 'result') {
            // Phase 3 specific: risk_details (rule engine, no LLM)
            if (data.risk_details && data.risk_details.length > 0) {
                const riskRows = data.risk_details.map(d => {
                    const stats = d.evidence_stats || {};
                    return `<tr>
                        <td style="font-weight:600">${escapeHtml(d.clause_id || '')}</td>
                        <td>${escapeHtml(d.gap_severity || '')}</td>
                        <td>${escapeHtml(d.risk_level || '')}</td>
                        <td><span class="verdict-badge verdict-${(d.verdict || '').toLowerCase().replace(/\s+/g, '-')}">${escapeHtml(d.verdict || '')}</span></td>
                        <td>${stats.found_adequate || 0}/${stats.total || 0}</td>
                    </tr>`;
                }).join('');
                bodyHtml = `
                    <div style="font-size:0.85rem;margin-bottom:6px">${t('sse.clauseCount')}: ${data.clause_count || data.risk_details.length} | ${t('sse.ruleEngine')}</div>
                    <span class="collapsible-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')">📊 ${t('sse.viewRiskResults')}</span>
                    <div class="collapsible-content">
                        <table class="risk-detail-table" style="width:100%;font-size:0.8rem;border-collapse:collapse">
                            <thead><tr style="background:#f8fafc;text-align:left">
                                <th style="padding:4px 6px">${t('table.clause')}</th>
                                <th style="padding:4px 6px">${t('detail.gapSeverity')}</th>
                                <th style="padding:4px 6px">${t('detail.riskLevel')}</th>
                                <th style="padding:4px 6px">${t('table.verdict')}</th>
                                <th style="padding:4px 6px">${t('table.evidence')}</th>
                            </tr></thead>
                            <tbody>${riskRows}</tbody>
                        </table>
                    </div>`;
            } else {
                // Generic result rendering for P1/P2/P4/P5
                const summary = [];
                if (data.evidence_summary) {
                    summary.push(`${t('evidence.foundLabel')}: ${data.evidence_summary.found || 0} | ${t('evidence.notFoundLabel')}: ${data.evidence_summary.not_found || 0} | ${t('evidence.inadequateLabel')}: ${data.evidence_summary.inadequate || 0}`);
                }
                if (data.total_suggestions !== undefined) {
                    summary.push(`${t('sse.suggestions')}: ${data.total_suggestions}`);
                }
                if (data.total_agreed !== undefined) {
                    summary.push(`${t('ui.agreed')}: ${data.total_agreed} | ${t('table.flags')}: ${data.total_flagged || 0}`);
                }
                if (data.usage) {
                    summary.push(`Token: ${(data.usage.total_tokens || 0).toLocaleString()}`);
                }
                bodyHtml = summary.length > 0 ? `<div style="margin-bottom:6px">${summary.join(' | ')}</div>` : '';
                if (data.llm_response) {
                    const formattedContent = formatPhaseResultContent(data.llm_response);
                    bodyHtml += `
                        <span class="collapsible-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')">📄 ${t('sse.viewLlmResponse')}</span>
                        <div class="collapsible-content">
                            <div class="llm-response-preview">${formattedContent}</div>
                        </div>`;
                }
            }
        } else if (status === 'error') {
            bodyHtml = `<div style="color:#dc2626">${escapeHtml(data.error || t('ui.unknownError'))}</div>`;
        }

        card.innerHTML = `
            <div class="crossexam-card-header">
                <span class="phase-badge phase-${phaseNum}">P${phaseNum}</span>
                <span class="card-status-text">${statusIcon} ${phaseName}</span>
                ${docInfo ? `<span class="card-tag card-tag-doc" title="${t('table.document')}">📄 ${escapeHtml(docInfo)}</span>` : ''}
                ${clauseIds ? `<span class="card-tag card-tag-clause" title="ISO 13485 ${t('table.clause')}">§ ${escapeHtml(clauseIds)}</span>` : ''}
                ${data.evidence_summary ? `<span class="card-tag card-tag-evidence" title="${t('sse.evidenceStats')}">🔍 ${data.evidence_summary.found || 0}/${(data.evidence_summary.found || 0) + (data.evidence_summary.not_found || 0) + (data.evidence_summary.inadequate || 0)}</span>` : ''}
                ${data.usage ? `<span class="card-tag card-tag-token" title="${t('card.tokenUsage')}">⚡ ${((data.usage.total_tokens || 0) / 1000).toFixed(1)}k</span>` : ''}
                <span class="card-timestamp">${now}</span>
            </div>
            <div class="crossexam-card-body">${bodyHtml}</div>`;

        // If it's a 'start' event, mark previous start card for same doc as done
        if (status === 'start') {
            const prevLoading = els.crossexamFeed.querySelectorAll(`.crossexam-card.loading.phase-${phaseNum}[data-doc="${data.doc_id}"]`);
            prevLoading.forEach(el => el.classList.remove('loading'));
        }
        if (data.doc_id) card.dataset.doc = data.doc_id;

        els.crossexamFeed.appendChild(card);
    }

    function renderPhaseConversation(phaseNum, phaseName, data) {
        const docLabel = data.doc_id ? `📄 ${escapeHtml(data.doc_id)}` : '';
        const clauseLabel = (data.clause_ids && data.clause_ids.length)
            ? `§ ${data.clause_ids.join(', ')}`
            : '';
        const contextTag = [docLabel, clauseLabel].filter(Boolean).join(' │ ');

        if (data.question_summary) {
            const qDiv = document.createElement('div');
            qDiv.className = 'exam-message msg-llm-question';
            qDiv.dataset.phase = phaseNum;
            if (activePhaseFilter !== 'all' && activePhaseFilter !== phaseNum) {
                qDiv.style.display = 'none';
            }
            const timeStr = new Date().toLocaleTimeString();
            qDiv.innerHTML = `
                <div class="msg-header">
                    <span class="msg-role role-llm-question">💻 ${t('sse.system')} → P${phaseNum} ${escapeHtml(phaseName)}</span>
                    <span><span class="msg-regulation">${contextTag}</span> <span class="msg-time">${timeStr}</span></span>
                </div>
                <div class="msg-body">${escapeHtml(data.question_summary)}</div>`;
            els.crossexamFeed.appendChild(qDiv);
        }

        if (data.answer_summary) {
            const aDiv = document.createElement('div');
            aDiv.className = 'exam-message msg-llm-answer';
            aDiv.dataset.phase = phaseNum;
            if (activePhaseFilter !== 'all' && activePhaseFilter !== phaseNum) {
                aDiv.style.display = 'none';
            }
            const timeStr = new Date().toLocaleTimeString();
            let bodyHtml = escapeHtml(data.answer_summary);
            if (data.details && typeof data.details === 'object') {
                bodyHtml += formatPhaseConversationDetails(data.details, phaseNum);
            }
            aDiv.innerHTML = `
                <div class="msg-header">
                    <span class="msg-role role-llm-answer">🤖 ${t('sse.llmResponse')} → P${phaseNum} ${escapeHtml(phaseName)}</span>
                    <span class="msg-time">${timeStr}</span>
                </div>
                <div class="msg-body">${bodyHtml}</div>`;
            els.crossexamFeed.appendChild(aDiv);
        }

        els.crossexamFeed.scrollTop = els.crossexamFeed.scrollHeight;
    }

    function formatPhaseConversationDetails(details, phaseNum) {
        let html = '';
        if (phaseNum === '1' && details.clauses) {
            html += '<table style="width:100%;font-size:0.82rem;border-collapse:collapse;margin:8px 0 4px">';
            html += '<thead><tr style="background:#f1f5f9;text-align:left"><th style="padding:3px 6px">' + t('table.clause') + '</th><th style="padding:3px 6px">' + t('evidence.foundLabel') + '</th><th style="padding:3px 6px">' + t('evidence.notFoundLabel') + '</th><th style="padding:3px 6px">' + t('evidence.inadequateLabel') + '</th></tr></thead><tbody>';
            for (const c of details.clauses) {
                html += `<tr>
                    <td style="padding:3px 6px;font-weight:500">${escapeHtml(c.clause_id || '')}</td>
                    <td style="padding:3px 6px;color:#16a34a">${c.found || 0}</td>
                    <td style="padding:3px 6px;color:#dc2626">${c.not_found || 0}</td>
                    <td style="padding:3px 6px;color:#d97706">${c.inadequate || 0}</td>
                </tr>`;
            }
            html += '</tbody></table>';
        }
        if (phaseNum === '2' && details.clauses) {
            html += '<table style="width:100%;font-size:0.82rem;border-collapse:collapse;margin:8px 0 4px">';
            html += '<thead><tr style="background:#f1f5f9;text-align:left"><th style="padding:3px 6px">' + t('table.clause') + '</th><th style="padding:3px 6px">' + t('table.evidence') + '</th><th style="padding:3px 6px">' + t('evidence.adequacy') + '</th><th style="padding:3px 6px">' + t('evidence.explanation') + '</th></tr></thead><tbody>';
            for (const c of details.clauses) {
                const icon = c.adequacy === 'full' ? '✅' : c.adequacy === 'partial' ? '⚠️' : c.adequacy === 'irrelevant' ? '❌' : '❓';
                html += `<tr>
                    <td style="padding:3px 6px;font-weight:500">${escapeHtml(c.clause_id || '')}</td>
                    <td style="padding:3px 6px">${escapeHtml(c.evidence_name || '')}</td>
                    <td style="padding:3px 6px">${icon} ${escapeHtml(c.adequacy || '')}</td>
                    <td style="padding:3px 6px;max-width:350px;word-break:break-word">${escapeHtml((c.explanation || '').substring(0, 200))}</td>
                </tr>`;
            }
            html += '</tbody></table>';
        }
        if (phaseNum === '4' && details.clauses) {
            html += '<div style="margin:8px 0 4px;font-size:0.82rem">';
            for (const c of details.clauses) {
                html += `<div style="margin-bottom:6px"><strong>§${escapeHtml(c.clause_id || '')}</strong>`;
                if (c.suggestion) html += ` — ${escapeHtml(c.suggestion.substring(0, 300))}`;
                if (c.regulation) html += `<br><span style="color:#6b7280;font-size:0.78rem">📜 ${escapeHtml(c.regulation)}</span>`;
                html += `</div>`;
            }
            html += '</div>';
        }
        return html;
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

        // Enrich header with clause context (clause_title, doc_id) from cache
        let contextLine = '';
        if (regulation && clauseContextCache[regulation]) {
            const ctx = clauseContextCache[regulation];
            const parts = [];
            if (ctx.clause_title) parts.push(ctx.clause_title);
            if (ctx.doc_id) parts.push(`📄 ${ctx.doc_id}`);
            if (ctx.selected_regulations && ctx.selected_regulations.length) {
                parts.push(`📜 ${ctx.selected_regulations.join(', ')}`);
            }
            if (parts.length) {
                contextLine = `<div class="msg-clause-context">${escapeHtml(parts.join(' │ '))}</div>`;
            }
        }

        msgDiv.innerHTML = `
            <div class="msg-header">
                <span class="msg-role role-${type}">${role}</span>
                <span>${regBadge} <span class="msg-time">${timeStr}</span></span>
            </div>
            ${contextLine}
            <div class="msg-body">${(type === 'analyzer' || type === 'verifier') ? formatLLMContent(content, type) : escapeHtml(content || '')}</div>`;
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
        div.textContent = `─── ${t('ui.roundN', {n: round})} ───`;

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
            showToast(t('toast.pauseFailed', {msg: err.message}), "error");
        }
    }

    async function resumeExam() {
        const runId = (els.sseRunIdInput && els.sseRunIdInput.value.trim()) || RUN_ID;
        if (!runId) return;
        try {
            await apiPost(`/${runId}/resume`, {});
        } catch (err) {
            showToast(t('toast.resumeFailed', {msg: err.message}), "error");
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
            showToast(t('toast.sendFailed', {msg: err.message}), "error");
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
            // If crossexam help popup exists, toggle it instead of appending
            if (els.crossexamHelpPopup) {
                togglePopup('crossexamHelp');
            } else {
                appendSystemMessage(
                    `<strong>${t('cmd.helpTitle')}:</strong><br>` +
                    `<code>/download &lt;type&gt; &lt;format&gt;</code> — ${t('cmd.opt.download')}<br>` +
                    `<code>/feedback daily|meta "&lt;text&gt;"</code> — ${t('cmd.opt.feedback')}<br>` +
                    `<code>/feedback history</code> — ${t('cmd.opt.feedbackHistory')}<br>` +
                    `<code>/run audit|meta</code> — ${t('cmd.opt.run')}<br>` +
                    `<code>/downloads</code> — ${t('cmd.opt.downloads')}<br>` +
                    `<code>/adjust &lt;id&gt; "&lt;clause&gt;" &lt;old&gt; -&gt; &lt;new&gt;</code> — ${t('cmd.opt.adjust')}<br>` +
                    `<code>/standards</code> — ${t('cmd.opt.standards')}<br>` +
                    `<code>/help</code> — ${t('cmd.helpBtn')}`
                );
            }
            return true;
        }

        if (cmd === "/standards") {
            try {
                const resp = await fetch("/api/report/standards/list");
                const data = await resp.json();
                let html = `<strong>${t('cmd.opt.standards')} (${data.standards.length}):</strong><br>`;
                for (const std of data.standards) {
                    html += `<br><strong>${std.name_zh}</strong> (${std.standard_id})<br>`;
                    for (const cl of std.clause_links) {
                        html += `&nbsp;&nbsp;${cl.standard_clause} \u2192 ISO 13485 ${cl.iso_13485_clause}<br>`;
                    }
                }
                appendSystemMessage(html);
            } catch (err) {
                showToast(t('toast.standardsFailed', {msg: err.message}), "error");
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
                    `<span style="color:#e74c3c">✗ ${t('ui.formatError')}</span><br>` +
                    `<code>/adjust &lt;standard_id&gt; "&lt;clause_name&gt;" &lt;old_clause&gt; -&gt; &lt;new_clause&gt;</code><br>` +
                    `${t('ui.example')}: <code>/adjust ISO_14971 "Clause 4 (Risk management process)" 7.1 -> 7.3.3</code>`
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
                showToast(t('toast.adjustFailed', {msg: err.message}), "error");
            }
            return true;
        }

        // ---- /download <type> <format> ----
        if (cmd === "/download") {
            return handleDownloadCommand(parts, 'crossexam');
        }

        // ---- /downloads — show download catalog ----
        if (cmd === "/downloads") {
            renderDownloadCatalog('crossexam');
            togglePopup('crossexamDownloads');
            return true;
        }

        // ---- /feedback ----
        if (cmd === "/feedback") {
            return await handleFeedbackCommand(message, 'crossexam');
        }

        // ---- /run audit | /run meta ----
        if (cmd === "/run") {
            const target = (parts[1] || '').toLowerCase();
            if (target === 'audit') {
                runDailyAudit();
                return true;
            } else if (target === 'meta') {
                runMetaReview();
                return true;
            }
            appendSystemMessage(`<span style="color:#e74c3c">✗ ${t('toast.unknownTarget')}</span>`);
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
    // Deep Report Export
    // ============================================================

    function exportDeepReport(format) {
        const url = `${API_BASE}/${RUN_ID}/export/deep_${format}`;
        showToast(t('toast.exportingDeep', {fmt: format.toUpperCase()}), "info");
        const a = document.createElement("a");
        a.href = url;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }


    // ============================================================
    // Cross-Exam History
    // ============================================================

    async function loadCrossexamHistory() {
        const listEl = document.getElementById('historyList');
        const countEl = document.getElementById('historyCount');
        const metaBtn = document.getElementById('btnRunMetaAnalysis');
        if (!listEl) return;

        listEl.innerHTML = '<div class="loading-cell">' + t('table.loading') + '</div>';

        try {
            const data = await apiFetch('/crossexam/history');
            const records = data.records || [];
            countEl.textContent = t('history.recordCount', {n: records.length});

            if (metaBtn) {
                metaBtn.disabled = !data.needs_meta_analysis;
                if (data.needs_meta_analysis) {
                    metaBtn.title = t('history.canRunQuality');
                }
            }

            if (records.length === 0) {
                listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📜</div><div class="empty-state-text">' + t('history.noCrossExamRecords') + '</div></div>';
                return;
            }

            listEl.innerHTML = records.map(r => {
                const isDaily = r.source === 'daily';
                const sourceTag = isDaily
                    ? `<span class="badge badge-daily">📅 ${t('history.dailySampling')}</span>`
                    : '<span class="badge badge-pipeline">⚙️ Pipeline P5</span>';
                const scoreHtml = isDaily && r.overall_score !== undefined
                    ? `<div class="record-scores" style="margin-top:4px">
                        <span>📜 Dim A: ${r.dim_a_score}/100</span>
                        <span>💬 Dim B: ${r.dim_b_score}/100</span>
                        <span style="font-weight:600">${t('card.overallScore')}: ${r.overall_score}/100</span>
                       </div>`
                    : '';
                const sampleInfo = isDaily && r.sample_rate
                    ? `<div class="record-sample" style="font-size:0.8rem;color:#64748b;margin-top:2px">${t('history.sampleRate')}: ${Math.round(r.sample_rate * 100)}% | MDSAP: ${r.mdsap_enabled ? '✅ ' + t('ui.enabled') : '❌ ' + t('ui.disabled')}</div>`
                    : '';
                return `
                <div class="history-record-card${isDaily ? ' daily-source' : ''}">
                    <div class="history-record-header">
                        <span class="record-id">📌 ${r.record_id}</span>
                        ${sourceTag}
                        <span class="record-time">${r.timestamp ? r.timestamp.substring(0, 19) : ''}</span>
                    </div>
                    <div class="history-record-body">
                        <div class="record-stats">
                            <span>📋 ${t('table.clause')}: ${r.total_clauses}</span>
                            <span>✅ ${t('ui.agreed')}: ${r.total_agreed}</span>
                            <span>⚠️ RA: ${r.total_flagged}</span>
                            <span>🔄 ${t('ui.rounds')}: ${r.total_rounds}</span>
                        </div>
                        ${scoreHtml}
                        <div class="record-regs">${t('crossref.lblRef')}: ${(r.selected_regulations || []).join(', ') || '—'}</div>
                        <div class="record-countries">${t('crossref.selectCountries')}: ${(r.countries || []).join(', ') || '—'}</div>
                        ${sampleInfo}
                    </div>
                    <div class="history-record-actions">
                        <button class="btn btn-sm btn-outline" onclick="window.__report.exportHistoryRecord('${r.record_id}', 'word')">📄 Word</button>
                        <button class="btn btn-sm btn-outline" onclick="window.__report.exportHistoryRecord('${r.record_id}', 'excel')">📊 Excel</button>
                    </div>
                </div>`;
            }).join('');

        } catch (e) {
            listEl.innerHTML = `<div class="error-state">❗ ${t('toast.loadFailed', {msg: e.message || e})}</div>`;
        }
    }

    function exportHistoryRecord(recordId, format) {
        const url = `${API_BASE}/crossexam/history/${recordId}/export/${format}`;
        showToast(t('toast.exportingCrossexam', {fmt: format.toUpperCase()}), "info");
        const a = document.createElement("a");
        a.href = url;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }


    // ============================================================
    // Meta-Analysis
    // ============================================================

    async function loadMetaAnalysis() {
        const section = document.getElementById('metaAnalysisSection');
        const content = document.getElementById('metaAnalysisContent');
        if (!section || !content) return;

        section.style.display = 'block';
        content.innerHTML = '<div class="loading-cell">' + t('ui.loadingQualityAnalysis') + '</div>';

        try {
            const data = await apiFetch('/crossexam/meta-analysis');
            if (!data.available) {
                content.innerHTML = '<div class="empty-state-text">' + t('ui.noQualityAnalysis') + '</div>';
                return;
            }

            const resp = data.llm_response || {};
            const score = resp.quality_score || 0;
            const scoreColor = score >= 0.7 ? '#27ae60' : score >= 0.4 ? '#f39c12' : '#e74c3c';
            const findings = resp.findings || [];
            const recommendations = resp.recommendations || [];
            const tuning = resp.prompt_tuning || {};

            content.innerHTML = `
                <div class="meta-summary">
                    <div class="meta-score" style="border-color: ${scoreColor}">
                        <div class="score-value" style="color: ${scoreColor}">${(score * 100).toFixed(0)}</div>
                        <div class="score-label">${t('ui.qualityScore')}</div>
                    </div>
                    <div class="meta-text">${resp.summary || t('ui.noSummary')}</div>
                </div>
                ${findings.length ? `<h4>🔍 ${t('ui.findings')}</h4><ul>${findings.map(f => `
                    <li class="finding finding-${f.severity || 'low'}">
                        <strong>[${f.severity || ''}]</strong> ${f.description || ''}
                        ${f.recommendation ? `<br><em>${t('ui.recommendation')}: ${f.recommendation}</em>` : ''}
                    </li>
                `).join('')}</ul>` : ''}
                ${recommendations.length ? `<h4>💡 ${t('ui.recommendations')}</h4><ul>${recommendations.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
                ${Object.keys(tuning).length ? `<h4>🔧 ${t('ui.promptTuning')}</h4><ul>${Object.entries(tuning).map(([k, v]) => `<li><strong>${k}</strong>: ${v}</li>`).join('')}</ul>` : ''}
            `;

        } catch (e) {
            content.innerHTML = `<div class="error-state">❗ ${t('toast.loadFailed', {msg: e.message || e})}</div>`;
        }
    }

    function exportMetaAnalysis(format) {
        const url = `${API_BASE}/crossexam/meta-analysis/export/${format}`;
        showToast(t('toast.exportingQuality', {fmt: format.toUpperCase()}), "info");
        const a = document.createElement("a");
        a.href = url;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    // ============================================================
    // Daily Audit Tab
    // ============================================================

    async function loadDailyAuditHistory() {
        if (!els.dailyAuditHistory) return;
        els.dailyAuditHistory.innerHTML = '<div class="loading-cell">' + t('ui.loadingAuditHistory') + '</div>';

        try {
            const data = await apiFetch('/daily-audit/history');
            const records = data.records || [];
            if (els.dailyAuditCount) els.dailyAuditCount.textContent = t('history.recordCount', {n: records.length});

            // Enable meta review button if >= 10 records
            if (els.btnRunMetaReview && records.length >= 10) {
                els.btnRunMetaReview.disabled = false;
                els.btnRunMetaReview.title = '';
            }

            if (records.length === 0) {
                els.dailyAuditHistory.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">🔍</div>
                        <div class="empty-state-text">${t('audit.empty')}</div>
                    </div>`;
                return;
            }

            // Show most recent result in summary cards
            const latest = records[0];
            showAuditSummary(latest);

            // Check for deviations
            if (latest.deviation_detected) {
                showDeviationAlert(latest);
            }

            // Render history list
            let html = '<div class="history-records">';
            for (const r of records) {
                const scoreColor = r.overall_score >= 80 ? '#27ae60' : r.overall_score >= 60 ? '#f39c12' : '#e74c3c';

                let qaLine = '';
                if (r.sampling_details && r.sampling_details.clauses_audited) {
                    const sd = r.sampling_details;
                    const qaAvg = sd.avg_qa_score || 0;
                    const qaColor = qaAvg >= 80 ? '#27ae60' : qaAvg >= 60 ? '#f39c12' : '#e74c3c';
                    const halCount = sd.hallucinations_found || 0;
                    qaLine = `<div class="record-scores" style="margin-top:2px">
                        <span>🔎 ${t('qa.title')}: ${sd.clauses_audited} ${t('qa.clausesAudited')}</span>
                        <span style="color:${qaColor}">${t('qa.avgScore')}: ${qaAvg.toFixed(0)}/100</span>
                        ${halCount > 0 ? `<span class="qa-hallucination">🚨 ${halCount}</span>` : ''}
                    </div>`;
                }

                html += `
                    <div class="history-record-card">
                        <div class="record-header">
                            <span class="record-date">📅 ${r.audit_date || r.timestamp || ''}</span>
                            <span class="record-score" style="color:${scoreColor}">${t('card.overallScore')}: ${r.overall_score}/100</span>
                        </div>
                        <div class="record-scores">
                            <span>📜 ${t('card.dimA')}: ${r.dim_a_score}/100</span>
                            <span>💬 ${t('card.dimB')}: ${r.dim_b_score}/100</span>
                        </div>
                        ${qaLine}
                        ${r.deviation_detected ? '<div class="record-deviation">⚠️ ' + t('audit.deviationTitle') + ': ' + (r.deviation_details || '') + '</div>' : ''}
                        <div class="record-actions">
                            <button class="btn btn-outline btn-sm" onclick="window.__report.exportAuditRecord('${r.audit_id}', 'word')">📄 Word</button>
                            <button class="btn btn-outline btn-sm" onclick="window.__report.exportAuditRecord('${r.audit_id}', 'excel')">📊 Excel</button>
                        </div>
                    </div>`;
            }
            html += '</div>';
            els.dailyAuditHistory.innerHTML = html;

            // Load meta review if available
            await loadLatestMetaReview();

        } catch (e) {
            els.dailyAuditHistory.innerHTML = `<div class="error-state">❍ ${t('toast.loadFailed', {msg: e.message || e})}</div>`;
        }
    }

    function showAuditSummary(result) {
        if (!els.dailyAuditSummary) return;
        els.dailyAuditSummary.style.display = 'flex';
        if (els.auditOverallScore) els.auditOverallScore.textContent = result.overall_score || '—';
        if (els.auditDimAScore) els.auditDimAScore.textContent = result.dim_a_score || '—';
        if (els.auditDimBScore) els.auditDimBScore.textContent = result.dim_b_score || '—';
    }

    function showDeviationAlert(result) {
        if (!els.deviationAlertBanner) return;
        els.deviationAlertBanner.style.display = 'flex';
        if (els.deviationAlertTitle) {
            els.deviationAlertTitle.textContent = t('audit.deviationTitle');
        }
        if (els.deviationAlertDetails) {
            els.deviationAlertDetails.innerHTML = `
                <p>${result.deviation_details || t('ui.deviationDefault')}</p>
                <p>${t('ui.deviationAdjust')}</p>
            `;
        }
    }

    async function runDailyAudit() {
        if (els.btnRunDailyAudit) els.btnRunDailyAudit.disabled = true;
        showToast(t('toast.auditRunning'), 'info');

        try {
            const result = await apiPost('/daily-audit/run', {});
            showToast(t('toast.auditDone', {score: result.overall_score}), 'success');
            showAuditSummary(result);
            if (result.deviation_detected) {
                showDeviationAlert(result);
            }
            // Reload history
            await loadDailyAuditHistory();
        } catch (e) {
            showToast(t('toast.auditFailed', {msg: e.message || e}), 'error');
        } finally {
            if (els.btnRunDailyAudit) els.btnRunDailyAudit.disabled = false;
        }
    }

    async function runMetaReview() {
        if (els.btnRunMetaReview) els.btnRunMetaReview.disabled = true;
        showToast(t('toast.metaRunning'), 'info');

        try {
            const result = await apiPost('/daily-audit/meta-review', {});
            showToast(t('toast.metaDone'), 'success');
            renderMetaReview(result);
        } catch (e) {
            showToast(t('toast.metaFailed', {msg: e.message || e}), 'error');
        } finally {
            if (els.btnRunMetaReview) els.btnRunMetaReview.disabled = false;
        }
    }

    async function loadLatestMetaReview() {
        try {
            const data = await apiFetch('/daily-audit/meta-review');
            if (data.available) {
                renderMetaReview(data);
            }
        } catch (e) {
            // Meta review not available yet — silent
        }
    }

    function renderMetaReview(data) {
        if (!els.metaReviewSection || !els.metaReviewContent) return;
        els.metaReviewSection.style.display = 'block';

        const avgA = data.avg_dim_a || 0;
        const avgB = data.avg_dim_b || 0;
        const trend = data.trend_analysis || {};
        const recommendations = data.recommendations || [];
        const summary = data.deviation_summary || '';

        els.metaReviewContent.innerHTML = `
            <div class="meta-summary">
                <div class="meta-score" style="border-color: ${avgA >= 80 ? '#27ae60' : '#f39c12'}">
                    <div class="score-value" style="color: ${avgA >= 80 ? '#27ae60' : '#f39c12'}">${avgA.toFixed(0)}</div>
                    <div class="score-label">${t('ui.avgDimA')}</div>
                </div>
                <div class="meta-score" style="border-color: ${avgB >= 80 ? '#27ae60' : '#f39c12'}">
                    <div class="score-value" style="color: ${avgB >= 80 ? '#27ae60' : '#f39c12'}">${avgB.toFixed(0)}</div>
                    <div class="score-label">${t('ui.avgDimB')}</div>
                </div>
            </div>
            ${summary ? `<div class="meta-text"><strong>${t('ui.deviationSummary')}:</strong> ${summary}</div>` : ''}
            ${trend.direction ? `<div class="meta-text"><strong>${t('ui.trend')}:</strong> ${trend.direction} (${trend.detail || ''})</div>` : ''}
            ${recommendations.length ? `<h4>💡 ${t('ui.recommendations')}</h4><ul>${recommendations.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
        `;
    }

    function exportDailyAudit(format) {
        const url = `${API_BASE}/daily-audit/export/${format}`;
        showToast(t('toast.exportingAudit', {fmt: format.toUpperCase()}), 'info');
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    function exportMetaReviewReport(format) {
        const url = `${API_BASE}/daily-audit/meta-review/export/${format}`;
        showToast(t('toast.exportingMetaReview', {fmt: format.toUpperCase()}), 'info');
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    function exportAuditRecord(auditId, format) {
        const url = `${API_BASE}/daily-audit/history/${auditId}/export/${format}`;
        showToast(t('toast.exportingAuditRecord', {fmt: format.toUpperCase()}), 'info');
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }


    // ============================================================
    // Unified Command Bar Logic
    // ============================================================

    // ---- Popup management ----
    const popupMap = {
        crossrefHelp:      () => els.crossrefHelpPopup,
        crossrefDownloads: () => els.crossrefDownloadCatalog,
        crossrefFeedback:  () => els.crossrefFeedbackHistory,
        crossexamHelp:     () => els.crossexamHelpPopup,
        crossexamDownloads:() => els.crossexamDownloadCatalog,
        crossexamFeedback: () => els.crossexamFeedbackHistory,
    };

    function togglePopup(name) {
        const el = popupMap[name] && popupMap[name]();
        if (!el) return;
        // Close all sibling popups first
        const prefix = name.startsWith('crossref') ? 'crossref' : 'crossexam';
        Object.keys(popupMap).forEach(k => {
            if (k.startsWith(prefix) && k !== name) {
                const other = popupMap[k]();
                if (other) other.style.display = 'none';
            }
        });
        el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }

    function closePopup(name) {
        const el = popupMap[name] && popupMap[name]();
        if (el) el.style.display = 'none';
    }

    // ---- Crossref command dispatch ----
    async function sendCrossrefCommand() {
        const input = els.crossrefCommandInput;
        if (!input) return;
        const message = input.value.trim();
        if (!message) return;

        if (message.startsWith('/')) {
            const parts = message.split(/\s+/);
            const cmd = parts[0].toLowerCase();

            if (cmd === '/help') {
                togglePopup('crossrefHelp');
                input.value = '';
                return;
            }
            if (cmd === '/downloads') {
                renderDownloadCatalog('crossref');
                togglePopup('crossrefDownloads');
                input.value = '';
                return;
            }
            if (cmd === '/download') {
                handleDownloadCommand(parts, 'crossref');
                input.value = '';
                return;
            }
            if (cmd === '/feedback') {
                await handleFeedbackCommand(message, 'crossref');
                input.value = '';
                return;
            }
            if (cmd === '/run') {
                const target = (parts[1] || '').toLowerCase();
                if (target === 'audit') { runDailyAudit(); }
                else if (target === 'meta') { runMetaReview(); }
                else { showToast(t('toast.unknownTarget'), 'error'); }
                input.value = '';
                return;
            }
            if (cmd === '/standards') {
                // Delegate to existing handler via crossexam
                try {
                    const resp = await fetch('/api/report/standards/list');
                    const data = await resp.json();
                    let msg = `${t('cmd.opt.standards')} (${data.standards.length}):\n`;
                    for (const std of data.standards) {
                        msg += `\n${std.name_zh} (${std.standard_id})\n`;
                        for (const cl of std.clause_links) {
                            msg += `  ${cl.standard_clause} \u2192 ISO 13485 ${cl.iso_13485_clause}\n`;
                        }
                    }
                    showToast(msg, 'info', 8000);
                } catch (err) {
                    showToast(t('toast.standardsFailed', {msg: err.message}), 'error');
                }
                input.value = '';
                return;
            }
            // Unrecognized command
            showToast(t('toast.unknownCommand', {cmd: cmd}), 'error');
            input.value = '';
            return;
        }

        // Not a command — treat as general feedback for daily audit
        showToast(t('toast.feedbackHint'), 'info');
        input.value = '';
    }

    // ---- Download command handler ----
    function handleDownloadCommand(parts, tab) {
        const type = (parts[1] || '').toLowerCase();
        const format = (parts[2] || 'word').toLowerCase();
        if (!['word', 'excel'].includes(format)) {
            showToast(t('toast.formatError'), 'error');
            return true;
        }
        const downloadMap = {
            report:    () => exportReport(format),
            deep:      () => exportDeepReport(format),
            audit:     () => exportDailyAudit(format),
            meta:      () => exportMetaReviewReport(format),
            crossexam: () => {
                // Download latest crossexam quality analysis
                const url = `${API_BASE}/crossexam/meta-analysis/export/${format}`;
                triggerDownload(url, `${t('dl.qualityReport')} (${format.toUpperCase()})`);
            },
            quality:   () => exportMetaAnalysis(format),
            feedback:  () => {
                // Download feedback records (reuse daily audit export as it includes feedback)
                const url = `${API_BASE}/daily-audit/feedback/export/${format}`;
                triggerDownload(url, `${t('dl.feedbackReport')} (${format.toUpperCase()})`);
            },
        };
        const fn = downloadMap[type];
        if (fn) {
            fn();
        } else {
            showToast(t('toast.unknownDownloadType', {type: type}), 'error');
        }
        return true;
    }

    function triggerDownload(url, label) {
        showToast(t('toast.downloading', {label: label}), 'info');
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    // ---- Feedback command handler ----
    async function handleFeedbackCommand(message, tab) {
        const parts = message.split(/\s+/);
        const subCmd = (parts[1] || '').toLowerCase();

        if (subCmd === 'history') {
            await loadFeedbackHistory(tab);
            togglePopup(tab === 'crossref' ? 'crossrefFeedback' : 'crossexamFeedback');
            return true;
        }

        if (subCmd === 'daily' || subCmd === 'meta') {
            // Extract text in quotes
            const textMatch = message.match(/"([^"]+)"/);
            if (!textMatch) {
                showToast(t('toast.feedbackFormat'), 'error');
                return true;
            }
            const feedbackText = textMatch[1];
            const auditType = subCmd;

            showToast(t('toast.feedbackSubmitting'), 'info');
            try {
                const result = await apiPost('/daily-audit/feedback', {
                    audit_type: auditType,
                    feedback_text: feedbackText,
                });
                if (result.re_evaluation) {
                    const reeval = result.re_evaluation;
                    showToast(
                        t('toast.feedbackReEvalSuccess', {score: auditType === 'daily' ? reeval.overall_score : `Dim A: ${reeval.avg_dim_a}, Dim B: ${reeval.avg_dim_b}`}),
                        'success'
                    );
                    // Refresh audit history if visible
                    if (document.querySelector('.tab-content[data-tab="dailyaudit"].active')) {
                        await loadDailyAuditHistory();
                    }
                } else {
                    showToast(t('toast.feedbackSaved'), 'info');
                }
            } catch (err) {
                showToast(t('toast.feedbackFailed', {msg: err.message}), 'error');
            }
            return true;
        }

        showToast(t('toast.feedbackUsage'), 'error');
        return true;
    }

    // ---- Feedback CRUD ----
    async function loadFeedbackHistory(tab) {
        const listEl = tab === 'crossref' ? els.crossrefFeedbackList : els.crossexamFeedbackList;
        if (!listEl) return;
        listEl.innerHTML = '<div class="empty-state-text">' + t('table.loading') + '</div>';

        try {
            const data = await apiFetch('/daily-audit/feedback');
            const records = data.records || [];
            if (records.length === 0) {
                listEl.innerHTML = '<div class="empty-state-text">' + t('ui.noFeedbackRecords') + '</div>';
                return;
            }
            listEl.innerHTML = records.map(fb => `
                <div class="feedback-record" data-id="${fb.feedback_id}">
                    <div class="feedback-record-header">
                        <span class="feedback-record-type">${fb.audit_type === 'daily' ? '📝 ' + t('audit.run') : '🧠 ' + t('audit.metaReview')}</span>
                        <span class="feedback-record-date">${fb.created_at ? fb.created_at.substring(0, 19) : ''}</span>
                    </div>
                    <div class="feedback-record-text">${escapeHtml(fb.feedback_text)}</div>
                    ${fb.re_evaluation_score != null ? `<div class="feedback-record-score">${t('ui.reEvalScore')}: ${fb.re_evaluation_score}</div>` : ''}
                    <div class="feedback-record-actions">
                        <button class="btn btn-sm btn-outline" onclick="window.__report.editFeedback('${fb.feedback_id}', '${tab}')">✂ ${t('ui.edit')}</button>
                        <button class="btn btn-sm btn-outline" onclick="window.__report.deleteFeedback('${fb.feedback_id}', '${tab}')" style="color:var(--non-compliant)">🗑 ${t('ui.delete')}</button>
                    </div>
                </div>
            `).join('');
        } catch (err) {
            listEl.innerHTML = `<div class="error-state">❗ ${t('toast.loadFailed', {msg: err.message})}</div>`;
        }
    }

    async function editFeedback(feedbackId, tab) {
        const newText = prompt(t('ui.enterNewFeedback'));
        if (!newText) return;
        try {
            const resp = await fetch(`${API_BASE}/daily-audit/feedback/${feedbackId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ feedback_text: newText }),
            });
            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${resp.status}`);
            }
            showToast(t('toast.feedbackUpdated'), 'success');
            await loadFeedbackHistory(tab);
        } catch (err) {
            showToast(t('toast.feedbackUpdateFailed', {msg: err.message}), 'error');
        }
    }

    async function deleteFeedback(feedbackId, tab) {
        if (!confirm(t('confirm.deleteFeedback'))) return;
        try {
            const resp = await fetch(`${API_BASE}/daily-audit/feedback/${feedbackId}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${resp.status}`);
            }
            showToast(t('toast.feedbackDeleted'), 'success');
            await loadFeedbackHistory(tab);
        } catch (err) {
            showToast(t('toast.feedbackDeleteFailed', {msg: err.message}), 'error');
        }
    }

    // escapeHtml defined above (line ~925) — single implementation

    // ---- Download catalog renderer ----
    function getDownloadCatalog() {
        const t = window.__i18n ? window.__i18n.t : (k) => k;
        return [
            { name: t('dl.complianceReport'), desc: t('dl.complianceDesc'), type: 'report', formats: ['word', 'excel'] },
            { name: t('dl.deepReport'), desc: t('dl.deepDesc'), type: 'deep', formats: ['word', 'excel'] },
            { name: t('dl.auditReport'), desc: t('dl.auditDesc'), type: 'audit', formats: ['word', 'excel'] },
            { name: t('dl.metaReport'), desc: t('dl.metaDesc'), type: 'meta', formats: ['word', 'excel'] },
            { name: t('dl.qualityReport'), desc: t('dl.qualityDesc'), type: 'quality', formats: ['word', 'excel'] },
            { name: t('dl.feedbackReport'), desc: t('dl.feedbackDesc'), type: 'feedback', formats: ['word', 'excel'] },
        ];
    }

    function renderDownloadCatalog(tab) {
        const listEl = tab === 'crossref' ? $('crossrefDownloadList') : $('crossexamDownloadList');
        if (!listEl) return;
        listEl.innerHTML = getDownloadCatalog().map(item => `
            <div class="download-catalog-item">
                <div class="download-item-info">
                    <div class="download-item-name">${item.name}</div>
                    <div class="download-item-desc">${item.desc}</div>
                </div>
                <div class="download-item-actions">
                    ${item.formats.map(fmt => `
                        <button class="btn btn-sm btn-outline" onclick="window.__report.cmdDownload('${item.type}', '${fmt}')">${fmt === 'word' ? '📄' : '📊'} ${fmt.toUpperCase()}</button>
                    `).join('')}
                </div>
            </div>
        `).join('');
    }

    function cmdDownload(type, format) {
        handleDownloadCommand(['', type, format], 'global');
    }


    // ============================================================
    // Phase Configuration Panel
    // ============================================================

    function initPhaseConfig() {
        if (!els.btnTogglePhaseConfig) return;

        els.btnTogglePhaseConfig.addEventListener("click", function () {
            var body = els.phaseConfigBody;
            var isHidden = body.style.display === "none";
            body.style.display = isHidden ? "block" : "none";
            this.textContent = isHidden
                ? "\u25B2 " + t("phase.collapseBtn", null, "\u6536\u5408")
                : "\u25BC " + t("phase.toggleBtn", null, "\u5C55\u958B");
        });

        var checkboxes = els.phaseConfigGrid.querySelectorAll('input[type="checkbox"]:not([disabled])');
        checkboxes.forEach(function (cb) {
            cb.addEventListener("change", updatePhaseConfigSummary);
        });

        if (els.btnApplyPhaseConfig) {
            els.btnApplyPhaseConfig.addEventListener("click", applyPhaseConfig);
        }
        if (els.btnResetPhaseConfig) {
            els.btnResetPhaseConfig.addEventListener("click", resetPhaseConfig);
        }
    }

    function updatePhaseConfigSummary() {
        var checkboxes = els.phaseConfigGrid.querySelectorAll('input[type="checkbox"]:not([disabled])');
        var skipped = [];
        checkboxes.forEach(function (cb) {
            if (cb.checked) {
                skipped.push(cb.getAttribute("data-phase"));
            }
        });
        phaseSkipConfig = skipped;

        if (skipped.length === 0) {
            els.phaseConfigSummary.textContent = t("phase.noSkip", null, "\u76EE\u524D\u8A2D\u5B9A\uFF1A\u57F7\u884C\u6240\u6709\u968E\u6BB5");
        } else {
            var phaseLabels = skipped.map(function (p) {
                var input = els.phaseConfigGrid.querySelector('input[data-phase="' + p + '"]');
                if (!input) return p;
                var item = input.closest(".phase-config-item");
                var nameEl = item ? item.querySelector(".phase-config-name") : null;
                return nameEl ? nameEl.textContent : p;
            });
            els.phaseConfigSummary.textContent =
                "\u5C07\u8DF3\u904E " + skipped.length + " \u500B\u968E\u6BB5\uFF1A" + phaseLabels.join("\u3001");
        }
    }

    function applyPhaseConfig() {
        apiPost("/phase-config", { skip_phases: phaseSkipConfig })
            .then(function () {
                showToast(t("phase.applySuccess", null, "\u968E\u6BB5\u8A2D\u5B9A\u5DF2\u5957\u7528"), "success");
                els.phaseConfigBody.style.display = "none";
                els.btnTogglePhaseConfig.textContent = "\u25BC " + t("phase.toggleBtn", null, "\u5C55\u958B");
                els.phaseConfigPanel.style.borderColor = "var(--partial)";
                setTimeout(function () { els.phaseConfigPanel.style.borderColor = ""; }, 2000);
            })
            .catch(function (e) {
                showToast(t("phase.applyError", null, "\u5957\u7528\u5931\u6557") + ": " + (e.message || e), "error");
            });
    }

    function resetPhaseConfig() {
        var checkboxes = els.phaseConfigGrid.querySelectorAll('input[type="checkbox"]:not([disabled])');
        checkboxes.forEach(function (cb) { cb.checked = false; });
        phaseSkipConfig = [];
        updatePhaseConfigSummary();
        apiPost("/phase-config", { skip_phases: [] }).catch(function () {});
    }

    // ============================================================
    // Init
    // ============================================================

    async function init() {
        if (window.__i18n) {
            await window.__i18n.init();
        }
        bindEvents();
        initPhaseConfig();
        loadReport();
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
