/**
 * 邮件模拟进度浮层（全站右上角，Turbo 导航不销毁）
 */
(function (global) {
    'use strict';

    var _sending = false;

    var STEPS = [
        { key: 'send', title: '发送模拟邮件', desc: '投递至绑定邮箱' },
        { key: 'fetch', title: '收取新邮件', desc: 'IMAP 拉取收件箱' },
        { key: 'parse', title: '象遇解析', desc: '提取公司与笔试信息' },
        { key: 'sync', title: '同步投递记录', desc: '更新实习 / 校招投递' },
    ];

    var _timers = [];

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

    function trackLabel(track) {
        return track === 'internship' ? '实习投递' : track === 'campus' ? '校招投递' : '投递记录';
    }

    function trackHref(track) {
        return track === 'internship' ? '/internships' : '/campus';
    }

    function buildStepsHtml() {
        var html = '';
        for (var i = 0; i < STEPS.length; i++) {
            var s = STEPS[i];
            html +=
                '<div class="mail-demo-toast__step" data-step="' +
                escHtml(s.key) +
                '">' +
                '<div class="mail-demo-toast__step-dot">' +
                String(i + 1) +
                '</div>' +
                '<div class="mail-demo-toast__step-text"><strong>' +
                escHtml(s.title) +
                '</strong><span>' +
                escHtml(s.desc) +
                '</span></div></div>';
        }
        return html;
    }

    function ensureHost() {
        var host = $('mailDemoToastHost');
        if (host) return host;
        host = document.createElement('div');
        host.id = 'mailDemoToastHost';
        host.className = 'mail-demo-toast-host';
        host.setAttribute('data-turbo-permanent', '');
        host.setAttribute('aria-live', 'polite');
        document.body.appendChild(host);
        return host;
    }

    function isSending() {
        return _sending;
    }

    function setSending(v) {
        _sending = !!v;
    }

    function hide(force) {
        if (_sending && !force) return;
        _timers.forEach(clearTimeout);
        _timers = [];
        var el = $('mailDemoToast');
        if (!el) return;
        el.classList.add('is-leaving');
        setTimeout(function () {
            if (el.parentNode) el.parentNode.removeChild(el);
        }, 420);
    }

    function showProgress(companyName) {
        var container = ensureHost();
        if (!container) return;
        hide();
        var el = document.createElement('div');
        el.id = 'mailDemoToast';
        el.className = 'mail-demo-toast';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        el.innerHTML =
            '<button type="button" class="mail-demo-toast__close" aria-label="关闭">×</button>' +
            '<div class="mail-demo-toast__head">' +
            '<div class="mail-demo-toast__icon" aria-hidden="true">' +
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16v16H4z"/><path d="m22 6-10 7L2 6"/></svg>' +
            '</div>' +
            '<div class="mail-demo-toast__titles">' +
            '<strong>邮件模拟进行中</strong>' +
            '<span>' +
            escHtml(companyName || '笔试邀请') +
            '</span></div></div>' +
            '<div class="mail-demo-toast__steps">' +
            buildStepsHtml() +
            '</div>';
        container.appendChild(el);
        el.querySelector('.mail-demo-toast__close').onclick = function () {
            setSending(false);
            hide(true);
        };
        requestAnimationFrame(function () {
            void el.offsetHeight;
            requestAnimationFrame(function () {
                el.classList.add('is-visible');
                setStepActive(0);
            });
        });
    }

    function setStepActive(idx) {
        var el = $('mailDemoToast');
        if (!el) return;
        var steps = el.querySelectorAll('.mail-demo-toast__step');
        for (var i = 0; i < steps.length; i++) {
            steps[i].classList.remove('is-active');
            if (i < idx) steps[i].classList.add('is-done');
            else if (i > idx) steps[i].classList.remove('is-done');
        }
        if (steps[idx]) steps[idx].classList.add('is-active');
    }

    function markStepDone(idx) {
        var el = $('mailDemoToast');
        if (!el) return;
        var steps = el.querySelectorAll('.mail-demo-toast__step');
        if (!steps[idx]) return;
        steps[idx].classList.remove('is-active');
        steps[idx].classList.add('is-done');
    }

    function finalizeProgress(sent, synced) {
        var el = $('mailDemoToast');
        if (!el) return;
        var sync = (synced && synced.sync) || {};
        var parsed = sync.new_insights > 0;
        var applied = (sync.applications_updated || []).length > 0;
        markStepDone(0);
        markStepDone(1);
        if (parsed) markStepDone(2);
        if (applied) markStepDone(3);
        el.querySelectorAll('.mail-demo-toast__step').forEach(function (node) {
            node.classList.remove('is-active');
        });
    }

    function showResult(data) {
        var el = $('mailDemoToast');
        if (!el) return;

        var sync = data.sync || {};
        var updates = sync.applications_updated || [];
        var parsed = sync.new_insights > 0;
        var applied = updates.length > 0;
        var u = applied ? updates[0] : null;

        var title = applied
            ? '模拟完成 · 投递已同步'
            : parsed
              ? '模拟完成 · 邮件已解析'
              : '模拟邮件已发送';
        var lines = [];
        lines.push(
            '已向 ' +
                (data.sent_to || '您的邮箱') +
                ' 发送「' +
                (data.company_name || '') +
                '」笔试邀请。'
        );
        if (parsed) lines.push('象遇已解析并提取笔试信息。');
        if (applied && u) {
            var action = (u.action || '').indexOf('created') >= 0 ? '新建' : '更新';
            lines.push(action + '了' + trackLabel(u.track || data.track) + '。');
        } else if (!parsed) {
            lines.push('请刷新收件箱查看。');
        }

        var th = trackHref(u && u.track ? u.track : data.track);
        el.classList.add('is-done');
        el.innerHTML =
            '<button type="button" class="mail-demo-toast__close" aria-label="关闭">×</button>' +
            '<div class="mail-demo-toast__head">' +
            '<div class="mail-demo-toast__icon mail-demo-toast__icon--ok" aria-hidden="true">✓</div>' +
            '<div class="mail-demo-toast__titles">' +
            '<strong>' +
            escHtml(title) +
            '</strong>' +
            '<span>' +
            escHtml(data.company_name || '') +
            '</span></div></div>' +
            '<p class="mail-demo-toast__summary">' +
            escHtml(lines.join(' ')) +
            '</p>' +
            '<div class="mail-demo-toast__links">' +
            '<a href="/mail-read">打开邮箱解析</a>' +
            '<a href="' +
            th +
            '">查看' +
            escHtml(trackLabel(u && u.track ? u.track : data.track)) +
            '</a>' +
            '</div>';
        el.querySelector('.mail-demo-toast__close').onclick = function () {
            setSending(false);
            hide();
        };
        el.classList.add('is-visible');
        _timers.push(
            setTimeout(function () {
                setSending(false);
                hide();
            }, 12000)
        );
    }

    function schedule(fn, ms) {
        var id = setTimeout(fn, ms);
        _timers.push(id);
        return id;
    }

    global.OfferFlowMailDemoToast = {
        showProgress: showProgress,
        hide: hide,
        isSending: isSending,
        setSending: setSending,
        setStepActive: setStepActive,
        markStepDone: markStepDone,
        finalizeProgress: finalizeProgress,
        showResult: showResult,
        schedule: schedule,
    };

    document.addEventListener('turbo:before-cache', function () {
        if (!_sending) hide();
    });
})(window);
