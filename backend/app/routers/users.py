from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.services.auth import hash_password
from app.routers.utils import require_user
from pydantic import BaseModel
from typing import Optional

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
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可操作")
    return user

@router.get("")
def list_users(db: Session=Depends(get_db), admin=Depends(require_admin)):
    users = db.query(User).order_by(User.id).all()
    return [{"id": u.id, "username": u.username, "real_name": u.real_name,
             "role": u.role, "is_active": u.is_active} for u in users]

@router.post("", status_code=201)
def create_user(data: UserCreate, db: Session=Depends(get_db), admin=Depends(require_admin)):
    if db.query(User).filter_by(username=data.username).first():
        raise HTTPException(400, "用户名已存在")
    if len(data.password) < 6:
        raise HTTPException(400, "密码至少6位")
    u = User(username=data.username, password_hash=hash_password(data.password),
             real_name=data.real_name, role=data.role, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "username": u.username, "real_name": u.real_name, "role": u.role}

@router.put("/{uid}")
def update_user(uid: int, data: UserUpdate, db: Session=Depends(get_db), admin=Depends(require_admin)):
    u = db.query(User).filter_by(id=uid).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    if data.real_name is not None:
        u.real_name = data.real_name
    if data.role is not None:
        if data.role not in ("admin", "manager", "sales"):
            raise HTTPException(400, "角色无效，可选: admin/manager/sales")
        u.role = data.role
    if data.is_active is not None:
        u.is_active = data.is_active
    db.commit()
    return {"message": "已更新"}

@router.delete("/{uid}", status_code=204)
def delete_user(uid: int, db: Session=Depends(get_db), admin=Depends(require_admin)):
    u = db.query(User).filter_by(id=uid).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    if u.id == 1:
        raise HTTPException(400, "不能删除系统管理员")
    db.delete(u)
    db.commit()

@router.put("/{uid}/reset-password")
def reset_password(uid: int, data: ResetPwd, db: Session=Depends(get_db), admin=Depends(require_admin)):
    u = db.query(User).filter_by(id=uid).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    if len(data.new_password) < 6:
        raise HTTPException(400, "密码至少6位")
    u.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "密码已重置"}
