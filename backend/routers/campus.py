from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, null
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.interview_rounds_util import (
    maybe_promote_pending_on_interview_schedule,
    promote_row_if_scheduled_interview,
)
from backend.models import LOCAL_USER_ID, Job
from backend.schemas import (
    ApplicationReorder,
    JobBatchBody,
    JobCreate,
    JobListResponse,
    JobResponse,
    JobUpdate,
)

router = APIRouter(prefix="/api/campus", tags=["校招投递"])


def _apply_job_status_side_effects(row: Job, new_status: str):
    if new_status == "replied":
        new_status = "sent"
    if new_status == "pending":
        row.applied_at = None
    elif new_status in ("sent", "offered", "rejected") and row.applied_at is None:
        row.applied_at = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    row.status = new_status


@router.get("", response_model=JobListResponse)
def get_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "applied_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status:
        if status == "sent":
            query = query.filter(Job.status.in_(["sent", "replied"]))
        else:
            query = query.filter(Job.status == status)
    if priority:
        query = query.filter(Job.priority == priority)
    if search:
        query = query.filter((Job.company.contains(search)) | (Job.position.contains(search)))

    sort_column = getattr(Job, sort_by, Job.applied_at)
    order_parts = [desc(Job.pinned), desc(Job.display_order)]
    order_parts.append(desc(sort_column) if sort_order == "desc" else asc(sort_column))
    query = query.order_by(*order_parts)

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return JobListResponse(total=total, page=page, page_size=page_size, items=items)


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(data: JobCreate, db: Session = Depends(get_db)):
    status_val = data.status or "pending"
    applied_at = null() if status_val == "pending" else data.applied_at
    max_order = db.query(func.max(Job.display_order)).scalar()
    job = Job(
        user_id=LOCAL_USER_ID,
        company=data.company,
        position=data.position or "",
        description=data.description,
        link=data.link,
        priority=data.priority or "normal",
        applied_at=applied_at,
        replied_at=data.replied_at,
        interview_rounds=data.interview_rounds,
        status=status_val,
        passed=data.passed or "unknown",
        completed=data.completed or False,
        total_package=data.total_package,
        monthly_salary=data.monthly_salary,
        months=data.months,
        stock=data.stock,
        benefits=data.benefits,
        remarks=data.remarks,
        display_order=float(max_order or 0) + 1,
    )
    promote_row_if_scheduled_interview(job)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/batch")
def batch_jobs(body: JobBatchBody, db: Session = Depends(get_db)):
    uid_set = set(body.ids)
    rows = db.query(Job).filter(Job.id.in_(body.ids)).all()
    if len(rows) != len(uid_set):
        raise HTTPException(status_code=400, detail="部分记录不存在")
    if body.delete:
        for r in rows:
            db.delete(r)
        db.commit()
        return {"ok": True, "affected": len(rows), "deleted": True}

    if body.pinned == 1:
        order_map = {jid: i for i, jid in enumerate(body.ids)}
        sorted_rows = sorted(rows, key=lambda x: order_map.get(x.id, 10**9))
        max_do = db.query(func.max(Job.display_order)).scalar()
        base = float(max_do or 0)
        n = len(sorted_rows)
        for i, r in enumerate(sorted_rows):
            r.pinned = 1
            r.display_order = base + float(n - i) * 0.001
    elif body.pinned == 0:
        for r in rows:
            r.pinned = 0
            r.display_order = 0.0

    for r in rows:
        if body.priority is not None:
            r.priority = body.priority
        if body.status is not None:
            _apply_job_status_side_effects(r, body.status)
    db.commit()
    return {"ok": True, "affected": len(rows), "deleted": False}


@router.get("/{item_id}", response_model=JobResponse)
def get_job(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Job).filter(Job.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="不存在")
    return item


@router.put("/{item_id}", response_model=JobResponse)
def update_job(item_id: str, data: JobUpdate, db: Session = Depends(get_db)):
    item = db.query(Job).filter(Job.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="不存在")

    update_data = data.model_dump(exclude_unset=True)
    new_status = update_data.get("status")
    if new_status == "pending":
        update_data["applied_at"] = None
    elif new_status in ("sent", "offered", "rejected"):
        if "applied_at" not in update_data and item.applied_at is None:
            update_data["applied_at"] = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
    maybe_promote_pending_on_interview_schedule(item, update_data)
    for key, value in update_data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_job(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Job).filter(Job.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="不存在")
    db.delete(item)
    db.commit()
    return {"message": "deleted"}


@router.post("/{item_id}/pin")
def pin_job(
    item_id: str,
    mode: str = Query("toggle", description="toggle | top | off"),
    db: Session = Depends(get_db),
):
    item = db.query(Job).filter(Job.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if mode == "off":
        item.pinned = 0
        item.display_order = 0.0
    elif mode == "top" or not item.pinned:
        item.pinned = 1
        max_do = db.query(func.max(Job.display_order)).scalar()
        item.display_order = float(max_do or 0) + 1.0
    else:
        item.pinned = 0
        item.display_order = 0.0
    db.commit()
    db.refresh(item)
    return item


@router.post("/reorder")
def reorder_jobs(body: ApplicationReorder, db: Session = Depends(get_db)):
    uid_set = set(body.ids)
    rows = db.query(Job).filter(Job.id.in_(body.ids)).all()
    if len(rows) != len(uid_set):
        raise HTTPException(status_code=400, detail="部分记录不存在")
    row_map = {r.id: r for r in rows}
    n = len(body.ids)
    for i, fid in enumerate(body.ids):
        item = row_map.get(fid)
        if item:
            item.display_order = float(n - i)
    db.commit()
    return {"ok": True, "count": n}
