/**
 * 实习/校招列表：Turbo 切页后统一拉起初始化（不依赖 extra_js 是否被重新执行）
 */
(function (global) {
    'use strict';

    function bootBatchPages() {
        function run() {
            if (global.__ofBootCampus && document.querySelector('[data-batch-page="campus"]')) {
                try {
                    global.__ofBootCampus();
                } catch (e) {
                    console.error('[campus boot]', e);
                }
            }
            if (global.__ofBootIntern && document.querySelector('[data-batch-page="intern"]')) {
                try {
                    global.__ofBootIntern();
                } catch (e) {
                    console.error('[intern boot]', e);
                }
            }
        }

        // Turbo 会先 merge DOM 再 eval extra_js；延后一帧，避免 boot 早于页面脚本定义 __ofBoot*
        if (typeof requestAnimationFrame === 'function') {
            requestAnimationFrame(run);
        } else {
            setTimeout(run, 0);
        }
    }

    document.addEventListener('turbo:load', bootBatchPages);
    document.addEventListener('turbo:render', bootBatchPages);
    if (document.readyState !== 'loading') bootBatchPages();
    else document.addEventListener('DOMContentLoaded', bootBatchPages);
})(window);
