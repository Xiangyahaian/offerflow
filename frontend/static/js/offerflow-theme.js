/**
 * 主题顺序：默认「晴空薄荷」排首位，其余按下列顺序出现在顶栏 / 设置页（共 12 套）
 * 晴空薄荷、柠光金、普鲁士蓝、马尔斯绿、晨湾缎、春露绿、晴屿蓝、沧浪青、
 * 春玫、糖果粉、汽水橙、泡泡蓝
 * 顶栏为色块浮层，设置页为 #themePicker 卡片网格
 */
(function (w) {
    if (typeof Turbo !== 'undefined' && Turbo.session && Turbo.session.drive) {
        try {
            Turbo.session.drive.progressBarDelay = 480;
        } catch (e) {}
    }

    var DEFAULT_THEME_ID = 'sky-mint';
    var GRAD_MORNING_BAY = 'linear-gradient(135deg, #6AD4BE 0%, #52C8E8 32%, #5AABF0 68%, #8FAEF5 100%)';
    var OFFERFLOW_THEMES = [
        { id: 'sky-mint', label: '晴空薄荷', color: '#52C5BE' },
        { id: 'schonbrunn', label: '柠光金', color: '#F5C518' },
        { id: 'prussian', label: '普鲁士蓝', color: '#003152' },
        { id: 'mars-green', label: '马尔斯绿', color: '#01847F' },
        { id: 'morning-bay', label: '晨湾缎', color: '#52B8E0', swatchBg: GRAD_MORNING_BAY },
        { id: 'spring-dew', label: '春露绿', color: '#4FB89E' },
        { id: 'island-air', label: '晴屿蓝', color: '#56ADD4' },
        { id: 'cerulean-ink', label: '沧浪青', color: '#2E6B8A' },
        { id: 'blossom-rose', label: '春玫', color: '#E7979C' },
        { id: 'candy-pink', label: '糖果粉', color: '#F0558C' },
        { id: 'soda-pop', label: '汽水橙', color: '#FF8A4C' },
        { id: 'bubble-blue', label: '泡泡蓝', color: '#45BFFF' },
    ];

    var LEGACY_THEME_MAP = {
        'purple-indigo': 'sky-mint',
        'blaze-orange': 'sky-mint',
        'aqua-spark': 'sky-mint',
        'midnight-ink': 'morning-bay',
        'forged-gold': 'spring-dew',
        'mist-rose': 'island-air',
        'mauve-silk': 'sky-mint',
        'wheat-spike': 'schonbrunn',
        'champagne-silk': 'schonbrunn',
        'dawn-gleam': 'schonbrunn',
        'molten-gold': 'schonbrunn',
        'palette-spring': 'sky-mint',
        'palette-dusk': 'sky-mint',
        'palette-porcelain': 'sky-mint',
        'sakura-rose': 'sky-mint',
        'cinnabar-veil': 'sky-mint',
        'rouge-mist': 'sky-mint',
        'rose-dawn': 'sky-mint',
        'crimson-dusk': 'sky-mint',
        amber: 'sky-mint',
        burgundy: 'sky-mint',
        'candy-strip': 'sky-mint',
        'rainbow-pop': 'sky-mint',
        'trio-harmony': 'sky-mint',
        'xiang-lustre': 'schonbrunn',
    };

    var ALLOWED = {
        'sky-mint': 1,
        schonbrunn: 1,
        prussian: 1,
        'mars-green': 1,
        'morning-bay': 1,
        'spring-dew': 1,
        'island-air': 1,
        'cerulean-ink': 1,
        'blossom-rose': 1,
        'candy-pink': 1,
        'soda-pop': 1,
        'bubble-blue': 1,
    };

    function themeById(id) {
        for (var i = 0; i < OFFERFLOW_THEMES.length; i++) {
            if (OFFERFLOW_THEMES[i].id === id) return OFFERFLOW_THEMES[i];
        }
        for (var j = 0; j < OFFERFLOW_THEMES.length; j++) {
            if (OFFERFLOW_THEMES[j].id === DEFAULT_THEME_ID) return OFFERFLOW_THEMES[j];
        }
        /* 列表首位即默认主题 */
        return OFFERFLOW_THEMES[0];
    }

    function getCurrentThemeId() {
        var t = document.documentElement.getAttribute('data-theme');
        if (t && LEGACY_THEME_MAP[t]) t = LEGACY_THEME_MAP[t];
        if (t && ALLOWED[t]) return t;
        try {
            var stored = localStorage.getItem('offerflow_theme');
            if (stored && LEGACY_THEME_MAP[stored]) stored = LEGACY_THEME_MAP[stored];
            if (stored && ALLOWED[stored]) return stored;
        } catch (e) {}
        return DEFAULT_THEME_ID;
    }

    function applyOfferflowTheme(themeId) {
        if (themeId && LEGACY_THEME_MAP[themeId]) themeId = LEGACY_THEME_MAP[themeId];
        if (!themeId || !ALLOWED[themeId]) themeId = DEFAULT_THEME_ID;
        try {
            document.documentElement.setAttribute('data-theme', themeId);
            localStorage.setItem('offerflow_theme', themeId);
        } catch (e) {}
        syncPopoverSwatches();
        syncSettingsThemeCards();
        updateThemeMenuTriggers();
    }

    function themeSwatchBackground(tm) {
        return tm && tm.swatchBg ? tm.swatchBg : tm.color;
    }

    function updateThemeMenuTriggers() {
        var tm = themeById(getCurrentThemeId());
        var bg = themeSwatchBackground(tm);
        document.querySelectorAll('.js-theme-menu-wrap .theme-menu-trigger').forEach(function (btn) {
            var dot = btn.querySelector('.theme-menu-trigger-dot');
            if (dot) {
                dot.style.background = bg;
                btn.style.background = '';
            } else {
                btn.style.background = bg;
            }
            btn.setAttribute('title', '主题：' + tm.label);
            btn.setAttribute('aria-label', '切换主题，当前：' + tm.label);
        });
    }

    function syncPopoverSwatches() {
        var cur = getCurrentThemeId();
        document.querySelectorAll('.theme-popover .theme-swatch[data-theme-id]').forEach(function (el) {
            var on = el.getAttribute('data-theme-id') === cur;
            el.classList.toggle('theme-swatch--active', on);
            el.setAttribute('aria-selected', on ? 'true' : 'false');
        });
    }

    function syncSettingsThemeCards() {
        var cur = getCurrentThemeId();
        document.querySelectorAll('.theme-opt-btn[data-theme-id]').forEach(function (el) {
            var on = el.getAttribute('data-theme-id') === cur;
            el.classList.toggle('theme-opt-btn--active', on);
        });
    }

    function renderPopoverSwatches(container) {
        if (!container) return;
        container.innerHTML = '';
        var title = document.createElement('p');
        title.className = 'theme-popover__title';
        title.textContent = '主题配色';
        container.appendChild(title);

        var grid = document.createElement('div');
        grid.className = 'theme-popover-grid';
        grid.setAttribute('role', 'presentation');

        OFFERFLOW_THEMES.forEach(function (tm) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'theme-swatch';
            b.dataset.themeId = tm.id;
            b.setAttribute('data-theme-id', tm.id);
            b.style.background = themeSwatchBackground(tm);
            b.setAttribute('role', 'option');
            b.setAttribute('aria-label', tm.label);
            b.setAttribute('title', tm.label);
            b.addEventListener('click', function (e) {
                e.stopPropagation();
                applyOfferflowTheme(tm.id);
                closeAllThemePopovers();
            });
            grid.appendChild(b);
        });
        container.appendChild(grid);
        syncPopoverSwatches();
    }

    function renderSettingsThemePicker() {
        var wrap = document.getElementById('themePicker');
        if (!wrap) return;
        var cur = getCurrentThemeId();
        wrap.innerHTML = OFFERFLOW_THEMES
            .map(function (t) {
                var active = t.id === cur ? ' theme-opt-btn--active' : '';
                return (
                    '<button type="button" class="theme-opt-btn' +
                    active +
                    '" data-theme-id="' +
                    t.id +
                    '">' +
                    '<span class="theme-opt-swatch" style="background:' +
                    themeSwatchBackground(t) +
                    '"></span>' +
                    '<span class="theme-opt-label">' +
                    t.label +
                    '</span></button>'
                );
            })
            .join('');
        wrap.querySelectorAll('.theme-opt-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var id = btn.getAttribute('data-theme-id');
                applyOfferflowTheme(id);
                renderSettingsThemePicker();
                if (typeof toast === 'function') toast('主题已更新', 'success');
            });
        });
    }

    var popoverOutsideHandler = null;

    function clearTopbarPopoverFixedStyles(popover) {
        if (!popover) return;
        popover.classList.remove('theme-popover--fixed-layer');
        popover.style.position = '';
        popover.style.left = '';
        popover.style.top = '';
        popover.style.right = '';
        popover.style.bottom = '';
        popover.style.transform = '';
    }

    /** 顶栏主题浮层：fixed 贴触发器，避免被 .main overflow 裁切 */
    function positionTopbarThemePopover(trigger, popover) {
        if (!trigger || !popover || popover.hidden) return;
        var pad = 8;
        var gap = 6;
        var r = trigger.getBoundingClientRect();
        var pr = popover.getBoundingClientRect();
        var belowTop = r.bottom + gap;
        var aboveTop = r.top - gap - pr.height;
        var top;
        if (belowTop + pr.height <= window.innerHeight - pad) {
            top = belowTop;
        } else if (aboveTop >= pad) {
            top = aboveTop;
        } else {
            top = Math.max(pad, Math.min(belowTop, window.innerHeight - pr.height - pad));
        }
        var left = r.left + (r.width - pr.width) / 2;
        left = Math.max(pad, Math.min(left, window.innerWidth - pr.width - pad));
        popover.style.position = 'fixed';
        popover.style.left = Math.round(left) + 'px';
        popover.style.top = Math.round(top) + 'px';
        popover.style.right = 'auto';
        popover.style.bottom = 'auto';
        popover.style.transform = 'none';
    }

    function closeAllThemePopovers() {
        document.querySelectorAll('.theme-popover').forEach(function (p) {
            p.hidden = true;
            clearTopbarPopoverFixedStyles(p);
        });
        document.querySelectorAll('.js-theme-menu-wrap').forEach(function (w) {
            if (w._themePopoverReposition) {
                window.removeEventListener('scroll', w._themePopoverReposition, true);
                window.removeEventListener('resize', w._themePopoverReposition, true);
                w._themePopoverReposition = null;
            }
        });
        document.querySelectorAll('.theme-menu-trigger').forEach(function (t) {
            t.setAttribute('aria-expanded', 'false');
        });
        if (popoverOutsideHandler) {
            document.removeEventListener('click', popoverOutsideHandler, true);
            popoverOutsideHandler = null;
        }
        document.removeEventListener('keydown', popoverEscHandler, true);
    }

    function popoverEscHandler(e) {
        if (e.key === 'Escape') closeAllThemePopovers();
    }

    function setupThemeMenu(wrap) {
        if (!wrap || wrap.dataset.themeMenuBound === '1') return;
        wrap.dataset.themeMenuBound = '1';
        var trigger = wrap.querySelector('.theme-menu-trigger');
        var popover = wrap.querySelector('.theme-popover');
        var inner = wrap.querySelector('.theme-popover-inner');
        if (!trigger || !popover || !inner) return;

        renderPopoverSwatches(inner);

        var useTopbarFixedLayer = !wrap.classList.contains('theme-menu-wrap--fixed');

        trigger.addEventListener('click', function (e) {
            e.stopPropagation();
            var wasClosed = popover.hidden;
            closeAllThemePopovers();
            if (wasClosed) {
                popover.hidden = false;
                trigger.setAttribute('aria-expanded', 'true');
                if (useTopbarFixedLayer) {
                    popover.classList.add('theme-popover--fixed-layer');
                    wrap._themePopoverReposition = function () {
                        if (popover.hidden) return;
                        positionTopbarThemePopover(trigger, popover);
                    };
                    window.addEventListener('scroll', wrap._themePopoverReposition, true);
                    window.addEventListener('resize', wrap._themePopoverReposition, true);
                    requestAnimationFrame(function () {
                        requestAnimationFrame(function () {
                            positionTopbarThemePopover(trigger, popover);
                        });
                    });
                }
                popoverOutsideHandler = function (ev) {
                    if (!wrap.contains(ev.target)) closeAllThemePopovers();
                };
                document.addEventListener('click', popoverOutsideHandler, true);
                document.addEventListener('keydown', popoverEscHandler, true);
            }
        });
    }

    function boot() {
        document.querySelectorAll('.js-theme-menu-wrap').forEach(setupThemeMenu);
        renderSettingsThemePicker();
        updateThemeMenuTriggers();
    }

    /** Turbo Drive 切换页面后同步侧栏高亮（active 类由前端维护，避免整页刷新） */
    function syncSidebarNavActive() {
        var path = (window.location.pathname || '/').replace(/\/+$/, '') || '/';
        document.querySelectorAll('.sidebar a.nav-item[href]').forEach(function (el) {
            var href = el.getAttribute('href');
            if (!href || href.charAt(0) === '#') return;
            var h = href.split('?')[0].replace(/\/+$/, '') || '/';
            var active = path === h || (h !== '/' && path.indexOf(h + '/') === 0);
            el.classList.toggle('active', active);
        });
    }

    function onTurboLoad() {
        syncSidebarNavActive();
        boot();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
    document.addEventListener('turbo:load', onTurboLoad);

    w.OFFERFLOW_THEMES = OFFERFLOW_THEMES;
    w.applyOfferflowTheme = applyOfferflowTheme;
    w.getCurrentThemeId = getCurrentThemeId;
    w.renderSettingsThemePicker = renderSettingsThemePicker;
    w.closeAllThemePopovers = closeAllThemePopovers;
})(window);
