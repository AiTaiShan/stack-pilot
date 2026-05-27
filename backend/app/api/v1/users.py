from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserUpdate, UserInDB

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("/me", response_model=dict)
async def get_current_user_info(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "code": 200, "message": "success",
        "data": {
            "id": str(user.id), "username": user.username,
            "email": user.email, "role": user.role,
            "phone": user.phone, "avatar": user.avatar
        }
    }


@router.put("/me", response_model=dict)
async def update_current_user(user_data: UserUpdate, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user_data.email:
        user.email = user_data.email
    if user_data.phone:
        user.phone = user_data.phone
    if user_data.avatar:
        user.avatar = user_data.avatar
    db.commit()
    db.refresh(user)
    return {
        "code": 200, "message": "success",
        "data": {"id": str(user.id), "username": user.username, "email": user.email}
    }
