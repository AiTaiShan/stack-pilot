from sqlalchemy.orm import Session
from app.models.project_member import ProjectMember
from app.models.user import User
from app.models.project import Project
from typing import List, Optional


class MemberService:
    def __init__(self, db: Session):
        self.db = db

    def add_member(self, project_id: str, user_id: str, role: str, invited_by: str) -> ProjectMember:
        existing = self.db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        ).first()
        if existing:
            raise ValueError("用户已经是项目成员")
        member = ProjectMember(project_id=project_id, user_id=user_id, role=role, invited_by=invited_by)
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(self, project_id: str, user_id: str) -> bool:
        member = self.db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        ).first()
        if not member:
            return False
        self.db.delete(member)
        self.db.commit()
        return True

    def update_member_role(self, member_id: str, role: str) -> Optional[ProjectMember]:
        member = self.db.query(ProjectMember).filter(ProjectMember.id == member_id).first()
        if not member:
            return None
        member.role = role
        self.db.commit()
        self.db.refresh(member)
        return member

    def get_project_members(self, project_id: str) -> List[ProjectMember]:
        return self.db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()

    def is_member(self, project_id: str, user_id: str) -> bool:
        member = self.db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        ).first()
        return member is not None

    def get_member_role(self, project_id: str, user_id: str) -> Optional[str]:
        member = self.db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        ).first()
        return member.role if member else None
