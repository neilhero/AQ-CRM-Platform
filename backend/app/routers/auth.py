from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.services.auth import authenticate, create_token, hash_password, get_current_user
from app.models import User
from app.permissions import ROLE_LABELS
from app.routers.utils import require_user

router = APIRouter()

class LoginReq(BaseModel):
    username: str
    password: str

class ChangePwdReq(BaseModel):
    old_password: str
    new_password: str

@router.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    user = authenticate(db, req.username, req.password)
    if not user:
        raise HTTPException(401, "Wrong username or password")
    token = create_token(user.id, user.username)
    return {
        "access_token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "role": user.role,
            "role_label": ROLE_LABELS.get(user.role, user.role)
        }
    }

@router.get("/me")
def me(user=Depends(require_user)):
    return {
        "user_id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "menus": ["*"],
    }

@router.put("/change-password")
def change_password(req: ChangePwdReq, db: Session = Depends(get_db), user=Depends(require_user)):
    if hash_password(req.old_password) != user.password_hash:
        raise HTTPException(400, "Old password incorrect")
    if len(req.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")
    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "Password changed"}
