"""象遇 · 拉取绑定邮箱并解析新邮件。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.ai_assistant_apply import (
    apply_mail_application_extract,
    is_recruitment_related_mail,
)
from backend.ai_assistant_demo import is_demo_mail
from backend.ai_assistant_extract import (
    MailApplicationExtract,
    MailParseResult,
    application_extract_to_json,
    parse_mail_with_llm,
)
from backend.mail_crypto import decrypt_secret
from backend.mail_imap import fetch_inbox_message_body, fetch_inbox_messages
from backend.models import (
    AiAssistantMailInsight,
    User,
    UserAiAssistantSettings,
    UserMailSettings,
)

logger = logging.getLogger(__name__)

PENDING_PARSE_SUMMARY = "新邮件，打开后由象遇解析。"
HISTORICAL_MAIL_SUMMARY = "（配置 IMAP 前收到的邮件，不计未读）"

_ALLOWED = {"qq", "foxmail", "163", "126", "yeah", "188", "other"}

BODY_STORE_MAX = 80_000


def reset_slot_watch_on_imap_saved(mail: UserMailSettings, slot: str) -> None:
    """首次/重新保存某槽位 IMAP 授权后，仅监听此后到达的邮件。"""
    now = datetime.utcnow()
    if slot == "primary":
        mail.primary_ivory_watch_since = now
        mail.primary_ivory_baseline_pending = True
    elif slot == "secondary":
        mail.secondary_ivory_watch_since = now
        mail.secondary_ivory_baseline_pending = True


def clear_slot_watch_on_imap_cleared(mail: UserMailSettings, slot: str) -> None:
    if slot == "primary":
        mail.primary_ivory_watch_since = None
        mail.primary_ivory_baseline_pending = False
    elif slot == "secondary":
        mail.secondary_ivory_watch_since = None
        mail.secondary_ivory_baseline_pending = False


def _ensure_slot_watch_started(mail: UserMailSettings, slot: str) -> None:
    """旧库已有 IMAP 但未写过 watch_since 时，在首次同步前补齐。"""
    if slot == "primary":
        if mail.primary_auth_encrypted and mail.primary_provider:
            if mail.primary_ivory_watch_since is None:
                mail.primary_ivory_watch_since = datetime.utcnow()
                mail.primary_ivory_baseline_pending = True
    elif slot == "secondary":
        if (
            mail.secondary_email
            and mail.secondary_auth_encrypted
            and mail.secondary_provider
        ):
            if mail.secondary_ivory_watch_since is None:
                mail.secondary_ivory_watch_since = datetime.utcnow()
                mail.secondary_ivory_baseline_pending = True


def _slot_watch_since(mail: UserMailSettings, slot: str) -> Optional[datetime]:
    if slot == "primary":
        return mail.primary_ivory_watch_since
    if slot == "secondary":
        return mail.secondary_ivory_watch_since
    return None


def _slot_baseline_pending(mail: UserMailSettings, slot: str) -> bool:
    if slot == "primary":
        return bool(mail.primary_ivory_baseline_pending)
    if slot == "secondary":
        return bool(mail.secondary_ivory_baseline_pending)
    return False


def _finish_slot_baseline(mail: UserMailSettings, slot: str) -> None:
    if slot == "primary":
        mail.primary_ivory_baseline_pending = False
    elif slot == "secondary":
        mail.secondary_ivory_baseline_pending = False


def _mail_received_at(mail_date: Any) -> Optional[datetime]:
    if not mail_date:
        return None
    raw = str(mail_date).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _is_new_after_watch(mail_date: Any, watch_since: Optional[datetime]) -> bool:
    """邮件收信时间不早于 IMAP 配置监听起点，才算「新邮件」。"""
    if watch_since is None:
        return False
    received = _mail_received_at(mail_date)
    if received is None:
        return False
    return received >= watch_since


def _reconcile_legacy_unread(
    db: Session,
    user_id: str,
    slot: str,
    watch_since: Optional[datetime],
) -> None:
    if watch_since is None:
        return
    rows = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            AiAssistantMailInsight.mail_slot == slot,
        )
        .all()
    )
    for row in rows:
        if not _is_new_after_watch(row.mail_date, watch_since):
            row.is_read = True
            row.is_mail_seen = True


def _slot_mailbox_address(user: User, mail: UserMailSettings, slot: str) -> str:
    if slot == "secondary":
        return (mail.secondary_email or "").strip()
    return (user.email or "").strip()


def _decrypt_auth(encrypted: str, *, label: str) -> str:
    try:
        return decrypt_secret(encrypted)
    except InvalidToken:
        raise ValueError(
            f"{label}授权码无法解密，请在邮箱读取中重新保存 IMAP 授权码"
        )


def mail_slots_configured(user: User, mail: UserMailSettings) -> Tuple[bool, bool]:
    primary = bool(mail.primary_provider and mail.primary_auth_encrypted)
    secondary = bool(
        mail.secondary_email and mail.secondary_provider and mail.secondary_auth_encrypted
    )
    return primary, secondary


def _fetch_slot_messages(
    user: User,
    mail: UserMailSettings,
    slot: str,
    limit: int = 25,
) -> Tuple[str, List[Dict[str, Any]]]:
    if slot == "primary":
        pwd = _decrypt_auth(mail.primary_auth_encrypted or "", label="主邮箱")
        items = fetch_inbox_messages(
            user.email,
            pwd,
            mail.primary_provider,
            mail.primary_imap_host,
            mail.primary_imap_port,
            limit=limit,
            include_bodies=False,
        )
        return user.email, items
    if slot == "secondary":
        pwd = _decrypt_auth(mail.secondary_auth_encrypted or "", label="第二邮箱")
        addr = mail.secondary_email or ""
        items = fetch_inbox_messages(
            addr,
            pwd,
            mail.secondary_provider,
            mail.secondary_imap_host,
            mail.secondary_imap_port,
            limit=limit,
            include_bodies=False,
        )
        return addr, items
    raise ValueError("无效邮箱槽位")


def _insight_key(user_id: str, slot: str, seq: str) -> Tuple[str, str, str]:
    return user_id, slot, str(seq)


def _existing_seqs(db: Session, user_id: str, slot: str) -> set[str]:
    rows = (
        db.query(AiAssistantMailInsight.mail_seq)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            AiAssistantMailInsight.mail_slot == slot,
        )
        .all()
    )
    return {r[0] for r in rows}


def _find_insight_row(
    db: Session, user_id: str, slot: str, seq: str
) -> Optional[AiAssistantMailInsight]:
    return (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            AiAssistantMailInsight.mail_slot == slot,
            AiAssistantMailInsight.mail_seq == str(seq),
        )
        .first()
    )


def _persist_insight_row(db: Session, row: AiAssistantMailInsight) -> AiAssistantMailInsight:
    """插入洞察记录；若并发已写入同槽位 seq，则复用已有行。"""
    existing = _find_insight_row(db, row.user_id, row.mail_slot, row.mail_seq)
    if existing:
        return existing
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        existing = _find_insight_row(db, row.user_id, row.mail_slot, row.mail_seq)
        if not existing:
            raise
        return existing


def _pending_parse_item(row: AiAssistantMailInsight) -> Dict[str, Any]:
    return {
        "insight_id": row.id,
        "mail_slot": row.mail_slot,
        "mail_seq": row.mail_seq,
        "subject": row.subject,
    }


def _fetch_mail_body_text(
    user: User,
    mail: UserMailSettings,
    slot: str,
    seq: str,
    snippet: str,
    *,
    max_len: int = BODY_STORE_MAX,
) -> str:
    fallback = (snippet or "").strip()
    try:
        if slot == "primary" and mail.primary_auth_encrypted:
            pwd = _decrypt_auth(mail.primary_auth_encrypted, label="主邮箱")
            body = fetch_inbox_message_body(
                user.email,
                pwd,
                mail.primary_provider,
                seq,
                mail.primary_imap_host,
                mail.primary_imap_port,
            )
            text = (body.get("body_text") or body.get("snippet") or fallback).strip()
            return text[:max_len] if text else fallback[:max_len]
        if slot == "secondary" and mail.secondary_auth_encrypted:
            pwd = _decrypt_auth(mail.secondary_auth_encrypted, label="第二邮箱")
            body = fetch_inbox_message_body(
                mail.secondary_email or "",
                pwd,
                mail.secondary_provider,
                seq,
                mail.secondary_imap_host,
                mail.secondary_imap_port,
            )
            text = (body.get("body_text") or body.get("snippet") or fallback).strip()
            return text[:max_len] if text else fallback[:max_len]
    except Exception as e:
        logger.info("象遇拉取正文跳过 seq=%s: %s", seq, e)
    return fallback[:max_len]


def _fallback_summary(subject: str, from_addr: str, snippet: str) -> str:
    subj = (subject or "(无主题)").strip()
    frm = (from_addr or "未知发件人").strip()
    sn = (snippet or "").strip()[:280]
    return f"【{frm}】{subj}" + (f"。{sn}" if sn else "")


def _try_apply_insight_application(
    db: Session,
    user: User,
    ai: UserAiAssistantSettings,
    row: AiAssistantMailInsight,
    application: Optional[MailApplicationExtract],
) -> Optional[Dict[str, Any]]:
    """将结构化抽取写入实习/校招表（每封邮件仅一次）。"""
    if row.application_applied or not application:
        return None
    if not (application.company or "").strip():
        return None
    if not is_recruitment_related_mail(
        row.category,
        application,
        subject=row.subject or "",
        body_snippet=(row.body_text or row.summary or "")[:2000],
    ):
        return {"ok": False, "action": "skip", "reason": "非实习/校招相关邮件"}
    try:
        result = apply_mail_application_extract(
            db,
            user.id,
            application,
            mail_subject=row.subject or "",
            ai=ai,
        )
        row.application_apply_result = json.dumps(result, ensure_ascii=False)
        if result.get("ok"):
            row.application_applied = True
        return result
    except Exception as e:
        logger.exception("邮件投递表同步失败 insight=%s: %s", row.id, e)
        err = {"ok": False, "action": "error", "reason": str(e)[:200]}
        row.application_apply_result = json.dumps(err, ensure_ascii=False)
        return err


def _parse_new_mail(
    user: User,
    mail: UserMailSettings,
    ai: UserAiAssistantSettings,
    slot: str,
    seq: str,
    subject: str,
    from_addr: str,
    snippet: str,
) -> Tuple[str, str, bool, str, Optional[str], Optional[MailApplicationExtract]]:
    """新邮件：拉取全文、LLM 摘要+JSON 抽取。"""
    body_full = _fetch_mail_body_text(
        user, mail, slot, seq, snippet, max_len=BODY_STORE_MAX
    )
    if ai.auto_parse_mail:
        parsed: MailParseResult = parse_mail_with_llm(
            ai,
            subject=subject,
            from_addr=from_addr,
            snippet=snippet,
            body_text=body_full,
        )
        extract_json = application_extract_to_json(parsed.application)
        return (
            parsed.summary,
            parsed.category,
            True,
            body_full,
            extract_json,
            parsed.application,
        )
    summary = _fallback_summary(subject, from_addr, snippet or body_full[:280])
    return summary, "general", True, body_full, None, None


def _parse_insight_rows(
    db: Session,
    user: User,
    mail: UserMailSettings,
    ai: UserAiAssistantSettings,
    pending_rows: List[tuple[AiAssistantMailInsight, Dict[str, Any]]],
) -> Tuple[int, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """解析待处理邮件洞察，返回 new_count / new_items / applications_updated / pending_parse_items。"""
    new_count = 0
    new_items: List[Dict[str, Any]] = []
    applications_updated: List[Dict[str, Any]] = []
    pending_parse_items: List[Dict[str, Any]] = []

    for row, it in pending_rows:
        subject = str(it.get("subject") or row.subject or "")
        from_addr = str(it.get("from_addr") or row.from_addr or "")
        snippet = str(it.get("snippet") or "")
        try:
            summary, category, is_parsed, body_full, extract_json, application = (
                _parse_new_mail(
                    user,
                    mail,
                    ai,
                    row.mail_slot,
                    row.mail_seq,
                    subject,
                    from_addr,
                    snippet,
                )
            )
            row.summary = summary
            row.category = category
            row.is_parsed = is_parsed
            row.from_addr = from_addr[:300]
            if subject:
                row.subject = subject[:500]
            if body_full:
                row.body_text = body_full[:BODY_STORE_MAX]
            if extract_json:
                row.application_extract = extract_json
        except Exception as e:
            logger.warning(
                "邮件解析失败 slot=%s seq=%s: %s", row.mail_slot, row.mail_seq, e
            )
            row.summary = "邮件解析失败，请稍后在邮箱解析中重试"
            row.is_parsed = False
            application = None
            extract_json = None

        if row.is_parsed:
            new_count += 1
            apply_result = _try_apply_insight_application(
                db, user, ai, row, application
            )
            if apply_result and apply_result.get("ok"):
                applications_updated.append(
                    {
                        "insight_id": row.id,
                        "subject": row.subject,
                        **apply_result,
                    }
                )
            new_items.append(
                {
                    "insight_id": row.id,
                    "mail_slot": row.mail_slot,
                    "mail_seq": row.mail_seq,
                    "subject": row.subject,
                }
            )
        else:
            pending_parse_items.append(_pending_parse_item(row))
        db.commit()

    return new_count, new_items, applications_updated, pending_parse_items


def _sync_parse_pending_only(
    db: Session,
    user: User,
    mail: UserMailSettings,
    ai: UserAiAssistantSettings,
    *,
    slots_only: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """仅解析库中待处理洞察（不再拉 IMAP）。"""
    q = db.query(AiAssistantMailInsight).filter(
        AiAssistantMailInsight.user_id == user.id,
        AiAssistantMailInsight.is_parsed.is_(False),
    )
    if slots_only:
        allow = {s.strip().lower() for s in slots_only if s}
        q = q.filter(AiAssistantMailInsight.mail_slot.in_(list(allow)))
    rows = q.order_by(AiAssistantMailInsight.created_at).all()
    pending_rows = [(r, {}) for r in rows]
    new_count, new_items, applications_updated, pending_parse_items = _parse_insight_rows(
        db, user, mail, ai, pending_rows
    )
    ai.updated_at = datetime.utcnow()
    db.commit()
    return {
        "scanned": 0,
        "new_insights": new_count,
        "new_items": new_items,
        "pending_parse_items": pending_parse_items,
        "applications_updated": applications_updated,
        "slots": slots_only or [],
        "synced_at": datetime.utcnow().isoformat() + "Z",
    }


def sync_user_mail_insights(
    db: Session,
    user: User,
    mail: UserMailSettings,
    ai: UserAiAssistantSettings,
    *,
    limit_per_slot: int = 20,
    slots_only: Optional[List[str]] = None,
    parse_mail: bool = True,
    fetch_mail: bool = True,
) -> Dict[str, Any]:
    """拉取邮箱新信并写入解析结果。返回统计。"""
    if not fetch_mail:
        return _sync_parse_pending_only(
            db, user, mail, ai, slots_only=slots_only
        )

    primary_ok, secondary_ok = mail_slots_configured(user, mail)
    if not primary_ok and not secondary_ok:
        raise ValueError("请先在「邮箱读取」中配置 IMAP 授权码")

    new_count = 0
    new_items: List[Dict[str, Any]] = []
    pending_parse_items: List[Dict[str, Any]] = []
    applications_updated: List[Dict[str, Any]] = []
    scanned = 0
    slots: List[str] = []
    if primary_ok:
        slots.append("primary")
    if secondary_ok:
        slots.append("secondary")
    if slots_only:
        allow = {s.strip().lower() for s in slots_only if s}
        slots = [s for s in slots if s in allow]
        if not slots:
            raise ValueError("指定同步的邮箱槽位未配置")

    for slot in slots:
        pending_rows: List[tuple[AiAssistantMailInsight, Dict[str, Any]]] = []
        newly_staged: List[Dict[str, Any]] = []
        _ensure_slot_watch_started(mail, slot)
        watch_since = _slot_watch_since(mail, slot)
        baseline_pending = _slot_baseline_pending(mail, slot)
        _reconcile_legacy_unread(db, user.id, slot, watch_since)

        mailbox, items = _fetch_slot_messages(user, mail, slot, limit=limit_per_slot)
        known = _existing_seqs(db, user.id, slot)
        for it in items:
            scanned += 1
            seq = str(it.get("uid") or it.get("seq") or "")
            if not seq:
                continue
            existing = _find_insight_row(db, user.id, slot, seq)
            if existing:
                known.add(seq)
                if not existing.is_parsed:
                    pending_rows.append((existing, it))
                continue
            if seq in known:
                continue
            subject = str(it.get("subject") or "")
            from_addr = str(it.get("from_addr") or "")
            snippet = str(it.get("snippet") or "")
            mail_date = it.get("date")

            is_historical = (
                not is_demo_mail(subject, snippet)
                and (
                    baseline_pending
                    or not _is_new_after_watch(mail_date, watch_since)
                )
            )
            if is_historical:
                row = AiAssistantMailInsight(
                    user_id=user.id,
                    mail_slot=slot,
                    mail_seq=seq,
                    mailbox=mailbox,
                    subject=subject[:500],
                    from_addr=from_addr[:300],
                    mail_date=str(mail_date)[:64] if mail_date else None,
                    summary=HISTORICAL_MAIL_SUMMARY,
                    body_text=None,
                    category="general",
                    is_read=True,
                    is_mail_seen=True,
                    is_parsed=True,
                    application_extract=None,
                    application_applied=False,
                    created_at=datetime.utcnow(),
                )
                row = _persist_insight_row(db, row)
                known.add(seq)
                continue

            row = AiAssistantMailInsight(
                user_id=user.id,
                mail_slot=slot,
                mail_seq=seq,
                mailbox=mailbox,
                subject=subject[:500],
                from_addr=from_addr[:300],
                mail_date=str(mail_date)[:64] if mail_date else None,
                summary="新邮件已收到，正在解析…",
                body_text=None,
                category="general",
                is_read=False,
                is_mail_seen=False,
                is_parsed=False,
                application_extract=None,
                application_applied=False,
                created_at=datetime.utcnow(),
            )
            row = _persist_insight_row(db, row)
            known.add(seq)
            if row.is_parsed:
                continue
            pending_rows.append((row, it))
            newly_staged.append(_pending_parse_item(row))

        if pending_rows:
            pending_parse_items.extend(newly_staged)
            if parse_mail:
                parsed_new, parsed_items, parsed_apps, still_pending = _parse_insight_rows(
                    db, user, mail, ai, pending_rows
                )
                new_count += parsed_new
                new_items.extend(parsed_items)
                applications_updated.extend(parsed_apps)

        if baseline_pending:
            _finish_slot_baseline(mail, slot)
            _reconcile_legacy_unread(db, user.id, slot, watch_since)

    ai.updated_at = datetime.utcnow()
    db.commit()
    return {
        "scanned": scanned,
        "new_insights": new_count,
        "new_items": new_items,
        "pending_parse_items": pending_parse_items,
        "applications_updated": applications_updated,
        "slots": slots,
        "synced_at": datetime.utcnow().isoformat() + "Z",
    }


def mark_all_mail_seen(db: Session, user_id: str) -> int:
    """邮箱读取页：将全部未读邮件标为已读（仅 is_mail_seen，不影响象遇 is_read）。"""
    rows = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            AiAssistantMailInsight.is_mail_seen.is_(False),
        )
        .all()
    )
    if not rows:
        return 0
    for row in rows:
        row.is_mail_seen = True
    db.commit()
    return len(rows)


def mark_mail_seen(
    db: Session,
    user: User,
    mail: UserMailSettings,
    *,
    mail_slot: str,
    mail_seq: str,
) -> bool:
    """邮箱读取页打开邮件：仅标记 is_mail_seen，不影响 象遇未读。"""
    slot = mail_slot.strip().lower()
    seq = str(mail_seq).strip()
    row = _find_insight_row(db, user.id, slot, seq)
    if row:
        if row.is_mail_seen:
            return False
        row.is_mail_seen = True
        db.commit()
        return True

    mailbox = _slot_mailbox_address(user, mail, slot)
    row = AiAssistantMailInsight(
        user_id=user.id,
        mail_slot=slot,
        mail_seq=seq,
        mailbox=mailbox,
        subject="",
        from_addr="",
        mail_date=None,
        summary="",
        category="general",
        is_read=False,
        is_mail_seen=True,
        is_parsed=False,
        application_extract=None,
        application_applied=False,
        created_at=datetime.utcnow(),
    )
    row = _persist_insight_row(db, row)
    if not row.is_mail_seen:
        row.is_mail_seen = True
    db.commit()
    return True


def mail_unread_status(db: Session, user_id: str) -> Dict[str, Any]:
    """待 AI 解析、未在邮箱页打开、侧栏角标汇总。"""
    pending = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            AiAssistantMailInsight.is_parsed.is_(False),
        )
        .order_by(desc(AiAssistantMailInsight.created_at))
        .limit(80)
        .all()
    )
    unseen = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            AiAssistantMailInsight.is_mail_seen.is_(False),
        )
        .order_by(desc(AiAssistantMailInsight.created_at))
        .limit(80)
        .all()
    )
    attention = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            ~and_(
                AiAssistantMailInsight.is_parsed.is_(True),
                AiAssistantMailInsight.is_mail_seen.is_(True),
            ),
        )
        .order_by(desc(AiAssistantMailInsight.created_at))
        .limit(80)
        .all()
    )

    def _item(r: AiAssistantMailInsight) -> Dict[str, Any]:
        return {
            "insight_id": r.id,
            "mail_slot": r.mail_slot,
            "mail_seq": r.mail_seq,
            "subject": r.subject,
        }

    return {
        "mail_nav_count": len(attention),
        "pending_parse_count": len(pending),
        "pending_parse_items": [_item(r) for r in pending],
        "unseen_count": len(unseen),
        "unseen_items": [_item(r) for r in unseen],
    }


def mark_all_mail_insights_read(db: Session, user_id: str) -> int:
    """象遇打开邮箱解析面板：仅标 is_read，不改动 is_mail_seen（邮箱读取页独立）。"""
    rows = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            AiAssistantMailInsight.is_parsed.is_(True),
            AiAssistantMailInsight.is_read.is_(False),
        )
        .all()
    )
    if not rows:
        return 0
    for row in rows:
        row.is_read = True
    db.commit()
    return len(rows)


def open_mail_insight(
    db: Session,
    user: User,
    mail: UserMailSettings,
    ai: UserAiAssistantSettings,
    *,
    insight_id: Optional[str] = None,
    mail_slot: Optional[str] = None,
    mail_seq: Optional[str] = None,
) -> Dict[str, Any]:
    """象遇打开单条解析：仅标 is_read，不改动 is_mail_seen。"""
    row: Optional[AiAssistantMailInsight] = None
    if insight_id:
        row = (
            db.query(AiAssistantMailInsight)
            .filter(
                AiAssistantMailInsight.id == insight_id,
                AiAssistantMailInsight.user_id == user.id,
            )
            .first()
        )
    elif mail_slot and mail_seq:
        row = (
            db.query(AiAssistantMailInsight)
            .filter(
                AiAssistantMailInsight.user_id == user.id,
                AiAssistantMailInsight.mail_slot == mail_slot,
                AiAssistantMailInsight.mail_seq == str(mail_seq),
            )
            .first()
        )
    if not row:
        raise ValueError("邮件记录不存在，请先同步邮箱")

    was_unread = bool(row.is_parsed and not row.is_read)
    row.is_read = True
    apply_result: Optional[Dict[str, Any]] = None
    application = None
    if not row.is_parsed or not (row.body_text or "").strip():
        subject = row.subject or ""
        from_addr = row.from_addr or ""
        summary, category, is_parsed, body_full, extract_json, application = _parse_new_mail(
            user,
            mail,
            ai,
            row.mail_slot,
            row.mail_seq,
            subject,
            from_addr,
            "",
        )
        if not row.is_parsed:
            row.summary = summary
            row.category = category
            row.is_parsed = is_parsed
            if extract_json:
                row.application_extract = extract_json
        if body_full and not (row.body_text or "").strip():
            row.body_text = body_full[:BODY_STORE_MAX]
    elif row.application_extract and not row.application_applied:
        from backend.ai_assistant_extract import application_extract_from_json

        application = application_extract_from_json(row.application_extract)

    apply_result = _try_apply_insight_application(db, user, ai, row, application)

    db.commit()
    db.refresh(row)
    return {
        "insight": row,
        "chat_message": None,
        "newly_parsed": False,
        "was_unread": was_unread,
        "application_sync": apply_result,
    }
