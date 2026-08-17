/**
 * 实习/校招列表：localStorage 筛选态在 Turbo 渲染前同步到 DOM，避免先闪「全部」再跳回。
 */
(function (global) {
    'use strict';

    function read(prefix) {
        var f = localStorage.getItem(prefix + '_filter') || 'all';
        if (f === 'replied') f = 'all';
        return {
            filter: f,
            priority: localStorage.getItem(prefix + '_priority_filter') || 'all',
            interview: localStorage.getItem(prefix + '_interview_filter') || 'all',
            sortField: localStorage.getItem(prefix + '_sort_field') || 'default',
            sortOrder: localStorage.getItem(prefix + '_sort_order') || 'asc',
            search: localStorage.getItem(prefix + '_search') || ''
        };
    }

    function apply(doc, prefix, state) {
        if (!doc || !state) return false;
        if (!doc.querySelector('[data-batch-page="' + prefix + '"]')) return false;

        doc.querySelectorAll('[data-batch-page="' + prefix + '"] .filter-tab').forEach(function (t) {
            t.classList.toggle('active', t.dataset.filter === state.filter);
        });

        var searchEl = doc.getElementById('searchInput');
        if (searchEl) searchEl.value = state.search || '';

        var pf = doc.getElementById('priorityFilter');
        var inf = doc.getElementById('interviewFilter');
        var sf = doc.getElementById('sortField');
        var so = doc.getElementById('sortOrder');
        if (pf) pf.value = state.priority;
        if (inf) inf.value = state.interview;
        if (sf) sf.value = state.sortField;
        if (so) so.value = state.sortOrder;
        return true;
    }

    if (!global.__OFBatchStateInit) {
        global.__OFBatchStateInit = true;
        document.addEventListener('turbo:before-render', function (e) {
            var newBody = e.detail.newBody;
            if (!newBody) return;
            var root = newBody.querySelector('[data-batch-page]');
            if (!root) return;
            var prefix = root.getAttribute('data-batch-page');
            if (!prefix) return;
            apply(newBody, prefix, read(prefix));
        });
    }

    global.OFBatchState = {
        read: read,
        apply: apply
    };
})(window);
