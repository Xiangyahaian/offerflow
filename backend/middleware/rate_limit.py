"""限速中间件（本地开源版保留基础能力）。"""
import logging
from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def get_client_ip(request):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    return get_remote_address(request)


_slowapi_env = Path(__file__).resolve().parents[2] / ".env.slowapi"
if not _slowapi_env.exists():
    _slowapi_env.write_text("", encoding="ascii")

limiter = Limiter(key_func=get_client_ip, config_filename=str(_slowapi_env))
