/**
 * 邮件模拟 · 仅邮箱读取页（选择面板 + 发送流程）
 * 进度浮层见 mail-demo-toast.js（全站 base，Turbo 导航不销毁）
 */
(function (global) {
    'use strict';

    var _options = null;
    var _selectedId = null;
    var _sending = false;
    var _docBound = false;

    function $(id) {
        return document.getElementById(id);
    }

    function escHtml(s) {
        return String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function toastApi() {
        return global.OfferFlowMailDemoToast;
    }

    function isMailReadPage() {
        return !!document.getElementById('mailApp') && !!$('mailDemoRoot');
    }

    function canUseDemo() {
        return !global.gUserIsPreview && typeof global.api === 'function';
    }

    function settleDemoCards() {
        var grid = $('mailDemoGrid');
        if (!grid) return;
        grid.querySelectorAll('.mail-demo__card').forEach(function (card) {
            card.classList.add('mail-demo__card--settled');
        });
    }

    function renderCompanies(companies) {
        var grid = $('mailDemoGrid');
        if (!grid) return;
        var html = '';
        for (var i = 0; i < companies.length; i++) {
            var c = companies[i];
            var sel = _selectedId === c.id ? ' is-selected' : '';
            html +=
                '<button type="button" class="mail-demo__card' +
                sel +
                '" data-id="' +
                escHtml(c.id) +
                '" style="--md-brand:' +
                escHtml(c.brand_color) +
                ';--md-accent:' +
                escHtml(c.brand_accent) +
                '">' +
                '<span class="mail-demo__card-glow" aria-hidden="true"></span>' +
                '<span class="mail-demo__card-main">' +
                '<span class="mail-demo__card-logo">' +
                escHtml(c.short_name.slice(0, 2)) +
                '</span>' +
                '<span class="mail-demo__card-text">' +
                '<span class="mail-demo__card-name">' +
                escHtml(c.name) +
                '</span>' +
                '<span class="mail-demo__card-tag">' +
                escHtml(c.tagline) +
                '</span>' +
                '<span class="mail-demo__card-pos">' +
                escHtml(c.position) +
                '</span>' +
                '</span>' +
                '</span>' +
                '<span class="mail-demo__card-check" aria-hidden="true">' +
                '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>' +
                '</span>' +
                '</button>';
        }
        grid.innerHTML = html;
        var t = toastApi();
        if (t && t.schedule) {
            t.schedule(function () {
                settleDemoCards();
            }, 520);
        } else {
            setTimeout(settleDemoCards, 520);
        }
    }

    function updateCardSelection() {
        var grid = $('mailDemoGrid');
        if (!grid) return;
        settleDemoCards();
        grid.querySelectorAll('.mail-demo__card').forEach(function (card) {
            var id = card.getAttribute('data-id');
            card.classList.toggle('is-selected', id === _selectedId);
        });
        updateMeta();
    }

    function updateMeta() {
        var meta = $('mailDemoMeta');
        var warn = $('mailDemoWarn');
        var sendBtn = $('mailDemoSend');
        if (!meta || !_options) return;

        var exam = _options.exam_datetime_label || '两天后 19:00';
        if (_options.target_email) {
            meta.innerHTML =
                '将发送至 <strong>' +
                escHtml(_options.target_email) +
                '</strong> · 笔试时间 <strong>' +
                escHtml(exam) +
                '</strong>';
        } else {
            meta.innerHTML = '请先在「邮箱设置」中配置 IMAP 授权码';
        }

        if (warn) {
            var warns = [];
            if (!_options.mail_configured) {
                warns.push('未配置邮箱 IMAP，无法收取模拟邮件');
            }
            if (!_options.ai_configured) {
                warns.push('未配置象遇模型 API，将只能收取邮件而无法 AI 解析');
            }
            if (warns.length) {
                warn.hidden = false;
                var warnText = warn.querySelector('.mail-demo__warn-text');
                if (warnText) warnText.textContent = warns.join('；');
                else warn.textContent = warns.join('；');
            } else {
                warn.hidden = true;
            }
        }

        if (sendBtn) {
            sendBtn.disabled =
                _sending || !_selectedId || !_options.mail_configured;
        }
    }

    function demoMailInList(items, testId) {
        var needle = '[#' + testId + ']';
        for (var i = 0; i < items.length; i++) {
            var subj = items[i].subject || '';
            if (subj.indexOf(needle) >= 0 || subj.indexOf(testId) >= 0) return true;
        }
        return false;
    }

    function pollDemoMailArrival(slot, testId, maxAttempts, intervalMs) {
        return new Promise(function (resolve, reject) {
            var attempts = 0;
            var t = toastApi();
            function tick() {
                var url =
                    '/api/mail/messages?slot=' +
                    encodeURIComponent(slot) +
                    '&limit=50&refresh=true';
                global
                    .api(url)
                    .then(function (res) {
                        if (demoMailInList(res.items || [], testId)) {
                            resolve(res);
                            return;
                        }
                        attempts++;
                        if (attempts >= maxAttempts) {
                            reject(
                                new Error(
                                    '等待邮件进入收件箱超时，请稍后点击「刷新收件箱」查看'
                                )
                            );
                            return;
                        }
                        if (t && t.schedule) t.schedule(tick, intervalMs);
                        else setTimeout(tick, intervalMs);
                    })
                    .catch(reject);
            }
            tick();
        });
    }

    function refreshMailSlot(slot) {
        if (
            typeof global.switchMailSlot === 'function' &&
            slot &&
            global.mailCurSlot &&
            global.mailCurSlot !== slot
        ) {
            global.switchMailSlot(slot);
            return Promise.resolve();
        }
        if (typeof global.refreshMail === 'function') {
            return global.refreshMail(true);
        }
        return Promise.resolve();
    }

    function loadOptions() {
        return global.api('/api/mail/demo/options').then(function (o) {
            _options = o;
            if (!_selectedId && o.companies && o.companies.length) {
                _selectedId = o.companies[0].id;
            }
            renderCompanies(o.companies || []);
            updateMeta();
        });
    }

    function getSelectedCompanyName() {
        if (!_options || !_options.companies || !_selectedId) return '';
        for (var i = 0; i < _options.companies.length; i++) {
            if (_options.companies[i].id === _selectedId) return _options.companies[i].name;
        }
        return '';
    }

    function openPanel() {
        if (!isMailReadPage()) return;
        if (!canUseDemo()) {
            if (typeof global.toast === 'function') {
                global.toast('请先注册正式账号后体验邮件模拟', 'warning');
            }
            return;
        }
        if (_sending) return;
        var root = $('mailDemoRoot');
        if (!root) return;
        root.classList.add('is-open');
        root.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        loadOptions().catch(function (e) {
            if (typeof global.toast === 'function') global.toast(e.message || '加载失败', 'error');
        });
    }

    function closePanel() {
        var root = $('mailDemoRoot');
        if (!root || !root.classList.contains('is-open')) return;
        root.classList.remove('is-open');
        root.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    }

    function prepareForTurboCache() {
        closePanel();
        document.body.style.overflow = '';
        var root = $('mailDemoRoot');
        if (!root) return;
        root.classList.remove('is-open');
        root.setAttribute('aria-hidden', 'true');
        var grid = $('mailDemoGrid');
        if (grid) grid.innerHTML = '';
    }

    function runSend() {
        if (_sending || !_selectedId || !_options || !_options.mail_configured) return;
        var t = toastApi();
        if (!t) return;

        _sending = true;
        if (t.setSending) t.setSending(true);
        var companyName = getSelectedCompanyName();
        closePanel();
        t.showProgress(companyName);
        t.setStepActive(0);

        global
            .api('/api/mail/demo/send', {
                method: 'POST',
                body: { company: _selectedId },
            })
            .then(function (sent) {
                t.markStepDone(0);
                t.setStepActive(1);
                return pollDemoMailArrival(sent.mail_slot, sent.test_id, 30, 2000).then(function () {
                    t.markStepDone(1);
                    return refreshMailSlot(sent.mail_slot).then(function () {
                        var inboxSync =
                            global.OfferFlowIvory && global.OfferFlowIvory.syncInboxQuiet
                                ? global.OfferFlowIvory.syncInboxQuiet()
                                : global.api('/api/mail/sync-inbox', { method: 'POST' });
                        return inboxSync.then(function () {
                            if (
                                global.OfferFlowIvory &&
                                global.OfferFlowIvory.refreshUnreadBadges
                            ) {
                                global.OfferFlowIvory.refreshUnreadBadges();
                            }
                            t.setStepActive(2);
                            return global
                                .api('/api/mail/demo/sync', {
                                    method: 'POST',
                                    body: {
                                        company: sent.company_id,
                                        test_id: sent.test_id,
                                    },
                                })
                                .then(function (synced) {
                                    t.finalizeProgress(sent, synced);
                                    if (
                                        global.OfferFlowIvory &&
                                        global.OfferFlowIvory.refreshUnreadBadges
                                    ) {
                                        global.OfferFlowIvory.refreshUnreadBadges();
                                    }
                                    var result = {
                                        sent_to: sent.sent_to,
                                        company_name: sent.company_name,
                                        company_id: sent.company_id,
                                        track: sent.track,
                                        ai_configured: sent.ai_configured,
                                        sync: synced.sync,
                                    };
                                    if (t.schedule) {
                                        t.schedule(function () {
                                            _sending = false;
                                            if (t.setSending) t.setSending(false);
                                            updateMeta();
                                            t.showResult(result);
                                        }, 320);
                                    }
                                });
                        });
                    });
                });
            })
            .catch(function (e) {
                _sending = false;
                if (t.setSending) t.setSending(false);
                t.hide();
                updateMeta();
                if (typeof global.toast === 'function') {
                    global.toast(e.message || '邮件模拟失败', 'error');
                }
            });
    }

    function onGridClick(e) {
        var card = e.target.closest('.mail-demo__card');
        if (!card || _sending) return;
        e.preventDefault();
        e.stopPropagation();
        var id = card.getAttribute('data-id');
        if (!id || id === _selectedId) return;
        _selectedId = id;
        updateCardSelection();
    }

    function bindDocEvents() {
        if (_docBound) return;
        _docBound = true;
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            var root = $('mailDemoRoot');
            if (root && root.classList.contains('is-open')) closePanel();
        });
        document.addEventListener('turbo:before-cache', prepareForTurboCache);
    }

    function bindPanelControls() {
        var closeBtn = $('mailDemoClose');
        var backdrop = $('mailDemoBackdrop');
        if (closeBtn) closeBtn.onclick = closePanel;
        if (backdrop) backdrop.onclick = closePanel;

        var sendBtn = $('mailDemoSend');
        if (sendBtn) sendBtn.onclick = runSend;

        var grid = $('mailDemoGrid');
        if (grid) grid.onclick = onGridClick;
    }

    function bindTriggers() {
        document.querySelectorAll('#mailDemoTrigger').forEach(function (btn) {
            btn.onclick = openPanel;
        });
    }

    function init() {
        bindDocEvents();
        if (!isMailReadPage()) return;
        bindPanelControls();
        bindTriggers();
    }

    global.OfferFlowMailDemo = {
        init: init,
        open: openPanel,
        close: closePanel,
        isSending: function () {
            return _sending;
        },
    };

    document.addEventListener('turbo:load', init);
    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})(window);
