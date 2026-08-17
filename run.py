"""启动 OfferFlow（本地开源版）。"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from backend.main import app  # noqa: E402

__all__ = ["app"]


def _setup_logging_when_main() -> None:
    import logging
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    env = os.getenv("ENV", "development")
    is_production = env == "production"

    root_logger.setLevel(logging.WARNING if is_production else logging.INFO)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING if is_production else logging.INFO)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root_logger.addHandler(console_handler)

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "offerflow.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    root_logger.addHandler(file_handler)


if __name__ == "__main__":
    import logging
    import uvicorn

    _setup_logging_when_main()
    env = os.getenv("ENV", "development")
    is_production = env == "production"
    port = int(os.getenv("PORT", "8001"))
    reload_enabled = not is_production and os.getenv("RELOAD", "1").strip() not in (
        "0",
        "false",
        "False",
        "no",
        "No",
    )
    logging.getLogger(__name__).info(
        "OfferFlow 启动 env=%s port=%s reload=%s", env, port, reload_enabled
    )
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload_enabled,
        reload_excludes=["logs/*", "*.log", ".git/*", "**/__pycache__/*", "*.pyc", ".venv/*"],
        log_level="warning" if is_production else "info",
    )
