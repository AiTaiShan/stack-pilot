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

    # MySQL 配置正则 - 只匹配同行的值（不跨行）
    mysql_patterns = {
        "password": [
            r'password:\s*["\']?([^"\'\s\n#]+)',  # 排除换行和注释符号
            r'MYSQL_PASSWORD[=:]\s*["\']?([^"\'\s\n#]+)',
            r'MYSQL_ROOT_PASSWORD[=:]\s*["\']?([^"\'\s\n#]+)',
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


def generate_dependency_services(repo_dir: str, app_services: list = None, service_versions: dict = None) -> str:
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

    # 使用检测到的版本（如果有）
    if service_versions is None:
        service_versions = {}
    compose = ""

    for service_name in external_services:
        if service_name not in EXTERNAL_SERVICES:
            continue

        service_info = EXTERNAL_SERVICES[service_name]
        if not service_info.image:  # 跳过无镜像的服务（如 sqlite）
            continue

        # 使用检测到的版本覆盖默认版本
        image = service_versions.get(service_name, service_info.image)
        port = service_info.default_port

        compose += f"""
  {service_name}:
    image: {image}
    ports:
      - "{port}:{port}"
"""

        # 添加健康检查（数据库类服务）
        healthcheck_cmd = _get_healthcheck_cmd(service_name)
        if healthcheck_cmd:
            compose += f"""    healthcheck:
      test: {healthcheck_cmd}
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 40s
"""

        # 添加启动命令（minio 等需要指定 command）
        startup_cmd = _get_startup_cmd(service_name)
        if startup_cmd:
            compose += f"""    command: {startup_cmd}
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


def generate_multi_module_compose(repo_dir: str, services: list, images: dict, service_versions: dict = None) -> None:
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
        # 防御性检查：跳过 common/library 类型，这些不应该作为独立容器运行
        if service.get("type") in ("common", "library"):
            logger.info("Skipping common/library service: %s (type=%s)", name, service.get("type"))
            continue

        # 仅 gateway / 前端对外暴露端口，内部服务不暴露
        svc_type = service.get("type", "service")
        lang = service.get("language", "")
        # 按 type 或名称中包含 gateway/registry 匹配
        expose = (svc_type in ("gateway", "registry")
                  or "gateway" in name.lower()
                  or "registry" in name.lower()
                  or lang == "node"
                  or name.endswith("-ui") or name.endswith("-web"))

        compose += f"""  {name}:
    image: {images[name]}
"""
        if expose:
            compose += f'    ports:\n      - "{service["port"]}:{service["port"]}"\n'
        compose += "    restart: unless-stopped\n"
        # Java 服务添加环境变量，覆盖 localhost -> Docker 服务名
        if lang == "java":
            env_vars = []
            if "redis" in ext_services:
                env_vars.append("SPRING_REDIS_HOST=redis")
            if "mysql" in ext_services:
                # 从 dependencies.json 读取数据库名
                db_name = ext_deps.get("service_details", {}).get("mysql", {}).get("env_vars", {}).get("MYSQL_DATABASE", "app")
                env_vars.append(f"SPRING_DATASOURCE_URL=jdbc:mysql://mysql:3306/{db_name}?useSSL=false&serverTimezone=Asia%2F8&characterEncoding=utf8&allowPublicKeyRetrieval=true")
            if env_vars:
                compose += "    environment:\n"
                for ev in env_vars:
                    compose += f"      - {ev}\n"


        # 加载外部依赖，构建 depends_on（含 registry/config + 数据库 condition）
        load_deps = load_deps_from_file(repo_dir) or {}
        ext_services = load_deps.get("external_services", [])
        db_services = [s for s in ext_services
                       if s in EXTERNAL_SERVICES and EXTERNAL_SERVICES[s].category == "database"]

        deps = []
        if service["type"] == "service":
            for s in services:
                if s["type"] in ("registry", "config") and s["name"] in images:
                    deps.append(("normal", s["name"]))
        elif service["type"] == "gateway":
            for s in services:
                if s["type"] == "registry" and s["name"] in images:
                    deps.append(("normal", s["name"]))

        for db in db_services:
            deps.append(("db", db))

        if deps:
            compose += "    depends_on:\n"
            for dtype, dname in deps:
                if dtype == "db":
                    compose += f"      {dname}:\n"
                    compose += f"        condition: service_healthy\n"
                else:
                    compose += f"      - {dname}\n"

        compose += "\n"

    # 添加外部依赖服务
    deps = load_deps_from_file(repo_dir)
    if deps.get("external_services"):
        compose += generate_dependency_services(repo_dir, service_versions=service_versions)

    logger.info("_generate_multi_module_compose: images=%s, services=%s, compose_preview=%s",
                list(images.keys()), [s["name"] for s in services], compose[:300])
    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)


def generate_microservices_compose(repo_dir: str, services: list, images: dict,
                                   frontend_image: str = None, frontend_info: dict = None) -> None:
    """生成微服务项目的 docker-compose.yml"""
    compose = """version: '3.8'

services:
"""

    ext_deps = load_deps_from_file(repo_dir) or {}
    ext_services = ext_deps.get("external_services", [])
    db_services = [s for s in ext_services
                   if s in EXTERNAL_SERVICES and EXTERNAL_SERVICES[s].category == "database"]

    # 如果有前端镜像，先添加前端服务
    if frontend_image and frontend_info:
        frontend_port = frontend_info.get("port", 3000)
        frontend_name = frontend_info.get("name", "frontend")

        # 动态查找 gateway 服务名
        # 优先按 type 查找，再按名称中包含 gateway 回退
        gateway_name = "gateway"
        for svc in services:
            if svc.get("type") == "gateway":
                gateway_name = svc["name"]
                break
        else:
            # 回退：按名称中包含 gateway 查找
            for svc in services:
                if "gateway" in svc.get("name", "").lower():
                    gateway_name = svc["name"]
                    break

        compose += f"""  {frontend_name}:
    image: {frontend_image}
    ports:
      - "{frontend_port}:{frontend_port}"
    restart: unless-stopped
    depends_on:
      - {gateway_name}

"""

    for service in services:
        name = service["name"]
        if name not in images:
            continue
        # 防御性检查：跳过 common/library 类型，这些不应该作为独立容器运行
        if service.get("type") in ("common", "library"):
            logger.info("Skipping common/library service: %s (type=%s)", name, service.get("type"))
            continue
        # 如果已经有 frontend_image，跳过 services 列表中的前端服务（语言为 node 的服务）
        if frontend_image and service.get("language") == "node":
            logger.info("Skipping frontend service from services list (already added via frontend_image): %s", name)
            continue

        port = service.get("port", 8080)
        svc_type = service.get("type", "service")
        lang = service.get("language", "")

        compose += "  " + name + ":\n"
        compose += "    image: " + images[name] + "\n"

        # 仅 gateway / 前端对外暴露端口，内部服务不暴露
        expose = (svc_type in ("gateway", "registry")
                  or "gateway" in name.lower()
                  or "registry" in name.lower()
                  or lang == "node"
                  or name.endswith("-ui") or name.endswith("-web"))
        if expose:
            compose += '    ports:\n      - "' + str(port) + ':' + str(port) + '"\n'

        compose += "    restart: unless-stopped\n"
        # Java 服务添加环境变量，覆盖 localhost -> Docker 服务名
        if lang == "java":
            env_vars = []
            if "redis" in ext_services:
                env_vars.append("SPRING_REDIS_HOST=redis")
            if "mysql" in ext_services:
                db_name = ext_deps.get("service_details", {}).get("mysql", {}).get("env_vars", {}).get("MYSQL_DATABASE", "app")
                env_vars.append(f"SPRING_DATASOURCE_URL=jdbc:mysql://mysql:3306/{db_name}?useSSL=false&serverTimezone=Asia%2F8&characterEncoding=utf8&allowPublicKeyRetrieval=true")
            if env_vars:
                compose += "    environment:\n"
                for ev in env_vars:
                    compose += f"      - {ev}\n"

        # depends_on
        depends = []
        for db in db_services:
            depends.append(("db", db))
        for s in services:
            if s["name"] == name or s["name"] not in images:
                continue
            sn = s["name"].lower()
            if svc_type == "gateway" and ("registry" in sn or "nacos" in sn):
                depends.append(("normal", s["name"]))
            elif svc_type == "service" and ("registry" in sn or "nacos" in sn or "config" in sn):
                depends.append(("normal", s["name"]))

        if depends:
            compose += "    depends_on:\n"
            for dtype, dname in depends:
                if dtype == "db":
                    compose += "      " + dname + ":\n"
                    compose += "        condition: service_healthy\n"
                else:
                    compose += "      - " + dname + "\n"

        compose += "\n"

    if ext_services:
        compose += generate_dependency_services(repo_dir)

    logger.info("generate_microservices_compose: images=%s, services=%s, frontend=%s, compose_preview=%s",
                list(images.keys()), [s["name"] for s in services], frontend_image, compose[:300])
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


def _get_healthcheck_cmd(service_name: str) -> Optional[str]:
    """获取数据库/中间件的健康检查命令"""
    checks = {
        # 数据库
        "mysql": ["CMD-SHELL", "mysqladmin ping -uroot -p${MYSQL_ROOT_PASSWORD} --silent"],
        "mariadb": ["CMD-SHELL", "mysqladmin ping -uroot -p${MYSQL_ROOT_PASSWORD} --silent"],
        "postgresql": ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-app}"],
        "postgres": ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"],
        "mongodb": ["CMD-SHELL", "mongosh --quiet --eval 'db.adminCommand(\"ping\")' 2>/dev/null || mongo --quiet --eval 'db.adminCommand(\"ping\")'"],
        "mongo": ["CMD-SHELL", "mongosh --quiet --eval 'db.adminCommand(\"ping\")' 2>/dev/null || mongo --quiet --eval 'db.adminCommand(\"ping\")'"],
        "oracle": ["CMD-SHELL", "sqlplus -L SYSTEM/${ORACLE_PWD:-oracle} @localhost:1521/XE 'SELECT 1 FROM DUAL;' 2>&1 | grep -q '1'"],
        "sqlserver": ["CMD-SHELL", "/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P '${SA_PASSWORD}' -Q 'SELECT 1' -b"],
        # 缓存
        "redis": ["CMD", "redis-cli", "ping"],
        "memcached": ["CMD-SHELL", "echo stats | nc 127.0.0.1 11211 | grep -q uptime"],
        # 消息队列
        "kafka": ["CMD-SHELL", "kafka-topics --bootstrap-server localhost:9092 --list >/dev/null 2>&1 || exit 1"],
        "rabbitmq": ["CMD-SHELL", "rabbitmq-diagnostics -q ping"],
        # 搜索引擎
        "elasticsearch": ["CMD-SHELL", "curl -s http://localhost:9200/_cluster/health | grep -qE 'status.*(green|yellow)'"],
        # 注册中心/配置中心
        "nacos": ["CMD-SHELL", "curl -s http://localhost:8848/nacos/v1/console/health/readiness | grep -q 'true'"],
        "consul": ["CMD-SHELL", "curl -sf http://localhost:8500/v1/status/leader > /dev/null 2>&1"],
        "etcd": ["CMD-SHELL", "etcdctl endpoint health 2>&1 | grep -q 'healthy'"],
        "zookeeper": ["CMD-SHELL", "echo ruok | nc 127.0.0.1 2181 | grep -q imok"],
        # 对象存储
        "minio": ["CMD-SHELL", "curl -s http://localhost:9000/minio/health/live | grep -q 'ok'"],
    }
    for key, cmd in checks.items():
        if key in service_name.lower():
            import json as _json
            return _json.dumps(cmd)
    return None




def _get_startup_cmd(service_name: str) -> Optional[str]:
    """获取需要指定启动命令的服务的 command"""
    commands = {
        "minio": ["server", "/data", "--console-address", ":9001"],
        "redis": None,  # 默认镜像有启动命令
        "mysql": None,
        "postgresql": None,
        "nacos": None,
        "rabbitmq": None,
        "kafka": None,
        "elasticsearch": None,
        "mongodb": None,
        "consul": ["agent", "-dev", "-client=0.0.0.0"],
        "zookeeper": None,
        "etcd": None,
    }
    cmd = commands.get(service_name.lower())
    if cmd is None:
        return None
    import json as _json
    return _json.dumps(cmd)
