/**
 * 防止点击非输入区时出现文本插入光标；防止焦点落在 body/容器上时误输入
 */
(function () {
    'use strict';

    var EDITABLE_SEL =
        'input, textarea, select, [contenteditable="true"], .inline-input, .inline-editable';

    function isEditableTarget(el) {
        if (!el || !el.closest) return false;
        return !!el.closest(EDITABLE_SEL);
    }

    function isEditableFocused() {
        var ae = document.activeElement;
        if (!ae || ae === document.body || ae === document.documentElement) return false;
        if (ae.isContentEditable) return true;
        if (ae.matches && ae.matches(EDITABLE_SEL)) return true;
        return false;
    }

    document.addEventListener(
        'mousedown',
        function (e) {
            if (isEditableTarget(e.target)) return;
            if (e.target.closest && e.target.closest('input, textarea, select, [contenteditable="true"]')) {
                return;
            }
            var ae = document.activeElement;
            if (!ae || ae === document.body || ae === document.documentElement) return;
            if (isEditableFocused()) return;
            try {
                ae.blur();
            } catch (err) {}
        },
        true
    );

    document.addEventListener(
        'keydown',
        function (e) {
            if (e.ctrlKey || e.metaKey || e.altKey) return;
            if (e.key === 'Tab' || e.key === 'Escape' || e.key === 'Enter') return;
            if (e.key && e.key.length !== 1) return;
            if (isEditableFocused()) return;
            if (isEditableTarget(e.target)) return;
            e.preventDefault();
        },
        true
    );
})();
