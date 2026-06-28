import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from sqlalchemy.orm import Session
from app.models import User

SECRET_KEY = "aq-crm-secret-key-2026"
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def create_token(user_id: int, username: str) -> str:
    payload = {"user_id": user_id, "username": username,
               "exp": datetime.now(timezone(timedelta(hours=8))) + timedelta(hours=TOKEN_EXPIRE_HOURS)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None

def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter_by(username=username, is_active=True).first()
    if user and verify_password(password, user.password_hash):
        return user
    return None

def get_current_user(db, token):
    payload = decode_token(token)
    if not payload:
        return None
    return db.query(User).filter_by(id=payload["user_id"], is_active=True).first()
