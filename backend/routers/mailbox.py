"""邮箱读取：配置 IMAP、拉取收件箱（只读）。"""
from __future__ import annotations

import copy
import time
from typing import Any, Literal

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.mail_crypto import decrypt_secret, ensure_encrypted
from backend.mail_imap import fetch_inbox_message_body, fetch_inbox_messages
from backend.ai_assistant_mail import (
    clear_slot_watch_on_imap_cleared,
    mail_unread_status,
    mark_all_mail_seen,
    mark_mail_seen,
    reset_slot_watch_on_imap_saved,
    sync_user_mail_insights,
)
from backend.mail_demo import (
    DEMO_COMPANIES,
    demo_company_ids,
    get_demo_exam_schedule,
    resolve_demo_recipient,
    send_demo_mail,
    sync_demo_mail,
)
from backend.models import User, UserAiAssistantSettings, UserMailSettings
from backend.schemas import (
    AiAssistantSyncResponse,
    MailDemoCompanyItem,
    MailDemoOptionsResponse,
    MailDemoSendRequest,
    MailDemoSendResponse,
    MailDemoSyncRequest,
    MailDemoSyncResponse,
    MailMarkSeenRequest,
    MailMessageBodyResponse,
    MailMessagesResponse,
    MailSettingsResponse,
    MailSettingsUpdate,
    MailUnreadItem,
    MailUnreadStatusResponse,
)

router = APIRouter(prefix="/api/mail", tags=["邮箱读取"])

_ALLOWED = {"qq", "foxmail", "163", "126", "yeah", "188", "other"}

# 进程内短时缓存：重复打开「邮箱读取」时可秒开（TTL 内不重复连 IMAP）
_MAIL_LIST_CACHE: dict[tuple[str, str, int], tuple[float, str, list[dict[str, Any]]]] = {}
_MAIL_CACHE_TTL_SEC = 72.0


def _mail_cache_key(user_id: str, slot: str, limit: int) -> tuple[str, str, int]:
    return (user_id, slot, limit)


def _mail_list_cache_get(user_id: str, slot: str, limit: int) -> tuple[str, list[dict[str, Any]]] | None:
    key = _mail_cache_key(user_id, slot, limit)
    hit = _MAIL_LIST_CACHE.get(key)
    if not hit:
        return None
    ts, mailbox, items = hit
    if time.monotonic() - ts > _MAIL_CACHE_TTL_SEC:
        del _MAIL_LIST_CACHE[key]
        return None
    return mailbox, copy.deepcopy(items)


def _mail_list_cache_set(user_id: str, slot: str, limit: int, mailbox: str, items: list[dict[str, Any]]) -> None:
    _MAIL_LIST_CACHE[_mail_cache_key(user_id, slot, limit)] = (
        time.monotonic(),
        mailbox,
        copy.deepcopy(items),
    )


def _invalidate_mail_list_cache_for_user(user_id: str) -> None:
    for k in list(_MAIL_LIST_CACHE.keys()):
        if k[0] == user_id:
            del _MAIL_LIST_CACHE[k]


def _decrypt_mail_auth(encrypted: str, *, slot_label: str = "邮箱") -> str:
    try:
        return decrypt_secret(encrypted)
    except InvalidToken:
        raise HTTPException(
            status_code=400,
            detail=f"{slot_label}授权码无法解密（可能因系统密钥已更换），请在邮箱读取设置中重新填写并保存 IMAP 授权码",
        )


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


def _get_or_create_settings(db: Session, user_id: str) -> UserMailSettings:
    row = db.query(UserMailSettings).filter(UserMailSettings.user_id == user_id).first()
    if row:
        return row
    row = UserMailSettings(user_id=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _settings_to_response(user: User, s: UserMailSettings) -> MailSettingsResponse:
    return MailSettingsResponse(
        primary_email=user.email,
        primary_provider=s.primary_provider,
        primary_imap_host=s.primary_imap_host,
        primary_imap_port=s.primary_imap_port or 993,
        primary_configured=bool(s.primary_provider and s.primary_auth_encrypted),
        secondary_email=s.secondary_email,
        secondary_provider=s.secondary_provider,
        secondary_imap_host=s.secondary_imap_host,
        secondary_imap_port=s.secondary_imap_port or 993,
        secondary_configured=bool(
            s.secondary_email and s.secondary_provider and s.secondary_auth_encrypted
        ),
    )


@router.get("/settings", response_model=MailSettingsResponse)
def get_mail_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = _get_or_create_settings(db, current_user.id)
    return _settings_to_response(current_user, s)


@router.put("/settings", response_model=MailSettingsResponse)
def update_mail_settings(
    body: MailSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = _get_or_create_settings(db, current_user.id)

    if getattr(body, "primary_email", None) is not None:
        em = (body.primary_email or "").strip()
        if em:
            current_user.email = em

    if body.primary_provider is not None:
        p = (body.primary_provider or "").strip().lower()
        if p and p not in _ALLOWED:
            raise HTTPException(status_code=400, detail="主邮箱类型无效")
        s.primary_provider = p or None

    if body.primary_imap_host is not None:
        s.primary_imap_host = (body.primary_imap_host or "").strip() or None
    if body.primary_imap_port is not None:
        s.primary_imap_port = int(body.primary_imap_port)

    if body.primary_auth_code is not None:
        code = body.primary_auth_code
        if code == "":
            s.primary_auth_encrypted = None
            clear_slot_watch_on_imap_cleared(s, "primary")
        else:
            if not s.primary_auth_encrypted:
                reset_slot_watch_on_imap_saved(s, "primary")
            s.primary_auth_encrypted = ensure_encrypted(code.strip())

    if body.secondary_email is not None:
        em = (body.secondary_email or "").strip()
        s.secondary_email = em or None
        if not em:
            s.secondary_provider = None
            s.secondary_imap_host = None
            s.secondary_auth_encrypted = None
            clear_slot_watch_on_imap_cleared(s, "secondary")

    if body.secondary_provider is not None:
        p2 = (body.secondary_provider or "").strip().lower()
        if p2 and p2 not in _ALLOWED:
            raise HTTPException(status_code=400, detail="第二邮箱类型无效")
        s.secondary_provider = p2 or None

    if body.secondary_imap_host is not None:
        s.secondary_imap_host = (body.secondary_imap_host or "").strip() or None
    if body.secondary_imap_port is not None:
        s.secondary_imap_port = int(body.secondary_imap_port)

    if body.secondary_auth_code is not None:
        c2 = body.secondary_auth_code
        if c2 == "":
            s.secondary_auth_encrypted = None
            clear_slot_watch_on_imap_cleared(s, "secondary")
        else:
            if not s.secondary_auth_encrypted:
                reset_slot_watch_on_imap_saved(s, "secondary")
            s.secondary_auth_encrypted = ensure_encrypted(c2.strip())

    if s.secondary_email and (not s.secondary_provider or not s.secondary_auth_encrypted):
        raise HTTPException(
            status_code=400,
            detail="填写第二邮箱时，需同时选择邮箱类型并填写授权码",
        )
    if s.primary_auth_encrypted and not s.primary_provider:
        raise HTTPException(
            status_code=400,
            detail="已保存主邮箱授权码时请选择邮箱类型；或勾选「清除主邮箱已保存的授权码」",
        )

    db.commit()
    db.refresh(s)
    _invalidate_mail_list_cache_for_user(current_user.id)
    return _settings_to_response(current_user, s)


@router.get("/unread-status", response_model=MailUnreadStatusResponse)
def mail_unread_status_api(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """邮箱侧未读：待解析角标 + 未打开列表圆点。"""
    data = mail_unread_status(db, current_user.id)
    return MailUnreadStatusResponse(
        mail_nav_count=int(data["mail_nav_count"]),
        pending_parse_count=int(data["pending_parse_count"]),
        pending_parse_items=[MailUnreadItem(**x) for x in data["pending_parse_items"]],
        unseen_count=int(data["unseen_count"]),
        unseen_items=[MailUnreadItem(**x) for x in data["unseen_items"]],
    )


@router.post("/sync-inbox", response_model=AiAssistantSyncResponse)
def mail_sync_inbox(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """拉取 IMAP 新信并写入待解析占位（立即驱动侧栏角标，不调用 AI）。"""
    mail = _get_or_create_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)
    try:
        stats = sync_user_mail_insights(
            db, current_user, mail, ai, parse_mail=False
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"收件箱同步失败：{e!s}")
    _invalidate_mail_list_cache_for_user(current_user.id)
    return AiAssistantSyncResponse(**stats)


@router.post("/parse-pending", response_model=AiAssistantSyncResponse)
def mail_parse_pending(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """解析库中待处理邮件（不再拉 IMAP）。"""
    mail = _get_or_create_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)
    try:
        stats = sync_user_mail_insights(
            db, current_user, mail, ai, fetch_mail=False
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"邮件解析失败：{e!s}")
    return AiAssistantSyncResponse(**stats)


@router.post("/mark-seen")
def mail_mark_seen_api(
    body: MailMarkSeenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """邮箱读取页打开邮件后标记已查看（不清除 象遇未读）。"""
    mail = _get_or_create_settings(db, current_user.id)
    mark_mail_seen(
        db,
        current_user,
        mail,
        mail_slot=body.mail_slot.strip().lower(),
        mail_seq=str(body.mail_seq).strip(),
    )
    return {"ok": True}


@router.post("/mark-all-seen")
def mail_mark_all_seen_api(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """邮箱读取页：将全部未读标为已读。"""
    marked = mark_all_mail_seen(db, current_user.id)
    return {"ok": True, "marked": marked}


@router.get("/demo/options", response_model=MailDemoOptionsResponse)
def mail_demo_options(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """演示面板：可选公司与当前邮箱/AI 配置状态。"""
    mail = _get_or_create_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)
    schedule = get_demo_exam_schedule()
    primary_ok = bool(mail.primary_provider and mail.primary_auth_encrypted)
    secondary_ok = bool(
        mail.secondary_email and mail.secondary_provider and mail.secondary_auth_encrypted
    )
    target_email: str | None = None
    if primary_ok:
        target_email = current_user.email
    elif secondary_ok:
        target_email = (mail.secondary_email or "").strip() or None

    companies: list[MailDemoCompanyItem] = []
    for cid in demo_company_ids():
        meta = DEMO_COMPANIES[cid]
        companies.append(
            MailDemoCompanyItem(
                id=cid,
                name=meta["name"],
                short_name=meta["short_name"],
                tagline=meta["tagline"],
                track=meta["track"],
                position=meta["position"],
                brand_color=meta["brand_color"],
                brand_accent=meta["brand_accent"],
                exam_datetime_label=schedule["exam_datetime_label"],
            )
        )

    ai_ok = bool(
        (ai.base_url or "").strip() and (ai.model or "").strip() and ai.api_key_encrypted
    )
    return MailDemoOptionsResponse(
        companies=companies,
        target_email=target_email,
        mail_configured=primary_ok or secondary_ok,
        ai_configured=ai_ok,
        exam_datetime_label=schedule["exam_datetime_label"],
    )


@router.post("/demo/send", response_model=MailDemoSendResponse)
def mail_demo_send(
    body: MailDemoSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发送演示笔试邮件到用户绑定邮箱（不拉取、不解析）。"""
    mail = _get_or_create_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)
    try:
        result = send_demo_mail(current_user, mail, ai, body.company.strip().lower())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"演示邮件发送失败：{e!s}")

    return MailDemoSendResponse(**result)


@router.post("/demo/sync", response_model=MailDemoSyncResponse)
def mail_demo_sync(
    body: MailDemoSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """演示邮件到达收件箱后，触发象遇解析与投递同步。"""
    mail = _get_or_create_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)
    try:
        result = sync_demo_mail(
            db,
            current_user,
            mail,
            ai,
            body.company.strip().lower(),
            body.test_id.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"演示邮件同步失败：{e!s}")

    _invalidate_mail_list_cache_for_user(current_user.id)
    sync_stats = result.pop("sync")
    return MailDemoSyncResponse(**result, sync=AiAssistantSyncResponse(**sync_stats))


@router.get("/messages", response_model=MailMessagesResponse)
def list_mail_messages(
    slot: Literal["primary", "secondary"] = Query("primary"),
    limit: int = Query(40, ge=1, le=80),
    refresh: bool = Query(False, description="为 true 时跳过服务端缓存并强制连接 IMAP"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = _get_or_create_settings(db, current_user.id)
    try:
        if slot == "primary":
            if not s.primary_provider or not s.primary_auth_encrypted:
                raise HTTPException(status_code=400, detail="请先在设置中配置主邮箱（注册邮箱）的 IMAP 授权码")
            mailbox_addr = current_user.email
            if not refresh:
                hit = _mail_list_cache_get(current_user.id, slot, limit)
                if hit:
                    mb_cached, items_cached = hit
                    return MailMessagesResponse(slot=slot, mailbox=mb_cached, items=items_cached)
            pwd = _decrypt_mail_auth(s.primary_auth_encrypted, slot_label="主邮箱")
            items = fetch_inbox_messages(
                current_user.email,
                pwd,
                s.primary_provider,
                s.primary_imap_host,
                s.primary_imap_port,
                limit=limit,
                include_bodies=False,
            )
            _mail_list_cache_set(current_user.id, slot, limit, mailbox_addr, items)
            return MailMessagesResponse(slot=slot, mailbox=mailbox_addr, items=items)
        # secondary
        if not s.secondary_email or not s.secondary_provider or not s.secondary_auth_encrypted:
            raise HTTPException(status_code=400, detail="未配置第二邮箱或授权信息不完整")
        mailbox_addr = s.secondary_email or ""
        if not refresh:
            hit = _mail_list_cache_get(current_user.id, slot, limit)
            if hit:
                mb_cached, items_cached = hit
                return MailMessagesResponse(slot=slot, mailbox=mb_cached, items=items_cached)
        pwd2 = _decrypt_mail_auth(s.secondary_auth_encrypted, slot_label="第二邮箱")
        items = fetch_inbox_messages(
            s.secondary_email,
            pwd2,
            s.secondary_provider,
            s.secondary_imap_host,
            s.secondary_imap_port,
            limit=limit,
            include_bodies=False,
        )
        _mail_list_cache_set(current_user.id, slot, limit, mailbox_addr, items)
        return MailMessagesResponse(slot=slot, mailbox=mailbox_addr, items=items)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IMAP 拉取失败：{e!s}")


@router.get("/message-body", response_model=MailMessageBodyResponse)
def get_mail_message_body(
    slot: Literal["primary", "secondary"] = Query("primary"),
    seq: str = Query(..., min_length=1, max_length=24),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按列表中的序号拉取单封邮件正文（每次单独连接 IMAP，避免列表加载拉取全部 RFC822）。"""
    s = _get_or_create_settings(db, current_user.id)
    try:
        if slot == "primary":
            if not s.primary_provider or not s.primary_auth_encrypted:
                raise HTTPException(status_code=400, detail="请先在设置中配置主邮箱（注册邮箱）的 IMAP 授权码")
            pwd = _decrypt_mail_auth(s.primary_auth_encrypted, slot_label="主邮箱")
            body = fetch_inbox_message_body(
                current_user.email,
                pwd,
                s.primary_provider,
                seq,
                s.primary_imap_host,
                s.primary_imap_port,
            )
            return MailMessageBodyResponse(**body)
        if not s.secondary_email or not s.secondary_provider or not s.secondary_auth_encrypted:
            raise HTTPException(status_code=400, detail="未配置第二邮箱或授权信息不完整")
        pwd2 = _decrypt_mail_auth(s.secondary_auth_encrypted, slot_label="第二邮箱")
        body = fetch_inbox_message_body(
            s.secondary_email,
            pwd2,
            s.secondary_provider,
            seq,
            s.secondary_imap_host,
            s.secondary_imap_port,
        )
        return MailMessageBodyResponse(**body)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IMAP 读取失败：{e!s}")
