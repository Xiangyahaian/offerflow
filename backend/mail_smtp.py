"""对外发信：模拟 / SMTP / Resend（事务邮件 API，适合绑定自有域名做正规站）。"""
import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from smtplib import SMTPAuthenticationError, SMTPException
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)


def is_email_delivery_mock() -> bool:
    """
    是否走「不落真实收件箱」的模拟路径。
    - SMTP_MOCK=true 时恒为模拟。
    - MAIL_PROVIDER=resend 且未配 RESEND_API_KEY 时视为未配置，走模拟。
    - 其它情况（默认 smtp）未配 SMTP_HOST 时走模拟。
    """
    if settings.SMTP_MOCK:
        return True
    prov = (getattr(settings, "MAIL_PROVIDER", None) or "smtp").strip().lower()
    if prov == "resend":
        return not (getattr(settings, "RESEND_API_KEY", "") or "").strip()
    return not (settings.SMTP_HOST or "").strip()


def _send_via_resend(
    to_addr: str,
    subject: str,
    body: str,
    body_html: Optional[str] = None,
) -> None:
    """Resend HTTPS API（需 RESEND_API_KEY；发件域名在 Resend 控制台完成 DNS 验证）。"""
    key = (getattr(settings, "RESEND_API_KEY", "") or "").strip()
    if not key:
        raise RuntimeError("已选择 MAIL_PROVIDER=resend 但未配置 RESEND_API_KEY")

    from_addr = format_email_from()
    if not from_addr:
        raise RuntimeError("使用 Resend 时必须配置 EMAIL_FROM（须为已在 Resend 验证的发件地址）")

    timeout = int(getattr(settings, "SMTP_TIMEOUT", None) or 30)
    payload = {"from": from_addr, "to": [to_addr], "subject": subject, "text": body}
    if body_html:
        payload["html"] = body_html
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": f"{settings.APP_NAME}/mail",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status and resp.status >= 400:
                raw = resp.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Resend 返回异常 HTTP {resp.status}：{raw[:400]}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(raw)
            msg = err.get("message") or err.get("name") or raw[:400]
        except Exception:
            msg = raw[:400] if raw else str(e)
        raise RuntimeError(f"Resend 发送失败：{msg}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 Resend API：{e.reason}") from e


def format_email_from() -> str:
    """
    发件人头：显示名 + 邮箱，例如 OfferFlow <postmaster@offerflow.top>。
    收件箱列表里的「名称」来自此处；字母头像多由客户端按显示名/地址自动生成。
    """
    raw_from = (settings.EMAIL_FROM or "").strip()
    raw_user = (settings.SMTP_USER or "").strip()
    display = (getattr(settings, "EMAIL_FROM_NAME", None) or settings.APP_NAME or "").strip()

    if raw_from and "<" in raw_from and ">" in raw_from:
        return raw_from

    _name, addr = parseaddr(raw_from)
    if not addr:
        addr = raw_user or raw_from
    if _name and not display:
        display = _name
    if not addr:
        return raw_from or raw_user or "noreply@offerflow.local"
    if display:
        return formataddr((display, addr))
    return addr


def _from_email_address_only() -> str:
    """仅邮箱地址（用于 Message-ID 域名等）。"""
    _name, addr = parseaddr(format_email_from())
    return addr or (settings.SMTP_USER or settings.EMAIL_FROM or "offerflow.local").strip()


def _message_id_domain() -> str:
    raw = _from_email_address_only()
    if "@" in raw:
        return raw.split("@", 1)[1]
    return raw or "offerflow.local"


def _build_mime_message(
    to_addr: str,
    subject: str,
    body: str,
    body_html: Optional[str] = None,
):
    if body_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = format_email_from()
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=_message_id_domain())
    return msg


def _send_via_smtp(
    to_addr: str,
    subject: str,
    body: str,
    body_html: Optional[str] = None,
) -> None:
    msg = _build_mime_message(to_addr, subject, body, body_html)

    host = settings.SMTP_HOST.strip()
    port = int(settings.SMTP_PORT or 587)
    user = (settings.SMTP_USER or "").strip()
    password = settings.SMTP_PASSWORD or ""
    timeout = int(getattr(settings, "SMTP_TIMEOUT", None) or 30)
    use_ssl = port == 465

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=timeout) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                smtp.ehlo()
                if port != 25:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
    except SMTPAuthenticationError as e:
        logger.warning("SMTP 认证失败 host=%s port=%s user=%s: %s", host, port, user, e)
        raise RuntimeError(
            "SMTP 登录失败：请核对 SMTP_USER、SMTP_PASSWORD。"
            "QQ/163 等邮箱需在网页邮箱中开启 SMTP，并使用「授权码」，不能使用网页登录密码。"
        ) from e
    except (TimeoutError, OSError) as e:
        logger.warning("SMTP 连接失败 host=%s port=%s: %s", host, port, e)
        raise RuntimeError(
            f"无法连接邮件服务器 {host}:{port}。"
            f"请检查网络、SMTP 地址与端口是否正确，以及云服务器安全组是否放行出站 {port}/TCP。"
        ) from e
    except SMTPException as e:
        logger.exception("SMTP 发送异常 host=%s port=%s", host, port)
        raise RuntimeError(f"邮件发送失败（SMTP）：{e}") from e


def send_email(
    to_addr: str,
    subject: str,
    body: str,
    body_html: Optional[str] = None,
) -> None:
    """
    发送事务邮件。提供 body_html 时发 multipart/alternative（纯文本 + HTML）。

    - 模拟：SMTP_MOCK=true，或未配置当前 MAIL_PROVIDER 所需密钥/主机时，只打日志。
    - MAIL_PROVIDER=smtp（默认）：走 SMTP_HOST 等。
    - MAIL_PROVIDER=resend：走 Resend HTTP API。
    """
    to_addr = (to_addr or "").strip()
    if not to_addr:
        raise ValueError("收件邮箱为空")

    if is_email_delivery_mock():
        logger.warning(
            "[邮件 MOCK] 未配置真实发信或已开启 SMTP_MOCK。收件人=%s 主题=%s\n%s",
            to_addr,
            subject,
            body,
        )
        if body_html:
            logger.debug("[邮件 MOCK HTML] 长度=%s", len(body_html))
        return

    prov = (getattr(settings, "MAIL_PROVIDER", None) or "smtp").strip().lower()
    if prov == "resend":
        _send_via_resend(to_addr, subject, body, body_html)
    else:
        _send_via_smtp(to_addr, subject, body, body_html)
    logger.info("事务邮件已投递 to=%s subject=%s", to_addr, subject)


def send_plain_email(to_addr: str, subject: str, body: str) -> None:
    """发送纯文本邮件（兼容旧调用）。"""
    send_email(to_addr, subject, body)
