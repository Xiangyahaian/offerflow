/**
 * OfferFlow 性能：GET 缓存、导航预取、Turbo 调优
 */
(function (global) {
    'use strict';

    var GET_TTL_MS = 45000;
    var USER_CACHE_KEY = 'offerflow_user_v6';
    var USER_CACHE_TTL_MS = 90000;
    var _getCache = new Map();

    /** 用户态 API 一律不缓存（URL 相同但 Token 不同会串数据，如校招/实习列表） */
    function shouldCacheGetUrl(url) {
        if (!url) return false;
        var path = String(url).split('?')[0];
        if (path.indexOf('/api/') === 0) return false;
        return true;
    }

    function now() {
        return Date.now();
    }

    function cacheGet(url) {
        var ent = _getCache.get(url);
        if (!ent) return null;
        if (ent.exp < now()) {
            _getCache.delete(url);
            return null;
        }
        return ent.data;
    }

    function cacheSet(url, data) {
        _getCache.set(url, { data: data, exp: now() + GET_TTL_MS });
    }

    function invalidateGetCache(prefix) {
        _getCache.forEach(function (_, key) {
            if (!prefix || key.indexOf(prefix) === 0) _getCache.delete(key);
        });
    }

    function readUserCache(ownerId) {
        try {
            var raw = sessionStorage.getItem(USER_CACHE_KEY);
            if (!raw) return null;
            var pack = JSON.parse(raw);
            if (!pack || !pack.user || pack.exp < now()) {
                sessionStorage.removeItem(USER_CACHE_KEY);
                return null;
            }
            if (!pack.ownerId) {
                sessionStorage.removeItem(USER_CACHE_KEY);
                return null;
            }
            if (ownerId && pack.ownerId !== ownerId) {
                return null;
            }
            var u = pack.user;
            if (u) {
                u = Object.assign({}, u);
                delete u.avatar_url;
            }
            return u;
        } catch (e) {
            return null;
        }
    }

    function writeUserCache(user) {
        if (!user || !user.id) return;
        var slim = Object.assign({}, user);
        delete slim.avatar_url;
        try {
            sessionStorage.setItem(
                USER_CACHE_KEY,
                JSON.stringify({
                    user: slim,
                    ownerId: user.id,
                    exp: now() + USER_CACHE_TTL_MS,
                })
            );
        } catch (e) {}
    }

    function clearUserCache() {
        try {
            sessionStorage.removeItem(USER_CACHE_KEY);
        } catch (e) {}
    }

    /** @deprecated 已停用：用户数据 GET 一律直连，避免多账号/多机串缓存 */
    function wrapApiFetch(doFetch) {
        return doFetch;
    }

    /** 预览访客：在 Turbo 替换 DOM 前就显示顶栏，避免岗位速递等页网格被二次顶下去 */
    function installPreviewBannerTurboPatch() {
        document.addEventListener('turbo:before-render', function (e) {
            var u = global.gUser;
            if (!u || !u.is_preview_guest) return;
            var newBody = e.detail && e.detail.newBody;
            if (!newBody) return;
            var banner = newBody.querySelector('#previewGuestBanner');
            if (banner) banner.hidden = false;
            var quotaEl = newBody.querySelector('#previewQuotaLeft');
            if (quotaEl) {
                var max = u.preview_applications_max || 5;
                var used = u.preview_applications_used || 0;
                quotaEl.textContent = String(Math.max(0, max - used));
            }
        });
    }

    function installTurboTuning() {
        if (global.Turbo) {
            try {
                Turbo.config.drive.progressBarDelay = 80;
            } catch (e) {}
        }
        document.addEventListener('turbo:click', function () {
            document.documentElement.classList.add('of-page-busy');
        });
        document.addEventListener('turbo:load', function () {
            document.documentElement.classList.remove('of-page-busy');
        });
        document.addEventListener('turbo:frame-load', function () {
            document.documentElement.classList.remove('of-page-busy');
        });
    }

    function installNavPrefetch() {
        var prefetched = new Set();
        function maybePrefetch(href) {
            if (!href || prefetched.has(href)) return;
            if (href.charAt(0) !== '/') return;
            if (href.indexOf('/login') === 0 || href.indexOf('/register') === 0) return;
            prefetched.add(href);
            var link = document.createElement('link');
            link.rel = 'prefetch';
            link.href = href;
            document.head.appendChild(link);
        }

        document.addEventListener(
            'mouseenter',
            function (e) {
                var a = e.target && e.target.closest ? e.target.closest('.sidebar-nav a.nav-item[href]') : null;
                if (!a) return;
                maybePrefetch(a.getAttribute('href'));
            },
            true
        );
        document.addEventListener(
            'touchstart',
            function (e) {
                var a = e.target && e.target.closest ? e.target.closest('.sidebar-nav a.nav-item[href]') : null;
                if (!a) return;
                maybePrefetch(a.getAttribute('href'));
            },
            { capture: true, passive: true }
        );
    }

    global.OfferFlowPerf = {
        cacheGet: cacheGet,
        cacheSet: cacheSet,
        invalidateGetCache: invalidateGetCache,
        readUserCache: readUserCache,
        writeUserCache: writeUserCache,
        clearUserCache: clearUserCache,
        shouldCacheGetUrl: shouldCacheGetUrl,
        wrapApiFetch: wrapApiFetch,
        install: function () {
            installTurboTuning();
            installPreviewBannerTurboPatch();
            installNavPrefetch();
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            global.OfferFlowPerf.install();
        });
    } else {
        global.OfferFlowPerf.install();
    }
})(window);
