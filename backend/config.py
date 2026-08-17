from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "OfferFlow"
    APP_VERSION: str = "3.0.0"
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/offerflow.db"
    ENV: str = "development"
    PORT: int = 8001
    SECRET_KEY: str = "local-dev-only-change-me"

    # 邮箱解析：IMAP 授权码 / 模型 API Key 加密（留空则从 SECRET_KEY 派生）
    AI_ASSISTANT_ENCRYPTION_KEY: str = ""
    AI_ASSISTANT_MAIL_WATCH_ENABLED: bool = True
    AI_ASSISTANT_MAIL_WATCH_INTERVAL_SEC: int = 60
    AI_ASSISTANT_MAIL_WATCH_LIMIT_PER_SLOT: int = 25

    # 演示发信（默认 mock，不连真实 SMTP）
    MAIL_PROVIDER: str = "smtp"
    SMTP_MOCK: bool = True
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TIMEOUT: int = 30
    EMAIL_FROM: str = "noreply@offerflow.local"
    EMAIL_FROM_NAME: str = "OfferFlow"


settings = Settings()
