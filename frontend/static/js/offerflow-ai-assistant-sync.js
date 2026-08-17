/**
 * 象遇 · 未读角标轮询（轻量）
 * 邮件 IMAP/AI 同步仅由服务端 watcher 或用户在邮箱/AI 页手动触发
 * v=20260606readall2
 */
(function (global) {
    'use strict';

    var UNREAD_POLL_MS = 60000;
    var MAIL_TOAST_MS = 5600;
    var _unreadTimer = null;
    var _backgroundStarted = false;
    var _syncInFlight = false;
    var _booted = false;
    var _unseenMap = {};
    var _unreadBootstrapped = false;
    var _notifiedPendingKeys = {};
    var _notifiedIvoryKeys = {};

    function isOnMailReadPage() {
        return !!document.getElementById('mailApp');
    }

    function canSync() {
        return !!global.gUserIsMember && typeof global.api === 'function';
    }

    function canPollUnread() {
        return !global.gUserIsPreview && typeof global.api === 'function';
    }

    function unreadKey(slot, seq) {
        return String(slot || '') + ':' + String(seq || '');
    }

    function notifyApplicationsUpdated(updates) {
        if (!updates || !updates.length) return;
        if (typeof global.toast !== 'function') return;
        var u = updates[0];
        var company = (u.company || '').trim() || '投递记录';
        var action = u.action || '';
        var msg = '已根据邮件更新：' + company;
        if (action.indexOf('created') >= 0) {
            msg = '已根据邮件新建投递：' + company;
        }
        global.toast(msg, 'success', { duration: MAIL_TOAST_MS });
    }

    function notifyMailReceived(items) {
        if (!items || !items.length) return;
        if (typeof global.toast !== 'function') return;
        if (document.hidden) return;

        var fresh = [];
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            var k = unreadKey(it.mail_slot, it.mail_seq);
            if (_notifiedPendingKeys[k]) continue;
            _notifiedPendingKeys[k] = true;
            fresh.push(it);
        }
        if (!fresh.length) return;

        if (fresh.length === 1) {
            var subj = (fresh[0].subject || '').trim() || '新邮件';
            global.toast('收到新邮件：' + subj, 'info', { duration: MAIL_TOAST_MS });
        } else {
            global.toast('收到 ' + fresh.length + ' 封新邮件', 'info', { duration: MAIL_TOAST_MS });
        }
    }

    function notifyMailParsed(items) {
        if (!items || !items.length) return;
        if (typeof global.toast !== 'function') return;
        if (document.hidden) return;

        var fresh = [];
        for (var j = 0; j < items.length; j++) {
            var row = items[j];
            var key = unreadKey(row.mail_slot, row.mail_seq);
            if (_notifiedIvoryKeys[key]) continue;
            _notifiedIvoryKeys[key] = true;
            fresh.push(row);
        }
        if (!fresh.length) return;

        if (fresh.length === 1) {
            var subject = (fresh[0].subject || '').trim() || '新邮件';
            global.toast('象遇已解析：' + subject, 'info', { duration: MAIL_TOAST_MS });
        } else {
            global.toast('象遇已解析 ' + fresh.length + ' 封新邮件', 'info', { duration: MAIL_TOAST_MS });
        }
    }

    function syncInboxQuiet() {
        if (!canSync()) return Promise.resolve(null);
        return global
            .api('/api/mail/sync-inbox', { method: 'POST' })
            .then(function (r) {
                if (r && r.pending_parse_items && r.pending_parse_items.length) {
                    notifyMailReceived(r.pending_parse_items);
                }
                return refreshUnreadBadges().then(function () {
                    return r;
                });
            })
            .catch(function () {
                return null;
            });
    }

    function parseMailQuiet() {
        if (!canSync()) return Promise.resolve(null);
        return global
            .api('/api/mail/parse-pending', { method: 'POST' })
            .then(function (r) {
                if (r && r.new_insights > 0) {
                    notifyMailParsed(r.new_items || []);
                }
                if (r && r.applications_updated && r.applications_updated.length) {
                    notifyApplicationsUpdated(r.applications_updated);
                }
                return refreshUnreadBadges().then(function () {
                    return r;
                });
            })
            .catch(function () {
                return null;
            });
    }

    function syncMailQuiet(options) {
        if (!canSync()) return Promise.resolve(null);
        options = options || {};
        if (_syncInFlight) return Promise.resolve(null);
        _syncInFlight = true;
        return syncInboxQuiet()
            .then(function (stub) {
                var hasPending =
                    stub &&
                    stub.pending_parse_items &&
                    stub.pending_parse_items.length;
                if (!hasPending && options.inboxOnly) {
                    return stub;
                }
                return parseMailQuiet().then(function (parsed) {
                    return parsed || stub;
                });
            })
            .finally(function () {
                _syncInFlight = false;
                refreshUnreadBadges();
            });
    }

    function applyUnseenMap(items) {
        var map = {};
        (items || []).forEach(function (it) {
            map[unreadKey(it.mail_slot, it.mail_seq)] = it;
        });
        _unseenMap = map;
        return map;
    }

    function getUnreadMap() {
        return _unseenMap;
    }

    function isUnread(slot, seq) {
        return !!_unseenMap[unreadKey(slot, seq)];
    }

    function setNavBadge(el, count) {
        if (!el) return;
        if (count > 0) {
            el.textContent = count > 99 ? '99+' : String(count);
            el.style.display = '';
        } else {
            el.style.display = 'none';
        }
    }

    /** 邮箱读取页：右下角「邮箱解析」浮动按钮角标 */
    function syncIcMailDockBadges(count) {
        if (!isOnMailReadPage()) return;
        var unread = Math.max(0, count | 0);
        var el = document.getElementById('icMailFabBadge');
        if (el) {
            if (unread > 0) {
                el.hidden = false;
                el.textContent = unread > 99 ? '99+' : String(unread);
            } else {
                el.hidden = true;
                el.textContent = '0';
            }
        }
        var fabBtn = document.getElementById('icMailFab');
        if (fabBtn) fabBtn.classList.toggle('has-unread', unread > 0);
    }

    function dispatchIvoryUnread(count, items) {
        syncIcMailDockBadges(count);
        if (typeof global.dispatchEvent !== 'function') return;
        global.dispatchEvent(
            new CustomEvent('offerflow:ai-assistant-unread', {
                detail: { count: count, items: items || [] },
            })
        );
    }

    function refreshUnreadBadges() {
        if (!canPollUnread()) {
            setNavBadge(document.getElementById('navMailUnreadBadge'), 0);
            dispatchIvoryUnread(0, []);
            var inboxBadge = document.getElementById('mailInboxUnreadBadge');
            if (inboxBadge) inboxBadge.style.display = 'none';
            _unseenMap = {};
            _unreadBootstrapped = false;
            if (typeof global.dispatchEvent === 'function') {
                global.dispatchEvent(new CustomEvent('offerflow:mail-unread', { detail: { map: {} } }));
            }
            return Promise.resolve({ unread_count: 0, items: [] });
        }
        return Promise.all([
            global.api('/api/mail/unread-status'),
            global.api('/api/ai-assistant/unread-status'),
        ])
            .then(function (results) {
                var mailData = results[0] || {};
                var aiAssistantData = results[1] || {};
                var mailNavCount =
                    mailData.mail_nav_count != null
                        ? mailData.mail_nav_count
                        : mailData.pending_parse_count || 0;
                var aiAssistantCount = aiAssistantData.unread_count || 0;
                var unseenItems = mailData.unseen_items || [];

                applyUnseenMap(unseenItems);

                if (_unreadBootstrapped) {
                    var newlyPending = (mailData.pending_parse_items || []).filter(function (it) {
                        return !_notifiedPendingKeys[unreadKey(it.mail_slot, it.mail_seq)];
                    });
                    if (newlyPending.length) notifyMailReceived(newlyPending);

                    var newlyAiAssistant = (aiAssistantData.items || []).filter(function (it) {
                        return !_notifiedIvoryKeys[unreadKey(it.mail_slot, it.mail_seq)];
                    });
                    if (newlyAiAssistant.length) notifyMailParsed(newlyAiAssistant);
                }
                _unreadBootstrapped = true;

                setNavBadge(document.getElementById('navMailUnreadBadge'), mailNavCount);
                dispatchIvoryUnread(aiAssistantCount, aiAssistantData.items || []);

                var inboxBadge = document.getElementById('mailInboxUnreadBadge');
                if (inboxBadge) {
                    var unseenCount = mailData.unseen_count || 0;
                    if (unseenCount > 0) {
                        inboxBadge.textContent = unseenCount > 99 ? '99+' : String(unseenCount);
                        inboxBadge.style.display = '';
                    } else {
                        inboxBadge.style.display = 'none';
                    }
                }

                if (typeof global.dispatchEvent === 'function') {
                    global.dispatchEvent(
                        new CustomEvent('offerflow:mail-unread', {
                            detail: { map: _unseenMap, count: mailData.unseen_count || 0 },
                        })
                    );
                }
                return { mail: mailData, aiAssistant: aiAssistantData };
            })
            .catch(function () {
                return null;
            });
    }

    function markAllIvoryInsightsRead() {
        dispatchIvoryUnread(0, []);
        if (!canPollUnread()) return Promise.resolve({ marked_count: 0 });
        return global
            .api('/api/ai-assistant/insights/read-all', { method: 'POST' })
            .then(function (r) {
                return refreshUnreadBadges().then(function () {
                    return r || { marked_count: 0 };
                });
            })
            .catch(function () {
                return refreshUnreadBadges();
            });
    }

    function openInsightQuiet(body) {
        if (!canPollUnread()) return Promise.resolve(null);
        return global
            .api('/api/ai-assistant/insights/open', { method: 'POST', body: body })
            .then(function (r) {
                var ins = r && r.insight;
                if (ins) {
                    _notifiedIvoryKeys[unreadKey(ins.mail_slot, ins.mail_seq)] = true;
                }
                refreshUnreadBadges();
                return r;
            })
            .catch(function () {
                return null;
            });
    }

    function markMailSeenQuiet(body) {
        if (!canPollUnread()) return Promise.resolve(null);
        return global
            .api('/api/mail/mark-seen', { method: 'POST', body: body })
            .then(function (r) {
                refreshUnreadBadges();
                return r;
            })
            .catch(function () {
                return null;
            });
    }

    function tickUnread() {
        if (document.hidden || !canPollUnread()) return;
        refreshUnreadBadges();
    }

    function stopBackgroundSync() {
        _backgroundStarted = false;
        if (_unreadTimer) {
            clearInterval(_unreadTimer);
            _unreadTimer = null;
        }
        setNavBadge(document.getElementById('navMailUnreadBadge'), 0);
        _unseenMap = {};
        _unreadBootstrapped = false;
        _notifiedPendingKeys = {};
        _notifiedIvoryKeys = {};
    }

    function ensureBackgroundSync() {
        if (_backgroundStarted) return;
        if (!canPollUnread()) return;
        _backgroundStarted = true;
        _unreadTimer = setInterval(tickUnread, UNREAD_POLL_MS);
        setTimeout(tickUnread, 8000);
    }

    function restartBackgroundSync() {
        stopBackgroundSync();
        ensureBackgroundSync();
    }

    function install() {
        if (_booted) return;
        _booted = true;
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) tickUnread();
        });
    }

    global.OfferFlowIvory = {
        syncInboxQuiet: syncInboxQuiet,
        parseMailQuiet: parseMailQuiet,
        syncMailQuiet: syncMailQuiet,
        refreshUnreadBadges: refreshUnreadBadges,
        notifyNewMail: notifyMailReceived,
        openInsightQuiet: openInsightQuiet,
        markAllIvoryInsightsRead: markAllIvoryInsightsRead,
        syncIcMailDockBadges: syncIcMailDockBadges,
        markMailSeenQuiet: markMailSeenQuiet,
        getUnreadMap: getUnreadMap,
        isUnread: isUnread,
        ensureBackgroundSync: ensureBackgroundSync,
        restartBackgroundSync: restartBackgroundSync,
        stopBackgroundSync: stopBackgroundSync,
        isOnMailReadPage: isOnMailReadPage,
    };

    install();
})(window);
