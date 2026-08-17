"""IMAP 拉取收件箱（QQ / 163 / 126 等），只读。"""
from __future__ import annotations

import email
import imaplib
import re
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

# Python 3.x 标准库 imaplib 未在 Commands 中注册「ID」(RFC2971)。
# 未注册时 _simple_command("ID", ...) 会在 _command() 里 KeyError，异常被吞掉后等于从未发送 ID，
# 网易 188/163 等会一直 SELECT → Unsafe Login。
if "ID" not in imaplib.Commands:
    imaplib.Commands["ID"] = ("NONAUTH", "AUTH", "SELECTED")

# 常见国内邮箱 IMAP（用户需在网页邮箱开启 IMAP 并生成「客户端授权码」）
IMAP_PRESETS: Dict[str, Tuple[str, int]] = {
    "qq": ("imap.qq.com", 993),
    "foxmail": ("imap.qq.com", 993),
    "163": ("imap.163.com", 993),
    "126": ("imap.126.com", 993),
    "yeah": ("imap.yeah.net", 993),
    "188": ("imap.188.com", 993),
}


def resolve_imap_host_port(provider: Optional[str], custom_host: Optional[str], custom_port: Optional[int]) -> Tuple[str, int]:
    p = (provider or "").strip().lower()
    if p == "other":
        h = (custom_host or "").strip()
        if not h:
            raise ValueError("自定义邮箱请填写 IMAP 服务器地址")
        port = int(custom_port or 993)
        return h, port
    if p in IMAP_PRESETS:
        host, port = IMAP_PRESETS[p]
        return host, port
    raise ValueError("不支持的邮箱类型，请选择 QQ / 163 / 126 / Yeah / 188 / Foxmail 或自定义")


def _escape_imap_quoted_content(s: str) -> str:
    """IMAP quoted-string 内转义。"""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _is_netease_mail(host: str, login_email: str) -> bool:
    h = (host or "").lower()
    if any(
        x in h
        for x in (
            "163.com",
            "126.com",
            "yeah.net",
            "188.com",
            "netease.com",
        )
    ):
        return True
    e = (login_email or "").lower().strip()
    return any(
        e.endswith("@" + d)
        for d in ("163.com", "126.com", "yeah.net", "188.com", "netease.com")
    )


def _netease_id_payloads(login_email: str) -> List[str]:
    """多套 ID 参数，兼容网易各产品线对客户端标识的校验（RFC 2971）。"""
    raw = (login_email or "").strip()
    if not raw:
        return ['("name" "OfferFlow" "version" "1.0.0" "vendor" "OfferFlow")']
    q = _escape_imap_quoted_content(raw)
    return [
        f'("name" "OfferFlow" "version" "1.0.0" "vendor" "OfferFlow" '
        f'"support-email" "{q}" "contact" "{q}" "os" "Windows" "os-version" "10")',
        f'("name" "NetEaseMailClient" "version" "1.0" "vendor" "OfferFlow" "support-email" "{q}")',
        f'("name" "Thunderbird" "version" "102.0" "vendor" "Mozilla" "support-email" "{q}")',
    ]


def _send_netease_imap_id(conn: imaplib.IMAP4_SSL, login_email: str) -> bool:
    """发送 IMAP ID，任一成功即返回 True。"""
    for payload in _netease_id_payloads(login_email):
        try:
            typ, _ = conn._simple_command("ID", payload)
            if typ == "OK":
                return True
        except Exception:
            continue
    return False


def _netease_imap_handshake(conn: imaplib.IMAP4_SSL, host: str, login_email: str) -> None:
    """网易系：SSL 建立后、LOGIN 前后各发一轮 IMAP ID（授权码 + SSL + ID 组合）。"""
    if not _is_netease_mail(host, login_email):
        return
    try:
        _send_netease_imap_id(conn, login_email)
    except Exception:
        # 登录前发 ID 若被服务器忽略/拒绝，不影响后续 LOGIN
        pass


def _decode_mime_header(value: Optional[str]) -> str:
    if not value:
        return ""
    parts: List[str] = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return "".join(parts)


def _decode_payload(part: email.message.Message) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return ""


def _html_to_plain(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:8000]


def _extract_bodies(msg: email.message.Message) -> Tuple[str, str]:
    plain, html_body = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            if ctype == "text/plain" and not plain:
                plain = _decode_payload(part)
            elif ctype == "text/html" and not html_body:
                html_body = _decode_payload(part)
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            plain = _decode_payload(msg)
        elif ctype == "text/html":
            html_body = _decode_payload(msg)
    if not plain and html_body:
        plain = _html_to_plain(html_body)
    return plain.strip(), html_body.strip()


def _safe_imap_close(conn: Optional[imaplib.IMAP4_SSL]) -> None:
    if conn is None:
        return
    try:
        conn.logout()
    except Exception:
        try:
            conn.shutdown()
        except Exception:
            pass


def _message_row_dict(seq: str, msg: email.message.Message, *, include_bodies: bool) -> Dict[str, Any]:
    subj, from_, date_iso = _message_headers_meta(msg)
    if include_bodies:
        plain, html_b = _extract_bodies(msg)
        snippet = (plain or _html_to_plain(html_b))[:240]
        return {
            "uid": seq,
            "subject": subj,
            "from_addr": from_,
            "date": date_iso,
            "snippet": snippet,
            "body_text": plain[:200000] if plain else None,
            "body_html": html_b[:500000] if html_b else None,
        }
    return {
        "uid": seq,
        "subject": subj,
        "from_addr": from_,
        "date": date_iso,
        "snippet": "",
        "body_text": None,
        "body_html": None,
    }


def _parse_batch_fetch_rfc822_headers(data: Any) -> Dict[str, bytes]:
    """解析单次 FETCH 多封 (RFC822.HEADER) 的响应，得到 {序号: 头字节}。"""
    out: Dict[str, bytes] = {}
    if not isinstance(data, list):
        return out
    for piece in data:
        if not isinstance(piece, tuple) or len(piece) < 2:
            continue
        meta, payload = piece[0], piece[1]
        if not isinstance(meta, (bytes, bytearray)) or not isinstance(payload, (bytes, bytearray)):
            continue
        m = re.match(br"^(\d+)", meta)
        if not m:
            continue
        out[m.group(1).decode("ascii")] = bytes(payload)
    return out


def _batch_fetch_rfc822_headers(conn: imaplib.IMAP4_SSL, ids: List[bytes]) -> Dict[str, bytes]:
    """一条 IMAP 命令拉取多封邮件头，避免逐封往返（显著降低延迟）。"""
    if not ids:
        return {}
    id_str = b",".join(ids)
    try:
        typ, data = conn.fetch(id_str, "(RFC822.HEADER)")
    except Exception:
        return {}
    if typ != "OK" or not data:
        return {}
    return _parse_batch_fetch_rfc822_headers(data)


def _message_headers_meta(msg: email.message.Message) -> Tuple[str, str, Optional[str]]:
    subj = _decode_mime_header(msg.get("Subject"))
    from_ = _decode_mime_header(msg.get("From"))
    date_hdr = msg.get("Date")
    date_iso: Optional[str] = None
    if date_hdr:
        try:
            dt = parsedate_to_datetime(date_hdr)
            if dt:
                date_iso = dt.isoformat()
        except Exception:
            date_iso = date_hdr[:80]
    return subj or "(无主题)", from_ or "", date_iso


def _connect_imap_inbox(
    login_email: str,
    password: str,
    provider: Optional[str],
    custom_host: Optional[str] = None,
    custom_port: Optional[int] = None,
    folder: str = "INBOX",
) -> Tuple[imaplib.IMAP4_SSL, str]:
    host, port = resolve_imap_host_port(provider, custom_host, custom_port)
    if not login_email or not password:
        raise ValueError("邮箱或授权码为空")

    conn: Optional[imaplib.IMAP4_SSL] = None
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=45)
        _netease_imap_handshake(conn, host, login_email)

        typ, _ = conn.login(login_email, password)
        if typ != "OK":
            raise ValueError("IMAP 登录失败，请检查授权码与邮箱类型是否匹配")

        _netease_imap_handshake(conn, host, login_email)

        typ, dat = conn.select(folder, readonly=False)
        if typ != "OK":
            hint = ""
            if dat and dat[0]:
                hint = dat[0].decode(errors="replace") if isinstance(dat[0], (bytes, bytearray)) else str(dat[0])
            raise ValueError(
                f"无法打开收件箱 {folder}"
                + (f"：{hint.strip()}" if hint and hint.strip() else "。请确认已在网页邮箱中开启 IMAP，且授权码与所选邮箱类型一致")
            )
        assert conn is not None
        return conn, host
    except Exception:
        _safe_imap_close(conn)
        raise


def fetch_inbox_messages(
    login_email: str,
    password: str,
    provider: Optional[str],
    custom_host: Optional[str] = None,
    custom_port: Optional[int] = None,
    folder: str = "INBOX",
    limit: int = 50,
    *,
    include_bodies: bool = False,
) -> List[Dict[str, Any]]:
    """
    拉取收件箱列表。默认仅 FETCH RFC822.HEADER（体积小），避免对每封邮件下载完整 MIME（此前为主要卡顿来源）。
    正文请在用户点开邮件时调用 fetch_inbox_message_body。
    """
    conn, _host = _connect_imap_inbox(login_email, password, provider, custom_host, custom_port, folder)
    fetch_spec = "(RFC822)" if include_bodies else "(RFC822.HEADER)"
    try:
        typ, data = conn.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return []

        ids = data[0].split()
        if len(ids) > limit:
            ids = ids[-limit:]
        ids.reverse()

        if not include_bodies:
            header_map = _batch_fetch_rfc822_headers(conn, ids)
            if len(header_map) == len(ids):
                batch_out: List[Dict[str, Any]] = []
                try:
                    for num in ids:
                        seq = num.decode() if isinstance(num, bytes) else str(num)
                        raw = header_map.get(seq)
                        if raw is None:
                            raise ValueError("batch header missing seq")
                        msg = email.message_from_bytes(raw)
                        batch_out.append(_message_row_dict(seq, msg, include_bodies=False))
                    return batch_out
                except Exception:
                    pass

        out: List[Dict[str, Any]] = []
        for num in ids:
            typ, msgdata = conn.fetch(num, fetch_spec)
            if typ != "OK" or not msgdata or not msgdata[0]:
                continue
            raw = msgdata[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            seq = num.decode() if isinstance(num, bytes) else str(num)
            msg = email.message_from_bytes(bytes(raw))
            out.append(_message_row_dict(seq, msg, include_bodies=include_bodies))
        return out
    finally:
        _safe_imap_close(conn)


def fetch_inbox_message_body(
    login_email: str,
    password: str,
    provider: Optional[str],
    seq: str,
    custom_host: Optional[str] = None,
    custom_port: Optional[int] = None,
    folder: str = "INBOX",
) -> Dict[str, Any]:
    """按 IMAP 序号拉取单封邮件全文（序号与列表接口返回的 uid 字段一致）。"""
    seq = (seq or "").strip()
    if not seq.isdigit():
        raise ValueError("无效的邮件序号")

    conn, _host = _connect_imap_inbox(login_email, password, provider, custom_host, custom_port, folder)
    try:
        typ, msgdata = conn.fetch(seq.encode("ascii"), "(RFC822)")
        if typ != "OK" or not msgdata or not msgdata[0]:
            raise ValueError("无法读取该邮件（可能已被删除或序号已变化，请刷新列表）")
        raw = msgdata[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            raise ValueError("邮件数据异常")
        msg = email.message_from_bytes(bytes(raw))
        subj, from_, date_iso = _message_headers_meta(msg)
        plain, html_b = _extract_bodies(msg)
        snippet = (plain or _html_to_plain(html_b))[:240]
        return {
            "seq": seq,
            "subject": subj,
            "from_addr": from_,
            "date": date_iso,
            "snippet": snippet,
            "body_text": plain[:200000] if plain else None,
            "body_html": html_b[:500000] if html_b else None,
        }
    finally:
        _safe_imap_close(conn)
