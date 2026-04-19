/**
 * AI-QMS Report — Internationalization (i18n)
 * =============================================
 *
 * Translations are loaded dynamically from the server's locale JSON files.
 * To add a new language: create src/chainlit_app/locales/<lang>.json —
 * the report page will automatically use it.
 *
 * Usage:
 *   window.__i18n.t('key')        — get translated string
 *   window.__i18n.t('key', {n:5}) — with interpolation: "共 {n} 筆" → "共 5 筆"
 *   window.__i18n.applyAll()      — apply translations to all [data-i18n] elements
 *   window.__i18n.lang            — current language code
 */

(function () {
    "use strict";

    const DEFAULT_LANG = "en-US";

    // In-memory cache: lang code → translations dict
    const _cache = {};

    // Current language and translations
    let currentLang = DEFAULT_LANG;
    let currentDict = {};

    // ── Core helpers ──

    async function _fetchTranslations(lang) {
        if (_cache[lang]) return _cache[lang];
        try {
            const resp = await fetch(`/api/report/i18n/translations/${encodeURIComponent(lang)}`);
            if (resp.ok) {
                const data = await resp.json();
                _cache[lang] = data;
                return data;
            }
        } catch (_) {}
        return null;
    }

    /**
     * Translate a key with optional interpolation.
     * @param {string} key — dot-notation key like 'toast.loadFailed'
     * @param {Object} [params] — interpolation values: {msg: 'err'} replaces {msg}
     * @returns {string}
     */
    function t(key, params) {
        let str = currentDict[key];
        if (str === undefined) return key;
        if (params) {
            for (const [k, v] of Object.entries(params)) {
                str = str.replace(new RegExp("\\{" + k + "\\}", "g"), v);
            }
        }
        return str;
    }

    /**
     * Apply translations to all elements with [data-i18n] attribute.
     */
    function applyAll() {
        document.querySelectorAll("[data-i18n]").forEach(function (el) {
            const key = el.getAttribute("data-i18n");
            if (key) el.textContent = t(key);
        });
        document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
            const key = el.getAttribute("data-i18n-placeholder");
            if (key) el.placeholder = t(key);
        });
        document.querySelectorAll("[data-i18n-title]").forEach(function (el) {
            const key = el.getAttribute("data-i18n-title");
            if (key) el.title = t(key);
        });
        document.title = t("page.title") !== "page.title" ? t("page.title") : document.title;
    }

    /**
     * Set language, load translations, and re-apply all translations.
     * @param {string} lang — language code like 'en-US', 'ja-JP', 'zh-TW'
     * @returns {Promise<void>}
     */
    async function setLang(lang) {
        // Normalize zh-CN → zh-TW for report page
        if (lang && lang.startsWith("zh") && lang !== "zh-TW") {
            lang = "zh-TW";
        } else if (!lang) {
            lang = DEFAULT_LANG;
        }

        const dict = await _fetchTranslations(lang);
        if (dict && Object.keys(dict).length > 0) {
            currentLang = lang;
            currentDict = dict;
        } else if (lang !== DEFAULT_LANG) {
            // Fallback to DEFAULT_LANG
            const fallback = await _fetchTranslations(DEFAULT_LANG);
            currentLang = DEFAULT_LANG;
            currentDict = fallback || {};
        }
        applyAll();
    }

    /**
     * Initialize: use URL ?lang= param first (injected by app.py), fall back to API.
     */
    async function init() {
        const urlLang = new URLSearchParams(window.location.search).get("lang");
        const targetLang = urlLang || DEFAULT_LANG;

        // Pre-load DEFAULT_LANG into cache for fallback
        if (targetLang !== DEFAULT_LANG) {
            _fetchTranslations(DEFAULT_LANG); // fire and forget — warms cache
        }

        if (urlLang) {
            await setLang(urlLang);
            return;
        }

        // Fallback: fetch from Chainlit user settings
        try {
            const resp = await fetch("/api/report/user/language");
            if (resp.ok) {
                const data = await resp.json();
                await setLang(data.language || DEFAULT_LANG);
                return;
            }
        } catch (_) {}

        await setLang(DEFAULT_LANG);
    }

    // ── Expose API ──
    window.__i18n = {
        t: t,
        setLang: setLang,
        applyAll: applyAll,
        init: init,
        get lang() { return currentLang; },
    };
})();
