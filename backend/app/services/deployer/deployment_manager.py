import json
import logging
import uuid
import threading
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
from app.services.scanner.dependency_detector import detect_project_dependencies, EXTERNAL_SERVICES
from app.services.deployer.docker_service import DockerService
from app.services.deployer.k8s_service import K8sService
from app.services.ai.ai_service import get_ai_service
from app.services.monitoring.monitoring_service import monitoring_service

logger = logging.getLogger(__name__)


class DeploymentManager:
    """部署编排管理器，支持中断恢复"""

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

    # 类级别共享状态，所有实例共享
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
            deployment.progress = 100
            deployment.completed_at = datetime.now(timezone.utc)
            db.commit()
            self._log(db, deployment_id, "info", "Deployment completed successfully")
            monitoring_service.record_deployment_end(deployment_id, True)

        except AppError as e:
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
        step_start = datetime.now(timezone.utc)

        # ====== Clone 仓库 ======
        clone_start = datetime.now(timezone.utc)
        repo_dir = self.git_service.clone(deployment.git_url, branch=deployment.branch)
        clone_duration_ms = int((datetime.now(timezone.utc) - clone_start).total_seconds() * 1000)
        self._log(db, deployment_id, "info", f"Repository cloned ({clone_duration_ms}ms)",
                  details={"event": "git_clone", "git_url": deployment.git_url, "branch": deployment.branch or "default",
                           "target_dir": repo_dir, "duration_ms": clone_duration_ms})

        # ====== 获取提交信息 ======
        commit_start = datetime.now(timezone.utc)
        commit_info = self.git_service.get_latest_commit(repo_dir)
        deployment.commit_hash = commit_info["hash"]
        deployment.commit_message = commit_info["message"]
        commit_duration_ms = int((datetime.now(timezone.utc) - commit_start).total_seconds() * 1000)
        self._log(db, deployment_id, "info", f"Commit info: {commit_info['hash'][:12]} - {commit_info['message'][:80]}",
                  details={"event": "git_commit", "commit_hash": commit_info["hash"],
                           "author": commit_info.get("author_name", ""), "message": commit_info["message"],
                           "duration_ms": commit_duration_ms})

        # ====== 检测项目类型 ======
        detect_start = datetime.now(timezone.utc)
        detected = self._detect_project_type(repo_dir)
        deps = detect_project_dependencies(repo_dir)
        detected["dependencies"] = deps
        detect_duration_ms = int((datetime.now(timezone.utc) - detect_start).total_seconds() * 1000)

        config = deployment.config or {}
        config.update(detected)
        deployment.config = config
        db.commit()

        # 记录检测结果
        self._log(db, deployment_id, "info", f"Project detected: {detected.get('type', 'single')} | {detected.get('language', 'unknown')} | {detected.get('framework', '')}",
                  details={"event": "project_detection", "type": detected.get("type"),
                           "language": detected.get("language"), "framework": detected.get("framework"),
                           "services": detected.get("services", []),
                           "external_services": deps.get("external_services", []),
                           "duration_ms": detect_duration_ms})

        step_end = datetime.now(timezone.utc)
        step_duration_ms = int((step_end - step_start).total_seconds() * 1000)
        logger.info("Step [clone] completed: deployment=%s duration=%dms type=%s lang=%s",
                     deployment_id[:12], step_duration_ms,
                     detected.get("type"), detected.get("language"))

    def _detect_project_type(self, repo_dir: str) -> dict:
        """检测项目类型，先用规则初筛，再交给 LLM 审核修正"""
        # 1. 规则初筛
        detected = self._rule_based_detect(repo_dir)

        # 2. LLM 审核
        detected = self._llm_review_detection(repo_dir, detected)

        return detected

    def _rule_based_detect(self, repo_dir: str) -> dict:
        """原有规则检测逻辑"""
        import os

        # 1. 检测是否为多模块 Java 项目（Spring Cloud）
        multi_module = self._detect_multi_module_java(repo_dir)
        if multi_module:
            return multi_module

        # 2. 检测是否为通用微服务项目（任何语言）
        microservices = self._detect_microservices(repo_dir)
        if microservices:
            return microservices

        # 3. 检测是否为 monorepo（前后端分离）
        monorepo = self._detect_monorepo(repo_dir)
        if monorepo:
            return monorepo

        # 4. 单项目
        return self._detect_single_project(repo_dir)

    def _llm_review_detection(self, repo_dir: str, detected: dict) -> dict:
        """调用 LLM 审核项目类型检测结果，修正错误并补充缺失信息"""
        import os

        structure = self._collect_project_structure(repo_dir)

        prompt = f"""分析以下项目结构，审核项目类型检测结果。

项目目录结构:
{structure}

当前检测结果:
{json.dumps(detected, ensure_ascii=False, indent=2)}

请判断：
1. 项目类型是否正确？（multi-module-java / microservices / monorepo / single）
2. 是否存在独立的前端项目目录？（可能叫 frontend、client、web、ui、app 或其他名字）
   判断依据：目录下有 package.json 或 index.html，且与后端目录并列
3. 如果是 Java 项目，JDK 版本要求是什么？（查看 pom.xml 中的 java.version 属性）
4. 前端项目使用的包管理器是什么？（pnpm-lock.yaml→pnpm, yarn.lock→yarn, package-lock.json→npm）
5. 项目配置文件中是否有需要适配 Docker 环境的连接地址？（如 localhost:3306 等硬编码地址）

返回纯 JSON，不要包含 markdown 代码块标记：
{{
  "type": "项目类型（保持原值或修正）",
  "frontend_dir": "前端目录名（如有，否则为 null）",
  "java_version": 17,
  "pkg_manager": "npm",
  "config_adaptation_needed": false,
  "corrections": "修正说明"
}}"""

        try:
            ai_service = get_ai_service()
            result = ai_service.chat(prompt)
            response_text = result.get("response", "{}")

            # 清理可能的 markdown 代码块标记
            response_text = response_text.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[-1]
            if response_text.endswith("```"):
                response_text = response_text.rsplit("```", 1)[0]
            response_text = response_text.strip()

            review = json.loads(response_text)

            # 根据 LLM 审核结果修正检测结果
            if review.get("frontend_dir") and "frontend" not in detected:
                frontend_path = os.path.join(repo_dir, review["frontend_dir"])
                if os.path.isdir(frontend_path):
                    frontend_info = self._detect_single_project(frontend_path)
                    frontend_info["dir"] = review["frontend_dir"]
                    detected["frontend"] = frontend_info
                    # 升级类型
                    if detected.get("type") == "multi-module-java":
                        detected["type"] = "multi-module-java-with-frontend"
                    elif detected.get("type") == "microservices":
                        detected["type"] = "microservices-with-frontend"

            if review.get("java_version"):
                detected["java_version"] = int(review["java_version"])
            if review.get("pkg_manager"):
                detected["pkg_manager"] = review["pkg_manager"]
            if review.get("config_adaptation_needed"):
                detected["config_adaptation_needed"] = True

            if review.get("corrections"):
                logger.info("LLM detection correction: %s", review["corrections"])

        except Exception as e:
            logger.warning("LLM detection review failed, using rule-based result: %s", e)

        return detected

    def _collect_project_structure(self, repo_dir: str, max_depth: int = 3) -> str:
        """收集项目结构摘要，用于 LLM 分析"""
        import os

        lines = []
        key_file_names = {
            "pom.xml", "package.json", "go.mod", "requirements.txt", "Dockerfile",
            "docker-compose.yml", "pnpm-lock.yaml", "yarn.lock", "package-lock.json",
            ".env", "start.sh", "build.gradle", "build.gradle.kts", "Cargo.toml",
            "Gemfile", "composer.json", "*.csproj",
        }
        skip_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__", ".stackpilot",
                     "dist", "build", ".idea", ".vscode", ".husky"}

        for root, dirs, files in os.walk(repo_dir):
            depth = root.replace(repo_dir, "").count(os.sep)
            if depth > max_depth:
                dirs.clear()
                continue
            dirs[:] = sorted([d for d in dirs if d not in skip_dirs])

            indent = "  " * depth
            basename = os.path.basename(root) if root != repo_dir else os.path.basename(repo_dir) + "/"
            lines.append(f"{indent}{basename}")

            key_files = [f for f in files
                         if f in key_file_names
                         or f.endswith(".properties")
                         or f.endswith(".yml")
                         or f.endswith(".yaml")]
            for f in key_files[:8]:
                lines.append(f"{indent}  {f}")

        return "\n".join(lines[:120])

    def _detect_microservices(self, repo_dir: str) -> dict:
        """检测通用微服务项目（任何语言）"""
        import os

        # 常见的微服务目录模式
        service_dirs = ["services", "microservices", "apps", "packages", "modules"]
        services = []

        for base_dir in service_dirs:
            base_path = os.path.join(repo_dir, base_dir)
            if not os.path.isdir(base_path):
                continue

            # 遍历子目录
            for item in sorted(os.listdir(base_path)):
                item_path = os.path.join(base_path, item)
                if not os.path.isdir(item_path):
                    continue

                # 检测是否为独立服务
                service_info = self._detect_service_in_dir(item_path, item)
                if service_info:
                    service_info["dir"] = f"{base_dir}/{item}"
                    services.append(service_info)

            if services:
                break

        # 也检查根目录下的服务目录（如 user-service/, order-service/）
        if not services:
            for item in sorted(os.listdir(repo_dir)):
                if item.startswith(".") or item in ["docs", "test", "tests", "scripts", "deploy", "k8s", "kubernetes"]:
                    continue
                item_path = os.path.join(repo_dir, item)
                if not os.path.isdir(item_path):
                    continue

                # 检查是否以 -service 或 _service 结尾
                if item.endswith("-service") or item.endswith("_service") or item.endswith("-api") or item.endswith("_api"):
                    service_info = self._detect_service_in_dir(item_path, item)
                    if service_info:
                        service_info["dir"] = item
                        services.append(service_info)

        if len(services) >= 2:  # 至少2个服务才算微服务项目
            return {
                "type": "microservices",
                "services": services
            }

        return None

    def _detect_service_in_dir(self, dir_path: str, name: str) -> dict:
        """检测目录是否为独立服务"""
        import os

        files = os.listdir(dir_path)
        service = {"name": name, "port": 8080, "language": "unknown", "framework": ""}

        # 检测语言
        if any(f.endswith(".java") for f in os.listdir(os.path.join(dir_path, "src")) if os.path.isdir(os.path.join(dir_path, "src"))) or "pom.xml" in files or "build.gradle" in files:
            service["language"] = "java"
            service["framework"] = "spring"
            service["port"] = 8080
        elif "package.json" in files:
            service["language"] = "node"
            service["framework"] = ""
            service["port"] = 3000
            try:
                with open(os.path.join(dir_path, "package.json")) as f:
                    pkg = json.load(f)
                    if "scripts" in pkg and "start" in pkg["scripts"]:
                        service["start_cmd"] = "npm start"
            except Exception:
                pass
        elif "requirements.txt" in files or "setup.py" in files or "pyproject.toml" in files:
            service["language"] = "python"
            service["framework"] = ""
            service["port"] = 8000
            for main_file in ["main.py", "app.py", "server.py"]:
                if main_file in files:
                    service["start_cmd"] = f"python {main_file}"
                    break
        elif "go.mod" in files:
            service["language"] = "go"
            service["framework"] = ""
            service["port"] = 8080
        elif "Cargo.toml" in files:
            service["language"] = "rust"
            service["framework"] = ""
            service["port"] = 8080
        elif "*.csproj" in " ".join(files) or any(f.endswith(".csproj") for f in files):
            service["language"] = "dotnet"
            service["framework"] = ""
            service["port"] = 5000
        else:
            return None

        # 检测端口
        for config_file in ["application.yml", "application.yaml", "application.properties", ".env", "config.yaml", "config.json"]:
            config_path = os.path.join(dir_path, config_file)
            if os.path.exists(config_path):
                try:
                    with open(config_path) as f:
                        content = f.read()
                        import re
                        # 尝试多种端口格式
                        port_match = re.search(r'(?:PORT|port|server\.port)\s*[=:]\s*(\d+)', content)
                        if port_match:
                            service["port"] = int(port_match.group(1))
                            break
                except Exception:
                    pass

        return service

    def _detect_multi_module_java(self, repo_dir: str) -> dict:
        """检测多模块 Java 项目（Maven/Gradle）"""
        import os
        import xml.etree.ElementTree as ET

        pom_path = os.path.join(repo_dir, "pom.xml")
        if not os.path.exists(pom_path):
            return None

        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()
            ns = {"m": "http://maven.apache.org/POM/4.0.0"}

            # 检查是否有 modules 标签
            modules = root.findall(".//m:module", ns)
            if not modules:
                # 尝试无命名空间
                modules = root.findall(".//module")

            if not modules:
                return None

            # 检测每个子模块
            services = []
            for module_elem in modules:
                module_name = module_elem.text.strip() if module_elem.text else ""
                module_dir = os.path.join(repo_dir, module_name)

                if not os.path.isdir(module_dir):
                    continue

                # 检测子模块类型
                module_info = self._detect_java_module(module_dir, module_name)
                if module_info:
                    services.append(module_info)

            if services:
                return {
                    "type": "multi-module-java",
                    "language": "java",
                    "framework": "spring-cloud",
                    "services": services
                }

        except Exception as e:
            logger.warning("Failed to parse pom.xml: %s", e)

        return None

    def _detect_java_module(self, module_dir: str, module_name: str) -> dict:
        """检测 Java 子模块类型"""
        import os

        has_pom = os.path.exists(os.path.join(module_dir, "pom.xml"))
        has_src = os.path.isdir(os.path.join(module_dir, "src"))

        if not (has_pom and has_src):
            return None

        # 检测端口（从 application.yml/properties）
        port = 8080
        for config_file in ["application.yml", "application.yaml", "application.properties"]:
            config_path = os.path.join(module_dir, "src", "main", "resources", config_file)
            if os.path.exists(config_path):
                try:
                    with open(config_path) as f:
                        content = f.read()
                        # 查找端口配置
                        import re
                        port_match = re.search(r'server\.port\s*[=:]\s*(\d+)', content)
                        if port_match:
                            port = int(port_match.group(1))
                except Exception:
                    pass

        # 判断模块类型
        module_type = "service"
        name_lower = module_name.lower()
        if "eureka" in name_lower or "registry" in name_lower:
            module_type = "registry"
        elif "gateway" in name_lower or "zuul" in name_lower:
            module_type = "gateway"
        elif "config" in name_lower:
            module_type = "config"
        elif "common" in name_lower or "util" in name_lower or "api" in name_lower:
            module_type = "common"

        return {
            "name": module_name,
            "dir": module_name,
            "type": module_type,
            "port": port,
            "language": "java",
            "framework": "spring"
        }

    def _detect_monorepo(self, repo_dir: str) -> dict:
        """检测 monorepo 项目结构"""
        import os

        common_frontend_dirs = ["frontend", "client", "web", "ui", "app"]
        common_backend_dirs = ["backend", "server", "api", "services"]

        frontend_dir = None
        backend_dir = None

        for d in common_frontend_dirs:
            path = os.path.join(repo_dir, d)
            if os.path.isdir(path):
                # 确认是前端项目
                if any(os.path.exists(os.path.join(path, f)) for f in ["package.json", "index.html"]):
                    frontend_dir = d
                    break

        for d in common_backend_dirs:
            path = os.path.join(repo_dir, d)
            if os.path.isdir(path):
                # 确认是后端项目
                if any(os.path.exists(os.path.join(path, f)) for f in [
                    "requirements.txt", "pom.xml", "go.mod", "main.py", "app.py",
                    "package.json", "build.gradle"
                ]):
                    backend_dir = d
                    break

        if frontend_dir and backend_dir:
            # 检测各子项目类型
            frontend_info = self._detect_single_project(os.path.join(repo_dir, frontend_dir))
            backend_info = self._detect_single_project(os.path.join(repo_dir, backend_dir))

            return {
                "type": "monorepo",
                "frontend": {
                    "dir": frontend_dir,
                    **frontend_info
                },
                "backend": {
                    "dir": backend_dir,
                    **backend_info
                }
            }

        return None

    def _detect_single_project(self, repo_dir: str) -> dict:
        """检测单个项目类型"""
        import os

        files = os.listdir(repo_dir)
        result = {"language": "unknown", "framework": ""}

        # Java / Maven / Gradle
        if "pom.xml" in files:
            result = {"language": "java", "framework": "spring"}
        elif "build.gradle" in files or "build.gradle.kts" in files:
            result = {"language": "java", "framework": "spring"}

        # Node.js
        elif "package.json" in files:
            if os.path.exists(os.path.join(repo_dir, "next.config.js")) or os.path.exists(os.path.join(repo_dir, "next.config.mjs")):
                result = {"language": "node", "framework": "next"}
            else:
                result = {"language": "node", "framework": ""}
            # 从 package.json 读取启动命令
            try:
                with open(os.path.join(repo_dir, "package.json")) as f:
                    pkg = json.load(f)
                    if "scripts" in pkg:
                        if "start" in pkg["scripts"]:
                            result["start_cmd"] = "npm start"
                        elif "dev" in pkg["scripts"]:
                            result["start_cmd"] = "npm run dev"
            except Exception:
                pass

        # Python
        elif "requirements.txt" in files or "setup.py" in files or "pyproject.toml" in files:
            if "manage.py" in files:
                result = {"language": "python", "framework": "django"}
            else:
                result = {"language": "python", "framework": ""}
            # 检测 Python 启动文件
            for main_file in ["main.py", "app.py", "server.py", "wsgi.py"]:
                if main_file in files:
                    result["start_cmd"] = f"python {main_file}"
                    break

        # Go
        elif "go.mod" in files:
            result = {"language": "go", "framework": ""}
            # 读取模块名
            try:
                with open(os.path.join(repo_dir, "go.mod")) as f:
                    for line in f:
                        if line.startswith("module "):
                            module = line.split()[-1].strip()
                            result["start_cmd"] = f"./{module.split('/')[-1]}"
                            break
            except Exception:
                pass

        # 检测通用启动脚本
        if "start_cmd" not in result:
            for script in ["start.sh", "run.sh", "entrypoint.sh"]:
                if script in files:
                    result["start_cmd"] = f"./{script}"
                    break

        # 检测端口
        if os.path.exists(os.path.join(repo_dir, "Dockerfile")):
            try:
                with open(os.path.join(repo_dir, "Dockerfile")) as f:
                    for line in f:
                        if "EXPOSE" in line:
                            ports = line.replace("EXPOSE", "").strip().split()
                            if ports:
                                result["port"] = int(ports[0])
                            break
            except Exception:
                pass

        return result

    def _cleanup_old_images(self, db: Session, deployment_id: str, repo_name: str):
        """清理旧的 Docker 镜像，防止磁盘空间膨胀"""
        import subprocess

        image_prefix = f"stackpilot/{repo_name}"

        try:
            # 获取当前项目的所有镜像
            result = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", "--filter", f"reference={image_prefix}*"],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                return

            images = [img.strip() for img in result.stdout.strip().split('\n') if img.strip()]

            if len(images) <= 1:
                return

            # 保留最新的镜像，删除旧的
            images_to_remove = images[1:]  # 跳过第一个（最新的）

            for img in images_to_remove:
                self._log(db, deployment_id, "info", f"Cleaning up old image: {img}")
                subprocess.run(["docker", "rmi", "-f", img], capture_output=True, timeout=30)

            if images_to_remove:
                self._log(db, deployment_id, "info", f"Cleaned up {len(images_to_remove)} old images")

        except Exception as e:
            # 清理失败不影响构建流程
            self._log(db, deployment_id, "warning", f"Image cleanup failed: {e}")

        # 清理悬空镜像（dangling images）
        try:
            subprocess.run(["docker", "image", "prune", "-f"], capture_output=True, timeout=60)
        except Exception:
            pass

    def _step_generate_review(self, db: Session, deployment_id: str, deployment: Deployment):
        """生成部署文件 + AI 审核 — 将 build 步骤中的文件生成和审核提取为独立步骤"""
        import os

        self._log(db, deployment_id, "info", "Starting generate_review step")

        # 刷新 deployment 对象以获取 clone 步骤写入的最新 config
        db.refresh(deployment)
        project_info = dict(deployment.config or {})
        repo_name = deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
        repo_dir = os.path.join(self.git_service.temp_dir, repo_name)
        project_type = project_info.get("type", "")
        deps = project_info.get("dependencies", {})

        # 如果 config 中没有 dependencies，尝试从文件加载
        if not deps:
            deps = self._load_deps_from_file(repo_dir)
            if deps:
                project_info["dependencies"] = deps

        self._log(db, deployment_id, "info", f"Project type: {project_type}, repo_dir: {repo_dir}")

        # 1. 保存依赖信息到文件
        if deps.get("external_services"):
            deps_dir = os.path.join(repo_dir, ".stackpilot")
            os.makedirs(deps_dir, exist_ok=True)
            with open(os.path.join(deps_dir, "dependencies.json"), "w") as f:
                json.dump(deps, f)
            self._log(db, deployment_id, "info",
                      f"External services: {', '.join(deps['external_services'])}")

        # 2. 生成部署文件
        self._log(db, deployment_id, "info", f"Generating deployment files for type: {project_type}")
        if project_type in ("multi-module-java", "multi-module-java-with-frontend"):
            self._generate_multi_module_files(repo_dir, project_info)
            if project_type == "multi-module-java-with-frontend":
                self._generate_frontend_dockerfile(repo_dir, project_info)
        elif project_type in ("microservices", "microservices-with-frontend"):
            self._generate_microservices_files(repo_dir, project_info)
            if project_type == "microservices-with-frontend":
                self._generate_frontend_dockerfile(repo_dir, project_info)
        elif project_type == "monorepo":
            self._generate_monorepo_files(repo_dir, project_info)
        else:
            if not os.path.exists(os.path.join(repo_dir, "Dockerfile")):
                self.docker_service.generate_dockerfile(project_info, repo_dir)
            else:
                self._log(db, deployment_id, "info", "Dockerfile already exists, skipping generation")
        self._log(db, deployment_id, "info", "Deployment files generated")

        # 3. AI 审核 Dockerfile(s)
        self._log(db, deployment_id, "info", "Starting AI review of Dockerfiles")
        self._ai_review_project_dockerfiles(db, deployment_id, repo_dir, project_info)
        self._log(db, deployment_id, "info", "AI review of Dockerfiles completed")

        # 4. 生成 docker-compose.yml
        self._log(db, deployment_id, "info", "Generating docker-compose.yml")
        if project_type not in (
            "multi-module-java", "multi-module-java-with-frontend",
            "microservices", "microservices-with-frontend", "monorepo"
        ):
            if deps.get("external_services"):
                self._generate_single_app_compose(repo_dir, repo_name, f"stackpilot/{repo_name}:latest", deps)
        self._log(db, deployment_id, "info", "docker-compose.yml generation completed")

        # 5. AI 审核 docker-compose.yml
        compose_path = os.path.join(repo_dir, "docker-compose.yml")
        if os.path.exists(compose_path):
            self._log(db, deployment_id, "info", "Starting AI review of docker-compose.yml")
            self._ai_review_compose(db, deployment_id, repo_dir, project_info, deps)
            self._log(db, deployment_id, "info", "AI review of docker-compose.yml completed")

        # 6. 适配配置文件
        self._log(db, deployment_id, "info", "Adapting config files for Docker")
        if project_info.get("config_adaptation_needed") or deps.get("external_services"):
            self._adapt_config_for_docker(repo_dir, deps)
        self._log(db, deployment_id, "info", "Config adaptation completed")

        # 7. 提取环境变量
        self._log(db, deployment_id, "info", "Extracting environment variables")
        pending = self._generate_service_env_vars(repo_dir, "spring")
        if not pending:
            pending = self._generate_service_env_vars(repo_dir, "generic")
        dc = dict(deployment.config or {})
        dc["pending_env_vars"] = pending
        deployment.config = dc
        db.commit()
        if pending:
            self._log(db, deployment_id, "info", f"Saved {len(pending)} env vars for user review")
        self._log(db, deployment_id, "info", "generate_review step completed")

    def _generate_multi_module_files(self, repo_dir: str, project_info: dict):
        """生成多模块 Java 项目的 Dockerfile（使用通配符模式）"""
        import os

        services = project_info.get("services", [])
        java_version = project_info.get("java_version", 17)
        for service in services:
            if service["type"] == "common":
                continue
            service_dir = os.path.join(repo_dir, service["dir"])
            dockerfile_content = f"""FROM eclipse-temurin:{java_version}-jre-alpine
WORKDIR /app
COPY target/*.jar app.jar
EXPOSE {service['port']}
CMD ["java", "-jar", "app.jar"]
"""
            dockerfile_path = os.path.join(service_dir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)

    def _generate_microservices_files(self, repo_dir: str, project_info: dict):
        """为微服务项目的每个服务生成 Dockerfile"""
        import os

        services = project_info.get("services", [])
        for service in services:
            service_dir = os.path.join(repo_dir, service["dir"])
            dockerfile_path = os.path.join(service_dir, "Dockerfile")
            if not os.path.exists(dockerfile_path):
                self.docker_service.generate_dockerfile(service, service_dir)

    def _generate_monorepo_files(self, repo_dir: str, project_info: dict):
        """为 monorepo 项目的前端和后端生成 Dockerfile"""
        import os

        frontend = project_info.get("frontend", {})
        backend = project_info.get("backend", {})
        if backend:
            backend_dir = os.path.join(repo_dir, backend.get("dir", "backend"))
            self.docker_service.generate_dockerfile(backend, backend_dir)
        if frontend:
            frontend_dir = os.path.join(repo_dir, frontend.get("dir", "frontend"))
            self.docker_service.generate_dockerfile(frontend, frontend_dir)

    def _generate_frontend_dockerfile(self, repo_dir: str, project_info: dict):
        """为组合项目生成前端 Dockerfile"""
        import os

        frontend_info = project_info.get("frontend", {})
        frontend_dir_name = frontend_info.get("dir", "frontend")
        frontend_dir = os.path.join(repo_dir, frontend_dir_name)
        if os.path.isdir(frontend_dir):
            self.docker_service.generate_dockerfile(frontend_info, frontend_dir)

    def _ai_review_project_dockerfiles(self, db: Session, deployment_id: str, repo_dir: str, project_info: dict):
        """扫描并 AI 审核项目中的所有 Dockerfile"""
        import os

        project_type = project_info.get("type", "")

        if project_type in ("microservices", "microservices-with-frontend",
                             "multi-module-java", "multi-module-java-with-frontend"):
            services = project_info.get("services", [])
            for service in services:
                if service["type"] == "common":
                    continue
                service_dir = os.path.join(repo_dir, service["dir"])
                dockerfile_path = os.path.join(service_dir, "Dockerfile")
                if os.path.exists(dockerfile_path):
                    self._ai_review_dockerfile(db, deployment_id, service_dir,
                        {**project_info, "service_name": service["name"]})
            frontend_info = project_info.get("frontend", {})
            if frontend_info:
                f_dir = os.path.join(repo_dir, frontend_info.get("dir", "frontend"))
                f_df = os.path.join(f_dir, "Dockerfile")
                if os.path.exists(f_df):
                    self._ai_review_dockerfile(db, deployment_id, f_dir,
                        {**project_info, "service_name": "frontend"})
        elif project_type == "monorepo":
            backend = project_info.get("backend", {})
            frontend = project_info.get("frontend", {})
            if backend:
                b_dir = os.path.join(repo_dir, backend.get("dir", "backend"))
                self._ai_review_dockerfile(db, deployment_id, b_dir, {**project_info, "service_name": "backend"})
            if frontend:
                f_dir = os.path.join(repo_dir, frontend.get("dir", "frontend"))
                self._ai_review_dockerfile(db, deployment_id, f_dir, {**project_info, "service_name": "frontend"})
        else:
            self._ai_review_dockerfile(db, deployment_id, repo_dir, project_info)

    def _generate_service_env_vars(self, repo_dir: str, style: str) -> list:
        """扫描项目配置文件，提取需要用户填写的环境变量占位符"""
        import os
        import re

        pending = []
        seen = set()
        skip_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__", ".stackpilot", "dist", "build"}

        placeholder_patterns = {
            "spring": [
                re.compile(r'(?:spring\.\w+(?:\.\w+)*\s*=\s*)\$\{([^}]+)\}'),
                re.compile(r'(?:spring\.\w+(?:\.\w+)*\s*=\s*)(CHANGE_ME|TODO|xxx|your_\w+)', re.IGNORECASE),
            ],
            "generic": [
                re.compile(r'(?:[A-Z_]+(?:HOST|PORT|USER|PASS|KEY|SECRET|TOKEN|URL|DSN)\s*[:=]\s*)\$\{([^}]+)\}'),
                re.compile(r'(?:[A-Z_]+(?:HOST|PORT|USER|PASS|KEY|SECRET|TOKEN|URL|DSN)\s*[:=]\s*)(CHANGE_ME|TODO|xxx|your_\w+)', re.IGNORECASE),
            ],
        }

        patterns = placeholder_patterns.get(style, placeholder_patterns["generic"])

        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for filename in files:
                if not any(filename.endswith(ext) for ext in [".properties", ".yml", ".yaml", ".env"]):
                    continue
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        for line_no, line in enumerate(f, 1):
                            line = line.strip()
                            if line.startswith("#") or not line:
                                continue
                            for pattern in patterns:
                                for match in pattern.finditer(line):
                                    var_name = match.group(1)
                                    # 避免重复
                                    if var_name not in seen:
                                        seen.add(var_name)
                                        pending.append({
                                            "name": var_name,
                                            "file": os.path.relpath(filepath, repo_dir),
                                            "line": line_no,
                                            "style": style,
                                        })
                except Exception:
                    continue

        return pending

    def _step_env_review(self, db: Session, deployment_id: str, deployment: Deployment):
        """占位实现 — 将在后续任务中替换为完整实现"""
        self._log(db, deployment_id, "info", "Env review step (placeholder)")

    def _step_build(self, db: Session, deployment_id: str, deployment: Deployment):
        """仅构建 Docker 镜像（文件生成和审核已在 generate_review 完成）"""
        import os

        db.refresh(deployment)
        project_info = deployment.config or {}
        repo_name = deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
        repo_dir = os.path.join(self.git_service.temp_dir, repo_name)
        commit_short = deployment.commit_hash[:8] if deployment.commit_hash else "latest"
        project_type = project_info.get("type", "")

        # 清理旧镜像
        self._cleanup_old_images(db, deployment_id, repo_name)

        # 按项目类型构建镜像
        if project_type in ("multi-module-java", "multi-module-java-with-frontend"):
            self._build_multi_module_java(db, deployment_id, deployment, repo_dir, repo_name, commit_short)
            if "with-frontend" in project_type:
                self._build_frontend_for_composite(db, deployment_id, deployment, repo_dir, repo_name, commit_short)
        elif project_type in ("microservices", "microservices-with-frontend"):
            self._build_microservices(db, deployment_id, deployment, repo_dir, repo_name, commit_short)
            if "with-frontend" in project_type:
                self._build_frontend_for_composite(db, deployment_id, deployment, repo_dir, repo_name, commit_short)
        elif project_type == "monorepo":
            self._build_monorepo(db, deployment_id, deployment, repo_dir, repo_name, commit_short)
        else:
            # 单体项目
            image_tag = f"stackpilot/{repo_name}:{commit_short}"
            self.docker_service.build_image(repo_dir, image_tag)
            deployment.image_tag = image_tag
        db.commit()

    def _ai_review_dockerfile(self, db: Session, deployment_id: str, repo_dir: str, project_info: dict):
        """AI 审核 Dockerfile，记录完整输入/输出"""
        import os

        dockerfile_path = os.path.join(repo_dir, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            return

        service_name = project_info.get("service_name", "main")
        ai_start = datetime.now(timezone.utc)

        try:
            ai_service = get_ai_service()

            with open(dockerfile_path) as f:
                dockerfile_content = f.read()

            scan_context = {
                "project_type": project_info.get("type", "unknown"),
                "language": project_info.get("language", "unknown"),
                "framework": project_info.get("framework", "unknown"),
                "start_cmd": project_info.get("start_cmd", "N/A"),
                "service_name": service_name,
                "external_dependencies": project_info.get("dependencies", {}).get("external_services", []),
            }

            input_info = {
                "provider": ai_service.provider,
                "model": ai_service.model,
                "service": service_name,
                "dockerfile_path": dockerfile_path,
                "dockerfile_content": dockerfile_content,
                "context": scan_context,
            }

            result = ai_service.review_dockerfile(dockerfile_content, scan_context)
            ai_end = datetime.now(timezone.utc)
            ai_duration_ms = int((ai_end - ai_start).total_seconds() * 1000)

            output_info = {
                "approved": result.get("approved"),
                "skipped": result.get("skipped"),
                "response": result.get("response", ""),
                "tool_calls": result.get("tool_calls", []),
                "modifications": result.get("modifications", []),
                "duration_ms": ai_duration_ms,
            }

            if result.get("skipped"):
                self._log(db, deployment_id, "warning",
                          f"AI review skipped ({service_name}): {result.get('reason', 'unknown')}",
                          details={"event": "ai_review", "type": "dockerfile", "input": input_info, "output": output_info})
            elif result.get("approved"):
                self._log(db, deployment_id, "info", f"AI approved Dockerfile ({service_name})",
                          details={"event": "ai_review", "type": "dockerfile", "input": input_info, "output": output_info})
            else:
                self._log(db, deployment_id, "warning",
                          f"AI modified Dockerfile ({service_name})",
                          details={"event": "ai_review", "type": "dockerfile", "input": input_info, "output": output_info})

                if result.get("modifications"):
                    with open(dockerfile_path) as f:
                        new_content = f.read()
                    if new_content != dockerfile_content:
                        self._log(db, deployment_id, "info", f"Dockerfile ({service_name}) updated by AI",
                                  details={"event": "ai_modification", "type": "dockerfile", "service": service_name,
                                           "before": dockerfile_content, "after": new_content})

        except Exception as e:
            ai_end = datetime.now(timezone.utc)
            ai_duration_ms = int((ai_end - ai_start).total_seconds() * 1000)
            self._log(db, deployment_id, "warning", f"AI review failed (continuing): {e}",
                      details={"event": "ai_review", "type": "dockerfile", "service": service_name,
                               "error": str(e), "duration_ms": ai_duration_ms})

    def _ai_review_compose(self, db: Session, deployment_id: str, repo_dir: str,
                           project_info: dict, deps_info: dict):
        """AI 审核 docker-compose.yml，注入完整扫描上下文"""
        import os

        compose_path = os.path.join(repo_dir, "docker-compose.yml")
        if not os.path.exists(compose_path):
            return

        self._log(db, deployment_id, "info", "AI reviewing docker-compose.yml...")

        try:
            ai_service = get_ai_service()

            with open(compose_path) as f:
                compose_content = f.read()

            enhanced_deps = dict(deps_info) if deps_info else {}
            enhanced_deps["project_type"] = project_info.get("type", "single")
            enhanced_deps["language"] = project_info.get("language", "unknown")
            enhanced_deps["framework"] = project_info.get("framework", "unknown")
            result = ai_service.review_docker_compose(compose_content, project_info, enhanced_deps)

            if result.get("skipped"):
                self._log(db, deployment_id, "warning",
                          f"AI compose review skipped: {result.get('reason', 'unknown')}")
            elif result.get("approved"):
                self._log(db, deployment_id, "info", "AI approved docker-compose.yml")
            else:
                self._log(db, deployment_id, "warning",
                          f"AI modified compose: {result.get('response', '')[:200]}")

                # 如果 AI 修改了文件，重新读取
                if result.get("modifications"):
                    with open(compose_path) as f:
                        new_content = f.read()
                    if new_content != compose_content:
                        self._log(db, deployment_id, "info", "docker-compose.yml updated by AI")

        except Exception as e:
            self._log(db, deployment_id, "warning", f"AI review failed (continuing): {e}")

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

    def _build_microservices(self, db: Session, deployment_id: str, deployment: Deployment,
                             repo_dir: str, repo_name: str, commit_short: str):
        """构建通用微服务项目（任何语言）"""
        import os

        project_info = deployment.config or {}
        services = project_info.get("services", [])
        images = {}

        for service in services:
            service_name = service["name"]
            service_dir = os.path.join(repo_dir, service["dir"])

            self._log(db, deployment_id, "info", f"Building service: {service_name}")

            # 生成 Dockerfile（如果不存在）
            dockerfile_path = os.path.join(service_dir, "Dockerfile")
            if not os.path.exists(dockerfile_path):
                self.docker_service.generate_dockerfile(service, service_dir)

            # 构建镜像
            image_tag = f"stackpilot/{repo_name}-{service_name}:{commit_short}"
            try:
                self.docker_service.build_image(service_dir, image_tag)
                images[service_name] = image_tag
                self._log(db, deployment_id, "info", f"Built {service_name}: {image_tag}")
            except Exception as e:
                self._log(db, deployment_id, "warning", f"Failed to build {service_name}: {e}")

        # 生成 docker-compose.yml
        self._generate_microservices_compose(repo_dir, services, images)

        deployment.image_tag = list(images.values())[0] if images else None
        deployment.config = {**project_info, "images": images, "compose": True}
        db.commit()

    def _generate_microservices_compose(self, repo_dir: str, services: list, images: dict):
        """生成微服务项目的 docker-compose.yml"""
        import os

        compose = """version: '3.8'

services:
"""

        # 添加应用服务
        for service in services:
            name = service["name"]
            if name not in images:
                continue

            compose += f"""  {name}:
    image: {images[name]}
    ports:
      - "{service['port']}:{service['port']}"
    environment:
      - SERVICE_NAME={name}
"""
            # 添加依赖关系
            deps = self._infer_service_deps(service, services)
            if deps:
                compose += "    depends_on:\n"
                for dep in deps:
                    if dep in images:
                        compose += f"      - {dep}\n"

            compose += "\n"

        # 添加外部依赖服务
        compose += self._generate_dependency_services(repo_dir, services)

        with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
            f.write(compose)

    def _generate_single_app_compose(self, repo_dir: str, repo_name: str, image_tag: str, deps: dict):
        """为单体应用生成包含依赖服务的 docker-compose.yml"""
        import os

        external_services = deps.get("external_services", [])
        db_init = deps.get("database_init", {})

        if not external_services:
            return

        compose = f"""version: '3.8'

services:
  app:
    image: {image_tag}
    ports:
      - "8080:8080"
    depends_on:
"""

        # 添加依赖服务到 depends_on
        for service_name in external_services:
            if service_name in EXTERNAL_SERVICES and EXTERNAL_SERVICES[service_name].image:
                compose += f"      - {service_name}\n"

        # 如果有数据库初始化，等待 db-init 完成
        if db_init.get("has_migrations") or db_init.get("has_schema_sql"):
            compose += "      - db-init\n"

        # 添加环境变量
        compose += "    environment:\n"
        for service_name in external_services:
            if service_name in EXTERNAL_SERVICES:
                service_info = EXTERNAL_SERVICES[service_name]
                if service_name == "mysql":
                    compose += f"      - MYSQL_HOST={service_name}\n"
                    compose += f"      - MYSQL_PORT={service_info.default_port}\n"
                elif service_name == "postgresql":
                    compose += f"      - POSTGRES_HOST={service_name}\n"
                    compose += f"      - POSTGRES_PORT={service_info.default_port}\n"
                elif service_name == "redis":
                    compose += f"      - REDIS_HOST={service_name}\n"
                    compose += f"      - REDIS_PORT={service_info.default_port}\n"
                elif service_name == "mongodb":
                    compose += f"      - MONGODB_HOST={service_name}\n"
                    compose += f"      - MONGODB_PORT={service_info.default_port}\n"
                elif service_name == "kafka":
                    compose += f"      - KAFKA_BOOTSTRAP_SERVERS={service_name}:{service_info.default_port}\n"
                elif service_name == "elasticsearch":
                    compose += f"      - ELASTICSEARCH_HOST={service_name}\n"
                    compose += f"      - ELASTICSEARCH_PORT={service_info.default_port}\n"

        # 添加初始化命令（如果有）— 真正执行迁移
        init_commands = db_init.get("init_commands", [])
        real_commands = [cmd for cmd in init_commands if not cmd.startswith("#")]
        if real_commands:
            migration_tool = db_init.get("migration_tool", "")
            tool_images = {
                "alembic": "python:3.11-slim", "django": "python:3.11-slim",
                "flyway": "flyway/flyway:latest", "prisma": "node:18-alpine",
                "typeorm": "node:18-alpine", "knex": "node:18-alpine",
            }
            init_image = tool_images.get(migration_tool, "python:3.11-slim")

            shell_parts = ["echo 'Waiting for database...'"]
            for service_name in external_services:
                if service_name in EXTERNAL_SERVICES:
                    service_info = EXTERNAL_SERVICES[service_name]
                    if service_info.category == "database":
                        port = service_info.default_port
                        shell_parts.append(
                            f"for i in $(seq 1 30); do nc -z {service_name} {port} && break || sleep 2; done"
                        )
            shell_parts.append("echo 'Database is ready'")
            for cmd in real_commands:
                shell_parts.append(f"echo 'Running: {cmd}' && {cmd}")
            shell_parts.append("echo 'Database initialization completed'")
            full_cmd = " && ".join(shell_parts)

            compose += f"""
  db-init:
    image: {init_image}
    command: sh -c "{full_cmd}"
    depends_on:
"""
            for service_name in external_services:
                if service_name in EXTERNAL_SERVICES:
                    service_info = EXTERNAL_SERVICES[service_name]
                    if service_info.category == "database":
                        compose += f"      - {service_name}\n"

            compose += "    volumes:\n      - .:/app\n    working_dir: /app\n"

        compose += "\n"

        # 添加依赖服务配置
        compose += self._generate_dependency_services(repo_dir)

        with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
            f.write(compose)

    def _generate_dependency_services(self, repo_dir: str, app_services: list = None) -> str:
        """生成外部依赖服务的 docker-compose 配置"""
        import os

        # 获取项目依赖信息
        config_path = os.path.join(repo_dir, ".stackpilot", "dependencies.json")
        if not os.path.exists(config_path):
            return ""

        try:
            with open(config_path) as f:
                deps = json.load(f)
        except Exception:
            return ""

        external_services = deps.get("external_services", [])
        if not external_services:
            return ""

        compose = ""

        for service_name in external_services:
            if service_name not in EXTERNAL_SERVICES:
                continue

            service_info = EXTERNAL_SERVICES[service_name]
            if not service_info.image:  # 跳过无镜像的服务（如 sqlite）
                continue

            port = service_info.default_port

            compose += f"""
  {service_name}:
    image: {service_info.image}
    ports:
      - "{port}:{port}"
"""

            # 添加环境变量
            if service_info.env_vars:
                compose += "    environment:\n"
                for key, value in service_info.env_vars.items():
                    compose += f"      - {key}={value}\n"

            # 添加数据卷（数据库持久化）
            if service_info.category == "database":
                compose += f"    volumes:\n      - {service_name}_data:/var/lib/{service_name}\n"

        # 添加数据库初始化服务
        db_init = deps.get("database_init", {})
        init_commands = db_init.get("init_commands", [])
        if init_commands:
            compose += self._generate_db_init_service(repo_dir, deps, init_commands)

        # 添加卷声明
        db_services = [s for s in external_services if s in EXTERNAL_SERVICES and EXTERNAL_SERVICES[s].category == "database"]
        if db_services:
            compose += "\nvolumes:\n"
            for s in db_services:
                compose += f"  {s}_data:\n"

        return compose

    def _generate_db_init_service(self, repo_dir: str, deps: dict, init_commands: list) -> str:
        """生成数据库初始化服务 — 真正执行迁移命令"""
        import os

        external_services = deps.get("external_services", [])
        db_init = deps.get("database_init", {})
        migration_tool = db_init.get("migration_tool", "")

        # 根据迁移工具选择合适的镜像
        tool_images = {
            "alembic": "python:3.11-slim",
            "django": "python:3.11-slim",
            "flyway": "flyway/flyway:latest",
            "prisma": "node:18-alpine",
            "typeorm": "node:18-alpine",
            "knex": "node:18-alpine",
            "golang-migrate": "migrate/migrate:latest",
        }
        init_image = tool_images.get(migration_tool, "python:3.11-slim")

        # 过滤掉注释命令，构建真正要执行的命令
        real_commands = [cmd for cmd in init_commands if not cmd.startswith("#")]
        if not real_commands:
            real_commands = ["echo 'No migration commands to execute'"]

        # 构建 shell 命令：先等待数据库就绪，再执行迁移
        shell_parts = ["echo 'Waiting for database...'"]
        # 等待数据库端口可达
        for service_name in external_services:
            if service_name in EXTERNAL_SERVICES:
                service_info = EXTERNAL_SERVICES[service_name]
                if service_info.category == "database":
                    port = service_info.default_port
                    shell_parts.append(
                        f"for i in $(seq 1 30); do nc -z {service_name} {port} && break || sleep 2; done"
                    )
        shell_parts.append("echo 'Database is ready'")
        for cmd in real_commands:
            shell_parts.append(f"echo 'Running: {cmd}' && {cmd}")
        shell_parts.append("echo 'Database initialization completed'")

        full_cmd = " && ".join(shell_parts)

        compose = f"""
  db-init:
    image: {init_image}
    command: sh -c "{full_cmd}"
    depends_on:
"""

        # 依赖数据库服务
        for service_name in external_services:
            if service_name in EXTERNAL_SERVICES:
                service_info = EXTERNAL_SERVICES[service_name]
                if service_info.category == "database":
                    compose += f"      - {service_name}\n"

        compose += "    volumes:\n      - .:/app\n    working_dir: /app\n"

        return compose

    def _infer_service_deps(self, service: dict, all_services: list) -> list:
        """推断服务依赖关系"""
        deps = []
        name = service["name"].lower()

        # 网关依赖注册中心
        if "gateway" in name or "proxy" in name:
            for s in all_services:
                if s["name"] != service["name"] and ("registry" in s["name"].lower() or "eureka" in s["name"].lower() or "consul" in s["name"].lower()):
                    deps.append(s["name"])

        # 普通服务可能依赖数据库服务或注册中心
        elif "service" in name or "api" in name:
            for s in all_services:
                s_name = s["name"].lower()
                if s["name"] != service["name"] and ("registry" in s_name or "eureka" in s_name or "config" in s_name):
                    deps.append(s["name"])

        return deps

    def _load_deps_from_file(self, repo_dir: str) -> dict:
        """从 .stackpilot/dependencies.json 加载依赖信息"""
        import os

        config_path = os.path.join(repo_dir, ".stackpilot", "dependencies.json")
        if not os.path.exists(config_path):
            return {}
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception:
            return {}

    def _adapt_config_for_docker(self, repo_dir: str, deps: dict):
        """将项目配置文件中的 localhost 替换为 Docker 服务名，修正端口映射"""
        import os
        import re

        external_services = deps.get("external_services", [])
        if not external_services:
            return

        # 服务名映射
        service_host_map = {
            "mysql": "mysql", "postgresql": "postgres", "redis": "redis",
            "kafka": "kafka", "zookeeper": "zookeeper", "elasticsearch": "elasticsearch",
            "mongodb": "mongodb", "minio": "minio", "nacos": "nacos",
            "memcached": "memcached", "rabbitmq": "rabbitmq", "rocketmq": "rocketmq",
        }

        # 端口映射：外部映射端口 -> 容器内部端口
        port_replacements = [
            # Redis: docker-compose 中 6380:6379，容器内用 6379
            (r"localhost:6380", "redis:6379"),
            (r"127\.0\.0\.1:6380", "redis:6379"),
            # Minio: docker-compose 中 9002:9000，容器内用 9000
            (r"localhost:9002", "minio:9000"),
            (r"127\.0\.0\.1:9002", "minio:9000"),
            # Minio Console: 9003:9001
            (r"localhost:9003", "minio:9001"),
            (r"127\.0\.0\.1:9003", "minio:9001"),
            # MySQL 内外一致
            (r"localhost:3306", "mysql:3306"),
            (r"127\.0\.0\.1:3306", "mysql:3306"),
            # PostgreSQL 内外一致
            (r"localhost:5432", "postgres:5432"),
            (r"127\.0\.0\.1:5432", "postgres:5432"),
            # Kafka 内外一致
            (r"localhost:9092", "kafka:9092"),
            (r"127\.0\.0\.1:9092", "kafka:9092"),
            # Zookeeper 内外一致
            (r"localhost:2181", "zookeeper:2181"),
            (r"127\.0\.0\.1:2181", "zookeeper:2181"),
            # Elasticsearch
            (r"localhost:9200", "elasticsearch:9200"),
            (r"127\.0\.0\.1:9200", "elasticsearch:9200"),
            # MongoDB
            (r"localhost:27017", "mongodb:27017"),
            (r"127\.0\.0\.1:27017", "mongodb:27017"),
            # RabbitMQ
            (r"localhost:5672", "rabbitmq:5672"),
            (r"127\.0\.0\.1:5672", "rabbitmq:5672"),
            # Nacos
            (r"localhost:8848", "nacos:8848"),
            (r"127\.0\.0\.1:8848", "nacos:8848"),
        ]

        # 只替换已检测到的外部服务相关的地址
        active_replacements = []
        for pattern, replacement in port_replacements:
            service_name = replacement.split(":")[0]
            if service_name in external_services or any(s in service_name for s in external_services):
                active_replacements.append((pattern, replacement))

        if not active_replacements:
            return

        # 扫描常见配置文件
        config_patterns = [
            "**/*.properties", "**/*.yml", "**/*.yaml", "**/.env",
            "**/conf/*", "**/config/*",
        ]

        skip_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__", ".stackpilot", "dist"}

        adapted_files = []
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for filename in files:
                if not any(filename.endswith(ext) for ext in [".properties", ".yml", ".yaml", ".env"]):
                    continue

                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception:
                    continue

                original = content
                for pattern, replacement in active_replacements:
                    content = re.sub(pattern, replacement, content)

                if content != original:
                    try:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(content)
                        rel_path = os.path.relpath(filepath, repo_dir)
                        adapted_files.append(rel_path)
                    except Exception:
                        pass

        if adapted_files:
            logger.info("Adapted config files for Docker: %s", adapted_files)

    def _build_multi_module_java(self, db: Session, deployment_id: str, deployment: Deployment,
                                  repo_dir: str, repo_name: str, commit_short: str):
        """构建多模块 Java 项目（Spring Cloud）"""
        import subprocess
        import os

        project_info = deployment.config or {}
        services = project_info.get("services", [])

        # 1. 先执行 Maven 整体构建
        self._log(db, deployment_id, "info", "Building multi-module Maven project...")
        result = subprocess.run(
            ["mvn", "clean", "package", "-DskipTests", "-pl", ",".join([s["dir"] for s in services if s["type"] != "common"])],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode != 0:
            # 尝试使用 mvnw
            result = subprocess.run(
                ["./mvnw", "clean", "package", "-DskipTests"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=600
            )

        if result.returncode != 0:
            raise AppError(
                code=ErrorCode.BUILD_ERROR,
                message=f"Maven build failed: {result.stderr[-500:]}",
                severity=ErrorSeverity.HIGH,
            )

        self._log(db, deployment_id, "info", "Maven build completed")

        # 2. 为每个服务构建 Docker 镜像
        images = {}
        for service in services:
            if service["type"] == "common":
                continue

            service_name = service["name"]
            service_dir = os.path.join(repo_dir, service["dir"])

            # 查找 jar 文件
            target_dir = os.path.join(service_dir, "target")
            jar_file = None
            if os.path.exists(target_dir):
                for f in os.listdir(target_dir):
                    if f.endswith(".jar") and not f.endswith("-sources.jar"):
                        jar_file = f
                        break

            if not jar_file:
                self._log(db, deployment_id, "warning", f"No jar found for {service_name}, skipping")
                continue

            # 生成 Dockerfile
            java_version = project_info.get("java_version", 17)
            dockerfile_content = f"""FROM eclipse-temurin:{java_version}-jre-alpine
WORKDIR /app
COPY target/{jar_file} app.jar
EXPOSE {service['port']}
CMD ["java", "-jar", "app.jar"]
"""
            dockerfile_path = os.path.join(service_dir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)

            # 构建镜像
            image_tag = f"stackpilot/{repo_name}-{service_name}:{commit_short}"
            self.docker_service.build_image(service_dir, image_tag)
            images[service_name] = image_tag
            self._log(db, deployment_id, "info", f"Built {service_name} image: {image_tag}")

        # 3. 生成 docker-compose.yml
        self._generate_multi_module_compose(repo_dir, services, images)

        deployment.image_tag = list(images.values())[0] if images else None
        deployment.config = {**project_info, "images": images, "compose": True}
        db.commit()

    def _generate_multi_module_compose(self, repo_dir: str, services: list, images: dict):
        """生成多模块项目的 docker-compose.yml"""
        import os

        compose = """version: '3.8'

services:
"""

        # 按类型排序：registry -> config -> gateway -> service
        type_order = {"registry": 0, "config": 1, "gateway": 2, "service": 3}
        sorted_services = sorted(services, key=lambda s: type_order.get(s["type"], 99))

        for service in sorted_services:
            name = service["name"]
            if name not in images:
                continue

            compose += f"""  {name}:
    image: {images[name]}
    ports:
      - "{service['port']}:{service['port']}"
"""
            # 添加依赖关系
            deps = []
            if service["type"] == "service":
                # 服务依赖 registry 和 config
                for s in services:
                    if s["type"] in ("registry", "config") and s["name"] in images:
                        deps.append(s["name"])
            elif service["type"] == "gateway":
                # 网关依赖 registry
                for s in services:
                    if s["type"] == "registry" and s["name"] in images:
                        deps.append(s["name"])

            if deps:
                compose += "    depends_on:\n"
                for dep in deps:
                    compose += f"      - {dep}\n"

            compose += "\n"

        # 添加外部依赖服务
        deps = self._load_deps_from_file(repo_dir)
        if deps.get("external_services"):
            compose += self._generate_dependency_services(repo_dir)

        with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
            f.write(compose)

    def _build_monorepo(self, db: Session, deployment_id: str, deployment: Deployment,
                        repo_dir: str, repo_name: str, commit_short: str):
        """构建 monorepo 项目（前端+后端）"""
        import os

        project_info = deployment.config or {}
        frontend = project_info.get("frontend", {})
        backend = project_info.get("backend", {})
        images = {}

        # 构建后端
        if backend:
            backend_dir = os.path.join(repo_dir, backend.get("dir", "backend"))
            backend_image = f"stackpilot/{repo_name}-backend:{commit_short}"
            self.docker_service.generate_dockerfile(backend, backend_dir)
            self.docker_service.build_image(backend_dir, backend_image)
            images["backend"] = backend_image
            self._log(db, deployment_id, "info", f"Built backend image: {backend_image}")

        # 构建前端
        if frontend:
            frontend_dir = os.path.join(repo_dir, frontend.get("dir", "frontend"))
            frontend_image = f"stackpilot/{repo_name}-frontend:{commit_short}"
            self.docker_service.generate_dockerfile(frontend, frontend_dir)
            self.docker_service.build_image(frontend_dir, frontend_image)
            images["frontend"] = frontend_image
            self._log(db, deployment_id, "info", f"Built frontend image: {frontend_image}")

        # 生成 docker-compose.yml
        self._generate_docker_compose(repo_dir, frontend, backend, images)

        deployment.image_tag = images.get("backend") or images.get("frontend")
        deployment.config = {**project_info, "images": images, "compose": True}
        db.commit()

    def _build_frontend_for_composite(self, db: Session, deployment_id: str, deployment: Deployment,
                                       repo_dir: str, repo_name: str, commit_short: str):
        """为组合项目（multi-module-java-with-frontend / microservices-with-frontend）构建前端镜像"""
        import os

        project_info = deployment.config or {}
        frontend_info = project_info.get("frontend", {})
        frontend_dir_name = frontend_info.get("dir", "frontend")
        frontend_dir = os.path.join(repo_dir, frontend_dir_name)

        if not os.path.isdir(frontend_dir):
            self._log(db, deployment_id, "warning", f"Frontend dir '{frontend_dir_name}' not found, skipping")
            return

        self._log(db, deployment_id, "info", f"Building frontend from {frontend_dir_name}/")

        # 生成前端 Dockerfile
        self.docker_service.generate_dockerfile(frontend_info, frontend_dir)

        # 构建前端镜像
        frontend_image = f"stackpilot/{repo_name}-frontend:{commit_short}"
        self.docker_service.build_image(frontend_dir, frontend_image)

        project_info["frontend_image"] = frontend_image
        deployment.config = project_info
        db.commit()

        self._log(db, deployment_id, "info", f"Frontend image built: {frontend_image}")

        # 为组合项目生成包含前端的 docker-compose
        self._generate_composite_compose(repo_dir, repo_name, project_info, frontend_image)

    def _generate_composite_compose(self, repo_dir: str, repo_name: str,
                                     project_info: dict, frontend_image: str):
        """为组合项目生成包含前端服务的 docker-compose.yml"""
        import os

        frontend_info = project_info.get("frontend", {})
        frontend_port = frontend_info.get("port", 5100)

        compose = f"""version: '3.8'

services:
  frontend:
    image: {frontend_image}
    ports:
      - "{frontend_port}:{frontend_port}"
    depends_on:
      - backend
    restart: unless-stopped

  backend:
    image: stackpilot/{repo_name}:latest
    ports:
      - "8080:8080"
    restart: unless-stopped

"""

        # 添加外部依赖服务
        deps = project_info.get("dependencies", {})
        if deps.get("external_services"):
            compose += self._generate_dependency_services(repo_dir)

        with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
            f.write(compose)

    def _generate_docker_compose(self, repo_dir: str, frontend: dict, backend: dict, images: dict):
        """生成 docker-compose.yml"""
        import os

        compose = """version: '3.8'

services:
"""
        backend_port = backend.get("port", 8000)
        frontend_port = frontend.get("port", 3000)

        if "backend" in images:
            compose += f"""  backend:
    image: {images['backend']}
    ports:
      - "{backend_port}:{backend_port}"
"""
            # 注入依赖服务环境变量
            backend_lang = backend.get("language", "unknown")
            framework = "spring" if backend_lang == "java" else "generic"
            env_vars = self._generate_service_env_vars(repo_dir, framework)
            if env_vars:
                compose += "    environment:\n"
                for k, v in sorted(env_vars.items()):
                    compose += f"      {k}={v}\n"
            else:
                compose += "    environment:\n      - NODE_ENV=production\n"

        if "frontend" in images:
            compose += f"""  frontend:
    image: {images['frontend']}
    ports:
      - "{frontend_port}:{frontend_port}"
    depends_on:
      - backend
"""

        # 添加外部依赖服务
        deps = self._load_deps_from_file(repo_dir)
        if deps.get("external_services"):
            compose += self._generate_dependency_services(repo_dir)

        with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
            f.write(compose)

    def _apply_confirmed_env_vars_to_compose(self, deployment_id: str) -> bool:
        """将用户确认的环境变量写入 docker-compose.yml"""
        import os

        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return False

        config = dict(deployment.config or {})
        confirmed_env_vars = config.get("pending_env_vars", {})

        if not confirmed_env_vars:
            self._log(self.db, deployment_id, "info", "No env vars to apply")
            return True

        repo_name = deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
        repo_dir = os.path.join(self.git_service.temp_dir, repo_name)
        compose_path = os.path.join(repo_dir, "docker-compose.yml")

        if not os.path.exists(compose_path):
            self._log(self.db, deployment_id, "warning", "docker-compose.yml not found")
            return False

        try:
            with open(compose_path, "r", encoding="utf-8") as f:
                c_lines = f.readlines()

            # 找 app 或 backend 服务
            service_idx = -1
            for j, line in enumerate(c_lines):
                s = line.strip()
                if s == "app:" or s == "backend:":
                    service_idx = j
                    break

            if service_idx < 0:
                self._log(self.db, deployment_id, "warning", "No app/backend service found")
                return False

            # 获取缩进
            indent = ""
            for ch in c_lines[service_idx]:
                if ch == " ":
                    indent += ch
                else:
                    break
            env_indent = indent + "    "
            child_indent = env_indent + "  "

            # 找现有 environment 块
            env_start = -1
            env_end = -1
            for j in range(service_idx + 1, len(c_lines)):
                if not c_lines[j].strip():
                    continue
                if not c_lines[j].startswith(indent):
                    break
                if c_lines[j].strip() == "environment:":
                    env_start = j
                    env_end = j + 1
                    for k in range(j + 1, len(c_lines)):
                        if not c_lines[k].startswith(env_indent) or not c_lines[k].strip():
                            env_end = k
                            break
                    break

            # 构建新 environment 段
            n_lines = []
            n_lines.append(env_indent + "environment:\n")
            for k, v in sorted(confirmed_env_vars.items()):
                n_lines.append(child_indent + k + "=" + v + "\n")

            if env_start >= 0:
                c_lines[env_start:env_end] = n_lines
            else:
                insert_pos = service_idx + 1
                for j in range(service_idx + 1, min(service_idx + 15, len(c_lines))):
                    if c_lines[j].strip() and not c_lines[j].strip().startswith("#"):
                        insert_pos = j + 1
                        break
                for nl in reversed(n_lines):
                    c_lines.insert(insert_pos, nl)

            with open(compose_path, "w", encoding="utf-8") as f:
                f.writelines(c_lines)

            self._log(self.db, deployment_id, "info",
                      f"Applied {len(confirmed_env_vars)} env vars to docker-compose.yml")
            return True

        except Exception as e:
            self._log(self.db, deployment_id, "error", f"Failed to apply env vars: {e}")
            return False

    def _step_push(self, db: Session, deployment_id: str, deployment: Deployment):
        if not deployment.image_tag:
            raise AppError(
                code=ErrorCode.DOCKER_ERROR,
                message="No image tag available for push",
                severity=ErrorSeverity.HIGH,
            )

        registry = (deployment.config or {}).get("registry", "")
        if not registry:
            self._log(db, deployment_id, "info", "No registry configured, skipping push step")
            return
        self.docker_service.push_image(deployment.image_tag, registry)

    def _step_deploy(self, db: Session, deployment_id: str, deployment: Deployment):
        db.refresh(deployment)
        platform = deployment.platform
        if platform == "k8s":
            self._deploy_to_k8s(db, deployment)
        elif platform == "coolify":
            self._deploy_to_coolify(deployment)
        elif platform == "local":
            self._deploy_to_local(db, deployment)
        else:
            raise AppError(
                code=ErrorCode.INVALID_PARAM,
                message=f"Unsupported platform: {platform}",
                severity=ErrorSeverity.HIGH,
            )

    def _deploy_to_local(self, db: Session, deployment: Deployment):
        import subprocess
        import os

        config = deployment.config or {}
        images = config.get("images", {})
        repo_name = deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
        repo_dir = os.path.join(self.git_service.temp_dir, repo_name)

        # 检测是否有外部依赖或是否为多服务项目
        has_deps = bool(config.get("dependencies", {}).get("external_services"))
        is_multi_service = config.get("type") in ("monorepo", "multi-module-java", "microservices") or config.get("compose")

        if is_multi_service or has_deps:
            self._deploy_compose_local(db, deployment, repo_dir, repo_name)
        else:
            app_name = config.get("app_name", "stackpilot-app")
            port = config.get("port", 8080)
            image = deployment.image_tag

            # 停止旧容器
            subprocess.run(["docker", "rm", "-f", app_name], capture_output=True, timeout=30)

            # 启动新容器
            cmd = ["docker", "run", "-d", "--name", app_name, "-p", f"{port}:{port}", image]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            # 清理悬空资源
            subprocess.run(["docker", "container", "prune", "-f"], capture_output=True, timeout=30)
            subprocess.run(["docker", "volume", "prune", "-f"], capture_output=True, timeout=30)

            if result.returncode != 0:
                raise AppError(
                    code=ErrorCode.DOCKER_ERROR,
                    message=f"Local deploy failed: {result.stderr}",
                    severity=ErrorSeverity.HIGH,
                )

            deployment.deploy_url = f"http://localhost:{port}"
            db.commit()
            self._log(db, str(deployment.id), "info", f"Deployed locally at http://localhost:{port}")

    def _deploy_compose_local(self, db: Session, deployment: Deployment, repo_dir: str, repo_name: str):
        """使用 docker-compose 部署 monorepo"""
        import subprocess

        compose_file = os.path.join(repo_dir, "docker-compose.yml")
        if not os.path.exists(compose_file):
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message="docker-compose.yml not found",
                severity=ErrorSeverity.HIGH,
            )

        project_name = f"stackpilot-{repo_name}"

        # 停止旧服务并清理资源
        subprocess.run(
            ["docker-compose", "-p", project_name, "-f", compose_file, "down", "--volumes", "--remove-orphans"],
            capture_output=True, timeout=60
        )

        # 启动新服务
        result = subprocess.run(
            ["docker-compose", "-p", project_name, "-f", compose_file, "up", "-d"],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            raise AppError(
                code=ErrorCode.DOCKER_ERROR,
                message=f"Docker Compose deploy failed: {result.stderr}",
                severity=ErrorSeverity.HIGH,
            )

        # 清理悬空资源
        subprocess.run(["docker", "container", "prune", "-f"], capture_output=True, timeout=30)
        subprocess.run(["docker", "volume", "prune", "-f"], capture_output=True, timeout=30)

        config = deployment.config or {}
        frontend_port = config.get("frontend", {}).get("port", 3000)
        backend_port = config.get("backend", {}).get("port", 8000)

        deployment.deploy_url = f"http://localhost:{frontend_port}"
        db.commit()
        self._log(db, str(deployment.id), "info",
                  f"Deployed via docker-compose. Frontend: http://localhost:{frontend_port}, Backend: http://localhost:{backend_port}")

    def _deploy_to_k8s(self, db: Session, deployment: Deployment):
        config = deployment.config or {}
        namespace = config.get("namespace", "default")
        app_name = config.get("app_name", "stackpilot-app")
        port = config.get("port", 80)
        replicas = config.get("replicas", 1)
        env_vars = config.get("env_vars", {})
        host = config.get("host", "")
        resources = config.get("resources", {})

        if not self.k8s_service:
            kubeconfig = config.get("kubeconfig")
            self.k8s_service = K8sService(kubeconfig=kubeconfig)

        self.k8s_service.create_namespace(namespace)
        self.k8s_service.create_deployment(
            namespace=namespace,
            name=app_name,
            image=deployment.image_tag,
            replicas=replicas,
            port=port,
            env_vars=env_vars,
            resources=resources,
        )
        self.k8s_service.create_service(
            namespace=namespace,
            name=app_name,
            port=port,
            target_port=port,
        )

        if host:
            self.k8s_service.create_ingress(
                namespace=namespace,
                name=app_name,
                host=host,
                service_name=app_name,
                service_port=port,
                tls=config.get("tls", False),
            )
            deployment.deploy_url = f"https://{host}"

    def _deploy_to_coolify(self, deployment: Deployment):
        import httpx

        config = deployment.config or {}
        coolify_url = config.get("coolify_url", "")
        coolify_token = config.get("coolify_token", "")
        app_name = config.get("app_name", "stackpilot-app")

        if not coolify_url or not coolify_token:
            raise AppError(
                code=ErrorCode.AUTH_ERROR,
                message="Coolify URL and token are required",
                severity=ErrorSeverity.HIGH,
            )

        with httpx.Client() as client:
            response = client.post(
                f"{coolify_url}/api/v1/applications",
                headers={"Authorization": f"Bearer {coolify_token}"},
                json={
                    "name": app_name,
                    "git_repository": deployment.git_url,
                    "git_branch": deployment.branch,
                    "image": deployment.image_tag,
                },
                timeout=60,
            )

            if response.status_code not in (200, 201):
                raise AppError(
                    code=ErrorCode.CLOUD_API_ERROR,
                    message=f"Coolify API error: {response.status_code} {response.text}",
                    severity=ErrorSeverity.HIGH,
                    retryable=True,
                )

            data = response.json()
            deployment.deploy_url = data.get("fqdn", data.get("url", ""))

    def _step_configure(self, db: Session, deployment_id: str, deployment: Deployment):
        config = deployment.config or {}
        env_vars = config.get("env_vars", {})

        if deployment.platform == "k8s" and env_vars:
            self._log(db, deployment_id, "info", f"Configured {len(env_vars)} environment variables")

    def _step_verify(self, db: Session, deployment_id: str, deployment: Deployment):
        import subprocess
        import time

        if deployment.platform == "k8s" and self.k8s_service:
            config = deployment.config or {}
            namespace = config.get("namespace", "default")
            app_name = config.get("app_name", "stackpilot-app")

            status = self.k8s_service.wait_for_deployment(
                namespace=namespace,
                name=app_name,
                timeout=config.get("verify_timeout", 120),
            )
            if status["status"] != "ready":
                raise AppError(
                    code=ErrorCode.K8S_ERROR,
                    message=f"Deployment verification failed: {status}",
                    severity=ErrorSeverity.HIGH,
                )
        elif deployment.platform == "local":
            self._verify_local_deployment(db, deployment)
        self._log(db, deployment_id, "info", "Deployment verified successfully")

    def _verify_local_deployment(self, db: Session, deployment: Deployment):
        """验证本地部署：容器状态 + 端口监听 + HTTP 可达"""
        import subprocess
        import time
        import socket

        config = deployment.config or {}
        repo_name = deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
        deployment_id = str(deployment.id)

        # 1. 等待容器启动（最多 30 秒）
        self._log(db, deployment_id, "info", "Verifying: waiting for containers to start...")
        time.sleep(5)

        # 2. 检查容器是否在运行
        is_compose = config.get("compose") or config.get("type") in (
            "monorepo", "multi-module-java", "microservices",
            "multi-module-java-with-frontend", "microservices-with-frontend"
        )

        if is_compose:
            project_name = f"stackpilot-{repo_name}"
            result = subprocess.run(
                ["docker-compose", "-p", project_name, "ps", "-q"],
                capture_output=True, text=True, timeout=15
            )
            container_ids = [c.strip() for c in result.stdout.strip().split('\n') if c.strip()]
            if not container_ids:
                raise AppError(
                    code=ErrorCode.DOCKER_ERROR,
                    message="No running containers found for compose project",
                    severity=ErrorSeverity.HIGH,
                )
            # 检查每个容器的状态
            for cid in container_ids:
                inspect = subprocess.run(
                    ["docker", "inspect", "--format", "{{.State.Status}}", cid],
                    capture_output=True, text=True, timeout=10
                )
                status = inspect.stdout.strip()
                if status != "running":
                    logs = subprocess.run(
                        ["docker", "logs", "--tail", "10", cid],
                        capture_output=True, text=True, timeout=10
                    )
                    raise AppError(
                        code=ErrorCode.DOCKER_ERROR,
                        message=f"Container {cid[:12]} status={status}. Logs: {logs.stderr[-300:]}",
                        severity=ErrorSeverity.HIGH,
                    )
            self._log(db, deployment_id, "info", f"Verify: {len(container_ids)} containers running")
        else:
            app_name = config.get("app_name", "stackpilot-app")
            inspect = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", app_name],
                capture_output=True, text=True, timeout=10
            )
            if inspect.returncode != 0 or inspect.stdout.strip() != "running":
                raise AppError(
                    code=ErrorCode.DOCKER_ERROR,
                    message=f"Container '{app_name}' is not running",
                    severity=ErrorSeverity.HIGH,
                )
            self._log(db, deployment_id, "info", f"Verify: container '{app_name}' is running")

        # 3. 检查端口是否可达（尝试连接 deploy_url 的端口）
        deploy_url = deployment.deploy_url or ""
        if deploy_url:
            import re
            port_match = re.search(r':(\d+)', deploy_url)
            if port_match:
                port = int(port_match.group(1))
                for attempt in range(6):
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(3)
                        sock.connect(("127.0.0.1", port))
                        sock.close()
                        self._log(db, deployment_id, "info", f"Verify: port {port} is listening")
                        break
                    except (ConnectionRefusedError, socket.timeout, OSError):
                        if attempt < 5:
                            time.sleep(5)
                        else:
                            raise AppError(
                                code=ErrorCode.DOCKER_ERROR,
                                message=f"Port {port} is not reachable after 30s",
                                severity=ErrorSeverity.HIGH,
                            )

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

    def _rollback_resources(self, db: Session, deployment_id: str):
        checkpoint = self._get_checkpoint(db, deployment_id)
        if not checkpoint:
            return

        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return

        if deployment.platform == "k8s" and self.k8s_service:
            config = deployment.config or {}
            namespace = config.get("namespace", "default")
            app_name = config.get("app_name", "stackpilot-app")
            try:
                self.k8s_service.delete_deployment(namespace, app_name)
                self._log(db, deployment_id, "info", "Rolled back K8s resources")
            except Exception as e:
                self._log(db, deployment_id, "warning", f"Failed to rollback K8s resources: {e}")

        self.git_service.cleanup(deployment.git_url)

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
