"""deployment_manager.py — 部署编排器（协调各步骤模块）"""
import json
import os
import uuid
import threading
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.deployment import (
    Deployment,
    DeploymentCheckpoint,
    DeploymentLog,
    DeploymentStatus,
    DeploymentStep,
)
from app.core.database import SessionLocal
from app.core.error_handler import AppError, ErrorCode, ErrorSeverity
from app.models.project import Project
from app.services.scanner.git_service import GitService
from app.services.deployer.docker_service import DockerService
from app.services.deployer.k8s_service import K8sService
from app.services.monitoring.monitoring_service import monitoring_service

logger = logging.getLogger(__name__)


class DeploymentManager:
    """部署编排管理器，协调各步骤模块"""

    STEPS: List[str] = [
        DeploymentStep.CLONE.value,
        DeploymentStep.GENERATE_REVIEW.value,
        DeploymentStep.BUILD.value,
        DeploymentStep.ENV_REVIEW.value,
        DeploymentStep.PUSH.value,
        DeploymentStep.DEPLOY.value,
        DeploymentStep.CONFIGURE.value,
        DeploymentStep.VERIFY.value,
    ]

    STEP_PROGRESS: Dict[str, int] = {
        DeploymentStep.CLONE.value: 10,
        DeploymentStep.GENERATE_REVIEW.value: 35,
        DeploymentStep.BUILD.value: 55,
        DeploymentStep.ENV_REVIEW.value: 65,
        DeploymentStep.PUSH.value: 75,
        DeploymentStep.DEPLOY.value: 85,
        DeploymentStep.CONFIGURE.value: 93,
        DeploymentStep.VERIFY.value: 100,
    }

    # 类级别共享状态
    _active_deployments: Dict[str, threading.Thread] = {}
    _cancel_flags: Dict[str, threading.Event] = {}
    _pause_flags: Dict[str, threading.Event] = {}

    def __init__(self, db: Session):
        self.db = db
        self.git_service = GitService()
        self.docker_service = DockerService()
        self.k8s_service: Optional[K8sService] = None

    @property

    def active_deployments(self) -> Dict[str, threading.Thread]:
        return DeploymentManager._active_deployments

    @property

    def cancel_flags(self) -> Dict[str, threading.Event]:
        return DeploymentManager._cancel_flags

    @property

    def pause_flags(self) -> Dict[str, threading.Event]:
        return DeploymentManager._pause_flags


    def start_deployment(
        self,
        deployment_id: str,
        git_url: str,
        branch: str = "main",
        platform: str = "k8s",
        config: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Deployment:
        config = config or {}
        project_id = config.get("project_id")
        if not project_id:
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                message="project_id is required in config",
                severity=ErrorSeverity.HIGH,
            )

        # 验证项目是否存在
        project = self.db.query(Project).filter(Project.id == uuid.UUID(project_id)).first()
        if not project:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message=f"Project {project_id} not found",
                severity=ErrorSeverity.HIGH,
            )

        deployment = Deployment(
            id=uuid.UUID(deployment_id) if isinstance(deployment_id, str) else deployment_id,
            project_id=uuid.UUID(project_id),
            user_id=uuid.UUID(user_id) if user_id else None,
            status=DeploymentStatus.PENDING,
            platform=platform,
            config=config,
            git_url=git_url,
            branch=branch,
            progress=0,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(deployment)
        self.db.commit()
        self.db.refresh(deployment)

        self.cancel_flags[deployment_id] = threading.Event()
        self.pause_flags[deployment_id] = threading.Event()

        thread = threading.Thread(
            target=self._execute_deployment,
            args=(str(deployment.id),),
            daemon=True,
        )
        self.active_deployments[deployment_id] = thread
        thread.start()

        return deployment


    def _execute_deployment(self, deployment_id: str):
        # 后台线程使用独立的数据库会话
        db = SessionLocal()
        deployment = None
        try:
            deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
            if not deployment:
                logger.error("Deployment %s not found", deployment_id)
                return

            deployment.status = DeploymentStatus.RUNNING
            db.commit()
            monitoring_service.record_deployment_start(deployment_id)

            checkpoint = self._get_checkpoint(db, deployment_id)
            start_index = 0
            if checkpoint:
                start_index = checkpoint.step_index + 1
                self._log(db, deployment_id, "info", f"Resuming from step: {checkpoint.step}", step=checkpoint.step)

            for i in range(start_index, len(self.STEPS)):
                step = self.STEPS[i]
                step_start = datetime.now(timezone.utc)

                if self.cancel_flags.get(deployment_id) and self.cancel_flags[deployment_id].is_set():
                    self._handle_cancellation(db, deployment_id, deployment)
                    return

                if self.pause_flags.get(deployment_id) and self.pause_flags[deployment_id].is_set():
                    self._handle_pause(db, deployment_id, deployment, step, i)
                    return

                deployment.current_step = DeploymentStep(step)
                deployment.progress = self._calculate_progress(i)
                db.commit()

                self._log(db, deployment_id, "info", f"Starting step: {step}", step=step,
                          details={"event": "step_start", "step": step, "timestamp": step_start.isoformat()})

                try:
                    self._execute_step(db, deployment_id, step, deployment)
                    step_end = datetime.now(timezone.utc)
                    duration_ms = int((step_end - step_start).total_seconds() * 1000)
                    self._save_checkpoint(db, deployment_id, step, i, {}, [])
                    self._log(db, deployment_id, "info", f"Completed step: {step}", step=step,
                              details={
                                  "event": "step_complete",
                                  "step": step,
                                  "duration_ms": duration_ms,
                                  "duration_s": round(duration_ms / 1000, 2),
                                  "started_at": step_start.isoformat(),
                                  "completed_at": step_end.isoformat(),
                              })
                except AppError as e:
                    db.rollback()
                    step_end = datetime.now(timezone.utc)
                    duration_ms = int((step_end - step_start).total_seconds() * 1000)
                    if e.retryable:
                        self._attempt_recovery(db, deployment_id, deployment, step, i, e)
                    else:
                        self._log(db, deployment_id, "error", f"Step {step} failed: {e.message}", step=step,
                                  details={
                                      "event": "step_failed",
                                      "step": step,
                                      "error": e.message,
                                      "error_code": e.code.value if hasattr(e.code, 'value') else str(e.code),
                                      "retryable": e.retryable,
                                      "duration_ms": duration_ms,
                                      "duration_s": round(duration_ms / 1000, 2),
                                  })
                        raise
                except Exception as e:
                    db.rollback()
                    step_end = datetime.now(timezone.utc)
                    duration_ms = int((step_end - step_start).total_seconds() * 1000)
                    self._log(db, deployment_id, "error", f"Step {step} failed: {e}", step=step,
                              details={
                                  "event": "step_failed",
                                  "step": step,
                                  "error": str(e),
                                  "error_type": type(e).__name__,
                                  "duration_ms": duration_ms,
                                  "duration_s": round(duration_ms / 1000, 2),
                              })
                    raise

            deployment.status = DeploymentStatus.SUCCESS
            deployment.current_step = None
            deployment.progress = 100
            deployment.completed_at = datetime.now(timezone.utc)
            db.commit()
            self._log(db, deployment_id, "info", "Deployment completed successfully")
            monitoring_service.record_deployment_end(deployment_id, True)

        except AppError as e:
            db.rollback()
            logger.error("Deployment %s failed: %s", deployment_id, e.message)
            if deployment is not None:
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = e.message
                deployment.error_details = e.to_dict()
                deployment.completed_at = datetime.now(timezone.utc)
                db.commit()
            self._log(db, deployment_id, "error", f"Deployment failed: {e.message}", details=e.to_dict())
            if deployment is not None:
                self._ai_diagnose_error(db, deployment_id, deployment, e.message)
            monitoring_service.record_deployment_end(deployment_id, False)

        except Exception as e:
            db.rollback()
            logger.error("Deployment %s failed with unexpected error: %s", deployment_id, e)
            if deployment is not None:
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = str(e)
                deployment.completed_at = datetime.now(timezone.utc)
                db.commit()
            self._log(db, deployment_id, "error", f"Deployment failed: {e}")
            monitoring_service.record_deployment_end(deployment_id, False)
            if deployment is not None:
                self._ai_diagnose_error(db, deployment_id, deployment, str(e))

        finally:
            db.close()
            self.active_deployments.pop(deployment_id, None)
            self.cancel_flags.pop(deployment_id, None)
            self.pause_flags.pop(deployment_id, None)


    def _execute_step(self, db: Session, deployment_id: str, step: str, deployment: Deployment):
        step_methods = {
            DeploymentStep.CLONE.value: self._step_clone,
            DeploymentStep.GENERATE_REVIEW.value: self._step_generate_review,
            DeploymentStep.BUILD.value: self._step_build,
            DeploymentStep.ENV_REVIEW.value: self._step_env_review,
            DeploymentStep.PUSH.value: self._step_push,
            DeploymentStep.DEPLOY.value: self._step_deploy,
            DeploymentStep.CONFIGURE.value: self._step_configure,
            DeploymentStep.VERIFY.value: self._step_verify,
        }

        method = step_methods.get(step)
        if method:
            method(db, deployment_id, deployment)
        else:
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Unknown deployment step: {step}",
                severity=ErrorSeverity.HIGH,
            )


    def _step_clone(self, db: Session, deployment_id: str, deployment: Deployment):
        from app.services.deployer.steps import clone_step
        clone_step.execute(db, deployment_id, deployment, self.git_service, self._log)
        return

    def _step_generate_review(self, db: Session, deployment_id: str, deployment: Deployment):
        from app.services.deployer.steps import review_step
        review_step.execute(db, deployment_id, deployment, self.git_service, self.docker_service, self._log)
        return

    def _step_build(self, db: Session, deployment_id: str, deployment: Deployment):
        from app.services.deployer.steps import build_step
        build_step.execute(db, deployment_id, deployment, self.git_service, self.docker_service, self._log)
        return

    def _step_push(self, db: Session, deployment_id: str, deployment: Deployment):
        from app.services.deployer.steps import deploy_step
        return

    def _step_deploy(self, db: Session, deployment_id: str, deployment: Deployment):
        from app.services.deployer.steps import deploy_step
        return

    def _step_verify(self, db: Session, deployment_id: str, deployment: Deployment):
        from app.services.deployer.steps import deploy_step
        deploy_step.step_verify(db, deployment_id, deployment, self._log)

    def _step_configure(self, db: Session, deployment_id: str, deployment: Deployment):
        from app.services.deployer.steps import deploy_step
        deploy_step.step_configure(db, deployment_id, deployment, self._log)

    def _step_env_review(self, db: Session, deployment_id: str, deployment: Deployment):
        """环境变量审核步骤 - 自动暂停等待用户确认"""
        config = dict(deployment.config or {})
        env_vars = config.get("pending_env_vars", {})

        if not env_vars:
            self._log(db, deployment_id, "info", "No environment variables to review, proceeding...")
            return

        self._log(db, deployment_id, "info",
                  f"Generated {len(env_vars)} environment variables for review")
        self._log(db, deployment_id, "info",
                  "Deployment paused for environment variable review. "
                  "Use GET /api/v1/deployments/{id}/env-vars to review, "
                  "PUT /api/v1/deployments/{id}/env-vars to modify, "
                  "and POST /api/v1/deployments/{id}/confirm-env-vars to confirm and proceed.")

        # 设置暂停标志 - 下一轮循环将自动暂停
        if deployment_id in self.pause_flags:
            self.pause_flags[deployment_id].set()

        self._log(db, deployment_id, "info", "Pause flag set, will pause before next step")


    def get_deployment_status(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return None

        return {
            "id": str(deployment.id),
            "status": deployment.status.value if deployment.status else None,
            "current_step": deployment.current_step.value if deployment.current_step else None,
            "progress": deployment.progress,
            "error_message": deployment.error_message,
            "can_resume": bool(deployment.can_resume),
            "started_at": deployment.started_at.isoformat() if deployment.started_at else None,
            "completed_at": deployment.completed_at.isoformat() if deployment.completed_at else None,
        }


    def get_deployment_logs(self, deployment_id: str) -> List[Dict[str, Any]]:
        logs = (
            self.db.query(DeploymentLog)
            .filter(DeploymentLog.deployment_id == deployment_id)
            .order_by(DeploymentLog.created_at.asc())
            .all()
        )

        return [
            {
                "timestamp": log.created_at.isoformat() if log.created_at else None,
                "level": log.level,
                "message": log.message,
                "details": log.details,
                "step": log.step,
            }
            for log in logs
        ]


    def cancel_deployment(self, deployment_id: str) -> bool:
        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return False

        # 如果部署已经完成或已取消，无法终止
        if deployment.status in (DeploymentStatus.SUCCESS, DeploymentStatus.FAILED, DeploymentStatus.CANCELLED):
            return False

        # 设置取消标志（如果有活跃线程）
        if deployment_id in self.cancel_flags:
            self.cancel_flags[deployment_id].set()

        # 立即更新数据库状态
        deployment.status = DeploymentStatus.CANCELLED
        deployment.completed_at = datetime.now(timezone.utc)
        deployment.error_message = "用户手动终止"
        self.db.commit()

        self._log(self.db, deployment_id, "info", "Deployment cancelled by user")
        return True


    def pause_deployment(self, deployment_id: str) -> bool:
        if deployment_id in self.pause_flags:
            self.pause_flags[deployment_id].set()
            return True

        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if deployment and deployment.status == DeploymentStatus.RUNNING:
            deployment.status = DeploymentStatus.PAUSED
            deployment.can_resume = 1
            self.db.commit()
            return True

        return False


    def resume_deployment(self, deployment_id: str) -> bool:
        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return False

        if deployment.status != DeploymentStatus.PAUSED:
            return False

        checkpoint = self._get_checkpoint(self.db, deployment_id)
        if not checkpoint and not deployment.can_resume:
            return False

        deployment.status = DeploymentStatus.RUNNING
        self.db.commit()

        self.cancel_flags[deployment_id] = threading.Event()
        self.pause_flags[deployment_id] = threading.Event()

        thread = threading.Thread(
            target=self._execute_deployment,
            args=(str(deployment.id),),
            daemon=True,
        )
        self.active_deployments[deployment_id] = thread
        thread.start()

        return True


    def rollback_deployment(self, deployment_id: str) -> bool:
        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return False

        if deployment.status not in (DeploymentStatus.FAILED, DeploymentStatus.CANCELLED):
            return False

        deployment.status = DeploymentStatus.ROLLING_BACK
        self.db.commit()

        try:
            self._rollback_resources(self.db, deployment_id)
            deployment.status = DeploymentStatus.ROLLED_BACK
            deployment.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self._log(self.db, deployment_id, "info", "Deployment rolled back successfully")
            return True
        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = f"Rollback failed: {e}"
            self.db.commit()
            self._log(self.db, deployment_id, "error", f"Rollback failed: {e}")
            return False


    def _handle_cancellation(self, db: Session, deployment_id: str, deployment: Deployment):
        # 状态可能已被 cancel_deployment 更新，这里只做清理
        if deployment.status != DeploymentStatus.CANCELLED:
            deployment.status = DeploymentStatus.CANCELLED
            deployment.completed_at = datetime.now(timezone.utc)
            db.commit()

        self._log(db, deployment_id, "info", "Deployment cancelled, cleaning up resources...")
        monitoring_service.record_deployment_end(deployment_id, False)
        self._rollback_resources(db, deployment_id)


    def _handle_pause(self, db: Session, deployment_id: str, deployment: Deployment, step: str, step_index: int):
        deployment.status = DeploymentStatus.PAUSED
        deployment.can_resume = 1
        deployment.resume_data = {"step": step, "step_index": step_index}
        db.commit()
        self._log(db, deployment_id, "info", f"Deployment paused at step: {step}")


    def _attempt_recovery(
        self,
        db: Session,
        deployment_id: str,
        deployment: Deployment,
        step: str,
        step_index: int,
        error: AppError,
    ):
        self._log(
            db,
            deployment_id,
            "warning",
            f"Attempting recovery for step {step}: {error.message}",
            details=error.to_dict(),
        )

        self._save_checkpoint(db, deployment_id, step, step_index, {"error": error.to_dict()}, [])
        raise error


    def _save_checkpoint(
        self,
        db: Session,
        deployment_id: str,
        step: str,
        step_index: int,
        state_data: Dict[str, Any],
        resources_created: List[str],
    ):
        checkpoint = DeploymentCheckpoint(
            deployment_id=uuid.UUID(deployment_id) if isinstance(deployment_id, str) else deployment_id,
            step=step,
            step_index=step_index,
            state_data=state_data,
            resources_created=resources_created,
        )
        db.add(checkpoint)
        db.commit()


    def _get_checkpoint(self, db: Session, deployment_id: str) -> Optional[DeploymentCheckpoint]:
        return (
            db.query(DeploymentCheckpoint)
            .filter(DeploymentCheckpoint.deployment_id == deployment_id)
            .order_by(DeploymentCheckpoint.step_index.desc())
            .first()
        )


    def _calculate_progress(self, step_index: int) -> int:
        if step_index == 0:
            return 0
        if step_index >= len(self.STEPS) - 1:
            return 100
        return self.STEP_PROGRESS.get(self.STEPS[step_index - 1], 0)


    def _log(
        self,
        db: Session,
        deployment_id: str,
        level: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        step: Optional[str] = None,
    ):
        log_entry = DeploymentLog(
            deployment_id=uuid.UUID(deployment_id) if isinstance(deployment_id, str) else deployment_id,
            level=level,
            message=message,
            details=details,
            step=step,
        )
        db.add(log_entry)
        db.commit()


    def _ai_diagnose_error(self, db: Session, deployment_id: str, deployment: Deployment, error_message: str):
        """AI 诊断部署错误"""
        try:
            ai_service = get_ai_service()

            project_info = deployment.config or {}
            project_info["error_step"] = deployment.current_step.value if deployment.current_step else "unknown"
            project_info["progress"] = deployment.progress

            diagnosis = ai_service.diagnose_error(error_message, project_info)

            if diagnosis.get("root_cause"):
                diagnosis_text = f"""AI 诊断结果：
- 根因: {diagnosis.get('root_cause', 'Unknown')}
- 修复步骤:
"""
                for i, step in enumerate(diagnosis.get("fix_steps", []), 1):
                    diagnosis_text += f"  {i}. {step}\n"

                if diagnosis.get("prevention"):
                    diagnosis_text += f"- 预防措施: {diagnosis['prevention']}"

                self._log(db, deployment_id, "info", diagnosis_text)

        except Exception as e:
            logger.debug("AI diagnosis failed: %s", e)

