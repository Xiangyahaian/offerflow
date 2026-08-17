"""邮件模拟 · 收件箱轻量轮询（等待演示邮件到达，不跳过 LLM 解析）。"""
from __future__ import annotations

import re
from typing import Any, Optional

DEMO_MAIL_MARKER = "OfferFlow 演示邮件"
DEMO_SUBJECT_TAG_RE = re.compile(r"\[#(\d{14,})\]")


def is_demo_mail(subject: str, snippet: str = "", body: str = "") -> bool:
    """是否为 OfferFlow 邮件模拟发出的演示信。"""
    subj = subject or ""
    blob = f"{subj} {snippet or ''} {body or ''}"
    if DEMO_MAIL_MARKER in blob:
        return True
    return bool(DEMO_SUBJECT_TAG_RE.search(subj))


def parse_demo_test_id(subject: str) -> Optional[str]:
    m = DEMO_SUBJECT_TAG_RE.search(subject or "")
    return m.group(1) if m else None


def find_demo_mail_seq(
    user: Any,
    mail: Any,
    slot: str,
    test_id: str,
    *,
    limit: int = 15,
) -> Optional[str]:
    """轻量 IMAP 轮询：仅查收件箱列表是否出现带 test_id 的主题。"""
    from backend.ai_assistant_mail import _fetch_slot_messages

    needle = f"[#{test_id}]"
    _, items = _fetch_slot_messages(user, mail, slot, limit=limit)
    for it in items:
        subj = str(it.get("subject") or "")
        if needle in subj or test_id in subj:
            seq = str(it.get("uid") or it.get("seq") or "")
            if seq:
                return seq
    return None
