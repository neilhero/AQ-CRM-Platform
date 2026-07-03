import hashlib, os, secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from sqlalchemy.orm import Session
from app.models import User

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "aq-crm-" + secrets.token_hex(32))
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"pbkdf2:sha256:100000${salt}${dk.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        parts = hashed.split("$")
        if len(parts) == 3 and hashed.startswith("pbkdf2:sha256:"):
            algo, iters_str, rest = parts[0], parts[1], parts[2]
            iters = int(iters_str)
            salt, stored = rest.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iters)
            return dk.hex() == stored
        return hashlib.sha256(password.encode()).hexdigest() == hashed
    except Exception:
        return False

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
