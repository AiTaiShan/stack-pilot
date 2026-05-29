"""review_step.py — 生成部署文件 + AI 审核步骤"""
import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from app.models.deployment import Deployment

logger = logging.getLogger(__name__)


def execute(db: Session, deployment_id: str, deployment: Deployment,
            git_service, docker_service, log_fn) -> None:
    """
    生成部署文件 + AI 审核
    1. 保存依赖信息
    2. 生成 Dockerfile(s)
    3. AI 审核
    4. 生成 docker-compose.yml
    5. 适配配置文件
    6. 提取环境变量
    """
    from app.services.deployer.services.compose_gen import (
        generate_multi_module_compose,
        generate_single_app_compose,
        load_deps_from_file,
        generate_dependency_services,
    )

    log_fn(db, deployment_id, "info", "Starting generate_review step")

    # 优先使用 Python属性（不会因 db.commit() expire），再读 config
    project_type = getattr(deployment, '_project_type', '') or (deployment.config or {}).get("type", "")
    repo_dir = getattr(deployment, '_repo_dir', '') or os.path.join(
        git_service.temp_dir,
        deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
    )
    project_info = dict(getattr(deployment, '_project_info', deployment.config or {}))
    deps = project_info.get("dependencies", {})

    # 如果 config 中没有 dependencies，尝试从文件加载
    if not deps:
        deps = load_deps_from_file(repo_dir)
        if deps:
            project_info["dependencies"] = deps

    log_fn(db, deployment_id, "info", f"Project type: {project_type}, repo_dir: {repo_dir}")

    # 1. 保存依赖信息到文件
    if deps.get("external_services"):
        deps_dir = os.path.join(repo_dir, ".stackpilot")
        os.makedirs(deps_dir, exist_ok=True)
        with open(os.path.join(deps_dir, "dependencies.json"), "w") as f:
            json.dump(deps, f)
        log_fn(db, deployment_id, "info",
               f"External services: {', '.join(deps['external_services'])}")

    # 2. 生成部署文件
    log_fn(db, deployment_id, "info", f"Generating deployment files for type: {project_type}")
    if project_type in ("multi-module-java", "multi-module-java-with-frontend"):
        _generate_multi_module_files(repo_dir, project_info)
        if project_type == "multi-module-java-with-frontend":
            _generate_frontend_dockerfile(repo_dir, project_info)
    elif project_type in ("microservices", "microservices-with-frontend"):
        _generate_microservices_files(repo_dir, project_info)
        if project_type == "microservices-with-frontend":
            _generate_frontend_dockerfile(repo_dir, project_info)
    elif project_type == "monorepo":
        _generate_monorepo_files(repo_dir, project_info)
    else:
        if not os.path.exists(os.path.join(repo_dir, "Dockerfile")):
            docker_service.generate_dockerfile(project_info, repo_dir)
        else:
            log_fn(db, deployment_id, "info", "Dockerfile already exists, skipping generation")
    log_fn(db, deployment_id, "info", "Deployment files generated")

    # 3. AI 审核 Dockerfile(s)
    log_fn(db, deployment_id, "info", "Starting AI review of Dockerfiles")
    _ai_review_project(db, deployment_id, repo_dir, deployment, log_fn)
    log_fn(db, deployment_id, "info", "AI review of project completed")

    # 4. 生成 docker-compose.yml
    log_fn(db, deployment_id, "info", "Generating docker-compose.yml")
    if project_type not in (
        "multi-module-java", "multi-module-java-with-frontend",
        "microservices", "microservices-with-frontend", "monorepo"
    ):
        repo_name = os.path.basename(repo_dir.rstrip("/"))
        if deps.get("external_services"):
            generate_single_app_compose(repo_dir, repo_name, f"stackpilot/{repo_name}:latest", deps)
    log_fn(db, deployment_id, "info", "docker-compose.yml generation completed")

    # 5. AI 审核 docker-compose.yml
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if os.path.exists(compose_path):
        log_fn(db, deployment_id, "info", "Starting AI review of docker-compose.yml")
        _ai_review_compose(db, deployment_id, repo_dir, project_info, deps, log_fn)
        log_fn(db, deployment_id, "info", "AI review of docker-compose.yml completed")

    # 6. 适配配置文件
    log_fn(db, deployment_id, "info", "Adapting config files for Docker")
    if project_info.get("config_adaptation_needed") or deps.get("external_services"):
        _adapt_config_for_docker(repo_dir, deps)
    log_fn(db, deployment_id, "info", "Config adaptation completed")

    # 7. 提取环境变量
    log_fn(db, deployment_id, "info", "Extracting environment variables")
    pending = _generate_service_env_vars(repo_dir, "spring")
    if not pending:
        pending = _generate_service_env_vars(repo_dir, "generic")
    logger.info("_step_generate_review_END: deployment.config_keys=%s", list((deployment.config or {}).keys()))
    dc = dict(deployment.config or {})
    dc["pending_env_vars"] = pending
    deployment.config = dc
    db.commit()
    if pending:
        log_fn(db, deployment_id, "info", f"Saved {len(pending)} env vars for user review")
    log_fn(db, deployment_id, "info", "generate_review step completed")


def _generate_multi_module_files(repo_dir: str, project_info: dict):
    """生成多模块 Java 项目的 Dockerfile（使用通配符模式）"""
    logger.info("_build_multi_module_files: project_info_keys=%s, has_services=%s, project_info_type=%s",
                list(project_info.keys()), "services" in project_info, type(project_info).__name__)
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


def _generate_microservices_files(repo_dir: str, project_info: dict):
    """为微服务项目的每个服务生成 Dockerfile"""
    services = project_info.get("services", [])
    for service in services:
        service_dir = os.path.join(repo_dir, service["dir"])
        dockerfile_path = os.path.join(service_dir, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            docker_service = None  # 将在调用时传入
            # 此处需要 docker_service 参数，需要重构
            pass


def _generate_monorepo_files(repo_dir: str, project_info: dict):
    """为 monorepo 项目的前端和后端生成 Dockerfile"""
    frontend = project_info.get("frontend", {})
    backend = project_info.get("backend", {})
    if backend:
        backend_dir = os.path.join(repo_dir, backend.get("dir", "backend"))
        docker_service = None  # 将在调用时传入
        # docker_service.generate_dockerfile(backend, backend_dir)
    if frontend:
        frontend_dir = os.path.join(repo_dir, frontend.get("dir", "frontend"))
        # docker_service.generate_dockerfile(frontend, frontend_dir)


def _generate_frontend_dockerfile(repo_dir: str, project_info: dict):
    """为组合项目生成前端 Dockerfile"""
    frontend_info = project_info.get("frontend", {})
    frontend_dir_name = frontend_info.get("dir", "frontend")
    frontend_dir = os.path.join(repo_dir, frontend_dir_name)
    if os.path.isdir(frontend_dir):
        docker_service = None  # 将在调用时传入
        # docker_service.generate_dockerfile(frontend_info, frontend_dir)


def _ai_review_project(db: Session, deployment_id: str, repo_dir: str,
                        deployment: Deployment, log_fn):
    """
    全项目 AI 审核 — 一次性把完整上下文发给 AI，让 AI 通过工具自行决定：
    - 哪些模块是可执行服务
    - 生成/优化 Dockerfile
    - 修改配置文件中 localhost 到 Docker 服务名的连接地址
    - 生成 docker-compose.yml
    """
    import os, json

    # 1. 收集完整项目信息
    project_info = dict(deployment.config or {})
    detected = project_info.get("type", "") if hasattr(deployment, '_project_type') else getattr(deployment, '_project_type', '')
    services = project_info.get("services", [])
    deps = project_info.get("dependencies", {}) or {}
    external_services = deps.get("external_services", [])

    # 2. 收集结构树、配置等关键文件
    structure = _collect_project_structure(repo_dir, max_depth=4)

    config_files = {}
    skip_config_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__", ".stackpilot", "dist", "build"}
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in skip_config_dirs]
        for f in files:
            if f in ("pom.xml", "build.gradle", "build.gradle.kts"):
                path = os.path.join(root, f)
                with open(path) as fh:
                    config_files[os.path.relpath(path, repo_dir)] = fh.read()
            elif f in ("application.yml", "application.yaml", "application.properties",
                       "application-druid.yml", "application-dev.yml", "bootstrap.yml"):
                path = os.path.join(root, f)
                try:
                    with open(path) as fh:
                        config_files[os.path.relpath(path, repo_dir)] = fh.read()
                except Exception:
                    pass

    # 3. 调用 AI 进行全面审核
    scan_report = {
        "project_type": project_info.get("type", "single"),
        "language": project_info.get("language", "unknown"),
        "framework": project_info.get("framework", ""),
        "project_structure": structure,
        "config_files": config_files,
        "services": services,
        "external_services": external_services,
    }

    ai_start = datetime.now(timezone.utc)
    log_fn(db, deployment_id, "info", "Starting full project AI review with tools...")

    try:
        from app.services.ai.ai_service import get_ai_service
        ai_service_instance = get_ai_service()

        # 调用 AI 服务进行全项目审核
        result = ai_service_instance.review_project(repo_dir, scan_report)
        ai_end = datetime.now(timezone.utc)
        ai_duration_ms = int((ai_end - ai_start).total_seconds() * 1000)

        executable_services = result.get("executable_services", [])
        modified_files = result.get("modified_files", [])
        compose_generated = result.get("compose_generated", False)
        summary = result.get("summary", "")

        log_fn(db, deployment_id, "info",
               f"AI review completed ({ai_duration_ms}ms): "
               f"{len(executable_services)} executable, {len(modified_files)} files modified, "
               f"compose={'yes' if compose_generated else 'no'}",
               details={
                   "event": "ai_review",
                   "type": "full_project",
                   "duration_ms": ai_duration_ms,
                   "executable_services": executable_services,
                   "modified_files": modified_files,
                   "compose_generated": compose_generated,
                   "summary": summary,
               })

        # 保存审核结果到 config
        config = dict(deployment.config or {})
        config["_ai_review_result"] = {
            "executable_services": executable_services,
            "modified_files": modified_files,
            "compose_generated": compose_generated,
        }
        deployment.config = config
        db.commit()

        return result

    except Exception as e:
        ai_end = datetime.now(timezone.utc)
        ai_duration_ms = int((ai_end - ai_start).total_seconds() * 1000)
        log_fn(db, deployment_id, "warning", f"AI review failed (continuing): {e}",
               details={"event": "ai_review", "type": "full_project",
                        "error": str(e), "duration_ms": ai_duration_ms})
        return {"executable_services": [], "modified_files": [], "compose_generated": False}


def _ai_review_compose(db: Session, deployment_id: str, repo_dir: str,
                        project_info: dict, deps_info: dict, log_fn):
    """AI 审核 docker-compose.yml，注入完整扫描上下文"""
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if not os.path.exists(compose_path):
        return

    log_fn(db, deployment_id, "info", "AI reviewing docker-compose.yml...")

    try:
        with open(compose_path) as f:
            compose_content = f.read()

        enhanced_deps = dict(deps_info) if deps_info else {}
        enhanced_deps["project_type"] = project_info.get("type", "single")
        enhanced_deps["language"] = project_info.get("language", "unknown")
        enhanced_deps["framework"] = project_info.get("framework", "unknown")
        from app.services.ai.ai_service import get_ai_service
        ai_service = get_ai_service()
        result = ai_service.review_docker_compose(compose_content, project_info, enhanced_deps)

        if result.get("skipped"):
            log_fn(db, deployment_id, "warning",
                   f"AI compose review skipped: {result.get('reason', 'unknown')}")
        elif result.get("approved"):
            log_fn(db, deployment_id, "info", "AI approved docker-compose.yml")
        else:
            log_fn(db, deployment_id, "warning",
                   f"AI modified compose: {result.get('response', '')[:200]}")

            # 如果 AI 修改了文件，重新读取
            if result.get("modifications"):
                with open(compose_path) as f:
                    new_content = f.read()
                if new_content != compose_content:
                    log_fn(db, deployment_id, "info", "docker-compose.yml updated by AI")

    except Exception as e:
        log_fn(db, deployment_id, "warning", f"AI compose review failed (continuing): {e}")


def _adapt_config_for_docker(repo_dir: str, deps: dict):
    """将项目配置文件中的 localhost 替换为 Docker 服务名，修正端口映射"""
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


def _generate_service_env_vars(repo_dir: str, style: str) -> list:
    """扫描项目配置文件，提取需要用户填写的环境变量占位符"""
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


def _collect_project_structure(repo_dir: str, max_depth: int = 3) -> str:
    """收集项目结构摘要，用于 LLM 分析"""
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
