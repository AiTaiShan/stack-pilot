"""clone_step.py — 从 Git 仓库克隆代码并检测项目类型"""
import json
import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentStep
from app.services.scanner.git_service import GitService
from app.services.scanner.dependency_detector import detect_project_dependencies, EXTERNAL_SERVICES
from app.core.error_handler import AppError, ErrorCode, ErrorSeverity

logger = logging.getLogger(__name__)


def execute(db: Session, deployment_id: str, deployment: Deployment, git_service: GitService, log_fn) -> None:
    """
    克隆仓库 + 检测项目类型
    结果保存到 deployment.config 和 deployment._project_info (Python 属性)
    """
    step_start = datetime.now(timezone.utc)

    # 1. Clone
    clone_start = datetime.now(timezone.utc)
    repo_dir = git_service.clone(deployment.git_url, branch=deployment.branch)
    clone_duration_ms = int((datetime.now(timezone.utc) - clone_start).total_seconds() * 1000)
    log_fn(db, deployment_id, "info", f"Repository cloned ({clone_duration_ms}ms)",
           details={"event": "git_clone", "git_url": deployment.git_url, "branch": deployment.branch or "default",
                    "target_dir": repo_dir, "duration_ms": clone_duration_ms})

    # 2. 获取提交信息
    commit_start = datetime.now(timezone.utc)
    commit_info = git_service.get_latest_commit(repo_dir)
    deployment.commit_hash = commit_info["hash"]
    deployment.commit_message = commit_info["message"]
    commit_duration_ms = int((datetime.now(timezone.utc) - commit_start).total_seconds() * 1000)
    log_fn(db, deployment_id, "info",
           f"Commit info: {commit_info['hash'][:12]} - {commit_info['message'][:80]}",
           details={"event": "git_commit", "commit_hash": commit_info["hash"],
                    "author": commit_info.get("author_name", ""), "message": commit_info["message"],
                    "duration_ms": commit_duration_ms})

    # 3. 检测项目类型 + 外部服务版本
    detect_start = datetime.now(timezone.utc)
    detected = _detect_project_type(repo_dir, deployment, db, deployment_id, log_fn)
    deps = detect_project_dependencies(repo_dir)
    detected["dependencies"] = deps
    # 保存外部服务版本到依赖文件
    service_versions = deps.get("service_versions", {})
    if service_versions:
        deps_dir = os.path.join(repo_dir, ".stackpilot")
        os.makedirs(deps_dir, exist_ok=True)
        deps_file = os.path.join(deps_dir, "dependencies.json")
        if os.path.exists(deps_file):
            with open(deps_file) as f:
                existing = json.load(f)
            existing["service_versions"] = service_versions
            with open(deps_file, "w") as f:
                json.dump(existing, f, indent=2)
    detected["_service_versions"] = service_versions
    detect_duration_ms = int((datetime.now(timezone.utc) - detect_start).total_seconds() * 1000)
    if service_versions:
        log_fn(db, deployment_id, "info",
               f"Detected service versions: {service_versions}",
               details={"event": "service_versions", "versions": service_versions})

    # 4. 保存到 config + Python 属性
    config = deployment.config or {}
    config.update(detected)
    config["_repo_dir"] = repo_dir
    deployment.config = config
    db.commit()

    deployment._project_type = detected.get("type", "")
    deployment._repo_dir = repo_dir
    deployment._project_info = config

    # 5. 记录检测结果
    log_fn(db, deployment_id, "info",
           f"Project detected: {detected.get('type', 'single')} | {detected.get('language', 'unknown')} | {detected.get('framework', '')}",
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


def _detect_project_type(repo_dir: str, deployment, db: Session, deployment_id: str, log_fn) -> dict:
    """检测项目类型，先用规则初筛，再交给 LLM 审核修正"""
    from app.services.scanner.detector import detect

    # 1. 规则初筛（使用通用检测器）
    scan_result = detect(repo_dir)

    detected = {
        "type": scan_result.project_type,
        "language": scan_result.language,
        "framework": scan_result.framework or "",
        "port": scan_result.port,
        "entry_point": scan_result.entry_point,
        "package_manager": scan_result.package_manager,
        "version": scan_result.version if hasattr(scan_result, 'version') and scan_result.version else "",
    }

    # Java 项目：规则引擎未提取 version，这里主动读取 pom.xml
    # 支持所有 Java 项目类型：multi-module-java、microservices、以及带前端的变体
    java_project_types = ("multi-module-java", "multi-module-java-with-frontend",
                          "microservices", "microservices-with-frontend")
    # 注意：scan_result.language 可能是 "node"（混合项目），所以用 languages 列表或 project_type 来判断
    has_java = (scan_result.language == "java"
                or any(l == "java" for l in getattr(scan_result, 'languages', []))
                or scan_result.project_type in java_project_types)
    if scan_result.project_type in java_project_types and has_java and not detected.get("version"):
        pom_path = os.path.join(repo_dir, "pom.xml")
        if os.path.exists(pom_path):
            import re as _re
            with open(pom_path, errors="ignore") as _f:
                _pom = _f.read()
            _m = _re.search(r'<java\.version>([^<]+)</java\.version>', _pom)
            if _m:
                detected["version"] = _m.group(1).strip()
                detected["java_version"] = int(detected["version"])
                log_fn(db, deployment_id, "info",
                       f"Detected Java version from pom.xml: {detected['version']}",
                       details={"event": "java_version_detected", "version": detected["version"]})

    if scan_result.services:
        detected["services"] = [
            {"name": s.name, "dir": s.dir, "type": s.type, "port": s.port,
             "language": s.language, "framework": s.framework or ""}
            for s in scan_result.services
        ]
    if scan_result.frontend:
        detected["frontend"] = {
            "dir": scan_result.frontend.dir, "language": scan_result.frontend.language,
            "framework": scan_result.frontend.framework or "", "port": scan_result.frontend.port,
        }
    if scan_result.backend:
        detected["backend"] = {
            "dir": scan_result.backend.dir, "language": scan_result.backend.language,
            "framework": scan_result.backend.framework or "", "port": scan_result.backend.port,
        }
    detected["_key_files"] = scan_result.key_files

    # 2. LLM 审核
    detected = _llm_review_detection(repo_dir, detected, db, deployment_id, log_fn)

    return detected


def _llm_review_detection(repo_dir: str, detected: dict, db: Session, deployment_id: str, log_fn) -> dict:
    """调用 LLM 审核项目类型检测结果，修正错误并补充缺失信息"""
    from app.services.ai.ai_service import get_ai_service
    from app.services.scanner.detector import _collect_project_structure as _collect_structure
    from app.services.scanner.rules.context import ProjectContext
    import re

    structure = _collect_structure(ProjectContext(repo_dir))

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
  "framework": "spring-boot",
  "pkg_manager": "npm",
  "config_adaptation_needed": false,
  "corrections": "修正说明",
  "services": [
    {{"name": "module-name", "dir": "module-dir", "type": "service|common|library"}}
  ]
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
                from app.services.scanner.detector import detect as _detect_sub
                frontend_scan = _detect_sub(frontend_path)
                frontend_info = {
                    "language": frontend_scan.language,
                    "framework": frontend_scan.framework or "",
                    "port": frontend_scan.port,
                    "entry_point": frontend_scan.entry_point,
                    "package_manager": frontend_scan.package_manager,
                }
                frontend_info["dir"] = review["frontend_dir"]
                detected["frontend"] = frontend_info

        # 确保项目类型正确反映是否有前端
        if detected.get("frontend"):
            if detected.get("type") == "multi-module-java":
                detected["type"] = "multi-module-java-with-frontend"
            elif detected.get("type") == "microservices":
                detected["type"] = "microservices-with-frontend"

        if review.get("java_version"):
            detected["java_version"] = int(review["java_version"])
        if review.get("framework"):
            detected["framework"] = review["framework"]
        if review.get("pkg_manager"):
            detected["pkg_manager"] = review["pkg_manager"]
        if review.get("config_adaptation_needed"):
            detected["config_adaptation_needed"] = True

        if review.get("corrections"):
            logger.info("LLM detection correction: %s", review["corrections"])

        # 如果 AI 返回了修正后的 services 列表，用它替换原有的
        if review.get("services") and isinstance(review["services"], list):
            corrected = False
            for svc in detected.get("services", []):
                ai_svc = next((s for s in review["services"] if s.get("name") == svc["name"]), None)
                if ai_svc and ai_svc.get("type") != svc.get("type"):
                    # 保护：不允许 LLM 将 "common" 类型改为其他类型
                    # common 模块是库/依赖，不应该作为独立容器运行
                    if svc.get("type") == "common":
                        logger.info("Protecting common service from LLM override: %s (kept type=%s, rejected type=%s)",
                                   svc["name"], svc["type"], ai_svc.get("type"))
                        continue
                    if "common" in svc.get("name", "").lower():
                        logger.info("Protecting service with 'common' in name from LLM override: %s", svc["name"])
                        continue
                    svc["type"] = ai_svc["type"]
                    corrected = True
            if corrected:
                logger.info("Services list corrected based on AI review: %s",
                            [(s["name"], s["type"]) for s in detected.get("services", [])])

    except Exception as e:
        logger.warning("LLM detection review failed, using rule-based result: %s", e)

    return detected




def _cleanup_old_images(db: Session, deployment_id: str, repo_name: str, git_service: GitService, log_fn):
    """清理旧的 Docker 镜像，防止磁盘空间膨胀"""
    import subprocess

    image_prefix = f"stackpilot/{repo_name}"

    try:
        # 按创建时间排序（最新的排第一），避免按字母序误删新镜像
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", "--filter", f"reference={image_prefix}*", "--sort", "created"],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            return

        images = [img.strip() for img in result.stdout.strip().split('\n') if img.strip()]

        # 保留最近 N 个镜像，支持回滚
        KEEP_IMAGES = 3
        if len(images) <= KEEP_IMAGES:
            return

        # 只清理超出保留数量的旧镜像
        images_to_remove = images[KEEP_IMAGES:]

        for img in images_to_remove:
            log_fn(db, deployment_id, "info", f"Cleaning up old image: {img}")
            subprocess.run(["docker", "rmi", "-f", img], capture_output=True, timeout=30)

        if images_to_remove:
            log_fn(db, deployment_id, "info", f"Cleaned up {len(images_to_remove)} old images")

    except Exception as e:
        # 清理失败不影响构建流程
        log_fn(db, deployment_id, "warning", f"Image cleanup failed: {e}")

    # 清理悬空镜像
    try:
        subprocess.run(["docker", "image", "prune", "-f"], capture_output=True, timeout=60)
    except Exception:
        pass