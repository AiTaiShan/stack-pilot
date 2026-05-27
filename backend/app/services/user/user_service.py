from sqlalchemy.orm import Session
from app.models.user import User
from typing import Optional


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def update_user(self, user_id: str, **kwargs) -> Optional[User]:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        self.db.commit()
        self.db.refresh(user)
        return user

    def deactivate_user(self, user_id: str) -> bool:
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        user.is_active = False
        self.db.commit()
        return True
