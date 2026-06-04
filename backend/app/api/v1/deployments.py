import os
import uuid
import yaml

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Dict

from app.core.database import get_db
from app.core.error_handler import AppError
from app.models.deployment import Deployment, DeploymentStatus
from app.services.deployer.services.env_review import (
    update_compose_service_env,
    delete_compose_service_env_var,
    read_compose_file,
    write_compose_file,
)
import logging

from app.schemas.deployment import (
    DeploymentCreate,
    DeploymentResponse,
    DeploymentStatusResponse,
    DeploymentLogResponse,
    DeploymentLogEntry,
)

logger = logging.getLogger(__name__)
from app.services.deployer.deployment_manager import DeploymentManager

router = APIRouter(prefix="/deployments", tags=["部署"])


def get_deployment_manager(db: Session = Depends(get_db)) -> DeploymentManager:
    return DeploymentManager(db)


def _get_repo_dir(deployment) -> str:
    """获取部署对应的仓库目录"""
    # 从 config 中获取 _repo_dir（clone_step 会保存到 config）
    config = deployment.config or {}
    repo_dir = config.get('_repo_dir', '')
    if repo_dir and os.path.exists(repo_dir):
        return repo_dir

    # 回退：从 git_url 推断临时目录路径
    from app.services.scanner.git_service import GitService
    git_service = GitService()
    return os.path.join(
        git_service.temp_dir,
        deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
    )


@router.get("/", response_model=dict)
async def list_deployments(
    project_id: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(Deployment)
    if project_id:
        query = query.filter(Deployment.project_id == project_id)
    deployments = query.order_by(Deployment.created_at.desc()).all()

    items = []
    for d in deployments:
        items.append({
            "id": str(d.id),
            "project_id": str(d.project_id),
            "status": d.status.value if d.status else "pending",
            "platform": d.platform,
            "git_url": d.git_url,
            "branch": d.branch,
            "deploy_url": d.deploy_url,
            "progress": d.progress,
            "current_step": d.current_step.value if d.current_step else None,
            "error_message": d.error_message,
            "started_at": d.started_at.isoformat() if d.started_at else None,
            "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })

    return {
        "code": 200,
        "message": "success",
        "data": {"items": items, "total": len(items)},
    }


@router.post("/", response_model=dict)
async def create_deployment(
    data: DeploymentCreate,
    db: Session = Depends(get_db),
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    try:
        # 检查是否已有相同项目+分支的部署正在运行
        project_id = data.config.get("project_id") if data.config else None
        if project_id:
            existing = db.query(Deployment).filter(
                Deployment.project_id == project_id,
                Deployment.branch == data.branch,
                Deployment.status.in_([DeploymentStatus.PENDING, DeploymentStatus.RUNNING, DeploymentStatus.PAUSED])
            ).first()

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"该项目分支已有部署正在执行中 (ID: {existing.id[:8]}...)，请等待完成后再试"
                )

        deployment_id = str(uuid.uuid4())
        deployment = manager.start_deployment(
            deployment_id=deployment_id,
            git_url=data.git_url,
            branch=data.branch,
            platform=data.platform,
            config=data.config,
        )
        return {
            "code": 200,
            "message": "success",
            "data": {
                "deployment_id": str(deployment.id),
                "status": deployment.status.value if deployment.status else "pending",
            },
        }
    except HTTPException:
        raise
    except AppError as e:
        raise HTTPException(status_code=500, detail=e.message)


@router.get("/{deployment_id}/status", response_model=dict)
async def get_deployment_status(
    deployment_id: str,
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    result = manager.get_deployment_status(deployment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Deployment not found")

    return {
        "code": 200,
        "message": "success",
        "data": result,
    }


@router.get("/{deployment_id}/logs", response_model=dict)
async def get_deployment_logs(
    deployment_id: str,
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    logs = manager.get_deployment_logs(deployment_id)

    return {
        "code": 200,
        "message": "success",
        "data": {"logs": logs},
    }


@router.post("/{deployment_id}/cancel", response_model=dict)
async def cancel_deployment(
    deployment_id: str,
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    success = manager.cancel_deployment(deployment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Deployment not found or cannot be cancelled")

    return {
        "code": 200,
        "message": "success",
        "data": {"cancelled": True},
    }


@router.post("/{deployment_id}/pause", response_model=dict)
async def pause_deployment(
    deployment_id: str,
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    success = manager.pause_deployment(deployment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Deployment not found or cannot be paused")

    return {
        "code": 200,
        "message": "success",
        "data": {"paused": True},
    }


@router.post("/{deployment_id}/resume", response_model=dict)
async def resume_deployment(
    deployment_id: str,
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    success = manager.resume_deployment(deployment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Deployment not found or cannot be resumed")

    return {
        "code": 200,
        "message": "success",
        "data": {"resumed": True},
    }


@router.post("/{deployment_id}/rollback", response_model=dict)
async def rollback_deployment(
    deployment_id: str,
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    success = manager.rollback_deployment(deployment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Deployment not found or cannot be rolled back")

    return {
        "code": 200,
        "message": "success",
        "data": {"rolled_back": True},
    }


@router.get("/{deployment_id}/compose-file", response_model=dict)
async def get_compose_file(
    deployment_id: str,
    db: Session = Depends(get_db),
):
    """获取 docker-compose.yml 文件内容"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    repo_dir = _get_repo_dir(deployment)
    try:
        content = read_compose_file(repo_dir)
        return {
            "code": 200,
            "message": "success",
            "data": {"content": content},
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Compose file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read compose file: {str(e)}")


@router.put("/{deployment_id}/compose-file", response_model=dict)
async def update_compose_file(
    deployment_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
):
    """保存 docker-compose.yml 文件内容"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    content = data.get("content")
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    repo_dir = _get_repo_dir(deployment)
    try:
        success = write_compose_file(repo_dir, content)
        return {
            "code": 200,
            "message": "success",
            "data": {"saved": success},
        }
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save compose file: {str(e)}")


@router.delete("/all", response_model=dict)
async def delete_all_deployments(db: Session = Depends(get_db)):
    """删除所有部署记录"""
    try:
        # 先删除关联的日志和检查点
        from app.models.deployment import DeploymentLog, DeploymentCheckpoint
        db.query(DeploymentLog).delete()
        db.query(DeploymentCheckpoint).delete()
        db.query(Deployment).delete()
        db.commit()
        return {
            "code": 200,
            "message": "success",
            "data": {"deleted": True},
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{deployment_id}/env-vars", response_model=dict)
async def get_deployment_env_vars(
    deployment_id: str,
    db: Session = Depends(get_db),
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    config = dict(deployment.config or {})
    grouped_env_vars = config.get("grouped_env_vars", {})

    return {
        "code": 200,
        "message": "success",
        "data": {"grouped_env_vars": grouped_env_vars},
    }


@router.put("/{deployment_id}/env-vars", response_model=dict)
async def update_deployment_env_vars(
    deployment_id: str,
    service_name: str = Query(...),
    env_vars: Dict[str, str] = Body(...),
    db: Session = Depends(get_db),
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if deployment.status != DeploymentStatus.WAITING_REVIEW:
        raise HTTPException(status_code=400, detail="Deployment not in waiting_review state")

    config = dict(deployment.config or {})
    grouped = config.get("grouped_env_vars", {})
    if service_name not in grouped:
        grouped[service_name] = {"env_vars": {}}

    for key, value in env_vars.items():
        grouped[service_name]["env_vars"][key] = {"value": value, "source": "user"}

    repo_dir = _get_repo_dir(deployment)
    success = update_compose_service_env(repo_dir, service_name, grouped[service_name]["env_vars"])
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update docker-compose.yml")

    config["grouped_env_vars"] = grouped
    deployment.config = config
    db.commit()

    return {"code": 200, "message": "success", "data": {"updated": list(env_vars.keys())}}


@router.delete("/{deployment_id}/env-vars/{service_name}/{var_name}", response_model=dict)
async def delete_deployment_env_var(
    deployment_id: str,
    service_name: str,
    var_name: str,
    db: Session = Depends(get_db),
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if deployment.status != DeploymentStatus.WAITING_REVIEW:
        raise HTTPException(status_code=400, detail="Deployment not in waiting_review state")

    repo_dir = _get_repo_dir(deployment)
    success = delete_compose_service_env_var(repo_dir, service_name, var_name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete env var from docker-compose.yml")

    config = dict(deployment.config or {})
    grouped = config.get("grouped_env_vars", {})
    if service_name in grouped and var_name in grouped[service_name].get("env_vars", {}):
        del grouped[service_name]["env_vars"][var_name]
        config["grouped_env_vars"] = grouped
        deployment.config = config
        db.commit()

    return {"code": 200, "message": "success", "data": {"deleted": var_name}}


@router.post("/{deployment_id}/confirm-env-vars", response_model=dict)
async def confirm_deployment_env_vars(
    deployment_id: str,
    db: Session = Depends(get_db),
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if deployment.status != DeploymentStatus.WAITING_REVIEW:
        raise HTTPException(status_code=400, detail="Deployment not in waiting_review state")

    config = dict(deployment.config or {})
    config["env_vars_confirmed"] = True
    deployment.config = config
    db.commit()

    success = manager.confirm_env_review(deployment_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to confirm env review")

    return {
        "code": 200,
        "message": "success",
        "data": {"env_vars_confirmed": True},
    }
