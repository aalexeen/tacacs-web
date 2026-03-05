"""Authentication: bcrypt + signed session cookies + users.json store."""

from __future__ import annotations

import json
import os
from pathlib import Path

import bcrypt as _bcrypt

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

COOKIE_NAME = "session"
SESSION_MAX_AGE = 60 * 60 * 8  # 8 hours

_SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me-in-production")
_serializer = URLSafeTimedSerializer(_SESSION_SECRET, salt="session")

USERS_FILE = Path(os.environ.get("USERS_FILE", "users.json"))

ROLES = ("admin", "operator", "viewer")


# ------------------------------------------------------------------
# Password helpers
# ------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ------------------------------------------------------------------
# users.json store
# ------------------------------------------------------------------

def _load_users() -> list[dict]:
    if not USERS_FILE.exists():
        return []
    return json.loads(USERS_FILE.read_text())


def _save_users(users: list[dict]) -> None:
    USERS_FILE.write_text(json.dumps(users, indent=2))


def get_user_by_id(user_id: str) -> dict | None:
    for u in _load_users():
        if u["id"] == user_id:
            return u
    return None


def get_user_by_username(username: str) -> dict | None:
    for u in _load_users():
        if u["username"] == username:
            return u
    return None


def list_users() -> list[dict]:
    return _load_users()


def create_user(username: str, password: str, role: str) -> dict:
    users = _load_users()
    if any(u["username"] == username for u in users):
        raise ValueError(f"User '{username}' already exists")
    if role not in ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(ROLES)}")
    import uuid
    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "enabled": True,
    }
    users.append(user)
    _save_users(users)
    return user


def delete_user(user_id: str) -> bool:
    users = _load_users()
    new_users = [u for u in users if u["id"] != user_id]
    if len(new_users) == len(users):
        return False
    _save_users(new_users)
    return True


def update_user_password(user_id: str, new_password: str) -> bool:
    users = _load_users()
    for u in users:
        if u["id"] == user_id:
            u["password_hash"] = hash_password(new_password)
            _save_users(users)
            return True
    return False


def update_user_role(user_id: str, new_role: str) -> bool:
    if new_role not in ROLES:
        raise ValueError(f"Invalid role '{new_role}'")
    users = _load_users()
    for u in users:
        if u["id"] == user_id:
            u["role"] = new_role
            _save_users(users)
            return True
    return False


def set_user_enabled(user_id: str, enabled: bool) -> bool:
    users = _load_users()
    for u in users:
        if u["id"] == user_id:
            u["enabled"] = enabled
            _save_users(users)
            return True
    return False


# ------------------------------------------------------------------
# Session token helpers
# ------------------------------------------------------------------

def create_session_token(user_id: str) -> str:
    return _serializer.dumps(user_id)


def decode_session_token(token: str) -> str | None:
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


# ------------------------------------------------------------------
# FastAPI dependencies
# ------------------------------------------------------------------

async def get_current_user(request: Request) -> dict:
    """Read cookie → decode → verify. Raises 401 if unauthenticated."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_session_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired")

    user = get_user_by_id(user_id)
    if user is None or not user.get("enabled", True):
        raise HTTPException(status_code=401, detail="User not found or disabled")

    return user


def require_operator(user: dict = Depends(get_current_user)) -> dict:
    """Allow operator and admin roles."""
    if user["role"] not in ("operator", "admin"):
        raise HTTPException(status_code=403, detail="Operator role required")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Allow admin role only."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
