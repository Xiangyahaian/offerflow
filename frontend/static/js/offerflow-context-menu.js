/**
 * OfferFlow 全局右键菜单：定位、动画、复制降级
 */
(function (global) {
    'use strict';

    function escHtml(s) {
        if (s == null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function escAttr(s) {
        if (s == null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    var _ctxOutsideBound = false;
    var _ctxCloseTimer = null;

    function copyTextFallback(text) {
        return new Promise(function (resolve, reject) {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.setAttribute('aria-hidden', 'true');
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            ta.style.top = '0';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            ta.setSelectionRange(0, text.length);
            try {
                var ok = document.execCommand('copy');
                document.body.removeChild(ta);
                ok ? resolve() : reject(new Error('copy failed'));
            } catch (err) {
                try {
                    document.body.removeChild(ta);
                } catch (e2) {}
                reject(err);
            }
        });
    }

    function copyTextToClipboard(text) {
        text = String(text || '').trim();
        if (!text) return Promise.reject(new Error('empty'));
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            return navigator.clipboard.writeText(text).catch(function () {
                return copyTextFallback(text);
            });
        }
        return copyTextFallback(text);
    }

    function positionCtxMenu(menu, x, y) {
        menu.classList.remove('show', 'is-closing');
        menu.style.visibility = 'visible';
        menu.style.left = '-9999px';
        menu.style.top = '0';

        var rect = menu.getBoundingClientRect();
        var pad = 12;
        var vw = window.innerWidth || document.documentElement.clientWidth;
        var vh = window.innerHeight || document.documentElement.clientHeight;
        var left = Math.min(Math.max(pad, x), Math.max(pad, vw - rect.width - pad));
        var top = Math.min(Math.max(pad, y), Math.max(pad, vh - rect.height - pad));
        menu.style.left = Math.round(left) + 'px';
        menu.style.top = Math.round(top) + 'px';

        void menu.offsetWidth;
        menu.classList.add('show');
    }

    function hideCtx() {
        var menu = document.getElementById('ctxMenu');
        if (!menu || !menu.classList.contains('show')) return;
        menu.classList.add('is-closing');
        menu.classList.remove('show');
        clearTimeout(_ctxCloseTimer);
        _ctxCloseTimer = setTimeout(function () {
            menu.classList.remove('is-closing');
            menu.innerHTML = '';
            menu.setAttribute('aria-hidden', 'true');
        }, 180);
    }

    function showCtx(x, y, items, opts) {
        opts = opts || {};
        var menu = document.getElementById('ctxMenu');
        if (!menu) return;

        clearTimeout(_ctxCloseTimer);
        menu.classList.remove('is-closing');

        var html = '<div class="ctx-menu__body">';

        var primary = [];
        var destructive = [];
        var afterDivider = false;
        for (var j = 0; j < items.length; j++) {
            var it = items[j];
            if (!it) continue;
            if (it.divider) {
                afterDivider = true;
                continue;
            }
            if (afterDivider) destructive.push(it);
            else primary.push(it);
        }

        function renderItems(list, startIndex) {
            var block = '';
            var idx = startIndex || 0;
            for (var k = 0; k < list.length; k++) {
                var row = list[k];
                var disabled = !!row.disabled;
                var cls =
                    'ctx-item' +
                    (row.danger ? ' danger' : '') +
                    (disabled ? ' ctx-item--disabled' : '');
                block +=
                    '<button type="button" class="' +
                    cls +
                    '" data-action="' +
                    escAttr(row.action || '') +
                    '" style="--ctx-i:' +
                    idx +
                    '"' +
                    (disabled ? ' disabled' : '') +
                    '>' +
                    '<span class="ctx-item__label">' +
                    escHtml(row.label || '') +
                    '</span>' +
                    '</button>';
                idx += 1;
            }
            return { html: block, next: idx };
        }

        var itemIndex = 0;
        if (primary.length) {
            html += '<div class="ctx-menu__section">';
            var mainBlock = renderItems(primary, itemIndex);
            html += mainBlock.html;
            itemIndex = mainBlock.next;
            html += '</div>';
        }
        if (destructive.length) {
            html += '<div class="ctx-menu__footer">';
            var footBlock = renderItems(destructive, itemIndex);
            html += footBlock.html;
            html += '</div>';
        }

        html += '</div>';

        menu.innerHTML = html;
        menu.setAttribute('aria-hidden', 'false');
        positionCtxMenu(menu, x, y);

        if (!_ctxOutsideBound) {
            _ctxOutsideBound = true;
            document.addEventListener(
                'mousedown',
                function (ev) {
                    var m = document.getElementById('ctxMenu');
                    if (!m || !m.classList.contains('show')) return;
                    if (m.contains(ev.target)) return;
                    hideCtx();
                },
                true
            );
            document.addEventListener('keydown', function (ev) {
                if (ev.key === 'Escape') hideCtx();
            });
            menu.addEventListener('click', function (ev) {
                var btn = ev.target.closest('.ctx-item');
                if (!btn || btn.disabled || btn.classList.contains('ctx-item--disabled')) return;
                var action = btn.getAttribute('data-action');
                if (global.ctxCallback) global.ctxCallback(action, btn);
                hideCtx();
            });
        }
    }

    function flashCtxSuccess(btn) {
        if (!btn) return;
        btn.classList.add('ctx-item--success');
        setTimeout(function () {
            btn.classList.remove('ctx-item--success');
        }, 520);
    }

    global.showCtx = showCtx;
    global.hideCtx = hideCtx;
    global.copyTextToClipboard = copyTextToClipboard;
    global.flashCtxMenuSuccess = flashCtxSuccess;
})(window);
