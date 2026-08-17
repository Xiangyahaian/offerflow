"""象遇 · 将邮件抽取 JSON 应用到实习/校招投递表。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.interview_rounds_util import (
    maybe_promote_pending_on_interview_schedule,
    parse_rounds,
    promote_row_if_scheduled_interview,
)
from backend.ai_assistant_apply_match import (
    MailApplyMatchDecision,
    load_catalog_link_by_id,
    resolve_mail_apply_match,
    resolve_position_label,
)
from backend.ai_assistant_extract import MailApplicationExtract, InterviewRoundExtract
from backend.models import Internship, Job, UserAiAssistantSettings, generate_uuid
from backend.schemas import normalize_application_status

logger = logging.getLogger(__name__)


def is_recruitment_related_mail(
    category: Optional[str],
    extract: Optional[MailApplicationExtract],
    *,
    subject: str = "",
    body_snippet: str = "",
) -> bool:
    """是否实习/校招相关邮件（优先使用邮件解析阶段 LLM 的分类与 application）。"""
    _ = subject, body_snippet
    cat = (category or "").strip().lower()
    if cat in ("recruit", "interview", "offer", "notice"):
        return True
    if not extract:
        return False
    if extract.track in ("internship", "campus"):
        return True
    if (extract.company or "").strip() and (
        extract.interview_rounds or extract.status
    ):
        return True
    return False


def _merge_rounds_json(
    existing: Optional[str], new_rounds: List[InterviewRoundExtract]
) -> str:
    rounds = parse_rounds(existing)
    for nr in new_rounds:
        if not nr.time:
            continue
        dup = False
        for er in rounds:
            if not isinstance(er, dict):
                continue
            if (
                str(er.get("type") or "") == nr.type
                and str(er.get("time") or "") == nr.time
            ):
                dup = True
                break
        if not dup:
            rounds.append({"type": nr.type, "time": nr.time})
    return json.dumps(rounds, ensure_ascii=False)


def _append_remarks(existing: Optional[str], addition: Optional[str]) -> str:
    add = (addition or "").strip()
    if not add:
        return (existing or "").strip()
    base = (existing or "").strip()
    if not base:
        return add
    if add in base:
        return base
    return f"{base}\n{add}"


def _row_by_decision(
    db: Session,
    user_id: str,
    decision: MailApplyMatchDecision,
) -> Tuple[Optional[Type[Any]], Optional[Any]]:
    if decision.action != "update" or not decision.record_id:
        return None, None
    if decision.track == "internship":
        row = (
            db.query(Internship)
            .filter(Internship.id == decision.record_id, Internship.user_id == user_id)
            .first()
        )
        return (Internship, row) if row else (None, None)
    if decision.track == "campus":
        row = (
            db.query(Job)
            .filter(Job.id == decision.record_id, Job.user_id == user_id)
            .first()
        )
        return (Job, row) if row else (None, None)
    return None, None


def apply_mail_application_extract(
    db: Session,
    user_id: str,
    extract: MailApplicationExtract,
    *,
    mail_subject: str = "",
    source_label: str = "邮件自动同步",
    ai: Optional[UserAiAssistantSettings] = None,
    decision_override: Optional[MailApplyMatchDecision] = None,
) -> Dict[str, Any]:
    """
    将抽取结果写入实习或校招表。匹配由 LLM 完成，无硬编码公司别名表。
    """
    company = (extract.company or "").strip()
    if not company:
        return {"ok": False, "action": "skip", "reason": "未识别公司名"}

    if extract.confidence < 0.35 and not extract.interview_rounds and not extract.status:
        return {"ok": False, "action": "skip", "reason": "置信度过低且无有效字段"}

    decision = decision_override or resolve_mail_apply_match(
        db, user_id, ai, extract, mail_subject=mail_subject
    )
    if decision.action == "skip":
        return {
            "ok": False,
            "action": "skip",
            "reason": decision.reason or "未匹配",
            "company": company,
            "match": decision.model_dump(),
        }

    resolved_link = load_catalog_link_by_id(db, decision.catalog_job_link_id)

    model, row = _row_by_decision(db, user_id, decision)
    track_name = "internship" if model is Internship else "campus" if model is Job else None

    update_data: Dict[str, Any] = {}
    if extract.status:
        st = normalize_application_status(extract.status) or extract.status
        update_data["status"] = st
    if extract.interview_rounds:
        existing_rounds = getattr(row, "interview_rounds", None) if row else None
        update_data["interview_rounds"] = _merge_rounds_json(
            existing_rounds, extract.interview_rounds
        )

    remark_piece = (extract.remarks or "").strip()
    if mail_subject and remark_piece:
        remark_piece = f"{remark_piece}（{mail_subject[:80]}）"
    elif mail_subject:
        remark_piece = f"{source_label}：{mail_subject[:100]}"

    if row is None:
        if decision.action != "create":
            return {
                "ok": False,
                "action": "skip",
                "reason": decision.reason or "无可用新建指令",
                "company": company,
                "match": decision.model_dump(),
            }
        if not extract.create_if_missing:
            return {
                "ok": False,
                "action": "skip",
                "reason": "未匹配到记录且不允许新建",
                "company": company,
            }

        track_use = decision.track or extract.track
        if track_use == "unknown":
            blob = f"{mail_subject} {extract.position or ''}"
            if "实习" in blob:
                track_use = "internship"
            elif any(k in blob for k in ("校招", "校园招聘", "应届")):
                track_use = "campus"
            else:
                track_use = "campus"
        use_intern = track_use == "internship"
        position_label = resolve_position_label(extract, decision)

        if use_intern:
            max_order = (
                db.query(func.max(Internship.display_order))
                .filter(Internship.user_id == user_id)
                .scalar()
            )
            row = Internship(
                id=generate_uuid(),
                user_id=user_id,
                company=company[:200],
                position=position_label,
                link=resolved_link,
                status=update_data.get("status") or "sent",
                interview_rounds=update_data.get("interview_rounds"),
                salary=(extract.salary or "")[:100] or None,
                remarks=_append_remarks(None, remark_piece),
                display_order=float(max_order or 0) + 1,
            )
            promote_row_if_scheduled_interview(row)
            db.add(row)
            track_name = "internship"
            action = "created_internship"
        else:
            max_order = (
                db.query(func.max(Job.display_order))
                .filter(Job.user_id == user_id)
                .scalar()
            )
            row = Job(
                id=generate_uuid(),
                user_id=user_id,
                company=company[:200],
                position=position_label,
                link=resolved_link,
                status=update_data.get("status") or "sent",
                interview_rounds=update_data.get("interview_rounds"),
                total_package=(extract.total_package or "")[:100] or None,
                monthly_salary=(extract.monthly_salary or "")[:100] or None,
                remarks=_append_remarks(None, remark_piece),
                display_order=float(max_order or 0) + 1,
            )
            promote_row_if_scheduled_interview(row)
            db.add(row)
            track_name = "campus"
            action = "created_job"
    else:
        action = "updated_job" if model is Job else "updated_internship"
        if extract.status:
            row.status = update_data["status"]
            if row.status == "pending":
                row.applied_at = None
            elif row.status in ("sent", "offered", "rejected", "accepted") and not row.applied_at:
                row.applied_at = datetime.utcnow().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
        if extract.interview_rounds:
            merged = update_data["interview_rounds"]
            patch = {"interview_rounds": merged}
            maybe_promote_pending_on_interview_schedule(row, patch)
            row.interview_rounds = patch["interview_rounds"]
            if patch.get("status"):
                row.status = patch["status"]
            if patch.get("applied_at") is not None:
                row.applied_at = patch["applied_at"]
        if extract.salary and model is Internship and not (row.salary or "").strip():
            row.salary = extract.salary[:100]
        if model is Job:
            if extract.total_package and not (row.total_package or "").strip():
                row.total_package = extract.total_package[:100]
            if extract.monthly_salary and not (row.monthly_salary or "").strip():
                row.monthly_salary = extract.monthly_salary[:100]
        if remark_piece:
            row.remarks = _append_remarks(row.remarks, remark_piece)
        if resolved_link and not (getattr(row, "link", None) or "").strip():
            row.link = resolved_link

    db.flush()
    result: Dict[str, Any] = {
        "ok": True,
        "action": action,
        "track": track_name,
        "record_id": row.id,
        "company": row.company,
        "position": row.position,
        "status": row.status,
        "interview_rounds": row.interview_rounds,
        "link": getattr(row, "link", None),
        "match": decision.model_dump(),
    }
    return result
