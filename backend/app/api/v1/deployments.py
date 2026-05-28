import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.error_handler import AppError
from app.models.deployment import Deployment, DeploymentStatus
import logging

from app.schemas.deployment import (
    DeploymentCreate,
    DeploymentResponse,
    DeploymentStatusResponse,
    DeploymentLogResponse,
    DeploymentLogEntry,
    EnvVarKeysDelete,
)

logger = logging.getLogger(__name__)
from app.services.deployer.deployment_manager import DeploymentManager

router = APIRouter(prefix="/deployments", tags=["部署"])


def get_deployment_manager(db: Session = Depends(get_db)) -> DeploymentManager:
    return DeploymentManager(db)


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

    config = deployment.config or {}
    pending_env_vars = config.get("pending_env_vars", {})
    confirmed = config.get("env_vars_confirmed", False)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "pending_env_vars": pending_env_vars,
            "confirmed": confirmed,
            "deployment_status": deployment.status.value if deployment.status else None,
        },
    }


@router.put("/{deployment_id}/env-vars", response_model=dict)
async def update_deployment_env_vars(
    deployment_id: str,
    env_vars: dict,
    db: Session = Depends(get_db),
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    config = dict(deployment.config or {})
    pending = config.get("pending_env_vars", {})

    if not isinstance(env_vars, dict):
        raise HTTPException(status_code=400, detail="env_vars must be a JSON object")

    for k, v in env_vars.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise HTTPException(status_code=400, detail="keys and values must be strings")

    pending.update(env_vars)
    config["pending_env_vars"] = pending
    deployment.config = config
    db.commit()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "pending_env_vars": pending,
            "total": len(pending),
        },
    }


@router.delete("/{deployment_id}/env-vars", response_model=dict)
async def delete_deployment_env_vars(
    deployment_id: str,
    body: EnvVarKeysDelete,
    db: Session = Depends(get_db),
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    keys = body.keys

    config = dict(deployment.config or {})
    pending = config.get("pending_env_vars", {})

    removed = []
    for key in keys:
        if key in pending:
            del pending[key]
            removed.append(key)

    config["pending_env_vars"] = pending
    deployment.config = config
    db.commit()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "removed": removed,
            "remaining": pending,
        },
    }


@router.post("/{deployment_id}/confirm-env-vars", response_model=dict)
async def confirm_deployment_env_vars(
    deployment_id: str,
    db: Session = Depends(get_db),
    manager: DeploymentManager = Depends(get_deployment_manager),
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if deployment.status != DeploymentStatus.PAUSED:
        raise HTTPException(status_code=400, detail="Deployment not in paused state")

    config = dict(deployment.config or {})
    pending_env_vars = config.get("pending_env_vars", {})

    if not pending_env_vars:
        raise HTTPException(status_code=400, detail="No pending env vars to confirm")

    config["env_vars_confirmed"] = True
    deployment.config = config
    db.commit()

    try:
        manager._apply_confirmed_env_vars_to_compose(deployment_id)
    except Exception as e:
        logger.warning(f"应用环境变量到 compose 文件失败: {e}")

    success = manager.resume_deployment(deployment_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to resume deployment")

    return {
        "code": 200,
        "message": "success",
        "data": {
            "env_vars_confirmed": True,
            "total_env_vars": len(pending_env_vars),
            "resumed": True,
        },
    }
