"""build_step.py — Maven/Docker 镜像构建步骤"""
import os
import subprocess
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from app.models.deployment import Deployment

from app.services.deployer.services.compose_gen import (
    generate_multi_module_compose,
    generate_microservices_compose,
    generate_single_app_compose,
    generate_dependency_services,
    load_deps_from_file,
    infer_service_deps,
)

logger = logging.getLogger(__name__)


def execute(db: Session, deployment_id: str, deployment: Deployment,
            git_service, docker_service, log_fn) -> None:
    """
    构建 Docker 镜像（文件生成和审核已在 generate_review 完成）
    1. 清理旧镜像
    2. 根据项目类型选择构建方式
    3. 生成 docker-compose.yml
    """
    # 优先使用 Python 属性（不会被 db.commit() expire），再回退到 config
    project_type = getattr(deployment, '_project_type', '') or (deployment.config or {}).get("type", "")

    # 检测是否有前端目录，如果有则升级项目类型
    repo_dir_temp = getattr(deployment, '_repo_dir', '') or (deployment.config or {}).get('_repo_dir', '') or os.path.join(
        git_service.temp_dir,
        deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
    )
    if repo_dir_temp and os.path.exists(repo_dir_temp) and "with-frontend" not in project_type:
        from app.services.scanner.rules.structure_rule import _find_frontend_directory
        from app.services.scanner.rules.context import ProjectContext
        ctx = ProjectContext(repo_dir_temp)
        fe_dir = _find_frontend_directory(ctx)
        if fe_dir:
            if project_type == "microservices":
                project_type = "microservices-with-frontend"
            elif project_type == "multi-module-java":
                project_type = "multi-module-java-with-frontend"
            # 更新 deployment.config 中的 type
            config = deployment.config or {}
            config["type"] = project_type
            deployment.config = config
            db.commit()
            log_fn(db, deployment_id, "info",
                   f"Upgraded project type to {project_type} (detected frontend: {fe_dir})")

    repo_dir = getattr(deployment, '_repo_dir', '') or os.path.join(
        git_service.temp_dir,
        deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
    )
    commit_short = deployment.commit_hash[:8] if deployment.commit_hash else "latest"
    repo_name = os.path.basename(repo_dir.rstrip("/"))

    # 清理旧镜像
    _cleanup_old_images(db, deployment_id, repo_name, log_fn)

    # 按项目类型构建镜像
    if project_type in ("multi-module-java", "multi-module-java-with-frontend"):
        _build_multi_module_java(db, deployment_id, deployment, repo_dir, repo_name, commit_short, docker_service, log_fn)
        if "with-frontend" in project_type:
            _build_frontend_for_composite(db, deployment_id, deployment, repo_dir, repo_name, commit_short, docker_service, log_fn)
    elif project_type in ("microservices", "microservices-with-frontend"):
        # 先构建前端镜像（如果有）
        frontend_image = None
        frontend_info = None
        if "with-frontend" in project_type:
            frontend_image, frontend_info = _build_frontend_for_composite(db, deployment_id, deployment, repo_dir, repo_name, commit_short, docker_service, log_fn)
        # 构建微服务镜像并生成包含前端的 compose
        _build_microservices(db, deployment_id, deployment, repo_dir, repo_name, commit_short, docker_service, log_fn, frontend_image, frontend_info)
    elif project_type == "monorepo":
        _build_monorepo(db, deployment_id, deployment, repo_dir, repo_name, commit_short, docker_service, log_fn)
    else:
        # 单体项目
        image_tag = f"stackpilot/{repo_name}:{commit_short}"
        docker_service.build_image(repo_dir, image_tag)
        deployment.image_tag = image_tag
    db.commit()


def _cleanup_old_images(db: Session, deployment_id: str, repo_name: str, log_fn):
    """清理旧的 Docker 镜像，防止磁盘空间膨胀，并确保不会使用缓存"""
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

        if not images:
            log_fn(db, deployment_id, "info", "No existing images found, proceeding with fresh build")
            return

        # 删除所有相关镜像，确保不会使用缓存
        log_fn(db, deployment_id, "info", f"Removing {len(images)} existing images to ensure fresh build...")
        for img in images:
            log_fn(db, deployment_id, "info", f"Removing image: {img}")
            subprocess.run(["docker", "rmi", "-f", img], capture_output=True, timeout=30)

        log_fn(db, deployment_id, "info", f"Removed {len(images)} images successfully")

    except Exception as e:
        log_fn(db, deployment_id, "warning", f"Image cleanup failed: {e}")

    try:
        subprocess.run(["docker", "image", "prune", "-f"], capture_output=True, timeout=60)
    except Exception:
        pass


def _build_multi_module_java(db: Session, deployment_id: str, deployment: Deployment,
                              repo_dir: str, repo_name: str, commit_short: str,
                              docker_service, log_fn):
    """构建多模块 Java 项目"""
    project_info = getattr(deployment, '_project_info', deployment.config or {})
    services = project_info.get("services", [])

    # 1. Maven 整体构建
    log_fn(db, deployment_id, "info", "Building multi-module Maven project...")
    result = subprocess.run(
        ["mvn", "clean", "package", "-DskipTests"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=600
    )

    if result.returncode != 0:
        result = subprocess.run(
            ["./mvnw", "clean", "package", "-DskipTests"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=600
        )

    if result.returncode != 0:
        from app.core.error_handler import AppError, ErrorCode, ErrorSeverity
        raise AppError(
            code=ErrorCode.BUILD_ERROR,
            message=f"Maven build failed: {result.stderr[-500:]}",
            severity=ErrorSeverity.HIGH,
        )

    log_fn(db, deployment_id, "info", "Maven build completed")

    # 2. 为每个可执行服务构建 Docker 镜像
    def _is_executable_jar(jar_path: str) -> bool:
        """检测 JAR 是否为可执行 JAR（通用方案）"""
        import zipfile
        try:
            with zipfile.ZipFile(jar_path) as zf:
                namelist = zf.namelist()
                if any(n.startswith("BOOT-INF/") for n in namelist):
                    return True
                if any(n.startswith("quarkus-app/") for n in namelist):
                    return True
                if "META-INF/MANIFEST.MF" in namelist:
                    manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8")
                    if "Main-Class: " in manifest:
                        return True
            return False
        except Exception:
            return False

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
                if f.endswith(".jar") and not f.endswith("-sources.jar") and not f.endswith("-javadoc.jar"):
                    jar_file = f
                    break

        if not jar_file:
            log_fn(db, deployment_id, "info", f"No jar for {service_name}, skipping (library)")
            continue

        # 检测是否为可执行 JAR
        jar_path = os.path.join(target_dir, jar_file)
        if not _is_executable_jar(jar_path):
            log_fn(db, deployment_id, "info", f"{service_name} JAR is not executable, skipping (library)")
            continue

        log_fn(db, deployment_id, "info", f"{service_name} is executable, building image...")

        # 生成 Dockerfile
        java_version = project_info.get("version") or project_info.get("java_version", 17)
        try:
            java_version = int(java_version)
        except (ValueError, TypeError):
            java_version = 17
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
        docker_service.build_image(service_dir, image_tag)
        images[service_name] = image_tag
        log_fn(db, deployment_id, "info", f"Built {service_name} image: {image_tag}")

    # 兜底：如果 images 为空，扫所有 target 目录找可执行 JAR
    if not images:
        import glob as _glob, zipfile as _zf
        log_fn(db, deployment_id, "info", "Fallback: scanning all target dirs for executable JARs...")
        for jar_path in _glob.glob(os.path.join(repo_dir, "**", "target", "*.jar"), recursive=True):
            jname = os.path.basename(jar_path)
            if any(x in jname for x in ["-sources", "-javadoc", "-tests"]):
                continue
            try:
                with _zf.ZipFile(jar_path) as z:
                    if any(n.startswith("BOOT-INF/") for n in z.namelist()):
                        mod_dir = os.path.dirname(os.path.dirname(jar_path))
                        mod_name = os.path.basename(mod_dir)
                        tag = f"stackpilot/{repo_name}-{mod_name}:{commit_short}"
                        docker_service.build_image(mod_dir, tag)
                        images[mod_name] = tag
                        log_fn(db, deployment_id, "info", f"Fallback built: {tag}")
                        break
            except Exception:
                continue

    # 3. 生成 docker-compose.yml（传入检测到的版本信息）
    service_versions = project_info.get("_service_versions", {})
    generate_multi_module_compose(repo_dir, services, images, service_versions)

    deployment.image_tag = list(images.values())[0] if images else None
    deployment.config = {**project_info, "images": images, "compose": True}
    db.commit()


def _build_microservices(db: Session, deployment_id: str, deployment: Deployment,
                          repo_dir: str, repo_name: str, commit_short: str,
                          docker_service, log_fn, frontend_image=None, frontend_info=None):
    """构建通用微服务项目（任何语言）"""
    project_info = getattr(deployment, '_project_info', deployment.config or {})
    services = project_info.get("services", [])
    images = {}

    # 检测是否有 Java 微服务，需要先 Maven 构建
    has_java = any(s.get("language") == "java" and s.get("type") != "common" for s in services)
    if has_java:
        log_fn(db, deployment_id, "info", "Building Java microservices with Maven...")
        result = subprocess.run(
            ["mvn", "clean", "package", "-DskipTests"],
            cwd=repo_dir, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["./mvnw", "clean", "package", "-DskipTests"],
                cwd=repo_dir, capture_output=True, text=True, timeout=600
            )
        if result.returncode != 0:
            raise AppError(
                code=ErrorCode.BUILD_ERROR,
                message=f"Maven build failed: {result.stderr[-300:]}",
                severity=ErrorSeverity.HIGH,
            )
        log_fn(db, deployment_id, "info", "Maven build completed")

    for service in services:
        if service.get("type") == "common":
            continue
        service_name = service["name"]
        service_dir = os.path.join(repo_dir, service["dir"])

        log_fn(db, deployment_id, "info", f"Building service: {service_name}")
        log_fn(db, deployment_id, "info", f"Building service: {service_name}")

        # Dockerfile 已在 review_step 生成，此处直接构建
        dockerfile_path = os.path.join(service_dir, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            log_fn(db, deployment_id, "warning", f"Dockerfile not found for {service_name}, generating fallback...")
            if service.get("language") == "java":
                java_ver = project_info.get("version") or project_info.get("java_version", "17")
                try: java_ver = int(java_ver)
                except: java_ver = 17
                with open(dockerfile_path, "w") as df:
                    df.write(f"""FROM eclipse-temurin:{java_ver}-jre-alpine
WORKDIR /app
COPY target/*.jar app.jar
EXPOSE {service.get("port", 8080)}
CMD ["java", "-jar", "app.jar"]
""")
            else:
                log_fn(db, deployment_id, "warning", f"No Dockerfile for {service_name}, skipping")
                continue
        image_tag = f"stackpilot/{repo_name}-{service_name}:{commit_short}"
        try:
            docker_service.build_image(service_dir, image_tag)
            images[service_name] = image_tag
            log_fn(db, deployment_id, "info", f"Built {service_name}: {image_tag}")
        except Exception as e:
            log_fn(db, deployment_id, "warning", f"Failed to build {service_name}: {e}")

    # 生成 docker-compose.yml（包含前端服务）
    generate_microservices_compose(repo_dir, services, images, frontend_image, frontend_info)

    deployment.image_tag = list(images.values())[0] if images else None
    deployment.config = {**project_info, "images": images, "compose": True}
    db.commit()


def _build_monorepo(db: Session, deployment_id: str, deployment: Deployment,
                    repo_dir: str, repo_name: str, commit_short: str,
                    docker_service, log_fn):
    """构建 monorepo 项目（前端+后端）"""
    project_info = getattr(deployment, '_project_info', deployment.config or {})
    frontend = project_info.get("frontend", {})
    backend = project_info.get("backend", {})
    images = {}

    # 构建后端
    if backend:
        backend_dir = os.path.join(repo_dir, backend.get("dir", "backend"))
        backend_image = f"stackpilot/{repo_name}-backend:{commit_short}"
        docker_service.generate_dockerfile(backend, backend_dir)
        docker_service.build_image(backend_dir, backend_image)
        images["backend"] = backend_image
        log_fn(db, deployment_id, "info", f"Built backend image: {backend_image}")

    # 构建前端
    if frontend:
        frontend_dir = os.path.join(repo_dir, frontend.get("dir", ""))
        frontend_image = f"stackpilot/{repo_name}-frontend:{commit_short}"
        docker_service.generate_dockerfile(frontend, frontend_dir)
        docker_service.build_image(frontend_dir, frontend_image)
        images["frontend"] = frontend_image
        log_fn(db, deployment_id, "info", f"Built frontend image: {frontend_image}")

    # 生成 docker-compose.yml
    _generate_monorepo_compose(repo_dir, frontend, backend, images)

    deployment.image_tag = images.get("backend") or images.get("frontend")
    deployment.config = {**project_info, "images": images, "compose": True}
    db.commit()


def _generate_monorepo_compose(repo_dir: str, frontend: dict, backend: dict, images: dict):
    """生成 monorepo 项目的 docker-compose.yml"""
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

    if "frontend" in images:
        compose += f"""  frontend:
    image: {images['frontend']}
    ports:
      - "{frontend_port}:{frontend_port}"
    depends_on:
      - backend
"""

    # 添加外部依赖服务
    deps = load_deps_from_file(repo_dir)
    if deps.get("external_services"):
        compose += generate_dependency_services(repo_dir, service_versions=service_versions)

    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)


def _build_frontend_for_composite(db: Session, deployment_id: str, deployment: Deployment,
                                    repo_dir: str, repo_name: str, commit_short: str,
                                    docker_service, log_fn):
    """为组合项目（multi-module-java-with-frontend / microservices-with-frontend）构建前端镜像"""
    project_info = getattr(deployment, '_project_info', deployment.config or {})
    frontend_info = project_info.get("frontend", {})
    frontend_dir_name = frontend_info.get("dir", "")
    frontend_dir = os.path.join(repo_dir, frontend_dir_name)

    if not os.path.isdir(frontend_dir):
        log_fn(db, deployment_id, "warning", f"Frontend dir '{frontend_dir_name}' not found, skipping")
        return None, None

    log_fn(db, deployment_id, "info", f"Building frontend from {frontend_dir_name}/")

    # 生成前端 Dockerfile
    docker_service.generate_dockerfile(frontend_info, frontend_dir)

    # 构建前端镜像
    frontend_image = f"stackpilot/{repo_name}-frontend:{commit_short}"
    docker_service.build_image(frontend_dir, frontend_image)

    project_info["frontend_image"] = frontend_image
    deployment.config = project_info
    db.commit()

    log_fn(db, deployment_id, "info", f"Frontend image built: {frontend_image}")

    # 返回前端镜像信息，供 generate_microservices_compose 使用
    return frontend_image, frontend_info


def _generate_composite_compose(repo_dir: str, repo_name: str,
                                 project_info: dict, frontend_image: str):
    """为组合项目生成包含前端服务的 docker-compose.yml"""
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
        compose += generate_dependency_services(repo_dir)

    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)


def _generate_docker_compose(repo_dir: str, frontend: dict, backend: dict, images: dict):
    """生成 docker-compose.yml"""
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
        env_vars = _generate_service_env_vars(repo_dir, framework)
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
    deps = load_deps_from_file(repo_dir)
    if deps.get("external_services"):
        compose += generate_dependency_services(repo_dir)

    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)
