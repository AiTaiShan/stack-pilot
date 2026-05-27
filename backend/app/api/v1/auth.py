from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=dict)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已被使用")
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    hashed_password = get_password_hash(user_data.password)
    user = User(username=user_data.username, email=user_data.email, password_hash=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return {
        "code": 200, "message": "success",
        "data": {
            "token": token, "refresh_token": refresh_token,
            "user": {"id": str(user.id), "username": user.username, "email": user.email}
        }
    }


@router.post("/login", response_model=dict)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    from datetime import datetime, timezone
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return {
        "code": 200, "message": "success",
        "data": {
            "token": token, "refresh_token": refresh_token,
            "user": {"id": str(user.id), "username": user.username, "email": user.email}
        }
    }
