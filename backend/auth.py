import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db import User, get_db


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "not logged in")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "not logged in")
    return user
