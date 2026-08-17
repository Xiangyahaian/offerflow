"""象遇 · OpenAI 兼容 Chat Completions 调用。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _normalize_base_url(base_url: str) -> str:
    u = (base_url or "").strip().rstrip("/")
    if not u:
        raise ValueError("请填写 API Base URL")
    return u


def _chat_url(base_url: str) -> str:
    root = _normalize_base_url(base_url)
    if root.endswith("/chat/completions"):
        return root
    return root + "/chat/completions"


def _is_dashscope_compatible(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "dashscope.aliyuncs.com" in u


def _is_qwen_hybrid_model(model: str) -> bool:
    """百炼千问混合思考模型（可开关思考）；纯 -thinking 型号不在此列。"""
    mdl = (model or "").strip().lower()
    if not mdl:
        return False
    if "-thinking" in mdl or mdl.endswith("-think"):
        return False
    return mdl.startswith("qwen") or mdl.startswith("qwq") or "/qwen" in mdl


def _apply_qwen_thinking_off(payload: Dict[str, Any], base_url: str, model: str) -> None:
    """
    阿里云百炼 OpenAI 兼容接口：混合思考千问在非流式调用下须设 enable_thinking=false。
    见 https://help.aliyun.com/zh/model-studio/deep-thinking
    """
    if not _is_dashscope_compatible(base_url):
        return
    if not _is_qwen_hybrid_model(model):
        return
    payload["enable_thinking"] = False


def _collect_reasoning(msg: Dict[str, Any], choice: Dict[str, Any]) -> str:
    """提取模型思考/推理字段（DeepSeek-R1、部分 OpenAI 兼容接口）。"""
    parts: List[str] = []
    for src in (msg, choice):
        for key in ("reasoning_content", "reasoning", "thinking"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content")
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
                    elif isinstance(item, str) and item.strip():
                        parts.append(item.strip())
    # 去重保序
    seen: set[str] = set()
    out: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return "\n\n".join(out)


def _extract_message_text(msg: Dict[str, Any]) -> str:
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: List[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    t = part.get("text")
                    if isinstance(t, str) and t.strip():
                        chunks.append(t.strip())
                elif part.get("type") == "thinking":
                    # thinking 块单独进 reasoning，不计入正文
                    continue
                else:
                    t = part.get("text") or part.get("content")
                    if isinstance(t, str) and t.strip():
                        chunks.append(t.strip())
            elif isinstance(part, str) and part.strip():
                chunks.append(part.strip())
        return "\n".join(chunks).strip()
    return ""


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 1024,
    temperature: float = 0.4,
    timeout_sec: int = 90,
) -> Tuple[str, Dict[str, Any]]:
    """
    返回 (assistant_text, meta_dict)。
    meta_dict 含 usage、reasoning、raw_message、finish_reason 等审计字段。
    """
    key = (api_key or "").strip()
    if not key:
        raise ValueError("请填写 API Key")
    mdl = (model or "").strip()
    if not mdl:
        raise ValueError("请填写模型名称")

    payload: Dict[str, Any] = {
        "model": mdl,
        "messages": messages,
        "max_tokens": max(16, min(int(max_tokens), 4096)),
        "temperature": float(temperature),
    }
    _apply_qwen_thinking_off(payload, base_url, mdl)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _chat_url(base_url),
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        detail = err_body or str(e.reason or e)
        try:
            parsed = json.loads(err_body)
            if isinstance(parsed, dict):
                det = parsed.get("error")
                if isinstance(det, dict) and det.get("message"):
                    detail = str(det["message"])
                elif parsed.get("message"):
                    detail = str(parsed["message"])
                elif parsed.get("detail"):
                    detail = str(parsed["detail"])
        except Exception:
            pass
        raise ValueError(f"模型接口返回 {e.code}：{detail}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"无法连接模型服务：{e.reason}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("模型返回非 JSON 响应") from e

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("模型响应无 choices 字段")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    msg = choice.get("message") or {}
    if not isinstance(msg, dict):
        msg = {}
    text = _extract_message_text(msg)
    reasoning = _collect_reasoning(msg, choice)
    if not text and not reasoning:
        raise ValueError("模型返回空内容")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    meta: Dict[str, Any] = {
        "usage": usage,
        "reasoning": reasoning or None,
        "raw_message": msg,
        "finish_reason": choice.get("finish_reason"),
        "model": data.get("model"),
        "response_id": data.get("id"),
    }
    return text, meta


def check_availability(
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> Tuple[bool, str, Optional[int]]:
    """探测连通性，返回 (ok, message, latency_ms)。"""
    import time

    t0 = time.perf_counter()
    try:
        text, _ = chat_completion(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
            temperature=0,
            timeout_sec=45,
        )
        ms = int((time.perf_counter() - t0) * 1000)
        preview = text[:80] + ("…" if len(text) > 80 else "")
        return True, f"连接成功（{ms} ms）· 模型回复：{preview}", ms
    except ValueError as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return False, str(e), ms
