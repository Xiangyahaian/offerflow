"""象遇 · 服务端邮箱监听：定时拉取 IMAP，发现新信即 AI 解析。"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Optional

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from sqlalchemy.orm import Session, joinedload

from backend.access_control import user_is_member
from backend.config import settings
from backend.database import SessionLocal
from backend.ai_assistant_mail import mail_slots_configured, sync_user_mail_insights
from backend.models import User, UserAiAssistantSettings, UserMailSettings

logger = logging.getLogger(__name__)

_stop = asyncio.Event()
_task: Optional[asyncio.Task] = None
_last_user_sync: Dict[str, float] = {}
_LOCK_PATH = Path(__file__).resolve().parent.parent / ".ai_assistant_watch.lock"
_USER_DEBOUNCE_SEC = 50.0


def _get_or_create_ai_settings(db: Session, user_id: str) -> UserAiAssistantSettings:
    row = (
        db.query(UserAiAssistantSettings)
        .filter(UserAiAssistantSettings.user_id == user_id)
        .first()
    )
    if row:
        return row
    row = UserAiAssistantSettings(user_id=user_id, auto_parse_mail=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _eligible_users(db: Session):
    return (
        db.query(User)
        .options(joinedload(User.mail_settings))
        .filter(User.is_preview_guest.is_(False))
        .join(UserMailSettings, UserMailSettings.user_id == User.id)
        .all()
    )


def _should_skip_user(user_id: str) -> bool:
    last = _last_user_sync.get(user_id)
    if last is None:
        return False
    return (time.monotonic() - last) < _USER_DEBOUNCE_SEC


def _mark_user_synced(user_id: str) -> None:
    _last_user_sync[user_id] = time.monotonic()


def run_watch_cycle() -> dict:
    """
    单次监听周期：扫描所有已配置邮箱的会员，对新邮件触发解析。
    多进程部署时用文件锁保证同一时刻仅一个 worker 执行。
    """
    if not getattr(settings, "AI_ASSISTANT_MAIL_WATCH_ENABLED", True):
        return {"skipped": True, "reason": "disabled"}

    lock_file = None
    try:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(_LOCK_PATH, "a+b")
        if sys.platform == "win32":
            lock_file.seek(0, 2)
            if lock_file.tell() < 1:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                raise BlockingIOError from e
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if lock_file:
            lock_file.close()
        return {"skipped": True, "reason": "lock_held"}
    except OSError as e:
        if lock_file:
            try:
                lock_file.close()
            except OSError:
                pass
        logger.warning("象遇监听锁不可用，本周期跳过: %s", e)
        return {"skipped": True, "reason": "lock_error"}

    stats = {
        "users_checked": 0,
        "users_synced": 0,
        "new_insights": 0,
        "errors": 0,
    }
    limit = int(getattr(settings, "AI_ASSISTANT_MAIL_WATCH_LIMIT_PER_SLOT", 25) or 25)
    db = SessionLocal()
    try:
        for user in _eligible_users(db):
            stats["users_checked"] += 1
            if not user_is_member(db, user):
                continue
            mail = user.mail_settings
            if not mail:
                continue
            p_ok, s_ok = mail_slots_configured(user, mail)
            if not p_ok and not s_ok:
                continue
            if _should_skip_user(user.id):
                continue
            ai = _get_or_create_ai_settings(db, user.id)
            try:
                sync_user_mail_insights(
                    db, user, mail, ai, limit_per_slot=limit, parse_mail=False
                )
                result = sync_user_mail_insights(
                    db, user, mail, ai, limit_per_slot=limit, fetch_mail=False
                )
                _mark_user_synced(user.id)
                stats["users_synced"] += 1
                stats["new_insights"] += int(result.get("new_insights") or 0)
                if result.get("new_insights"):
                    logger.info(
                        "象遇监听：用户 %s 解析新邮件 %s 封",
                        user.id,
                        result["new_insights"],
                    )
            except ValueError as e:
                logger.debug("象遇监听跳过用户 %s: %s", user.id, e)
            except Exception as e:
                stats["errors"] += 1
                db.rollback()
                logger.exception("象遇监听失败 user=%s: %s", user.id, e)
    finally:
        db.close()
        if lock_file:
            try:
                if sys.platform == "win32":
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            lock_file.close()

    if stats["new_insights"] or stats["errors"]:
        logger.info("象遇监听周期完成: %s", stats)
    return stats


async def _watch_loop() -> None:
    interval = max(
        30, int(getattr(settings, "AI_ASSISTANT_MAIL_WATCH_INTERVAL_SEC", 60) or 60)
    )
    logger.info("象遇邮箱监听已启动，间隔 %s 秒", interval)
    while not _stop.is_set():
        try:
            await asyncio.to_thread(run_watch_cycle)
        except Exception:
            logger.exception("象遇监听周期异常")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def start_background_watcher() -> None:
    global _task
    if not getattr(settings, "AI_ASSISTANT_MAIL_WATCH_ENABLED", True):
        logger.info("象遇邮箱监听未启用（AI_ASSISTANT_MAIL_WATCH_ENABLED=false）")
        return
    if _task and not _task.done():
        return
    _stop.clear()
    _task = asyncio.create_task(_watch_loop())


async def stop_background_watcher() -> None:
    global _task
    _stop.set()
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    logger.info("象遇邮箱监听已停止")
