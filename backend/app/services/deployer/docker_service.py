import os
import logging
import subprocess
from typing import Dict, List, Optional, Any

from app.core.error_handler import (
    AppError,
    ErrorCode,
    ErrorSeverity,
    handle_error,
    with_retry,
)

logger = logging.getLogger(__name__)


class DockerService:
    """Docker 镜像构建和推送服务（使用 subprocess 调用 docker CLI）"""

    def __init__(self, registry_url: str = ""):
        self.registry_url = registry_url

    @handle_error
    @with_retry(config_name="docker")
    def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: str = "Dockerfile",
        build_args: Optional[Dict[str, str]] = None,
    ) -> str:
        logger.info("Building Docker image: %s from %s", tag, path)

        if not os.path.exists(os.path.join(path, dockerfile)):
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message=f"Dockerfile not found at {os.path.join(path, dockerfile)}",
                severity=ErrorSeverity.HIGH,
            )

        cmd = ["docker", "build", "-t", tag, "-f", dockerfile]
        if build_args:
            for key, value in build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])
        cmd.append(".")

        logger.info("Docker build starting: tag=%s path=%s cmd=%s", tag, path, " ".join(cmd))
        build_start = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)

        try:
            build_env = {**os.environ, "DOCKER_BUILDKIT": "0"}
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=600,
                env=build_env,
            )
            build_end = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
            duration_ms = int((build_end - build_start).total_seconds() * 1000)

            if result.returncode != 0:
                logger.error("Docker build failed: tag=%s duration=%dms stderr=%s",
                             tag, duration_ms, result.stderr[:500])
                raise AppError(
                    code=ErrorCode.DOCKER_ERROR,
                    message=f"Docker build failed: {result.stderr[:300]}",
                    severity=ErrorSeverity.HIGH,
                    retryable=True,
                )
            logger.info("Docker build completed: tag=%s duration=%dms", tag, duration_ms)
            return tag
        except subprocess.TimeoutExpired:
            raise AppError(
                code=ErrorCode.TIMEOUT_ERROR,
                message="Docker build timeout (600s)",
                severity=ErrorSeverity.HIGH,
                retryable=True,
            )

    @handle_error
    @with_retry(config_name="docker")
    def push_image(self, image_tag: str, registry: Optional[str] = None) -> str:
        logger.info("Pushing Docker image: %s", image_tag)

        registry = registry or self.registry_url
        full_tag = f"{registry}/{image_tag}" if registry else image_tag

        try:
            if registry:
                result = subprocess.run(
                    ["docker", "tag", image_tag, full_tag],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode != 0:
                    raise AppError(
                        code=ErrorCode.DOCKER_ERROR,
                        message=f"Docker tag failed: {result.stderr}",
                        severity=ErrorSeverity.HIGH,
                    )

            result = subprocess.run(
                ["docker", "push", full_tag],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                raise AppError(
                    code=ErrorCode.DOCKER_ERROR,
                    message=f"Docker push failed: {result.stderr}",
                    severity=ErrorSeverity.HIGH,
                    retryable=True,
                )

            logger.info("Successfully pushed image: %s", full_tag)
            return full_tag
        except subprocess.TimeoutExpired:
            raise AppError(
                code=ErrorCode.TIMEOUT_ERROR,
                message="Docker push timeout (300s)",
                severity=ErrorSeverity.HIGH,
                retryable=True,
            )

    @handle_error
    def generate_dockerfile(self, project_info: Dict[str, Any], output_path: str) -> str:
        language = project_info.get("language", "unknown")
        framework = project_info.get("framework", "")
        start_cmd = project_info.get("start_cmd") or project_info.get("start_command")
        port = project_info.get("port", 8080)
        build_cmd = project_info.get("build_cmd") or project_info.get("build_command")
        version = project_info.get("version", "")  # 语言版本，如 "1.24.0"

        from app.services.scanner.detector import get_template
        gen_func = get_template(language)

        if gen_func:
            dockerfile_content = gen_func(port=port, build_cmd=build_cmd or "",
                                           start_cmd=start_cmd or "", framework=framework,
                                           version=version)
        else:
            # fallback 通用模板
            cmd = start_cmd or "echo 'Please configure your application start command'"
            dockerfile_content = f"""FROM ubuntu:22.04
WORKDIR /app
COPY . .
EXPOSE {port}
CMD ["sh", "-c", "{cmd}"]
"""

        os.makedirs(output_path, exist_ok=True)
        dockerfile_path = os.path.join(output_path, "Dockerfile")

        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)

        logger.info("Generated Dockerfile at %s for %s/%s", dockerfile_path, language, framework)
        return dockerfile_path
