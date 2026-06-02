"""deploy_step.py — 部署、验证、推送、配置步骤"""
import os
import subprocess
import time
import socket
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from app.models.deployment import Deployment
from app.core.error_handler import AppError, ErrorCode, ErrorSeverity

logger = logging.getLogger(__name__)





def _get_deploy_url_from_containers(repo_dir, repo_name):
    """通用方案：从运行容器获取应用访问地址"""
    import subprocess
    import re
    import json as _json

    # 1. 从 dependencies.json 获取基础设施端口（通用，非硬编码）
    infra_ports = set()
    deps_file = os.path.join(repo_dir, ".stackpilot", "dependencies.json")
    try:
        with open(deps_file) as f:
            deps = _json.load(f)
        for svc_name, svc_info in deps.get("service_details", {}).items():
            if svc_info.get("category") in ("database", "cache", "mq", "search", "storage"):
                infra_ports.add(svc_info.get("port", 0))
    except Exception:
        pass

    # 2. 从运行容器获取端口映射
    project_name = f"stackpilot-{repo_name}"
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={project_name}", "--format", "{{.Names}}:{{.Ports}}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            port_matches = re.findall(r'0\.0\.0\.0:(\d+)->', line)
            for port_str in port_matches:
                port = int(port_str)
                if port not in infra_ports:
                    return f"http://localhost:{port}"
    except Exception:
        pass
    return None



def step_push(db: Session, deployment_id: str, deployment: Deployment, docker_service, log_fn):
    """推送镜像到注册中心"""
    logger.info("_step_push: image_tag=%s, project_type=%s, config_keys=%s, config_images=%s",
                str(deployment.image_tag),
                getattr(deployment, '_project_type', ''),
                list((deployment.config or {}).keys())[:10],
                list(((deployment.config or {}).get("images", {}) or {}).keys()))
    if not deployment.image_tag:
        raise AppError(
            code=ErrorCode.DOCKER_ERROR,
            message="No image tag available for push",
            severity=ErrorSeverity.HIGH,
        )

    registry = (deployment.config or {}).get("registry", "")
    if not registry:
        log_fn(db, deployment_id, "info", "No registry configured, skipping push step")
        return
    docker_service.push_image(deployment.image_tag, registry)


def step_deploy(db: Session, deployment_id: str, deployment: Deployment, git_service, log_fn):
    """部署应用到目标平台"""
    platform = deployment.platform
    if platform == "k8s":
        _deploy_to_k8s(db, deployment, log_fn)
    elif platform == "coolify":
        _deploy_to_coolify(deployment, log_fn)
    elif platform == "local":
        _deploy_to_local(db, deployment, git_service, log_fn, deployment_id)
    else:
        raise AppError(
            code=ErrorCode.INVALID_PARAM,
            message=f"Unsupported platform: {platform}",
            severity=ErrorSeverity.HIGH,
        )


def _deploy_to_local(db: Session, deployment: Deployment, git_service, log_fn, deployment_id: str):
    """本地部署"""
    config = deployment.config or {}
    images = config.get("images", {})
    repo_dir = getattr(deployment, "_repo_dir", "") or config.get("_repo_dir") or os.path.join(
        git_service.temp_dir,
        deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
    )
    repo_name = os.path.basename(repo_dir.rstrip("/"))

    # 检测是否有外部依赖或是否为多服务项目
    has_deps = bool(config.get("dependencies", {}).get("external_services"))
    is_multi_service = config.get("type") in ("monorepo", "multi-module-java", "microservices") or config.get("compose")

    if is_multi_service or has_deps:
        _deploy_compose_local(db, deployment, repo_dir, repo_name, log_fn, deployment_id)
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
        log_fn(db, str(deployment.id), "info", f"Deployed locally at http://localhost:{port}")


def _deploy_compose_local(db: Session, deployment: Deployment, repo_dir: str, repo_name: str, log_fn, deployment_id: str):
    """使用 docker-compose 部署"""
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

    # 预拉取外部镜像（避免 up 时超时）
    log_fn(db, deployment_id, "info", "Pulling external images first...")
    try:
        subprocess.run(
            ["docker-compose", "-p", project_name, "-f", compose_file, "pull"],
            capture_output=True, text=True, timeout=600
        )
    except subprocess.TimeoutExpired:
        log_fn(db, deployment_id, "warning", "Image pull timed out, continuing with local images")

    # 启动新服务
    result = subprocess.run(
        ["docker-compose", "-p", project_name, "-f", compose_file, "up", "-d"],
        capture_output=True, text=True, timeout=600
    )

    # 检查容器是否实际在运行（不依赖 returncode，docker-compose 可能因变量警告返回非零）
    time.sleep(5)
    check = subprocess.run(
        ["docker-compose", "-p", project_name, "-f", compose_file, "ps", "-q"],
        capture_output=True, text=True, timeout=15
    )
    running = [c.strip() for c in check.stdout.strip().split('\n') if c.strip()]
    if not running:
        # 没有容器在运行才视为失败
        error_detail = result.stderr[:300] if result.stderr else "No containers started"
        raise AppError(
            code=ErrorCode.DOCKER_ERROR,
            message=f"Docker Compose deploy failed: {error_detail}",
            severity=ErrorSeverity.HIGH,
        )

    # 清理悬空资源
    subprocess.run(["docker", "container", "prune", "-f"], capture_output=True, timeout=30)
    subprocess.run(["docker", "volume", "prune", "-f"], capture_output=True, timeout=30)

    config = deployment.config or {}
    config = deployment.config or {}
    deploy_url = _get_deploy_url_from_containers(repo_dir, repo_name)
    if deploy_url:
        deployment.deploy_url = deploy_url
        db.commit()
        log_fn(db, str(deployment.id), "info", f"Deployed via docker-compose. Service: {deploy_url}")
    else:
        log_fn(db, str(deployment.id), "warning", "Deploy succeeded but no accessible service found")



def _deploy_to_k8s(db: Session, deployment: Deployment, log_fn):
    """部署到 Kubernetes"""
    config = deployment.config or {}
    namespace = config.get("namespace", "default")
    app_name = config.get("app_name", "stackpilot-app")
    port = config.get("port", 80)
    replicas = config.get("replicas", 1)
    env_vars = config.get("env_vars", {})
    host = config.get("host", "")
    resources = config.get("resources", {})

    k8s_service = None
    if not k8s_service:
        kubeconfig = config.get("kubeconfig")
        from app.services.deployer.k8s_service import K8sService
        k8s_service = K8sService(kubeconfig=kubeconfig)

    k8s_service.create_namespace(namespace)
    k8s_service.create_deployment(
        namespace=namespace,
        name=app_name,
        image=deployment.image_tag,
        replicas=replicas,
        port=port,
        env_vars=env_vars,
        resources=resources,
    )
    k8s_service.create_service(
        namespace=namespace,
        name=app_name,
        port=port,
        target_port=port,
    )

    if host:
        k8s_service.create_ingress(
            namespace=namespace,
            name=app_name,
            host=host,
            service_name=app_name,
            service_port=port,
            tls=config.get("tls", False),
        )
        deployment.deploy_url = f"https://{host}"


def _deploy_to_coolify(deployment: Deployment, log_fn):
    """部署到 Coolify"""
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


def step_configure(db: Session, deployment_id: str, deployment: Deployment, log_fn):
    """配置服务"""
    config = deployment.config or {}
    env_vars = config.get("env_vars", {})

    if deployment.platform == "k8s" and env_vars:
        log_fn(db, deployment_id, "info", f"Configured {len(env_vars)} environment variables")


def step_verify(db: Session, deployment_id: str, deployment: Deployment, log_fn):
    """验证部署结果"""
    if deployment.platform == "k8s":
        config = deployment.config or {}
        namespace = config.get("namespace", "default")
        app_name = config.get("app_name", "stackpilot-app")

        from app.services.deployer.k8s_service import K8sService
        k8s_service = K8sService(kubeconfig=config.get("kubeconfig"))
        status = k8s_service.wait_for_deployment(
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
        _verify_local_deployment(db, deployment, log_fn)
    log_fn(db, deployment_id, "info", "Deployment verified successfully")


def _verify_local_deployment(db: Session, deployment: Deployment, log_fn):
    """验证本地部署：容器状态 + 端口监听 + HTTP 可达"""
    config = deployment.config or {}
    repo_name = deployment.git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
    deployment_id = str(deployment.id)

    log_fn(db, deployment_id, "info", "Verifying: waiting for containers to start...")
    time.sleep(5)

    is_compose = config.get("compose", False)

    if is_compose:
        project_name = f"stackpilot-{repo_name}"
        repo_dir = config.get('_repo_dir', os.path.join('/tmp/stackpilot_repos', repo_name))
        compose_file = os.path.join(repo_dir, 'docker-compose.yml')
        result = subprocess.run(
            ["docker-compose", "-p", project_name, "-f", compose_file, "ps", "-q"],
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
                raise AppError(
                    code=ErrorCode.DOCKER_ERROR,
                    message=f"Container {cid[:12]} status: {status}",
                    severity=ErrorSeverity.HIGH,
                )
    else:
        app_name = config.get("app_name", "stackpilot-app")
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={app_name}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=15
        )
        if app_name not in result.stdout:
            raise AppError(
                code=ErrorCode.DOCKER_ERROR,
                message=f"Container '{app_name}' is not running",
                severity=ErrorSeverity.HIGH,
            )

    # 检查端口监听
    deploy_url = deployment.deploy_url or ""
    if deploy_url and "localhost:" in deploy_url:
        try:
            port = int(deploy_url.split(":")[-1].split("/")[0])
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            if result != 0:
                log_fn(db, deployment_id, "warning", f"Port {port} is not listening")
        except Exception as e:
            log_fn(db, deployment_id, "warning", f"Port check failed: {e}")


def get_deployment_status(deployment_id: str, db) -> Optional[Dict[str, Any]]:
    from app.models.deployment import Deployment
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
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


def get_deployment_logs(deployment_id: str, db) -> list:
    from app.models.deployment import DeploymentLog
    logs = (
        db.query(DeploymentLog)
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
