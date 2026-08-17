"""演示用模拟校招/实习笔试邀请邮件：发信 + 象遇同步解析 + 投递表更新。"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.ai_assistant_apply import apply_mail_application_extract
from backend.ai_assistant_apply_match import MailApplyMatchDecision
from backend.ai_assistant_demo import find_demo_mail_seq, is_demo_mail
from backend.ai_assistant_extract import (
    InterviewRoundExtract,
    MailApplicationExtract,
    application_extract_from_json,
    application_extract_to_json,
)
from backend.ai_assistant_mail import HISTORICAL_MAIL_SUMMARY
from backend.mail_smtp import send_plain_email
from backend.models import AiAssistantMailInsight, Internship, Job, User, UserAiAssistantSettings, UserMailSettings

logger = logging.getLogger(__name__)

_WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

DEMO_COMPANIES: Dict[str, Dict[str, Any]] = {
    "bytedance": {
        "name": "字节跳动",
        "short_name": "字节",
        "tagline": "日常实习 · 笔试",
        "track": "internship",
        "position": "后端开发实习生(模拟)",
        "brand_color": "#000000",
        "brand_accent": "#fe2c55",
        "subject": "【字节跳动】实习招聘 - 在线笔试邀请",
        "body": """同学，你好！

感谢你对字节跳动实习岗位的关注与申请。

你已通过简历筛选，现邀请参加在线笔试（OfferFlow 演示邮件 #{test_id}），安排如下：

【招聘类型】日常实习
【应聘公司】字节跳动
【应聘职位】后端开发实习生(模拟)
【考核环节】在线笔试
【笔试时间】{exam_date}（{weekday}）{exam_time} - 21:00（北京时间）
【笔试时长】约 120 分钟
【笔试平台】牛客网
【笔试链接】https://exam.nowcoder.com/mock/bytedance-intern-{test_id}

注意事项：
1. 请使用电脑作答，推荐 Chrome 浏览器；
2. 开考后 30 分钟内可进入，迟到视为放弃；
3. 笔试含选择题、编程题，可使用 C++/Java/Python 任一语言；
4. 请提前调试摄像头与网络环境。

祝考试顺利！

字节跳动校园招聘团队
ByteDance Campus Recruitment

---
本邮件为 OfferFlow 演示邮件，用于体验象遇智能解析与投递同步，非字节跳动官方邮件。编号：{test_id}
""",
    },
    "meituan": {
        "name": "美团",
        "short_name": "美团",
        "tagline": "2026 校招 · 笔试",
        "track": "campus",
        "position": "后端开发工程师(模拟)",
        "brand_color": "#FFC300",
        "brand_accent": "#000000",
        "subject": "【美团】2026校园招聘 - 技术岗位笔试通知",
        "body": """您好，

感谢您关注美团 2026 校园招聘。

恭喜您通过简历筛选，现邀请您参加技术岗位在线笔试（OfferFlow 演示邮件 #{test_id}），安排如下：

【招聘类型】2026 届校园招聘
【应聘公司】美团
【应聘职位】后端开发工程师(模拟)
【考核环节】在线笔试
【笔试时间】{exam_date}（{weekday}）{exam_time} - 21:00（北京时间）
【笔试时长】约 120 分钟
【笔试平台】美团校招笔试系统
【考前链接】https://exam.meituan.com/mock/campus-tech-{test_id}

注意事项：
1. 请提前 15 分钟登录并完成设备检测；
2. 笔试全程需开启摄像头，请确保环境安静；
3. 内容含计算机基础、算法与后端相关题目；
4. 如需改期，请于 48 小时内回复本邮件说明可参加时段。

祝您考试顺利！

美团校园招聘团队
Meituan Campus Recruitment

---
本邮件为 OfferFlow 演示邮件，用于体验象遇智能解析与投递同步，非美团官方邮件。编号：{test_id}
""",
    },
    "jd": {
        "name": "京东",
        "short_name": "京东",
        "tagline": "2026 校招 · 笔试",
        "track": "campus",
        "position": "软件开发工程师(模拟)",
        "brand_color": "#E1251B",
        "brand_accent": "#FFFFFF",
        "subject": "【京东】2026届校园招聘 - 软件开发工程师笔试邀请",
        "body": """尊敬的同学，您好：

感谢您应聘京东 2026 届校园招聘技术类岗位（OfferFlow 演示邮件 #{test_id}）。

经简历筛选，现邀请您参加软件开发工程师(模拟)岗位在线笔试，安排如下：

【招聘类型】2026 届校园招聘
【应聘公司】京东
【应聘职位】软件开发工程师(模拟)
【考核环节】在线笔试（闭卷）
【笔试时间】{exam_date}（{weekday}）{exam_time} - 21:00（北京时间）
【笔试时长】约 120 分钟
【笔试平台】北森测评系统
【笔试入口】https://exam.beisen.com/jd/mock/{test_id}

注意事项：
1. 请使用电脑作答，不支持手机端；
2. 请携带身份证，考前完成身份核验；
3. 考试期间不得查阅资料或使用 AI 工具；
4. 如遇技术问题，请联系京东校招技术支持。

祝您考试顺利！

京东集团人力资源部 · 校园招聘
JD Campus Recruitment

---
本邮件为 OfferFlow 演示邮件，用于体验象遇智能解析与投递同步，非京东官方邮件。编号：{test_id}
""",
    },
    "pinduoduo": {
        "name": "拼多多",
        "short_name": "拼多多",
        "tagline": "暑期实习 · 笔试",
        "track": "internship",
        "position": "服务端开发实习生(模拟)",
        "brand_color": "#E02E24",
        "brand_accent": "#FF6A00",
        "subject": "【拼多多】暑期实习招聘 - 服务端开发笔试邀请",
        "body": """同学你好，

感谢你对拼多多暑期实习岗位的关注（OfferFlow 演示邮件 #{test_id}）。

你已通过简历筛选，现邀请参加服务端开发实习生(模拟)岗位在线笔试：

【招聘类型】暑期日常实习
【应聘公司】拼多多
【应聘职位】服务端开发实习生(模拟)
【考核环节】在线笔试
【笔试时间】{exam_date}（{weekday}）{exam_time} - 21:00（北京时间）
【笔试时长】约 120 分钟
【笔试平台】拼多多校招笔试系统
【登录链接】https://exam.pinduoduo.com/mock/intern-{test_id}

注意事项：
1. 建议使用 Chrome 浏览器，保持网络稳定；
2. 笔试含算法题与工程基础题，请提前准备 IDE 环境；
3. 开考 30 分钟后禁止入场；
4. 如有疑问，请回复本邮件或联系拼多多校招邮箱。

祝考试顺利！

拼多多人力资源部 · 校园招聘组
PDD Campus Recruitment

---
本邮件为 OfferFlow 演示邮件，用于体验象遇智能解析与投递同步，非拼多多官方邮件。编号：{test_id}
""",
    },
}


def demo_company_ids() -> List[str]:
    return list(DEMO_COMPANIES.keys())


def get_demo_exam_schedule(now: Optional[datetime] = None) -> Dict[str, str]:
    """统一：两天后的晚上 19:00。"""
    base = (now or datetime.now()).replace(second=0, microsecond=0)
    target = base + timedelta(days=2)
    target = target.replace(hour=19, minute=0)
    return {
        "exam_date": f"{target.year}年{target.month}月{target.day}日",
        "weekday": _WEEKDAY_ZH[target.weekday()],
        "exam_time": "19:00",
        "exam_datetime_label": (
            f"{target.year}年{target.month}月{target.day}日（{_WEEKDAY_ZH[target.weekday()]}）19:00"
        ),
    }


def render_demo_mail(company_id: str, *, test_id: Optional[str] = None) -> Tuple[str, str, Dict[str, str]]:
    cid = (company_id or "").strip().lower()
    meta = DEMO_COMPANIES.get(cid)
    if not meta:
        raise ValueError(f"未知演示公司：{company_id}")
    schedule = get_demo_exam_schedule()
    tid = test_id or datetime.now().strftime("%Y%m%d%H%M%S")
    fmt = defaultdict(str, test_id=tid, **schedule)
    body = meta["body"].format_map(fmt)
    subject = meta["subject"]
    return subject, body, schedule


def resolve_demo_recipient(user: User, mail: UserMailSettings) -> Tuple[str, str]:
    """返回 (邮箱地址, slot 说明)。"""
    primary_ok = bool(mail.primary_provider and mail.primary_auth_encrypted)
    secondary_ok = bool(
        mail.secondary_email and mail.secondary_provider and mail.secondary_auth_encrypted
    )
    if not primary_ok and not secondary_ok:
        raise ValueError("请先在「邮箱读取 → 邮箱设置」中配置 IMAP 授权码")
    if primary_ok:
        return user.email, "primary"
    return (mail.secondary_email or "").strip(), "secondary"


def _ai_ready(ai: Optional[UserAiAssistantSettings]) -> bool:
    if not ai:
        return False
    return bool((ai.base_url or "").strip() and (ai.model or "").strip() and ai.api_key_encrypted)


def send_demo_mail(
    user: User,
    mail: UserMailSettings,
    ai: UserAiAssistantSettings,
    company_id: str,
) -> Dict[str, Any]:
    """仅发送演示邮件，不拉取收件箱、不触发 AI 解析。"""
    cid = (company_id or "").strip().lower()
    if cid not in DEMO_COMPANIES:
        raise ValueError("请选择有效的演示公司")

    to_addr, slot_hint = resolve_demo_recipient(user, mail)
    test_id = datetime.now().strftime("%Y%m%d%H%M%S")
    subject, body, schedule = render_demo_mail(cid, test_id=test_id)
    full_subject = f"{subject} [#{test_id}]"

    send_plain_email(to_addr, full_subject, body)
    logger.info("演示邮件已发送 user=%s company=%s to=%s test_id=%s", user.id, cid, to_addr, test_id)

    company_meta = DEMO_COMPANIES[cid]
    return {
        "ok": True,
        "test_id": test_id,
        "company_id": cid,
        "company_name": company_meta["name"],
        "track": company_meta["track"],
        "position": company_meta["position"],
        "sent_to": to_addr,
        "mail_slot": slot_hint,
        "subject": full_subject,
        "exam_datetime": schedule["exam_datetime_label"],
        "ai_configured": _ai_ready(ai),
    }


def _demo_exam_iso_time(now: Optional[datetime] = None) -> str:
    base = (now or datetime.now()).replace(second=0, microsecond=0)
    target = base + timedelta(days=2)
    target = target.replace(hour=19, minute=0)
    return target.strftime("%Y-%m-%dT%H:%M:%S")


def build_demo_application_extract(company_id: str) -> MailApplicationExtract:
    """演示邮件结构化抽取兜底（不依赖 LLM）。"""
    cid = (company_id or "").strip().lower()
    meta = DEMO_COMPANIES[cid]
    return MailApplicationExtract(
        track=meta["track"],
        company=meta["name"],
        position=meta["position"],
        status="sent",
        interview_rounds=[
            InterviewRoundExtract(type="笔试", time=_demo_exam_iso_time())
        ],
        remarks="OfferFlow 邮件模拟自动同步",
        create_if_missing=True,
        confidence=1.0,
    )


def _demo_company_match(a: str, b: str) -> bool:
    import re

    na = re.sub(r"[\s·\-—（）()]", "", (a or "")).lower()
    nb = re.sub(r"[\s·\-—（）()]", "", (b or "")).lower()
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def demo_apply_decision(
    db: Session,
    user_id: str,
    company_id: str,
    extract: MailApplicationExtract,
) -> MailApplyMatchDecision:
    """演示邮件投递匹配：优先更新已有同公司记录，否则按演示 track 新建。"""
    cid = (company_id or "").strip().lower()
    meta = DEMO_COMPANIES.get(cid) or {}
    company = (meta.get("name") or extract.company or "").strip()
    track = meta.get("track") or extract.track or "campus"
    position = (meta.get("position") or extract.position or "").strip() or None

    for model, tk in ((Internship, "internship"), (Job, "campus")):
        rows = (
            db.query(model)
            .filter(model.user_id == user_id)
            .order_by(model.display_order.asc())
            .limit(200)
            .all()
        )
        for row in rows:
            if _demo_company_match(row.company or "", company):
                return MailApplyMatchDecision(
                    action="update",
                    track=tk,
                    record_id=row.id,
                    position_label=position,
                    confidence=0.95,
                    reason="演示邮件匹配已有投递",
                )

    from backend.ai_assistant_apply_match import find_catalog_id_for_company

    return MailApplyMatchDecision(
        action="create",
        track=track if track in ("internship", "campus") else "campus",
        catalog_job_link_id=find_catalog_id_for_company(db, company),
        position_label=position,
        confidence=0.95,
        reason="演示邮件新建投递",
    )


def _reset_stale_demo_insight(
    db: Session,
    user_id: str,
    test_id: str,
) -> None:
    """若演示信曾被误判为历史邮件，重置为待解析。"""
    rows = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user_id,
            AiAssistantMailInsight.subject.contains(test_id),
        )
        .all()
    )
    changed = False
    for row in rows:
        if not is_demo_mail(row.subject or "", row.body_text or ""):
            continue
        if row.summary == HISTORICAL_MAIL_SUMMARY or (
            row.is_parsed and not row.application_extract
        ):
            row.is_parsed = False
            row.is_read = False
            row.summary = "新邮件已收到，正在解析…"
            row.application_applied = False
            row.application_apply_result = None
            changed = True
    if changed:
        db.commit()


def ensure_demo_insight_applied(
    db: Session,
    user: User,
    ai: UserAiAssistantSettings,
    company_id: str,
    test_id: str,
) -> Optional[Dict[str, Any]]:
    """演示同步后兜底：确保写入实习/校招投递表。"""
    tid = (test_id or "").strip()
    cid = (company_id or "").strip().lower()
    if not tid or cid not in DEMO_COMPANIES:
        return None

    row = (
        db.query(AiAssistantMailInsight)
        .filter(
            AiAssistantMailInsight.user_id == user.id,
            AiAssistantMailInsight.subject.contains(tid),
        )
        .order_by(AiAssistantMailInsight.created_at.desc())
        .first()
    )
    if not row:
        return None

    if row.application_apply_result:
        try:
            prev = json.loads(row.application_apply_result)
            if row.application_applied and prev.get("ok"):
                return prev
        except json.JSONDecodeError:
            pass

    extract = (
        application_extract_from_json(row.application_extract)
        if row.application_extract
        else None
    )
    if not extract or not (extract.company or "").strip():
        extract = build_demo_application_extract(cid)
    elif not extract.interview_rounds:
        fallback = build_demo_application_extract(cid)
        extract.interview_rounds = fallback.interview_rounds
        extract.status = extract.status or fallback.status
        extract.track = extract.track if extract.track in ("internship", "campus") else fallback.track

    if not extract.create_if_missing:
        extract.create_if_missing = True

    decision = demo_apply_decision(db, user.id, cid, extract)
    result = apply_mail_application_extract(
        db,
        user.id,
        extract,
        mail_subject=row.subject or "",
        ai=ai,
        decision_override=decision,
    )
    row.application_extract = application_extract_to_json(extract)
    row.application_apply_result = json.dumps(result, ensure_ascii=False)
    if result.get("ok"):
        row.application_applied = True
        if not row.is_parsed:
            row.is_parsed = True
    db.commit()
    return result


def sync_demo_mail(
    db: Session,
    user: User,
    mail: UserMailSettings,
    ai: UserAiAssistantSettings,
    company_id: str,
    test_id: str,
    *,
    verify_retries: int = 2,
    verify_delay_sec: float = 0.5,
) -> Dict[str, Any]:
    """确认演示邮件已在收件箱后，触发象遇解析与投递同步。"""
    cid = (company_id or "").strip().lower()
    tid = (test_id or "").strip()
    if cid not in DEMO_COMPANIES:
        raise ValueError("请选择有效的演示公司")
    if not tid:
        raise ValueError("缺少演示邮件编号")

    _, slot_hint = resolve_demo_recipient(user, mail)
    mail_arrived = bool(find_demo_mail_seq(user, mail, slot_hint, tid))
    if not mail_arrived:
        for attempt in range(max(0, verify_retries)):
            time.sleep(verify_delay_sec)
            if find_demo_mail_seq(user, mail, slot_hint, tid):
                mail_arrived = True
                logger.info("演示邮件校验到达 test_id=%s attempt=%s", tid, attempt + 1)
                break

    if not mail_arrived:
        raise ValueError("演示邮件尚未出现在收件箱，请稍后在邮箱读取页刷新后重试")

    _reset_stale_demo_insight(db, user.id, tid)

    from backend.ai_assistant_mail import sync_user_mail_insights

    try:
        stub_stats = sync_user_mail_insights(
            db, user, mail, ai, slots_only=[slot_hint], parse_mail=False
        )
        stats = sync_user_mail_insights(
            db, user, mail, ai, slots_only=[slot_hint], fetch_mail=False
        )
        if stub_stats.get("pending_parse_items"):
            stats["pending_parse_items"] = stub_stats["pending_parse_items"]
    except Exception as e:
        logger.warning("演示邮件同步失败: %s", e)
        raise

    demo_apply = ensure_demo_insight_applied(db, user, ai, cid, tid)
    if demo_apply and demo_apply.get("ok"):
        updated = list(stats.get("applications_updated") or [])
        already = {u.get("record_id") for u in updated if u.get("record_id")}
        if demo_apply.get("record_id") not in already:
            updated.append(
                {
                    "insight_id": None,
                    "subject": DEMO_COMPANIES[cid]["name"],
                    **demo_apply,
                }
            )
        stats["applications_updated"] = updated

    company_meta = DEMO_COMPANIES[cid]
    return {
        "ok": True,
        "test_id": tid,
        "company_id": cid,
        "company_name": company_meta["name"],
        "track": company_meta["track"],
        "position": company_meta["position"],
        "mail_slot": slot_hint,
        "mail_received": True,
        "ai_configured": _ai_ready(ai),
        "sync": stats,
    }


def send_demo_mail_and_sync(
    db: Session,
    user: User,
    mail: UserMailSettings,
    ai: UserAiAssistantSettings,
    company_id: str,
    *,
    sync_retries: int = 12,
    sync_delay_sec: float = 1.0,
) -> Dict[str, Any]:
    """兼容旧调用：发送后阻塞轮询收件箱再同步。"""
    sent = send_demo_mail(user, mail, ai, company_id)
    tid = sent["test_id"]
    slot_hint = sent["mail_slot"]

    time.sleep(0.8)
    mail_arrived = False
    for attempt in range(max(1, sync_retries)):
        if find_demo_mail_seq(user, mail, slot_hint, tid):
            mail_arrived = True
            break
        if attempt < sync_retries - 1:
            time.sleep(sync_delay_sec)

    if mail_arrived:
        logger.info("演示邮件已出现在收件箱 test_id=%s attempt=%s", tid, attempt + 1)
    else:
        logger.warning("演示邮件轮询超时 test_id=%s，仍尝试同步一次", tid)

    synced = sync_demo_mail(db, user, mail, ai, company_id, tid, verify_retries=0)
    return {**sent, **synced}
