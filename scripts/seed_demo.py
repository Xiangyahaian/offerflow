"""写入示例投递数据（本地演示用）。用法: python scripts/seed_demo.py"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database import Base, SessionLocal, engine
from backend.models import LOCAL_USER_ID, Internship, Job

Base.metadata.create_all(bind=engine)


def seed(force: bool = False) -> None:
    db = SessionLocal()
    try:
        job_n = db.query(Job).count()
        intern_n = db.query(Internship).count()
        if (job_n or intern_n) and not force:
            print(f"已有数据（校招 {job_n} / 实习 {intern_n}），跳过。加 --force 可清空后重写。")
            return
        if force:
            db.query(Job).delete()
            db.query(Internship).delete()
            db.commit()

        now = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        from backend.auth import ensure_local_user

        ensure_local_user(db)
        jobs = [
            Job(
                user_id=LOCAL_USER_ID,
                company="字节跳动",
                position="后端开发工程师",
                status="sent",
                priority="top",
                applied_at=now - timedelta(days=12),
                monthly_salary="30K",
                months="16薪",
                total_package="约 55 万",
                interview_rounds=json.dumps(
                    [{"type": "一面", "time": (now + timedelta(days=3)).strftime("%Y-%m-%dT14:00")}],
                    ensure_ascii=False,
                ),
                remarks="校招提前批",
                display_order=5,
            ),
            Job(
                user_id=LOCAL_USER_ID,
                company="阿里巴巴",
                position="Java 开发",
                status="interview",
                priority="important",
                applied_at=now - timedelta(days=20),
                monthly_salary="28K",
                months="16薪",
                interview_rounds=json.dumps(
                    [
                        {"type": "笔试", "time": (now - timedelta(days=5)).strftime("%Y-%m-%d")},
                        {"type": "一面", "time": (now + timedelta(days=1)).strftime("%Y-%m-%dT10:30")},
                    ],
                    ensure_ascii=False,
                ),
                display_order=4,
            ),
            Job(
                user_id=LOCAL_USER_ID,
                company="腾讯",
                position="客户端开发",
                status="pending",
                priority="normal",
                applied_at=None,
                remarks="待投递",
                display_order=3,
            ),
            Job(
                user_id=LOCAL_USER_ID,
                company="美团",
                position="机器学习工程师",
                status="offered",
                priority="top",
                applied_at=now - timedelta(days=40),
                monthly_salary="35K",
                months="15薪",
                total_package="约 60 万",
                stock="RSU 若干",
                remarks="已拿 Offer",
                display_order=2,
                pinned=1,
            ),
            Job(
                user_id=LOCAL_USER_ID,
                company="网易",
                position="游戏服务端",
                status="rejected",
                priority="minor",
                applied_at=now - timedelta(days=30),
                display_order=1,
            ),
        ]
        interns = [
            Internship(
                user_id=LOCAL_USER_ID,
                company="华为",
                position="软件开发实习",
                status="sent",
                priority="important",
                applied_at=now - timedelta(days=8),
                salary="250/天",
                display_order=3,
            ),
            Internship(
                user_id=LOCAL_USER_ID,
                company="小红书",
                position="数据分析实习",
                status="pending",
                priority="normal",
                applied_at=None,
                display_order=2,
            ),
            Internship(
                user_id=LOCAL_USER_ID,
                company="拼多多",
                position="后端实习",
                status="offered",
                priority="top",
                applied_at=now - timedelta(days=25),
                salary="400/天",
                display_order=1,
                pinned=1,
            ),
        ]
        db.add_all(jobs + interns)
        db.commit()
        print(f"已写入示例数据：校招 {len(jobs)} 条，实习 {len(interns)} 条")
    finally:
        db.close()


if __name__ == "__main__":
    seed(force="--force" in sys.argv)
