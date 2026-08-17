from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def normalize_application_status(status: Optional[str]) -> Optional[str]:
    if status == "replied":
        return "sent"
    return status


def normalize_application_position(position: Optional[str]) -> str:
    if position is None:
        return ""
    return str(position).strip()


class InternshipCreate(BaseModel):
    company: str = Field(..., min_length=1, max_length=200)
    position: Optional[str] = Field(default="", max_length=200)
    description: Optional[str] = None
    link: Optional[str] = None
    priority: Optional[str] = "normal"
    applied_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    interview_rounds: Optional[str] = None
    status: Optional[str] = "pending"
    passed: Optional[str] = "unknown"
    completed: Optional[bool] = False
    salary: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status_create(cls, v):
        return normalize_application_status(v)

    @field_validator("position", mode="before")
    @classmethod
    def _norm_position_create(cls, v):
        return normalize_application_position(v)


class InternshipUpdate(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    applied_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    interview_rounds: Optional[str] = None
    status: Optional[str] = None
    passed: Optional[str] = None
    completed: Optional[bool] = None
    salary: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status_update(cls, v):
        return normalize_application_status(v)


class InternshipResponse(BaseModel):
    id: str
    user_id: str | None = None
    company: str
    position: str
    description: Optional[str] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    applied_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    interview_rounds: Optional[str] = None
    status: Optional[str] = None
    passed: Optional[str] = None
    completed: Optional[bool] = None
    salary: Optional[str] = None
    remarks: Optional[str] = None
    pinned: Optional[int] = 0
    display_order: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status_response(cls, v):
        return normalize_application_status(v)

    model_config = {"from_attributes": True}


class InternshipListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[InternshipResponse]


class InternshipBatchBody(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=200)
    delete: bool = False
    status: Optional[str] = None
    priority: Optional[str] = None
    pinned: Optional[int] = Field(None, ge=0, le=1)

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status_batch(cls, v):
        return normalize_application_status(v)

    @model_validator(mode="after")
    def require_action(self):
        if self.delete:
            return self
        if self.status is None and self.priority is None and self.pinned is None:
            raise ValueError("请指定要修改的字段，或选择删除")
        return self


class JobCreate(BaseModel):
    company: str = Field(..., min_length=1, max_length=200)
    position: Optional[str] = Field(default="", max_length=200)
    description: Optional[str] = None
    link: Optional[str] = None
    priority: Optional[str] = "normal"
    applied_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    interview_rounds: Optional[str] = None
    status: Optional[str] = "pending"
    passed: Optional[str] = "unknown"
    completed: Optional[bool] = False
    total_package: Optional[str] = None
    monthly_salary: Optional[str] = None
    months: Optional[str] = None
    stock: Optional[str] = None
    benefits: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def _norm_job_status_create(cls, v):
        return normalize_application_status(v)

    @field_validator("position", mode="before")
    @classmethod
    def _norm_job_position_create(cls, v):
        return normalize_application_position(v)


class JobUpdate(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    applied_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    interview_rounds: Optional[str] = None
    status: Optional[str] = None
    passed: Optional[str] = None
    completed: Optional[bool] = None
    total_package: Optional[str] = None
    monthly_salary: Optional[str] = None
    months: Optional[str] = None
    stock: Optional[str] = None
    benefits: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def _norm_job_status_update(cls, v):
        return normalize_application_status(v)


class JobResponse(BaseModel):
    id: str
    user_id: str | None = None
    company: str
    position: str
    description: Optional[str] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    applied_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    interview_rounds: Optional[str] = None
    status: Optional[str] = None
    passed: Optional[str] = None
    completed: Optional[bool] = None
    total_package: Optional[str] = None
    monthly_salary: Optional[str] = None
    months: Optional[str] = None
    stock: Optional[str] = None
    benefits: Optional[str] = None
    remarks: Optional[str] = None
    pinned: Optional[int] = 0
    display_order: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("status", mode="before")
    @classmethod
    def _norm_job_status_response(cls, v):
        return normalize_application_status(v)

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[JobResponse]


class JobBatchBody(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=200)
    delete: bool = False
    status: Optional[str] = None
    priority: Optional[str] = None
    pinned: Optional[int] = Field(None, ge=0, le=1)

    @field_validator("status", mode="before")
    @classmethod
    def _norm_job_status_batch(cls, v):
        return normalize_application_status(v)

    @model_validator(mode="after")
    def require_action(self):
        if self.delete:
            return self
        if self.status is None and self.priority is None and self.pinned is None:
            raise ValueError("请指定要修改的字段，或选择删除")
        return self


class DashboardStats(BaseModel):
    total_internships: int
    total_jobs: int
    unread_mail: int = 0
    pending_internships: int
    pending_jobs: int
    offered_internships: int
    offered_jobs: int


class DashboardResponse(BaseModel):
    stats: DashboardStats


class ApplicationReorder(BaseModel):
    ids: List[str] = Field(..., min_length=1)

# ============ 邮箱读取 / AI 解析 ============

class MailSettingsResponse(BaseModel):

    primary_email: str

    primary_provider: Optional[str] = None

    primary_imap_host: Optional[str] = None

    primary_imap_port: int = 993

    primary_configured: bool = False

    secondary_email: Optional[str] = None

    secondary_provider: Optional[str] = None

    secondary_imap_host: Optional[str] = None

    secondary_imap_port: int = 993

    secondary_configured: bool = False

class MailSettingsUpdate(BaseModel):

    primary_provider: Optional[str] = None

    primary_imap_host: Optional[str] = None

    primary_imap_port: Optional[int] = None

    """传空字符串表示清除主邮箱授权码；不传该字段表示不修改"""

    primary_auth_code: Optional[str] = None

    secondary_email: Optional[str] = None

    secondary_provider: Optional[str] = None

    secondary_imap_host: Optional[str] = None

    secondary_imap_port: Optional[int] = None

    secondary_auth_code: Optional[str] = None

class MailMessageItem(BaseModel):

    uid: str

    subject: str

    from_addr: str

    date: Optional[str] = None

    snippet: str = ""

    body_text: Optional[str] = None

    body_html: Optional[str] = None

class MailMessagesResponse(BaseModel):

    slot: str

    mailbox: str

    items: List[MailMessageItem]

class MailMessageBodyResponse(BaseModel):

    seq: str

    subject: str

    from_addr: str

    date: Optional[str] = None

    snippet: str = ""

    body_text: Optional[str] = None

    body_html: Optional[str] = None





# ============ 会员管理 ============

class AiAssistantModelOption(BaseModel):

    id: str

    label: str

class AiAssistantProviderOption(BaseModel):

    id: str

    label: str

    base_url: str

    models: List[AiAssistantModelOption]

class AiAssistantProvidersResponse(BaseModel):

    providers: List[AiAssistantProviderOption]

class AiAssistantSettingsResponse(BaseModel):

    provider_id: Optional[str] = None

    base_url: Optional[str] = None

    model: Optional[str] = None

    api_key_configured: bool = False

    auto_parse_mail: bool = True

    primary_mail_configured: bool = False

    secondary_mail_configured: bool = False

    primary_email: str = ""

    secondary_email: Optional[str] = None

    resume_configured: bool = False

    resume_filename: Optional[str] = None

    resume_updated_at: Optional[datetime] = None

    resume_summary_preview: Optional[str] = None

class AiAssistantSettingsUpdate(BaseModel):

    provider_id: Optional[str] = None

    base_url: Optional[str] = None

    model: Optional[str] = None

    api_key: Optional[str] = None

    auto_parse_mail: Optional[bool] = None

class AiAssistantCheckRequest(BaseModel):

    base_url: Optional[str] = None

    model: Optional[str] = None

    api_key: Optional[str] = None

class AiAssistantCheckResponse(BaseModel):

    ok: bool

    message: str

    latency_ms: Optional[int] = None

class AiAssistantMailInsightItem(BaseModel):

    id: str

    mail_slot: str

    mail_seq: str

    mailbox: Optional[str] = None

    subject: Optional[str] = None

    from_addr: Optional[str] = None

    mail_date: Optional[str] = None

    summary: str

    category: str = "general"

    is_read: bool = False

    is_parsed: bool = False

    application_extract: Optional[dict] = None

    application_applied: bool = False

    application_apply_result: Optional[dict] = None

    created_at: datetime



    class Config:

        from_attributes = True



    @field_validator("application_extract", "application_apply_result", mode="before")

    @classmethod

    def _parse_json_cols(cls, v):

        if v is None or isinstance(v, dict):

            return v

        if isinstance(v, str) and v.strip():

            try:

                import json



                return json.loads(v)

            except json.JSONDecodeError:

                return None

        return None

class AiAssistantUnreadItem(BaseModel):

    insight_id: str

    mail_slot: str

    mail_seq: str

    subject: Optional[str] = None

class AiAssistantUnreadStatusResponse(BaseModel):

    unread_count: int = 0

    items: List[AiAssistantUnreadItem] = Field(default_factory=list)

class MailUnreadItem(BaseModel):

    mail_slot: str

    mail_seq: str

    subject: Optional[str] = None

    insight_id: Optional[str] = None

class MailUnreadStatusResponse(BaseModel):

    """邮箱侧：侧栏角标 + 待解析 + 未在邮箱页打开（列表圆点）。"""

    mail_nav_count: int = 0

    pending_parse_count: int = 0

    pending_parse_items: List[MailUnreadItem] = Field(default_factory=list)

    unseen_count: int = 0

    unseen_items: List[MailUnreadItem] = Field(default_factory=list)

class MailMarkSeenRequest(BaseModel):

    mail_slot: str = Field(..., min_length=3, max_length=16)

    mail_seq: str = Field(..., min_length=1, max_length=24)

class AiAssistantInsightOpenRequest(BaseModel):

    insight_id: Optional[str] = None

    mail_slot: Optional[str] = None

    mail_seq: Optional[str] = None

class AiAssistantApplicationSyncItem(BaseModel):

    insight_id: Optional[str] = None

    subject: Optional[str] = None

    ok: bool = False

    action: Optional[str] = None

    track: Optional[str] = None

    record_id: Optional[str] = None

    company: Optional[str] = None

    position: Optional[str] = None

    reason: Optional[str] = None

class AiAssistantInsightOpenResponse(BaseModel):

    insight: AiAssistantMailInsightItem

    newly_parsed: bool = False

    application_sync: Optional[dict] = None

class AiAssistantInsightsResponse(BaseModel):

    total: int

    items: List[AiAssistantMailInsightItem]

    last_sync_at: Optional[str] = None

class AiAssistantSyncResponse(BaseModel):

    scanned: int

    new_insights: int

    slots: List[str] = Field(default_factory=list)

    synced_at: str

    new_items: List[AiAssistantUnreadItem] = Field(default_factory=list)

    pending_parse_items: List[AiAssistantUnreadItem] = Field(default_factory=list)

    applications_updated: List[AiAssistantApplicationSyncItem] = Field(default_factory=list)

class MailDemoCompanyItem(BaseModel):

    id: str

    name: str

    short_name: str

    tagline: str

    track: str

    position: str

    brand_color: str

    brand_accent: str

    exam_datetime_label: str

class MailDemoOptionsResponse(BaseModel):

    companies: List[MailDemoCompanyItem] = Field(default_factory=list)

    target_email: Optional[str] = None

    mail_configured: bool = False

    ai_configured: bool = False

    exam_datetime_label: str = ""

class MailDemoSendRequest(BaseModel):

    company: str = Field(..., min_length=2, max_length=32, description="bytedance|meituan|jd|pinduoduo")

class MailDemoSendResponse(BaseModel):

    ok: bool = True

    test_id: str

    company_id: str

    company_name: str

    track: str

    position: str

    sent_to: str

    mail_slot: str

    subject: str

    exam_datetime: str

    ai_configured: bool = False

class MailDemoSyncRequest(BaseModel):

    company: str = Field(..., min_length=2, max_length=32)

    test_id: str = Field(..., min_length=8, max_length=32)

class MailDemoSyncResponse(BaseModel):

    ok: bool = True

    test_id: str

    company_id: str

    company_name: str

    track: str

    mail_slot: str

    mail_received: bool = False

    ai_configured: bool = False

    sync: AiAssistantSyncResponse

