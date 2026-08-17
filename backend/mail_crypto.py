"""使用 Fernet 加密存储 IMAP 授权码、模型 API Key 等敏感配置。"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings

logger = logging.getLogger(__name__)


def _encryption_key_material() -> bytes:
    """优先使用独立加密密钥，未配置时从 SECRET_KEY 派生。"""
    dedicated = (getattr(settings, "AI_ASSISTANT_ENCRYPTION_KEY", None) or "").strip()
    source = dedicated or (settings.SECRET_KEY or "")
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_encryption_key_material())


def is_fernet_encrypted(token: str) -> bool:
    """判断字符串是否为已加密的 Fernet 密文。"""
    if not token:
        return False
    try:
        _fernet().decrypt(token.encode("ascii"))
        return True
    except (InvalidToken, ValueError, UnicodeEncodeError):
        return False


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def ensure_encrypted(value: str) -> str:
    """已是密文则原样返回，否则加密后返回。"""
    if not value:
        return ""
    if is_fernet_encrypted(value):
        return value
    return encrypt_secret(value)


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.warning("检测到未加密的敏感配置，将在下次保存或启动迁移时加密")
        return token


def migrate_plaintext_user_secrets(db) -> int:
    """将数据库中仍为明文的 IMAP 授权码 / API Key 批量加密。返回迁移行数。"""
    from backend.models import UserAiAssistantSettings, UserMailSettings

    changed = 0
    for mail in db.query(UserMailSettings).all():
        row_changed = False
        for field in ("primary_auth_encrypted", "secondary_auth_encrypted"):
            raw = getattr(mail, field, None)
            if raw and not is_fernet_encrypted(raw):
                setattr(mail, field, encrypt_secret(raw))
                row_changed = True
        if row_changed:
            changed += 1

    for ai in db.query(UserAiAssistantSettings).all():
        raw = ai.api_key_encrypted
        if raw and not is_fernet_encrypted(raw):
            ai.api_key_encrypted = encrypt_secret(raw)
            changed += 1

    if changed:
        db.commit()
        logger.info("敏感配置加密迁移完成，影响 %s 条用户配置", changed)
    return changed
