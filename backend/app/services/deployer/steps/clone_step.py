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

    # 3. 检测项目类型
    detect_start = datetime.now(timezone.utc)
    detected = _detect_project_type(repo_dir, deployment, db, deployment_id, log_fn)
    deps = detect_project_dependencies(repo_dir)
    detected["dependencies"] = deps
    detect_duration_ms = int((datetime.now(timezone.utc) - detect_start).total_seconds() * 1000)

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
    # 1. 规则初筛
    detected = _rule_based_detect(repo_dir)

    # 2. LLM 审核
    detected = _llm_review_detection(repo_dir, detected, db, deployment_id, log_fn)

    return detected


def _rule_based_detect(repo_dir: str) -> dict:
    """原有规则检测逻辑"""
    # 1. 检测是否为多模块 Java 项目（Spring Cloud）
    multi_module = _detect_multi_module_java(repo_dir)
    if multi_module:
        return multi_module

    # 2. 检测是否为通用微服务项目（任何语言）
    microservices = _detect_microservices(repo_dir)
    if microservices:
        return microservices

    # 3. 检测是否为 monorepo（前后端分离）
    monorepo = _detect_monorepo(repo_dir)
    if monorepo:
        return monorepo

    # 4. 单项目
    return _detect_single_project(repo_dir)


def _llm_review_detection(repo_dir: str, detected: dict, db: Session, deployment_id: str, log_fn) -> dict:
    """调用 LLM 审核项目类型检测结果，修正错误并补充缺失信息"""
    from app.services.ai.ai_service import get_ai_service
    import re

    structure = _collect_project_structure(repo_dir)

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
                frontend_info = _detect_single_project(frontend_path)
                frontend_info["dir"] = review["frontend_dir"]
                detected["frontend"] = frontend_info
                # 升级类型
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
                    svc["type"] = ai_svc["type"]
                    corrected = True
            if corrected:
                logger.info("Services list corrected based on AI review: %s",
                            [(s["name"], s["type"]) for s in detected.get("services", [])])

    except Exception as e:
        logger.warning("LLM detection review failed, using rule-based result: %s", e)

    return detected


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


def _detect_microservices(repo_dir: str) -> dict:
    """检测通用微服务项目（任何语言）"""
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
            service_info = _detect_service_in_dir(item_path, item)
            if service_info:
                service_info["dir"] = f"{base_dir}/{item}"
                services.append(service_info)

        if services:
            break

    # 也检查根目录下的服务目录
    if not services:
        for item in sorted(os.listdir(repo_dir)):
            if item.startswith(".") or item in ["docs", "test", "tests", "scripts", "deploy", "k8s", "kubernetes"]:
                continue
            item_path = os.path.join(repo_dir, item)
            if not os.path.isdir(item_path):
                continue

            # 检查是否以 -service 或 _service 结尾
            if item.endswith("-service") or item.endswith("_service") or item.endswith("-api") or item.endswith("_api"):
                service_info = _detect_service_in_dir(item_path, item)
                if service_info:
                    service_info["dir"] = item
                    services.append(service_info)

    if len(services) >= 2:  # 至少2个服务才算微服务项目
        return {
            "type": "microservices",
            "services": services
        }

    return None


def _detect_service_in_dir(dir_path: str, name: str) -> dict:
    """检测目录是否为独立服务"""
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
                    port_match = re.search(r'(?:PORT|port|server\.port)\s*[=:]\s*(\d+)', content)
                    if port_match:
                        service["port"] = int(port_match.group(1))
                        break
            except Exception:
                pass

    return service


def _detect_multi_module_java(repo_dir: str) -> dict:
    """检测多模块 Java 项目（Maven/Gradle）"""
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
            module_info = _detect_java_module(module_dir, module_name)
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


def _detect_java_module(module_dir: str, module_name: str) -> dict:
    """检测 Java 子模块类型"""
    has_pom = os.path.exists(os.path.join(module_dir, "pom.xml"))
    has_src = os.path.isdir(os.path.join(module_dir, "src"))

    if not (has_pom and has_src):
        return None

    # 检测端口
    port = 8080
    for config_file in ["application.yml", "application.yaml", "application.properties"]:
        config_path = os.path.join(module_dir, "src", "main", "resources", config_file)
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    content = f.read()
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


def _detect_monorepo(repo_dir: str) -> dict:
    """检测 monorepo 项目结构"""
    common_frontend_dirs = ["frontend", "client", "web", "ui", "app"]
    common_backend_dirs = ["backend", "server", "api", "services"]

    frontend_dir = None
    backend_dir = None

    for d in common_frontend_dirs:
        path = os.path.join(repo_dir, d)
        if os.path.isdir(path):
            if any(os.path.exists(os.path.join(path, f)) for f in ["package.json", "index.html"]):
                frontend_dir = d
                break

    for d in common_backend_dirs:
        path = os.path.join(repo_dir, d)
        if os.path.isdir(path):
            if any(os.path.exists(os.path.join(path, f)) for f in [
                "requirements.txt", "pom.xml", "go.mod", "main.py", "app.py",
                "package.json", "build.gradle"
            ]):
                backend_dir = d
                break

    if frontend_dir and backend_dir:
        # 检测各子项目类型
        frontend_info = _detect_single_project(os.path.join(repo_dir, frontend_dir))
        backend_info = _detect_single_project(os.path.join(repo_dir, backend_dir))

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


def _detect_single_project(repo_dir: str) -> dict:
    """检测单个项目类型"""
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


def _cleanup_old_images(db: Session, deployment_id: str, repo_name: str, git_service: GitService, log_fn):
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