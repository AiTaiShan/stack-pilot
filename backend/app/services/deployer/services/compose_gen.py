"""compose_gen.py — Docker Compose 文件生成服务"""
import json
import os
import re
import logging
from typing import Dict, List, Optional, Any, Tuple

from app.services.scanner.dependency_detector import EXTERNAL_SERVICES

logger = logging.getLogger(__name__)


def _read_app_db_config(repo_dir: str, service_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    从应用配置文件中读取数据库密码和数据库名
    返回 (password, database_name)
    支持 application.yml, application-druid.yml, .env 等格式
    """
    config_files = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "target", ".mvn", "__pycache__"}]
        for f in files:
            if f in ("application.yml", "application.yaml", "application.properties",
                     "application-druid.yml", "application-prod.yml", ".env"):
                config_files.append(os.path.join(root, f))

    password = None
    database = None

    # MySQL 配置正则
    mysql_patterns = {
        "password": [
            r'password:\s*["\']?([^"\'\s]+)',
            r'MYSQL_PASSWORD[=:]\s*["\']?([^"\'\s]+)',
            r'MYSQL_ROOT_PASSWORD[=:]\s*["\']?([^"\'\s]+)',
        ],
        "database": [
            r'MYSQL_DATABASE[=:]\s*["\']?([^"\'\s]+)',
            r'mysql.*database[=:]\s*["\']?([^"\'\s]+)',
            r'jdbc:mysql://[^/]+/([^?\s"\']+)',  # JDBC URL: jdbc:mysql://host:port/DBNAME
        ]
    }

    # PostgreSQL 配置正则
    pg_patterns = {
        "password": [
            r'POSTGRES_PASSWORD[=:]\s*["\']?([^"\'\s]+)',
            r'postgresql.*password[=:]\s*["\']?([^"\'\s]+)',
        ],
        "database": [
            r'POSTGRES_DB[=:]\s*["\']?([^"\'\s]+)',
            r'jdbc:postgresql://[^/]+/([^?\s"\']+)',
        ]
    }

    patterns = mysql_patterns if service_name == "mysql" else pg_patterns

    for filepath in config_files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # 读取密码
            if not password:
                for pattern in patterns["password"]:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        p = matches[0].strip()
                        if p and p not in ("${...}", "${...}", "xxx", "your_password", "CHANGE_ME"):
                            password = p
                            break

            # 读取数据库名
            if not database:
                for pattern in patterns["database"]:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        db = matches[0].strip()
                        if db and db not in ("${...}", "${...}", "xxx", "your_db", "CHANGE_ME"):
                            database = db
                            break
        except Exception:
            continue

    return password, database


def generate_single_app_compose(repo_dir: str, repo_name: str, image_tag: str, deps: dict) -> None:
    """为单体应用生成包含依赖服务的 docker-compose.yml"""
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

    # 添加初始化命令 — 只有真正有迁移命令时才生成 db-init
    init_commands = db_init.get("init_commands", [])
    real_commands = [cmd for cmd in init_commands if not cmd.startswith("#") and "echo" not in cmd and "placeholder" not in cmd and "No migration" not in cmd]
    if real_commands:
        migration_tool = db_init.get("migration_tool", "")
        tool_images = {
            "alembic": "python:3.11-slim", "django": "python:3.11-slim",
            "flyway": "flyway/flyway:latest", "prisma": "node:18-alpine",
            "typeorm": "node:18-alpine", "knex": "node:18-alpine",
        }
        init_image = tool_images.get(migration_tool, "python:3.11-slim")

        shell_parts = ['echo "Waiting for database..."']
        for service_name in external_services:
            if service_name in EXTERNAL_SERVICES:
                service_info = EXTERNAL_SERVICES[service_name]
                if service_info.category == "database":
                    port = service_info.default_port
                    shell_parts.append(
                        f'for i in $(seq 1 30); do nc -z {service_name} {port} && break || sleep 2; done'
                    )
        shell_parts.append('echo "Database is ready"')
        for cmd in real_commands:
            shell_parts.append(f'echo "Running: {cmd}" && {cmd}')
        shell_parts.append('echo "Database initialization completed"')
        full_cmd = " && ".join(shell_parts)

        # 使用 YAML 序列格式避免引号嵌套问题
        esc_full_cmd = full_cmd.replace('\\"', '\\\\"')
        compose += f"""
  db-init:
    image: {init_image}
    command: ["sh", "-c", "{esc_full_cmd}"]
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
    compose += generate_dependency_services(repo_dir)

    logger.info("_generate_single_app_compose: services=%s, compose_preview=%s",
                [s for s in external_services], compose[:300])
    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)


def generate_dependency_services(repo_dir: str, app_services: list = None) -> str:
    """生成外部依赖服务的 docker-compose 配置"""
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

        # 添加环境变量 - 自动读取应用配置中的数据库密码和库名
        if service_info.env_vars:
            app_password, app_database = _read_app_db_config(repo_dir, service_name)
            compose += "    environment:\n"
            for key, value in service_info.env_vars.items():
                # 同步应用配置中的数据库密码
                if key in ("MYSQL_ROOT_PASSWORD", "POSTGRES_PASSWORD", "MONGO_INITDB_ROOT_PASSWORD", "ORACLE_PWD", "SA_PASSWORD"):
                    if app_password:
                        value = app_password
                        logger.info(f"Synced {key} from app config: {value[:3]}***")
                # 同步应用配置中的数据库名
                if key in ("MYSQL_DATABASE", "POSTGRES_DB", "MONGO_INITDB_DATABASE"):
                    if app_database:
                        value = app_database
                        logger.info(f"Synced {key} from app config: {value}")
                compose += f"      - {key}={value}\n"

        # 添加数据卷（数据库持久化 + SQL/seed 文件挂载）
        if service_info.category == "database":
            compose += f"    volumes:\n      - {service_name}_data:/var/lib/{service_name}\n"
            # 检测数据库类型 + SQL 文件，通用 mount 方案
            db_init = deps.get("database_init", {})
            schema_files = db_init.get("schema_files", [])
            seed_files = db_init.get("seed_files", [])
            all_files = schema_files + seed_files
            supported_db = ["mysql", "postgres", "mariadb"]
            if any(k in service_name.lower() for k in supported_db):
                idx = 1
                for sf in all_files:
                    abs_path = os.path.join(repo_dir, sf)
                    if os.path.exists(abs_path):
                        compose += f"      - {abs_path}:/docker-entrypoint-initdb.d/{idx:02d}-{os.path.basename(sf)}\n"
                        idx += 1

    # 添加数据库初始化服务（仅当有真实迁移工具命令时）
    db_init = deps.get("database_init", {})
    init_commands = db_init.get("init_commands", [])
    migration_tool = db_init.get("migration_tool", "")
    real_cmds = [c for c in init_commands
                 if not c.startswith("#") and c.strip()
                 and "echo" not in c and "placeholder" not in c]
    if migration_tool and real_cmds:
        compose += generate_db_init_service(repo_dir, deps, init_commands)

    # 添加卷声明
    db_services = [s for s in external_services if s in EXTERNAL_SERVICES and EXTERNAL_SERVICES[s].category == "database"]
    if db_services:
        compose += "\nvolumes:\n"
        for s in db_services:
            compose += f"  {s}_data:\n"

    return compose


def generate_db_init_service(repo_dir: str, deps: dict, init_commands: list) -> str:
    """生成数据库初始化服务 — 真正执行迁移命令"""
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
    real_commands = [cmd for cmd in init_commands
                    if not cmd.startswith("#") and cmd.strip()
                    and "echo" not in cmd and "placeholder" not in cmd]
    if not real_commands:
        return ""

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
        shell_parts.append(f'echo "Running: {cmd}" && {cmd}')
    shell_parts.append("echo 'Database initialization completed'")

    full_cmd = " && ".join(shell_parts)

    full_cmd_esc = full_cmd.replace('"', '\\"')
    compose = f"""
  db-init:
    image: {init_image}
    command: ["sh", "-c", "{full_cmd_esc}"]
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


def generate_multi_module_compose(repo_dir: str, services: list, images: dict) -> None:
    """生成多模块项目的 docker-compose.yml"""
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
    deps = load_deps_from_file(repo_dir)
    if deps.get("external_services"):
        compose += generate_dependency_services(repo_dir)

    logger.info("_generate_multi_module_compose: images=%s, services=%s, compose_preview=%s",
                list(images.keys()), [s["name"] for s in services], compose[:300])
    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)


def generate_microservices_compose(repo_dir: str, services: list, images: dict) -> None:
    """生成微服务项目的 docker-compose.yml"""
    compose = """version: '3.8'

services:
"""

    for service in services:
        name = service["name"]
        if name not in images:
            continue

        port = service.get("port", 8080)
        compose += f"""  {name}:
    image: {images[name]}
    ports:
      - "{port}:{port}"
"""
        # 推断服务间依赖
        deps = infer_service_deps(service, services)
        if deps:
            compose += "    depends_on:\n"
            for dep in deps:
                compose += f"      - {dep}\n"

        compose += "\n"

    # 添加外部依赖服务
    deps = load_deps_from_file(repo_dir)
    if deps.get("external_services"):
        compose += generate_dependency_services(repo_dir)

    logger.info("generate_microservices_compose: images=%s, services=%s, compose_preview=%s",
                list(images.keys()), [s["name"] for s in services], compose[:300])
    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)


def infer_service_deps(service: dict, all_services: list) -> list:
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


def load_deps_from_file(repo_dir: str) -> dict:
    """从 .stackpilot/dependencies.json 加载依赖信息"""
    config_path = os.path.join(repo_dir, ".stackpilot", "dependencies.json")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception:
        return {}
