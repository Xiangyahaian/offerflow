"""象遇 · 邮件结构化抽取（JSON）与投递表字段对齐。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from cryptography.fernet import InvalidToken
from pydantic import BaseModel, Field, field_validator

from backend.ai_assistant_llm import chat_completion
from backend.mail_crypto import decrypt_secret
from backend.models import UserAiAssistantSettings

logger = logging.getLogger(__name__)

VALID_ROUND_TYPES = ("笔试", "一面", "二面", "三面", "HR面")
VALID_STATUS = ("pending", "sent", "rejected", "offered", "accepted")
VALID_TRACK = ("internship", "campus", "unknown")

ROUND_TYPE_ALIASES = {
    "技术一面": "一面",
    "第一轮": "一面",
    "第一轮面试": "一面",
    "技术面": "一面",
    "技术二面": "二面",
    "第二轮": "二面",
    "第二轮面试": "二面",
    "终面": "三面",
    "第三轮": "三面",
    "hr面": "HR面",
    "hr 面": "HR面",
    "人事面": "HR面",
}


class InterviewRoundExtract(BaseModel):
    type: str = "一面"
    time: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def norm_type(cls, v: Any) -> str:
        t = str(v or "").strip()
        if not t:
            return "一面"
        if t in VALID_ROUND_TYPES:
            return t
        low = t.lower()
        for k, val in ROUND_TYPE_ALIASES.items():
            if k.lower() in low or low in k.lower():
                return val
        if "笔试" in t:
            return "笔试"
        if "hr" in low:
            return "HR面"
        if "二面" in t or "复试" in t:
            return "二面"
        if "三面" in t or "终面" in t:
            return "三面"
        if "一面" in t or "初试" in t:
            return "一面"
        return "一面"

    @field_validator("time", mode="before")
    @classmethod
    def norm_time(cls, v: Any) -> str:
        return _normalize_datetime_str(str(v or "").strip())


class MailApplicationExtract(BaseModel):
    """与实习/校招投递表字段对齐的抽取结果。"""

    track: str = "unknown"
    company: Optional[str] = None
    position: Optional[str] = None
    status: Optional[str] = None
    interview_rounds: List[InterviewRoundExtract] = Field(default_factory=list)
    salary: Optional[str] = None
    total_package: Optional[str] = None
    monthly_salary: Optional[str] = None
    remarks: Optional[str] = None
    create_if_missing: bool = True
    confidence: float = 0.0

    @field_validator("track", mode="before")
    @classmethod
    def norm_track(cls, v: Any) -> str:
        t = str(v or "unknown").strip().lower()
        if t in ("intern", "internship", "实习"):
            return "internship"
        if t in ("campus", "job", "校招", "正式"):
            return "campus"
        return "unknown" if t not in VALID_TRACK else t

    @field_validator("status", mode="before")
    @classmethod
    def norm_status(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        s = str(v).strip().lower()
        mapping = {
            "未投递": "pending",
            "已投递": "sent",
            "拒绝": "rejected",
            "被拒": "rejected",
            "拒绝信": "rejected",
            "offer": "offered",
            "录用": "offered",
            "接受": "accepted",
            "面试": "sent",
            "面试中": "sent",
        }
        if s in mapping:
            return mapping[s]
        if s in VALID_STATUS:
            return s
        if s == "replied":
            return "sent"
        return None


class MailParseResult(BaseModel):
    summary: str
    category: str = "general"
    application: Optional[MailApplicationExtract] = None


def _normalize_datetime_str(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip().replace("：", ":").replace("／", "/")
    if "T" in s and re.match(r"\d{4}-\d{2}-\d{2}T", s):
        try:
            dt = datetime.fromisoformat(s.replace("Z", ""))
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    m = re.search(
        r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?"
        r"(?:[（(]周[一二三四五六日天][)）])?"
        r"\s*(\d{1,2})?:?(\d{1,2})?",
        s,
    )
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4) or 0)
        mm = int(m.group(5) or 0)
        return datetime(y, mo, d, hh, mm).strftime("%Y-%m-%dT%H:%M:%S")
    return s[:32]


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _category_from_application(app: Optional[MailApplicationExtract], summary: str) -> str:
    if not app:
        low = (summary or "").lower()
        if "招聘" in summary or "投递" in summary:
            return "recruit"
        if "面试" in summary:
            return "interview"
        if "offer" in low:
            return "offer"
        if "拒绝" in summary:
            return "notice"
        return "general"
    st = app.status or ""
    if st == "rejected":
        return "notice"
    if st == "offered" or st == "accepted":
        return "offer"
    if app.interview_rounds:
        return "interview"
    if st == "sent":
        return "recruit"
    return "general"


def parse_mail_llm_payload(raw: str) -> MailParseResult:
    """解析模型返回的 JSON（或回退为纯摘要）。"""
    data = _extract_json_object(raw)
    if not data:
        text = (raw or "").strip()
        return MailParseResult(summary=text or "（无摘要）", category="general")

    summary = str(data.get("summary") or "").strip() or "（无摘要）"
    category = str(data.get("category") or "").strip().lower() or "general"
    app_raw = data.get("application")
    application: Optional[MailApplicationExtract] = None
    if isinstance(app_raw, dict) and app_raw:
        try:
            application = MailApplicationExtract.model_validate(app_raw)
        except Exception as e:
            logger.warning("邮件 application JSON 校验失败: %s", e)
    if category not in ("recruit", "interview", "offer", "notice", "general"):
        category = _category_from_application(application, summary)
    else:
        if category == "general" and application:
            category = _category_from_application(application, summary)
    return MailParseResult(summary=summary, category=category, application=application)


def parse_mail_with_llm(
    settings: UserAiAssistantSettings,
    *,
    subject: str,
    from_addr: str,
    snippet: str,
    body_text: str,
) -> MailParseResult:
    """一次 LLM 调用：中文摘要 + 与投递表对齐的 application JSON。"""
    fallback_summary = _fallback_summary_plain(subject, from_addr, snippet)

    if not settings.api_key_encrypted or not settings.base_url or not settings.model:
        return MailParseResult(summary=fallback_summary, category="general")

    try:
        api_key = decrypt_secret(settings.api_key_encrypted)
    except InvalidToken:
        return MailParseResult(summary=fallback_summary, category="general")

    system = (
        "你是 OfferFlow 邮件解析器。必须只输出一个 JSON 对象，不要 Markdown、不要解释。\n"
        "JSON 结构：\n"
        '{"summary":"3-5句中文摘要","category":"recruit|interview|offer|notice|general",'
        '"application":{...}或 null}\n'
        "application 字段（与求职投递表对齐，无关邮件填 null）：\n"
        '- track: "internship"（实习）| "campus"（校招/全职）| "unknown"\n'
        "- company: 公司名（必填，以邮件正文/主题为准，勿改成其他简称）\n"
        "- position: 岗位名，无则空字符串\n"
        '- status: null 或 "pending"|"sent"|"rejected"|"offered"|"accepted"\n'
        '- interview_rounds: [{"type":"笔试|一面|二面|三面|HR面","time":"2026-06-10T10:00:00"}]\n'
        "  时间用 ISO 本地时间；从邮件提取面试/笔试时间\n"
        "- salary: 实习日薪等（实习邮件）\n"
        "- total_package / monthly_salary: 校招薪酬（如有）\n"
        "- remarks: 可写入表格备注的短句\n"
        "- create_if_missing: true\n"
        "- confidence: 0-1\n"
        "规则：面试邀请通常 status=sent 并填 interview_rounds；拒信 status=rejected；"
        "录用通知 status=offered。禁止 emoji。"
    )
    user_msg = (
        f"主题：{subject}\n发件人：{from_addr}\n摘要：{snippet}\n\n正文：\n{body_text[:6000]}"
    )
    try:
        text, _ = chat_completion(
            base_url=settings.base_url or "",
            api_key=api_key,
            model=settings.model or "",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=900,
            temperature=0.2,
        )
        result = parse_mail_llm_payload(text)
        if not result.summary:
            result.summary = fallback_summary
        return result
    except Exception as e:
        logger.warning("象遇结构化解析失败: %s", e)
        return MailParseResult(summary=fallback_summary, category="general")


def _fallback_summary_plain(subject: str, from_addr: str, snippet: str) -> str:
    subj = (subject or "(无主题)").strip()
    frm = (from_addr or "未知发件人").strip()
    sn = (snippet or "").strip()[:280]
    return f"【{frm}】{subj}" + (f"。{sn}" if sn else "")


def application_extract_to_json(app: Optional[MailApplicationExtract]) -> Optional[str]:
    if not app:
        return None
    return app.model_dump_json(exclude_none=True)


def application_extract_from_json(raw: Optional[str]) -> Optional[MailApplicationExtract]:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return MailApplicationExtract.model_validate(data)
    except Exception:
        return None
    return None
