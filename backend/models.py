import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base

LOCAL_USER_ID = "local"


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    """本地单用户占位（邮箱解析 / IMAP 配置挂在此账号上）。"""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False, default="!")
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_preview_guest = Column(Boolean, default=False)

    mail_settings = relationship(
        "UserMailSettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserMailSettings(Base):
    __tablename__ = "user_mail_settings"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    primary_provider = Column(String(20), nullable=True)
    primary_imap_host = Column(String(200), nullable=True)
    primary_imap_port = Column(Integer, default=993)
    primary_auth_encrypted = Column(Text, nullable=True)
    secondary_email = Column(String(255), nullable=True)
    secondary_provider = Column(String(20), nullable=True)
    secondary_imap_host = Column(String(200), nullable=True)
    secondary_imap_port = Column(Integer, default=993)
    secondary_auth_encrypted = Column(Text, nullable=True)
    primary_ivory_watch_since = Column(DateTime, nullable=True)
    primary_ivory_baseline_pending = Column(Boolean, default=False, nullable=False)
    secondary_ivory_watch_since = Column(DateTime, nullable=True)
    secondary_ivory_baseline_pending = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="mail_settings")


class UserAiAssistantSettings(Base):
    __tablename__ = "user_ai_assistant_settings"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    provider_id = Column(String(40), nullable=True)
    base_url = Column(String(500), nullable=True)
    model = Column(String(120), nullable=True)
    api_key_encrypted = Column(Text, nullable=True)
    auto_parse_mail = Column(Boolean, default=True, nullable=False)
    resume_filename = Column(String(255), nullable=True)
    resume_text = Column(Text, nullable=True)
    resume_summary = Column(Text, nullable=True)
    resume_updated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="ai_assistant_settings", uselist=False)


class AiAssistantMailInsight(Base):
    __tablename__ = "ai_assistant_mail_insights"
    __table_args__ = (
        Index("ix_ivory_insight_user_mail", "user_id", "mail_slot", "mail_seq", unique=True),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    mail_slot = Column(String(16), nullable=False)
    mail_seq = Column(String(24), nullable=False)
    mailbox = Column(String(255), nullable=True)
    subject = Column(String(500), nullable=True)
    from_addr = Column(String(300), nullable=True)
    mail_date = Column(String(64), nullable=True)
    summary = Column(Text, nullable=False)
    body_text = Column(Text, nullable=True)
    category = Column(String(40), default="general", nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    is_mail_seen = Column(Boolean, default=False, nullable=False)
    is_parsed = Column(Boolean, default=False, nullable=False)
    application_extract = Column(Text, nullable=True)
    application_applied = Column(Boolean, default=False, nullable=False)
    application_apply_result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Internship(Base):
    __tablename__ = "internships"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True, default=LOCAL_USER_ID)
    company = Column(String(200), nullable=False)
    position = Column(String(200), nullable=False, default="")
    description = Column(Text)
    link = Column(String(500))
    priority = Column(String(20), default="normal")
    applied_at = Column(DateTime, default=datetime.utcnow)
    replied_at = Column(DateTime)
    interview_rounds = Column(Text)
    status = Column(String(20), default="pending")
    passed = Column(String(20), default="unknown")
    completed = Column(Boolean, default=False)
    salary = Column(String(100))
    remarks = Column(Text)
    pinned = Column(Integer, default=0)
    display_order = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True, default=LOCAL_USER_ID)
    company = Column(String(200), nullable=False)
    position = Column(String(200), nullable=False, default="")
    description = Column(Text)
    link = Column(String(500))
    priority = Column(String(20), default="normal")
    applied_at = Column(DateTime, default=datetime.utcnow)
    replied_at = Column(DateTime)
    interview_rounds = Column(Text)
    status = Column(String(20), default="pending")
    passed = Column(String(20), default="unknown")
    completed = Column(Boolean, default=False)
    total_package = Column(String(100))
    monthly_salary = Column(String(100))
    months = Column(String(50))
    stock = Column(String(100))
    benefits = Column(Text)
    remarks = Column(Text)
    pinned = Column(Integer, default=0)
    display_order = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
