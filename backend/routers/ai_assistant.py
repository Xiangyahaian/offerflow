"""象遇 API：模型配置 + 邮箱 AI 解析（无对话）。"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.ai_assistant_llm import check_availability
from backend.ai_assistant_mail import (
    mail_slots_configured,
    mark_all_mail_insights_read,
    open_mail_insight,
    sync_user_mail_insights,
)
from backend.ai_assistant_providers import AI_ASSISTANT_PROVIDERS, find_provider
from backend.mail_crypto import decrypt_secret, ensure_encrypted
from backend.models import (
    AiAssistantMailInsight,
    User,
    UserAiAssistantSettings,
    UserMailSettings,
)
from backend.schemas import (
    AiAssistantCheckRequest,
    AiAssistantCheckResponse,
    AiAssistantInsightOpenRequest,
    AiAssistantInsightOpenResponse,
    AiAssistantInsightsResponse,
    AiAssistantMailInsightItem,
    AiAssistantModelOption,
    AiAssistantProviderOption,
    AiAssistantProvidersResponse,
    AiAssistantSettingsResponse,
    AiAssistantSettingsUpdate,
    AiAssistantSyncResponse,
    AiAssistantUnreadItem,
    AiAssistantUnreadStatusResponse,
)

router = APIRouter(prefix="/api/ai-assistant", tags=["象遇"])


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


def _get_mail_settings(db: Session, user_id: str) -> UserMailSettings:
    row = db.query(UserMailSettings).filter(UserMailSettings.user_id == user_id).first()
    if row:
        return row
    row = UserMailSettings(user_id=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _settings_response(
    user: User, mail: UserMailSettings, ai: UserAiAssistantSettings
) -> AiAssistantSettingsResponse:
    p_ok, s_ok = mail_slots_configured(user, mail)
    return AiAssistantSettingsResponse(
        provider_id=ai.provider_id,
        base_url=ai.base_url,
        model=ai.model,
        api_key_configured=bool(ai.api_key_encrypted),
        auto_parse_mail=bool(ai.auto_parse_mail),
        primary_mail_configured=p_ok,
        secondary_mail_configured=s_ok,
        primary_email=user.email or "",
        secondary_email=mail.secondary_email,
    )


def _resolve_llm_credentials(
    ai: UserAiAssistantSettings, body: Optional[AiAssistantCheckRequest] = None
) -> tuple[str, str, str]:
    base = (body.base_url if body and body.base_url is not None else ai.base_url) or ""
    model = (body.model if body and body.model is not None else ai.model) or ""
    if body and body.api_key is not None:
        key = (body.api_key or "").strip()
    elif ai.api_key_encrypted:
        try:
            key = decrypt_secret(ai.api_key_encrypted)
        except InvalidToken:
            raise HTTPException(
                status_code=400,
                detail="API Key 无法解密，请重新填写并保存",
            )
    else:
        key = ""
    return base.strip(), model.strip(), key


@router.get("/providers", response_model=AiAssistantProvidersResponse)
def list_providers(current_user: User = Depends(get_current_user)):
    out: List[AiAssistantProviderOption] = []
    for p in AI_ASSISTANT_PROVIDERS:
        out.append(
            AiAssistantProviderOption(
                id=p["id"],
                label=p["label"],
                base_url=p.get("base_url") or "",
                models=[AiAssistantModelOption(id=m["id"], label=m["label"]) for m in p["models"]],
            )
        )
    return AiAssistantProvidersResponse(providers=out)


@router.get("/settings", response_model=AiAssistantSettingsResponse)
def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mail = _get_mail_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)
    return _settings_response(current_user, mail, ai)


@router.put("/settings", response_model=AiAssistantSettingsResponse)
def update_settings(
    body: AiAssistantSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mail = _get_mail_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)

    if body.provider_id is not None:
        pid = (body.provider_id or "").strip().lower()
        if pid:
            prov = find_provider(pid)
            if not prov:
                raise HTTPException(status_code=400, detail="不支持的模型服务商")
            ai.provider_id = pid
            if body.base_url is None and prov.get("base_url"):
                ai.base_url = prov["base_url"]
            if body.model is None and prov.get("models"):
                ai.model = prov["models"][0]["id"]
        else:
            ai.provider_id = None

    if body.base_url is not None:
        ai.base_url = (body.base_url or "").strip() or None
    if body.model is not None:
        ai.model = (body.model or "").strip() or None
    if body.api_key is not None:
        k = (body.api_key or "").strip()
        ai.api_key_encrypted = ensure_encrypted(k) if k else None
    if body.auto_parse_mail is not None:
        ai.auto_parse_mail = bool(body.auto_parse_mail)

    ai.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ai)
    return _settings_response(current_user, mail, ai)


@router.post("/check", response_model=AiAssistantCheckResponse)
def check_model(
    body: AiAssistantCheckRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ai = _get_or_create_ai_settings(db, current_user.id)
    base, model, key = _resolve_llm_credentials(ai, body)
    if not key:
        raise HTTPException(status_code=400, detail="请填写 API Key")
    ok, msg, ms = check_availability(base_url=base, api_key=key, model=model)
    return AiAssistantCheckResponse(ok=ok, message=msg, latency_ms=ms)


@router.get("/insights", response_model=AiAssistantInsightsResponse)
def list_insights(
    limit: int = Query(40, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AiAssistantMailInsight)
        .filter(AiAssistantMailInsight.user_id == current_user.id)
        .order_by(desc(AiAssistantMailInsight.created_at))
        .limit(limit)
        .all()
    )
    ai = _get_or_create_ai_settings(db, current_user.id)
    last_sync = ai.updated_at.isoformat() + "Z" if ai.updated_at else None
    return AiAssistantInsightsResponse(
        total=len(rows),
        items=[AiAssistantMailInsightItem.model_validate(r) for r in rows],
        last_sync_at=last_sync,
    )


@router.get("/unread-status", response_model=AiAssistantUnreadStatusResponse)
def unread_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == current_user.id,
            AiAssistantMailInsight.is_parsed.is_(True),
            AiAssistantMailInsight.is_read.is_(False),
        )
        .order_by(desc(AiAssistantMailInsight.created_at))
        .limit(80)
        .all()
    )
    items = [
        AiAssistantUnreadItem(
            insight_id=r.id,
            mail_slot=r.mail_slot,
            mail_seq=r.mail_seq,
            subject=r.subject,
        )
        for r in rows
    ]
    return AiAssistantUnreadStatusResponse(unread_count=len(items), items=items)


@router.post("/insights/open", response_model=AiAssistantInsightOpenResponse)
def open_insight(
    body: AiAssistantInsightOpenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.insight_id and not (body.mail_slot and body.mail_seq):
        raise HTTPException(status_code=400, detail="请提供 insight_id 或 mail_slot + mail_seq")
    mail = _get_mail_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)
    try:
        result = open_mail_insight(
            db,
            current_user,
            mail,
            ai,
            insight_id=body.insight_id,
            mail_slot=body.mail_slot,
            mail_seq=body.mail_seq,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"操作失败：{e!s}")
    ins = result["insight"]
    return AiAssistantInsightOpenResponse(
        insight=AiAssistantMailInsightItem.model_validate(ins),
        newly_parsed=bool(result.get("newly_parsed")),
        application_sync=result.get("application_sync"),
    )


@router.post("/insights/read-all")
def read_all_insights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """打开邮箱解析面板时：仅标象遇已读（is_read），邮箱读取页未读（is_mail_seen）不变。"""
    marked = mark_all_mail_insights_read(db, current_user.id)
    return {"ok": True, "marked_count": marked}


@router.post("/insights/{insight_id}/read")
def mark_insight_read(
    insight_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """仅标记已读；解析在收到新邮件时已由同步完成。"""
    row = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.id == insight_id,
            AiAssistantMailInsight.user_id == current_user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    row.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/sync-mail", response_model=AiAssistantSyncResponse)
def sync_mail(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mail = _get_mail_settings(db, current_user.id)
    ai = _get_or_create_ai_settings(db, current_user.id)
    try:
        stats = sync_user_mail_insights(db, current_user, mail, ai)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"邮箱同步失败：{e!s}")
    return AiAssistantSyncResponse(**stats)
