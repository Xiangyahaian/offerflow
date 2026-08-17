"""象遇 · 由 LLM 决定邮件与投递表/岗位速递的匹配（无硬编码别名表）。"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.ai_assistant_extract import MailApplicationExtract, _extract_json_object
from backend.ai_assistant_llm import chat_completion
from backend.mail_crypto import decrypt_secret
from backend.models import Internship, Job, UserAiAssistantSettings

logger = logging.getLogger(__name__)

VALID_ACTIONS = ("update", "create", "skip")
VALID_TRACKS = ("internship", "campus")


class MailApplyMatchDecision(BaseModel):
    action: str = "skip"
    track: Optional[str] = None
    record_id: Optional[str] = None
    catalog_job_link_id: Optional[str] = None
    position_label: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def norm_action(cls, v: Any) -> str:
        a = str(v or "skip").strip().lower()
        return a if a in VALID_ACTIONS else "skip"

    @field_validator("track", mode="before")
    @classmethod
    def norm_track(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        t = str(v).strip().lower()
        if t in ("intern", "internship", "实习"):
            return "internship"
        if t in ("campus", "job", "校招", "全职"):
            return "campus"
        return t if t in VALID_TRACKS else None


def _ai_ready(ai: Optional[UserAiAssistantSettings]) -> bool:
    return bool(
        ai
        and ai.api_key_encrypted
        and (ai.base_url or "").strip()
        and (ai.model or "").strip()
    )


def _compact_records(
    db: Session,
    user_id: str,
    model: type,
    track: str,
    limit: int = 100,
) -> List[Dict[str, str]]:
    rows = (
        db.query(model)
        .filter(model.user_id == user_id)
        .order_by(model.display_order.asc())
        .limit(limit)
        .all()
    )
    out: List[Dict[str, str]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "track": track,
                "company": (r.company or "")[:120],
                "position": (r.position or "")[:120],
                "link": ((getattr(r, "link", None) or "")[:200]),
                "status": (r.status or "")[:32],
            }
        )
    return out


def _retrieve_catalog_candidates(
    db: Session,
    email_company: str,
    *,
    max_items: int = 80,
) -> List[Any]:
    """开源版已移除岗位速递 catalog，始终返回空。"""
    return []


def _compact_catalog(rows: List[Any]) -> List[Dict[str, str]]:
    return []


def _parse_match_payload(raw: str) -> MailApplyMatchDecision:
    data = _extract_json_object(raw)
    if not data:
        return MailApplyMatchDecision(action="skip", reason="模型未返回 JSON")
    try:
        return MailApplyMatchDecision.model_validate(data)
    except Exception as e:
        logger.warning("apply match JSON 校验失败: %s", e)
        return MailApplyMatchDecision(action="skip", reason="JSON 格式无效")


def resolve_mail_apply_match(
    db: Session,
    user_id: str,
    ai: Optional[UserAiAssistantSettings],
    extract: MailApplicationExtract,
    *,
    mail_subject: str = "",
) -> MailApplyMatchDecision:
    """
    由 LLM 判断：更新哪条投递、或新建哪类投递、岗位速递选哪条链接。
    写入表中的公司名始终以邮件抽取为准（见 apply 层）。
    LLM 返回 skip 或不可用时，使用规则回退（公司名 + track）。
    """
    company = (extract.company or "").strip()
    if not company:
        return MailApplyMatchDecision(action="skip", reason="邮件未识别公司")

    if not _ai_ready(ai):
        fallback = _rule_fallback_decision(db, user_id, extract, mail_subject=mail_subject)
        if fallback.action != "skip":
            return fallback
        return MailApplyMatchDecision(
            action="skip",
            reason="未配置 AI 助手，且规则匹配无法确定投递",
        )

    internships = _compact_records(db, user_id, Internship, "internship")
    campus_jobs = _compact_records(db, user_id, Job, "campus")
    catalog = _compact_catalog(_retrieve_catalog_candidates(db, company))

    app_json = extract.model_dump(exclude_none=True)
    system = (
        "你是 OfferFlow 求职投递匹配助手。只输出一个 JSON 对象，不要 Markdown。\n"
        "根据【邮件投递信息】与【用户已有投递】【岗位速递候选】做语义匹配（含简称、母子公司、"
        "「中核集团」与「中核科技」等同一主体）。\n"
        "JSON 字段：\n"
        '- action: "update" | "create" | "skip"\n'
        '- track: "internship" | "campus" | null（update/create 时必填）\n'
        '- record_id: 已有投递 id（action=update 时必填，须来自下列列表）\n'
        '- catalog_job_link_id: 岗位速递 id（action=create 且能匹配到合适链接时填写，否则 null）\n'
        '- position_label: 新建时写入表格的岗位名（优先邮件岗位，可略作规范化；无则 null）\n'
        '- confidence: 0-1\n'
        '- reason: 一句中文说明\n'
        "规则：\n"
        "1. 若邮件对应用户已有同公司/同岗位（语义相同）的投递 → action=update，填 record_id+track。\n"
        "2. 若无已有投递 → action=create；track 与邮件 internship/campus 一致，"
        "未知时结合邮件正文判断实习或校招。\n"
        "3. create 时：在 catalog_job_links 中选最匹配的一条填 catalog_job_link_id；"
        "都不合适则 null（仍将新建投递，链接留空）。\n"
        "4. 勿编造 id；id 必须来自输入列表。\n"
        "5. 表格中的公司名以邮件为准，不要用 catalog 公司名替换邮件公司名。"
    )
    user_msg = json.dumps(
        {
            "mail_subject": mail_subject[:300],
            "mail_application": app_json,
            "user_internships": internships,
            "user_campus_jobs": campus_jobs,
            "catalog_job_links": catalog,
            "catalog_note": (
                f"岗位速递共展示 {len(catalog)} 条候选（全库可能更多），"
                "无合适项则 catalog_job_link_id 填 null。"
            ),
        },
        ensure_ascii=False,
    )

    try:
        api_key = decrypt_secret(ai.api_key_encrypted)
        text, _ = chat_completion(
            base_url=ai.base_url or "",
            api_key=api_key,
            model=ai.model or "",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=500,
            temperature=0.15,
        )
        decision = _parse_match_payload(text)
        decision = _validate_decision(decision, internships, campus_jobs, catalog)
        if decision.action == "skip":
            fallback = _rule_fallback_decision(
                db, user_id, extract, mail_subject=mail_subject
            )
            if fallback.action != "skip":
                logger.info(
                    "投递 LLM 匹配 skip，规则回退: %s -> %s",
                    decision.reason,
                    fallback.reason,
                )
                return fallback
        return decision
    except Exception as e:
        logger.warning("LLM 投递匹配失败: %s", e)
        fallback = _rule_fallback_decision(
            db, user_id, extract, mail_subject=mail_subject
        )
        if fallback.action != "skip":
            return fallback
        return MailApplyMatchDecision(action="skip", reason=f"匹配失败: {str(e)[:120]}")


def _normalize_company_token(name: str) -> str:
    import re as _re

    return _re.sub(r"[\s·\-—（）()]", "", (name or "")).lower()


def _company_names_match(a: str, b: str) -> bool:
    na = _normalize_company_token(a)
    nb = _normalize_company_token(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    for length in (4, 3, 2):
        if len(na) >= length and len(nb) >= length:
            if na[:length] == nb[:length]:
                return True
    return False


def _infer_track_from_blob(extract: MailApplicationExtract, mail_subject: str) -> str:
    if extract.track in VALID_TRACKS:
        return extract.track
    blob = f"{mail_subject} {extract.position or ''} {extract.remarks or ''}"
    if "实习" in blob or "intern" in blob.lower():
        return "internship"
    if any(k in blob for k in ("校招", "校园招聘", "应届")):
        return "campus"
    return "campus"


def _find_existing_application(
    db: Session,
    user_id: str,
    company: str,
) -> Optional[MailApplyMatchDecision]:
    for model, track in ((Internship, "internship"), (Job, "campus")):
        rows = (
            db.query(model)
            .filter(model.user_id == user_id)
            .order_by(model.display_order.asc())
            .limit(200)
            .all()
        )
        for row in rows:
            if _company_names_match(row.company or "", company):
                return MailApplyMatchDecision(
                    action="update",
                    track=track,
                    record_id=row.id,
                    position_label=(row.position or "")[:200] or None,
                    confidence=0.75,
                    reason="规则匹配已有投递记录",
                )
    return None


def find_catalog_id_for_company(db: Session, company: str) -> Optional[str]:
    for row in _retrieve_catalog_candidates(db, company, max_items=20):
        if _company_names_match(row.company or "", company):
            return row.id
    return None


def _rule_fallback_decision(
    db: Session,
    user_id: str,
    extract: MailApplicationExtract,
    *,
    mail_subject: str = "",
) -> MailApplyMatchDecision:
    """LLM 不可用或返回 skip 时，按公司名 + track 规则创建或更新投递。"""
    company = (extract.company or "").strip()
    if not company:
        return MailApplyMatchDecision(action="skip", reason="无公司名")

    has_signal = bool(
        extract.interview_rounds
        or extract.status
        or extract.confidence >= 0.35
        or extract.create_if_missing
    )
    if not has_signal:
        return MailApplyMatchDecision(action="skip", reason="抽取信息不足")

    existing = _find_existing_application(db, user_id, company)
    if existing:
        return existing

    if not extract.create_if_missing:
        return MailApplyMatchDecision(action="skip", reason="无已有记录且不允许新建")

    track = _infer_track_from_blob(extract, mail_subject)
    catalog_id = find_catalog_id_for_company(db, company)
    return MailApplyMatchDecision(
        action="create",
        track=track,
        catalog_job_link_id=catalog_id,
        position_label=(extract.position or "").strip()[:200] or None,
        confidence=max(extract.confidence, 0.7),
        reason="规则回退新建投递",
    )


def _validate_decision(
    decision: MailApplyMatchDecision,
    internships: List[Dict[str, str]],
    campus_jobs: List[Dict[str, str]],
    catalog: List[Dict[str, str]],
) -> MailApplyMatchDecision:
    """校验 LLM 返回的 id 确实存在。"""
    if decision.action == "skip":
        return decision

    id_map: Dict[str, str] = {}
    for r in internships + campus_jobs:
        id_map[r["id"]] = r["track"]
    catalog_ids = {c["id"] for c in catalog}

    if decision.action == "update":
        rid = (decision.record_id or "").strip()
        if not rid or rid not in id_map:
            return MailApplyMatchDecision(
                action="skip",
                reason="模型返回的 record_id 无效",
                confidence=decision.confidence,
            )
        decision.track = id_map[rid]
        return decision

    if decision.action == "create":
        if decision.track not in VALID_TRACKS:
            decision.track = "campus"
        cid = (decision.catalog_job_link_id or "").strip()
        if cid and cid not in catalog_ids:
            decision.catalog_job_link_id = None
        return decision

    return MailApplyMatchDecision(action="skip", reason="未知 action")


def load_catalog_link_by_id(db: Session, link_id: Optional[str]) -> Optional[str]:
    return None


def resolve_position_label(
    extract: MailApplicationExtract,
    decision: MailApplyMatchDecision,
) -> str:
    pos = (decision.position_label or extract.position or "").strip()
    if pos and pos.lower() not in ("无", "-", "暂无", "n/a"):
        return pos[:200]
    if (extract.position or "").strip():
        return (extract.position or "").strip()[:200]
    return "待定"
