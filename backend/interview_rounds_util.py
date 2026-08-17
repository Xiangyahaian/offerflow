"""面试轮次 JSON 的共用解析与业务副作用。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional


def parse_rounds(interview_rounds: Optional[str]) -> List[Any]:
    if not interview_rounds:
        return []
    try:
        data = json.loads(interview_rounds)
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def rounds_have_scheduled_time(interview_rounds: Optional[str]) -> bool:
    """是否至少安排了一场带日期的笔试/面试。"""
    for item in parse_rounds(interview_rounds):
        if isinstance(item, dict) and str(item.get("time") or "").strip():
            return True
    return False


def maybe_promote_pending_on_interview_schedule(row: Any, update_data: dict) -> None:
    """
    写入面试/笔试时间后，若仍为未投递，自动变为已投递并补投递日期。
    与前端「填了面试时间即视为已投递」一致。
    """
    if "interview_rounds" not in update_data:
        return
    if not rounds_have_scheduled_time(update_data.get("interview_rounds")):
        return

    st = update_data.get("status", getattr(row, "status", None)) or "pending"
    if st == "replied":
        st = "sent"
    if st != "pending":
        return

    update_data["status"] = "sent"
    if update_data.get("applied_at") is None and getattr(row, "applied_at", None) is None:
        update_data["applied_at"] = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )


def promote_row_if_scheduled_interview(row: Any) -> None:
    """创建或更新后，按行对象再校正一次（用于 create）。"""
    if (getattr(row, "status", None) or "pending") not in ("pending", "replied"):
        return
    if not rounds_have_scheduled_time(getattr(row, "interview_rounds", None)):
        return
    row.status = "sent"
    if getattr(row, "applied_at", None) is None:
        row.applied_at = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
