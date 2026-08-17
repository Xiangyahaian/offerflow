/**
 * OfferFlow 全局 Toast 通知
 */
(function (global) {
    'use strict';

    var ICONS = {
        success:
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<path d="M20 6L9 17l-5-5"/></svg>',
        error:
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
        warning:
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<path d="M12 9v4M12 17h.01"/><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>',
        info:
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
    };

    function escapeHtml(s) {
        if (global.escHtml) return global.escHtml(String(s));
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function toast(msg, type, options) {
        type = type || 'success';
        options = options || {};
        var duration = typeof options.duration === 'number' ? options.duration : 1600;
        var progressMs = duration;
        var container = document.getElementById('toastContainer');
        if (!container) return;

        var maxStack = 4;
        while (container.children.length >= maxStack) {
            container.removeChild(container.firstElementChild);
        }

        var el = document.createElement('div');
        el.className = 'toast toast-' + type;
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');

        var icon = ICONS[type] || ICONS.success;
        var html =
            '<div class="toast__glow" aria-hidden="true"></div>' +
            '<div class="toast__icon-wrap">' + icon + '</div>' +
            '<div class="toast__body"><p class="toast__message">' + escapeHtml(msg) + '</p></div>' +
            '<div class="toast__progress" aria-hidden="true"><span></span></div>';

        el.innerHTML = html;

        if (options.undoLabel) {
            var undoBtn = document.createElement('button');
            undoBtn.type = 'button';
            undoBtn.className = 'toast-undo';
            undoBtn.textContent = options.undoLabel;
            undoBtn.onclick = function () {
                if (typeof options.undoCallback === 'function') options.undoCallback();
                dismissToast(el);
            };
            el.insertBefore(undoBtn, el.querySelector('.toast__progress'));
        }

        var progressBar = el.querySelector('.toast__progress > span');
        if (progressBar) progressBar.style.animationDuration = progressMs + 'ms';

        container.appendChild(el);
        /* 等布局完成再开启动画，避免首帧卡顿 */
        requestAnimationFrame(function () {
            void el.offsetHeight;
            requestAnimationFrame(function () {
                el.classList.add('is-visible');
            });
        });

        var leaveTimer = null;
        var LEAVE_MS = 480;

        function dismissToast(node) {
            if (!node || node.classList.contains('is-leaving')) return;
            if (leaveTimer) clearTimeout(leaveTimer);
            node.classList.remove('is-visible');
            node.style.animation = 'none';
            void node.offsetHeight;
            node.classList.add('is-leaving');
            setTimeout(function () {
                if (node.parentNode) node.parentNode.removeChild(node);
            }, LEAVE_MS);
        }

        leaveTimer = setTimeout(function () {
            dismissToast(el);
        }, duration);

        el.addEventListener('click', function (ev) {
            if (ev.target.closest('.toast-undo')) return;
            dismissToast(el);
        });
    }

    global.toast = toast;
})(typeof window !== 'undefined' ? window : global);
