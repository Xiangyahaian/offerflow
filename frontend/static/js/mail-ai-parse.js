/**
 * 邮箱读取页 · 模型配置 + 邮箱解析浮窗
 */
(function () {
    'use strict';

    var PROVIDERS = [];
    var SETTINGS = null;
    var MAIL_INSIGHTS = [];
    var MAIL_DOCK_OPEN = false;
    var ACTIVE_MAIL_DETAIL_ID = null;

    function $(id) {
        return document.getElementById(id);
    }

    function toast(msg, type) {
        if (typeof window.toast === 'function') window.toast(msg, type || 'info');
    }

    function api(url, opts) {
        if (typeof window.api === 'function') return window.api(url, opts || {});
        return Promise.reject(new Error('api 不可用'));
    }

    function escHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function simpleMarkdown(raw) {
        if (!raw) return '';
        var s = escHtml(raw);
        s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/\n\n/g, '</p><p>');
        s = s.replace(/\n/g, '<br>');
        return '<p>' + s + '</p>';
    }

    function categoryLabel(cat) {
        var m = {
            recruit: '招聘',
            interview: '面试',
            offer: 'Offer',
            notice: '通知',
            general: '邮件',
        };
        return m[cat] || '邮件';
    }

    function openConfig() {
        var backdrop = $('icConfigBackdrop');
        var panel = $('icConfigPanel');
        if (!backdrop || !panel) return;
        backdrop.classList.add('is-open');
        panel.classList.add('is-open');
        panel.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
    }

    function closeConfig() {
        var backdrop = $('icConfigBackdrop');
        var panel = $('icConfigPanel');
        if (!backdrop || !panel) return;
        backdrop.classList.remove('is-open');
        panel.classList.remove('is-open');
        panel.setAttribute('aria-hidden', 'true');
        var mailPanel = $('mailSettingsPanel');
        if (!mailPanel || !mailPanel.classList.contains('is-open')) {
            document.body.style.overflow = '';
        }
    }

    function markAllMailInsightsRead() {
        MAIL_INSIGHTS.forEach(function (it) {
            if (it.is_parsed) it.is_read = true;
        });
        updateMailBadges(0);
        renderMailDockList();
        if (window.OfferFlowIvory && window.OfferFlowIvory.markAllIvoryInsightsRead) {
            window.OfferFlowIvory.markAllIvoryInsightsRead();
            return;
        }
        api('/api/ai-assistant/insights/read-all', { method: 'POST' }).catch(function () {});
    }

    function applyIvoryUnreadFromServer(count, items) {
        var unreadKeys = {};
        (items || []).forEach(function (it) {
            if (it && it.mail_slot != null && it.mail_seq != null) {
                unreadKeys[String(it.mail_slot) + ':' + String(it.mail_seq)] = true;
            }
        });
        if (typeof count === 'number') {
            if (count === 0) {
                MAIL_INSIGHTS.forEach(function (it) {
                    if (it.is_parsed) it.is_read = true;
                });
            } else if (items && items.length) {
                MAIL_INSIGHTS.forEach(function (it) {
                    var key = String(it.mail_slot) + ':' + String(it.mail_seq);
                    if (it.is_parsed) it.is_read = !unreadKeys[key];
                });
            }
        }
        updateMailBadges(typeof count === 'number' ? count : undefined);
        if (MAIL_DOCK_OPEN) renderMailDockList();
    }

    function isMailDockOpen() {
        var dock = $('icMailDock');
        return MAIL_DOCK_OPEN || !!(dock && dock.classList.contains('is-open'));
    }

    function syncMailDockTriggerState(open) {
        var btn = $('icMailFab');
        if (!btn) return;
        btn.classList.toggle('is-active', !!open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function openMailDock() {
        if (isMailDockOpen()) return;
        MAIL_DOCK_OPEN = true;
        var dock = $('icMailDock');
        if (!dock) return;
        markAllMailInsightsRead();
        dock.classList.add('is-open');
        dock.setAttribute('aria-hidden', 'false');
        syncMailDockTriggerState(true);
        renderMailDockList();
        requestAnimationFrame(function () {
            var panel = dock.querySelector('.ic-mail-dock__panel');
            if (panel) panel.classList.add('is-visible');
        });
    }

    function closeMailDock() {
        if (!isMailDockOpen()) return;
        MAIL_DOCK_OPEN = false;
        var dock = $('icMailDock');
        if (!dock) return;
        var panel = dock.querySelector('.ic-mail-dock__panel');
        if (panel) panel.classList.remove('is-visible');
        dock.classList.remove('is-open');
        dock.setAttribute('aria-hidden', 'true');
        syncMailDockTriggerState(false);
        hideMailDetail();
    }

    function toggleMailDock() {
        if (isMailDockOpen()) closeMailDock();
        else openMailDock();
    }

    function hideMailDetail() {
        ACTIVE_MAIL_DETAIL_ID = null;
        var list = $('icMailDockList');
        var detail = $('icMailDockDetail');
        if (list) list.hidden = false;
        if (detail) detail.hidden = true;
        renderMailDockList();
    }

    function fillMailDetailBody(it) {
        var body = $('icMailDetailBody');
        if (!body || !it) return;
        body.innerHTML =
            '<div class="ic-mail-detail__tag">' +
            escHtml(categoryLabel(it.category)) +
            '</div>' +
            '<h4 class="ic-mail-detail__subject">' +
            escHtml(it.subject || '(无主题)') +
            '</h4>' +
            '<p class="ic-mail-detail__from">' +
            escHtml(it.from_addr || '') +
            '</p>' +
            '<div class="ic-mail-detail__summary">' +
            simpleMarkdown(it.summary || '') +
            '</div>';
    }

    function showMailDetail(id) {
        var it = MAIL_INSIGHTS.find(function (x) {
            return x.id === id;
        });
        if (!it) return;
        ACTIVE_MAIL_DETAIL_ID = id;
        var list = $('icMailDockList');
        var detail = $('icMailDockDetail');
        if (!list || !detail) return;
        list.hidden = true;
        detail.hidden = false;
        fillMailDetailBody(it);
        api('/api/ai-assistant/insights/open', { method: 'POST', body: { insight_id: id } })
            .then(function (r) {
                if (r && r.insight) {
                    var idx = MAIL_INSIGHTS.findIndex(function (x) {
                        return x.id === id;
                    });
                    if (idx >= 0) MAIL_INSIGHTS[idx] = r.insight;
                    it = r.insight;
                    if (ACTIVE_MAIL_DETAIL_ID === id) fillMailDetailBody(it);
                } else {
                    it.is_read = true;
                }
                updateMailBadges();
                renderMailDockList();
            })
            .catch(function () {});
    }

    function updateMailBadges(serverCount) {
        var unread =
            typeof serverCount === 'number'
                ? Math.max(0, serverCount)
                : MAIL_INSIGHTS.filter(function (x) {
                      return x.is_parsed && !x.is_read;
                  }).length;
        if (window.OfferFlowIvory && window.OfferFlowIvory.syncIcMailDockBadges) {
            window.OfferFlowIvory.syncIcMailDockBadges(unread);
            return;
        }
        var fab = $('icMailFabBadge');
        if (fab) {
            if (unread > 0) {
                fab.hidden = false;
                fab.textContent = unread > 99 ? '99+' : String(unread);
            } else {
                fab.hidden = true;
            }
        }
        var fabBtn = $('icMailFab');
        if (fabBtn) fabBtn.classList.toggle('has-unread', unread > 0);
    }

    function fillProviderSelect() {
        var sel = $('icProvider');
        if (!sel) return;
        sel.innerHTML = PROVIDERS.map(function (p) {
            return '<option value="' + escHtml(p.id) + '">' + escHtml(p.label) + '</option>';
        }).join('');
    }

    function updateModelSuggestions(providerId) {
        var prov = PROVIDERS.find(function (p) {
            return p.id === providerId;
        });
        var list = $('icModelSuggestions');
        if (!list || !prov) return;
        list.innerHTML = (prov.models || [])
            .map(function (m) {
                return '<option value="' + escHtml(m.id) + '">' + escHtml(m.label) + '</option>';
            })
            .join('');
    }

    function onProviderChange() {
        var provEl = $('icProvider');
        if (!provEl) return;
        var pid = provEl.value;
        var prov = PROVIDERS.find(function (p) {
            return p.id === pid;
        });
        var baseEl = $('icBaseUrl');
        if (prov && prov.base_url && baseEl) baseEl.value = prov.base_url;
        updateModelSuggestions(pid);
        var input = $('icModelInput');
        if (input && prov && prov.models && prov.models.length && !input.value.trim()) {
            input.value = prov.models[0].id;
        }
    }

    function applySettingsToForm(s) {
        SETTINGS = s;
        if (!s) return;
        var provEl = $('icProvider');
        var baseEl = $('icBaseUrl');
        var modelEl = $('icModelInput');
        var parseEl = $('icAutoParse');
        var keyEl = $('icApiKey');
        var keyHint = $('icApiKeyHint');
        if (!provEl || !baseEl || !modelEl || !parseEl || !keyEl || !keyHint) return;
        provEl.value = s.provider_id || 'deepseek';
        baseEl.value = s.base_url || '';
        updateModelSuggestions(s.provider_id || 'deepseek');
        modelEl.value = s.model || '';
        parseEl.checked = s.auto_parse_mail !== false;
        keyEl.value = '';
        keyHint.textContent = s.api_key_configured
            ? '已加密保存 API Key，留空表示不修改'
            : '请填写 API Key（将加密保存）';
    }

    function getModelValue() {
        var el = $('icModelInput');
        return el ? el.value.trim() : '';
    }

    function renderMailDockList() {
        var list = $('icMailDockList');
        if (!list) return;
        if (ACTIVE_MAIL_DETAIL_ID) return;
        var dockItems = MAIL_INSIGHTS.filter(function (it) {
            return it.is_parsed;
        });
        var parsingCount = MAIL_INSIGHTS.filter(function (it) {
            return !it.is_parsed;
        }).length;
        if (!dockItems.length) {
            list.innerHTML =
                '<div class="ic-mail-dock__empty">' +
                (parsingCount > 0
                    ? '有 ' + parsingCount + ' 封新邮件正在解析…'
                    : '绑定邮箱并配置模型后，新邮件将自动解析并显示在此') +
                '</div>';
            return;
        }
        list.innerHTML = dockItems
            .map(function (it, idx) {
                var unread = it.is_parsed && !it.is_read ? ' is-unread' : '';
                var snip = (it.summary || '').replace(/\s+/g, ' ').trim();
                if (snip.length > 100) snip = snip.slice(0, 100) + '…';
                return (
                    '<article class="ic-mail-card' +
                    unread +
                    '" data-id="' +
                    escHtml(it.id) +
                    '" style="--ic-stagger:' +
                    idx +
                    '">' +
                    '<div class="ic-mail-card__head">' +
                    '<span class="ic-mail-card__tag">' +
                    escHtml(categoryLabel(it.category)) +
                    '</span>' +
                    (unread ? '<span class="ic-mail-card__dot" aria-hidden="true"></span>' : '') +
                    '</div>' +
                    '<h4 class="ic-mail-card__subject">' +
                    escHtml(it.subject || '(无主题)') +
                    '</h4>' +
                    '<p class="ic-mail-card__from">' +
                    escHtml(it.from_addr || '') +
                    '</p>' +
                    '<p class="ic-mail-card__snip">' +
                    escHtml(snip) +
                    '</p></article>'
                );
            })
            .join('');
    }

    function loadProviders() {
        return api('/api/ai-assistant/providers').then(function (d) {
            PROVIDERS = d.providers || [];
            fillProviderSelect();
        });
    }

    function loadSettings() {
        return api('/api/ai-assistant/settings').then(function (s) {
            applySettingsToForm(s);
        });
    }

    function loadInsights() {
        return api('/api/ai-assistant/insights?limit=50').then(function (d) {
            MAIL_INSIGHTS = d.items || [];
            updateMailBadges();
            if (MAIL_DOCK_OPEN) renderMailDockList();
        });
    }

    function setSyncDot(live) {
        var dot = $('icSyncDot');
        if (dot) dot.classList.toggle('is-live', !!live);
    }

    function syncMail(quiet) {
        setSyncDot(true);
        var p =
            window.OfferFlowIvory && OfferFlowIvory.syncMailQuiet
                ? OfferFlowIvory.syncMailQuiet()
                : api('/api/ai-assistant/sync-mail', { method: 'POST' });
        return p
            .then(function (stats) {
                return loadInsights().then(function () {
                    if (!quiet) {
                        var n = (stats && stats.new_insights) || 0;
                        toast(n > 0 ? '已同步，新增 ' + n + ' 条解析' : '已同步', 'success');
                    }
                    return stats;
                });
            })
            .catch(function (e) {
                if (!quiet) toast((e && e.message) || '同步失败', 'error');
            })
            .finally(function () {
                setSyncDot(false);
            });
    }

    function saveConfig() {
        var body = {
            provider_id: $('icProvider').value,
            base_url: $('icBaseUrl').value.trim(),
            model: getModelValue(),
            auto_parse_mail: $('icAutoParse').checked,
        };
        var key = $('icApiKey').value.trim();
        if (key) body.api_key = key;
        api('/api/ai-assistant/settings', { method: 'PUT', body: body })
            .then(function (s) {
                applySettingsToForm(s);
                toast('配置已保存', 'success');
                closeConfig();
            })
            .catch(function (e) {
                toast((e && e.message) || '保存失败', 'error');
            });
    }

    function checkAvailability() {
        var btn = $('icCheckBtn');
        var res = $('icCheckResult');
        if (!btn || !res) return;
        btn.disabled = true;
        res.className = 'ic-check-result is-show';
        res.textContent = '正在检测连接…';
        var body = {
            base_url: $('icBaseUrl').value.trim(),
            model: getModelValue(),
        };
        var key = $('icApiKey').value.trim();
        if (key) body.api_key = key;
        api('/api/ai-assistant/check', { method: 'POST', body: body })
            .then(function (d) {
                res.className = 'ic-check-result is-show ' + (d.ok ? 'is-ok' : 'is-fail');
                res.textContent = d.message || (d.ok ? '可用' : '不可用');
            })
            .catch(function (e) {
                res.className = 'ic-check-result is-show is-fail';
                res.textContent = (e && e.message) || '检测失败';
            })
            .finally(function () {
                btn.disabled = false;
            });
    }

    function bindEvents() {
        var root = $('mailApp');
        if (!root || root.getAttribute('data-mail-ai-bound') === '1') return;
        root.setAttribute('data-mail-ai-bound', '1');

        var openCfg = $('icOpenConfigBtn');
        if (openCfg) openCfg.onclick = openConfig;
        var closeBtn = $('icConfigClose');
        if (closeBtn) closeBtn.onclick = closeConfig;
        var cancelBtn = $('icConfigCancel');
        if (cancelBtn) cancelBtn.onclick = closeConfig;
        var backdrop = $('icConfigBackdrop');
        if (backdrop) backdrop.onclick = closeConfig;
        var saveBtn = $('icConfigSave');
        if (saveBtn) saveBtn.onclick = saveConfig;
        var checkBtn = $('icCheckBtn');
        if (checkBtn) checkBtn.onclick = checkAvailability;
        var provider = $('icProvider');
        if (provider) provider.onchange = onProviderChange;

        var fab = $('icMailFab');
        if (fab) fab.onclick = toggleMailDock;
        var dockClose = $('icMailDockClose');
        if (dockClose) dockClose.onclick = closeMailDock;
        var dockBackdrop = $('icMailDockBackdrop');
        if (dockBackdrop) dockBackdrop.onclick = closeMailDock;
        var dockSync = $('icDockSyncBtn');
        if (dockSync) dockSync.onclick = function () { syncMail(false); };
        var detailBack = $('icMailDetailBack');
        if (detailBack) detailBack.onclick = hideMailDetail;

        var list = $('icMailDockList');
        if (list) {
            list.addEventListener('click', function (e) {
                var card = e.target.closest('.ic-mail-card');
                if (!card) return;
                showMailDetail(card.getAttribute('data-id'));
            });
        }

        window.addEventListener('offerflow:ai-assistant-unread', function (ev) {
            var d = (ev && ev.detail) || {};
            applyIvoryUnreadFromServer(d.count, d.items);
        });
    }

    function init() {
        if (!$('mailApp') || !$('icMailFab')) return;
        bindEvents();
        loadProviders()
            .then(loadSettings)
            .then(loadInsights)
            .catch(function (e) {
                console.warn('[mail-ai-parse]', e);
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
