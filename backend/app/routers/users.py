from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.permissions import ROLE_LABELS, validate_role, require_admin_role
from app.routers.utils import require_user
from app.services.auth import hash_password

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    real_name: str
    role: str = "sales"


class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class ResetPwd(BaseModel):
    new_password: str


def require_admin(user=Depends(require_user)):
    return require_admin_role(user)


def _user_out(user: User):
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "is_active": user.is_active,
    }


@router.get("")
def list_users(db: Session = Depends(get_db), admin=Depends(require_admin)):
    users = db.query(User).order_by(User.id).all()
    return [_user_out(u) for u in users]


@router.post("", status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    validate_role(data.role)
    if db.query(User).filter_by(username=data.username).first():
        raise HTTPException(400, "用户名已存在")
    if len(data.password) < 6:
        raise HTTPException(400, "密码至少6位")
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        real_name=data.real_name,
        role=data.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.put("/{uid}")
def update_user(uid: int, data: UserUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if data.real_name is not None:
        user.real_name = data.real_name
    if data.role is not None:
        validate_role(data.role)
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.delete("/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == 1:
        raise HTTPException(400, "不能删除系统管理员")
    db.delete(user)
    db.commit()


@router.put("/{uid}/reset-password")
def reset_password(uid: int, data: ResetPwd, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if len(data.new_password) < 6:
        raise HTTPException(400, "密码至少6位")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "密码已重置"}
