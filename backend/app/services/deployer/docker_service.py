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
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=600,
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
        start_cmd = project_info.get("start_cmd")
        port = project_info.get("port", 8080)

        # 从 lock 文件检测包管理器
        if "pkg_manager" not in project_info:
            if os.path.exists(os.path.join(output_path, "pnpm-lock.yaml")):
                project_info["pkg_manager"] = "pnpm"
            elif os.path.exists(os.path.join(output_path, "yarn.lock")):
                project_info["pkg_manager"] = "yarn"
            else:
                project_info["pkg_manager"] = "npm"

        dockerfile_content = self._get_dockerfile_template(language, framework, start_cmd, port, project_info)

        os.makedirs(output_path, exist_ok=True)
        dockerfile_path = os.path.join(output_path, "Dockerfile")

        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)

        logger.info("Generated Dockerfile at %s for %s/%s", dockerfile_path, language, framework)
        return dockerfile_path

    def _get_dockerfile_template(self, language: str, framework: str, start_cmd: str = None,
                                  port: int = 8080, project_info: dict = None) -> str:
        language = language.lower()
        framework = framework.lower()
        project_info = project_info or {}

        if language in ("javascript", "typescript", "node", "js", "ts"):
            pkg_manager = project_info.get("pkg_manager", "npm")
            return self._node_template(framework, pkg_manager)
        elif language in ("python", "py"):
            return self._python_template(framework, start_cmd)
        elif language in ("go", "golang"):
            return self._go_template()
        elif language in ("java",):
            java_version = project_info.get("java_version", 17)
            return self._java_template(framework, java_version)
        else:
            return self._generic_template(start_cmd, port)

    def _node_template(self, framework: str, pkg_manager: str = "npm") -> str:
        install_cmds = {
            "pnpm": "RUN npm install -g pnpm && pnpm install --registry=https://registry.npmmirror.com",
            "yarn": "RUN yarn install --registry=https://registry.npmmirror.com",
            "npm": "RUN npm install --registry=https://registry.npmmirror.com",
        }
        build_cmds = {"pnpm": "RUN pnpm run build", "yarn": "RUN yarn build", "npm": "RUN npm run build"}
        start_cmds = {"pnpm": 'CMD ["pnpm", "start"]', "yarn": 'CMD ["yarn", "start"]', "npm": 'CMD ["npm", "start"]'}

        install = install_cmds.get(pkg_manager, install_cmds["npm"])
        build = build_cmds.get(pkg_manager, build_cmds["npm"])
        start = start_cmds.get(pkg_manager, start_cmds["npm"])

        # 需要复制的 lock 文件
        lock_files = {"pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock", "npm": "package-lock.json"}

        if framework in ("next", "nextjs"):
            return f"""FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
{install}
COPY . .
{build}

FROM node:18-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/public ./public
ENV NODE_ENV=production
EXPOSE 3000
{start}
"""
        return f"""FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
{install}
COPY . .
{build}
RUN if [ -d dist ]; then cp -r dist /output; elif [ -d build ]; then cp -r build /output; else mkdir /output && echo "<h1>Build output not found</h1>" > /output/index.html; fi

FROM nginx:alpine
COPY --from=builder /output /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
"""

    def _python_template(self, framework: str, start_cmd: str = None) -> str:
        if framework in ("django",):
            return """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
"""
        if start_cmd:
            return f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "{start_cmd}"]
"""
        return """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

    def _go_template(self) -> str:
        return """FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/main .
EXPOSE 8080
CMD ["./main"]
"""

    def _java_template(self, framework: str, java_version: int = 17) -> str:
        if framework in ("spring", "springboot", "spring-boot"):
            return f"""FROM eclipse-temurin:{java_version}-jdk-alpine AS builder
WORKDIR /app
COPY . .
RUN ./mvnw package -DskipTests

FROM eclipse-temurin:{java_version}-jre-alpine
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
"""
        return f"""FROM eclipse-temurin:{java_version}-jdk-alpine
WORKDIR /app
COPY . .
RUN javac -d out src/**/*.java
EXPOSE 8080
CMD ["java", "-cp", "out", "Main"]
"""

    def _generic_template(self, start_cmd: str = None, port: int = 8080) -> str:
        cmd = start_cmd or "echo 'Please configure your application start command'"
        return f"""FROM ubuntu:22.04
WORKDIR /app
COPY . .
EXPOSE {port}
CMD ["sh", "-c", "{cmd}"]
"""
