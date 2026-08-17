"""本地开源版：无登录，固定本地用户。"""
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import LOCAL_USER_ID, User


def ensure_local_user(db: Session) -> User:
    user = db.query(User).filter(User.id == LOCAL_USER_ID).first()
    if user:
        return user
    user = User(
        id=LOCAL_USER_ID,
        username="local",
        email="local@offerflow.local",
        password_hash="!",
        is_admin=True,
        is_preview_guest=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(db: Session = Depends(get_db)) -> User:
    return ensure_local_user(db)
