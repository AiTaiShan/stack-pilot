import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.scanner.git_service import GitService

router = APIRouter(prefix="/projects", tags=["项目"])


@router.get("/", response_model=dict)
async def list_projects(page: int = 1, page_size: int = 20, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Project).filter(Project.owner_id == uuid.UUID(current_user["sub"]))
    total = query.count()
    projects = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "code": 200, "message": "success",
        "data": {
            "items": [
                {
                    "id": str(p.id), "name": p.name, "git_url": p.git_url,
                    "description": p.description, "default_branch": p.default_branch,
                    "is_archived": p.is_archived, "created_at": p.created_at.isoformat()
                } for p in projects
            ],
            "pagination": {"page": page, "page_size": page_size, "total": total}
        }
    }


@router.post("/", response_model=dict)
async def create_project(project_data: ProjectCreate, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not project_data.git_url.startswith(("http://", "https://", "git@")):
        raise HTTPException(status_code=400, detail="Git地址格式不正确")

    # 自动检测默认分支
    default_branch = "main"
    git_service = GitService()
    try:
        branches = git_service.list_remote_branches(project_data.git_url)
        if branches:
            # 优先使用 main，其次 master，否则取第一个
            if "main" in branches:
                default_branch = "main"
            elif "master" in branches:
                default_branch = "master"
            else:
                default_branch = branches[0]
    except Exception:
        pass  # 获取失败时使用默认值 main

    project = Project(
        name=project_data.name, git_url=project_data.git_url,
        description=project_data.description, owner_id=uuid.UUID(current_user["sub"]),
        default_branch=default_branch
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {
        "code": 200, "message": "success",
        "data": {"id": str(project.id), "name": project.name, "git_url": project.git_url, "default_branch": default_branch}
    }


@router.get("/{project_id}", response_model=dict)
async def get_project(project_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == uuid.UUID(project_id), Project.owner_id == uuid.UUID(current_user["sub"])).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "code": 200, "message": "success",
        "data": {
            "id": str(project.id), "name": project.name, "git_url": project.git_url,
            "description": project.description, "default_branch": project.default_branch,
            "is_archived": project.is_archived, "created_at": project.created_at.isoformat()
        }
    }


@router.put("/{project_id}", response_model=dict)
async def update_project(project_id: str, project_data: ProjectUpdate, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == uuid.UUID(project_id), Project.owner_id == uuid.UUID(current_user["sub"])).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project_data.name is not None:
        project.name = project_data.name
    if project_data.description is not None:
        project.description = project_data.description
    if project_data.default_branch is not None:
        project.default_branch = project_data.default_branch

    db.commit()
    db.refresh(project)
    return {
        "code": 200, "message": "success",
        "data": {
            "id": str(project.id), "name": project.name, "git_url": project.git_url,
            "description": project.description, "default_branch": project.default_branch
        }
    }


@router.get("/{project_id}/branches", response_model=dict)
async def get_project_branches(project_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == uuid.UUID(project_id), Project.owner_id == uuid.UUID(current_user["sub"])).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    git_service = GitService()
    try:
        branches = git_service.list_remote_branches(project.git_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分支失败: {str(e)}")

    return {
        "code": 200, "message": "success",
        "data": {
            "branches": branches,
            "default_branch": project.default_branch or (branches[0] if branches else "main")
        }
    }
