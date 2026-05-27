import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.project_member import MemberAdd, MemberUpdate, MemberResponse

router = APIRouter(prefix="/projects/{project_id}/members", tags=["项目成员"])


@router.get("/", response_model=dict)
async def list_members(project_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    current_user_id = uuid.UUID(current_user["sub"])
    is_owner = str(project.owner_id) == current_user["sub"]
    is_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user_id
    ).first()
    if not is_owner and not is_member:
        raise HTTPException(status_code=403, detail="没有权限查看项目成员")
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    owner = db.query(User).filter(User.id == project.owner_id).first()
    member_list = [{
        "id": str(project.owner_id),
        "username": owner.username if owner else "unknown",
        "role": "owner", "created_at": project.created_at.isoformat()
    }]
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        member_list.append({
            "id": str(m.id),
            "username": user.username if user else "unknown",
            "role": m.role, "created_at": m.created_at.isoformat()
        })
    return {"code": 200, "message": "success", "data": {"items": member_list}}


@router.post("/", response_model=dict)
async def add_member(project_id: str, member_data: MemberAdd, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == uuid.UUID(current_user["sub"])).first()
    if not project:
        raise HTTPException(status_code=403, detail="只有项目所有者可以添加成员")
    user = db.query(User).filter(User.username == member_data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户已经是项目成员")
    member = ProjectMember(
        project_id=project_id, user_id=user.id,
        role=member_data.role, invited_by=uuid.UUID(current_user["sub"])
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return {
        "code": 200, "message": "success",
        "data": {"id": str(member.id), "username": user.username, "role": member.role}
    }


@router.put("/{member_id}", response_model=dict)
async def update_member(project_id: str, member_id: str, member_data: MemberUpdate, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == uuid.UUID(current_user["sub"])).first()
    if not project:
        raise HTTPException(status_code=403, detail="只有项目所有者可以修改成员角色")
    member = db.query(ProjectMember).filter(ProjectMember.id == member_id, ProjectMember.project_id == project_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")
    member.role = member_data.role
    db.commit()
    db.refresh(member)
    return {
        "code": 200, "message": "success",
        "data": {"id": str(member.id), "role": member.role}
    }


@router.delete("/{member_id}", response_model=dict)
async def remove_member(project_id: str, member_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == uuid.UUID(current_user["sub"])).first()
    if not project:
        raise HTTPException(status_code=403, detail="只有项目所有者可以移除成员")
    member = db.query(ProjectMember).filter(ProjectMember.id == member_id, ProjectMember.project_id == project_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")
    db.delete(member)
    db.commit()
    return {"code": 200, "message": "成员已移除"}
