from sqlalchemy.orm import Session
from app.models.project import Project
from typing import List, Optional


class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def create_project(self, name: str, git_url: str, owner_id: str, description: str = None) -> Project:
        if not git_url.startswith(("http://", "https://", "git@")):
            raise ValueError("Git地址格式不正确")
        project = Project(name=name, git_url=git_url, owner_id=owner_id, description=description)
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_project_by_id(self, project_id: str) -> Optional[Project]:
        return self.db.query(Project).filter(Project.id == project_id).first()

    def get_projects_by_owner(self, owner_id: str, page: int = 1, page_size: int = 20) -> tuple:
        query = self.db.query(Project).filter(Project.owner_id == owner_id)
        total = query.count()
        projects = query.offset((page - 1) * page_size).limit(page_size).all()
        return projects, total

    def update_project(self, project_id: str, **kwargs) -> Optional[Project]:
        project = self.get_project_by_id(project_id)
        if not project:
            return None
        for key, value in kwargs.items():
            if hasattr(project, key) and value is not None:
                setattr(project, key, value)
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete_project(self, project_id: str) -> bool:
        project = self.get_project_by_id(project_id)
        if not project:
            return False
        self.db.delete(project)
        self.db.commit()
        return True

    def archive_project(self, project_id: str) -> Optional[Project]:
        project = self.get_project_by_id(project_id)
        if not project:
            return None
        project.is_archived = True
        self.db.commit()
        self.db.refresh(project)
        return project
