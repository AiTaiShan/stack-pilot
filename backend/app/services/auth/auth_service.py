from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from datetime import datetime, timezone


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def register(self, username: str, email: str, password: str) -> dict:
        existing_user = self.db.query(User).filter(User.username == username).first()
        if existing_user:
            raise ValueError("用户名已被使用")
        existing_email = self.db.query(User).filter(User.email == email).first()
        if existing_email:
            raise ValueError("邮箱已被注册")
        hashed_password = get_password_hash(password)
        user = User(username=username, email=email, password_hash=hashed_password)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        token = create_access_token({"sub": str(user.id)})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        return {
            "token": token,
            "refresh_token": refresh_token,
            "user": {"id": str(user.id), "username": user.username, "email": user.email}
        }

    def login(self, username: str, password: str) -> dict:
        user = self.db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("用户名或密码错误")
        user.last_login_at = datetime.now(timezone.utc)
        self.db.commit()
        token = create_access_token({"sub": str(user.id)})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        return {
            "token": token,
            "refresh_token": refresh_token,
            "user": {"id": str(user.id), "username": user.username, "email": user.email}
        }

    def refresh_token(self, refresh_token: str) -> dict:
        from app.core.security import verify_token
        payload = verify_token(refresh_token)
        if not payload:
            raise ValueError("无效的刷新Token")
        user_id = payload["sub"]
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("用户不存在")
        new_token = create_access_token({"sub": str(user.id)})
        new_refresh_token = create_refresh_token({"sub": str(user.id)})
        return {
            "token": new_token,
            "refresh_token": new_refresh_token,
            "user": {"id": str(user.id), "username": user.username, "email": user.email}
        }
