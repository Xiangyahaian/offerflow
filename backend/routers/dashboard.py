from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional, Type

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Internship, Job
from backend.schemas import DashboardResponse, DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["工作台"])


def _parse_round_datetime(time_str: str) -> Optional[datetime]:
    s = str(time_str or "").strip()
    if not s:
        return None
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", ""))
        else:
            dt = datetime.fromisoformat(s + "T00:00:00")
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _is_written_or_interview_round(round_type: str) -> bool:
    t = (round_type or "").strip()
    if not t:
        return False
    if t == "笔试":
        return True
    return "面" in t


def _has_upcoming_written_or_interview(interview_rounds: Optional[str], now: datetime) -> bool:
    if not interview_rounds:
        return False
    try:
        rounds: List[Any] = json.loads(interview_rounds)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(rounds, list):
        return False
    for item in rounds:
        if not isinstance(item, dict):
            continue
        if not _is_written_or_interview_round(str(item.get("type") or "")):
            continue
        dt = _parse_round_datetime(str(item.get("time") or ""))
        if dt is not None and dt >= now:
            return True
    return False


def _is_applied_status(status: Optional[str]) -> bool:
    st = status or "pending"
    if st == "replied":
        st = "sent"
    return st != "pending"


def _count_upcoming_action(db: Session, model: Type[Any], now: datetime) -> int:
    rows = db.query(model.status, model.interview_rounds).all()
    count = 0
    for status, interview_rounds in rows:
        if not _is_applied_status(status):
            continue
        if _has_upcoming_written_or_interview(interview_rounds, now):
            count += 1
    return count


@router.get("/stats", response_model=DashboardResponse)
def get_dashboard_stats(db: Session = Depends(get_db)):
    now = datetime.utcnow()

    intern_counts = dict(
        db.query(Internship.status, func.count(Internship.id)).group_by(Internship.status).all()
    )
    total_internships = sum(intern_counts.values())
    pending_internships = _count_upcoming_action(db, Internship, now)
    offered_internships = intern_counts.get("offered", 0)

    job_counts = dict(db.query(Job.status, func.count(Job.id)).group_by(Job.status).all())
    total_jobs = sum(job_counts.values())
    pending_jobs = _count_upcoming_action(db, Job, now)
    offered_jobs = job_counts.get("offered", 0) + job_counts.get("accepted", 0)

    stats = DashboardStats(
        total_internships=total_internships,
        total_jobs=total_jobs,
        unread_mail=0,
        pending_internships=pending_internships,
        pending_jobs=pending_jobs,
        offered_internships=offered_internships,
        offered_jobs=offered_jobs,
    )
    return DashboardResponse(stats=stats)
