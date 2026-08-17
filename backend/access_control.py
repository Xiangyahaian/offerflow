"""本地开源版：无会员门槛，邮箱解析对本地用户全开。"""
from sqlalchemy.orm import Session

from backend.models import User


def user_is_member(db: Session, user: User) -> bool:
    return True


def user_is_registered(user: User) -> bool:
    return True
