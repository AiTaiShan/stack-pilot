"""依赖检测器 - 检测项目使用的外部服务和中间件"""
import os
import re
import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DatabaseInitInfo:
    """数据库初始化信息"""
    has_migrations: bool = False           # 是否有迁移文件
    migration_tool: str = ""               # 迁移工具
    migration_dir: str = ""                # 迁移目录
    has_schema_sql: bool = False           # 是否有建表 SQL
    schema_files: List[str] = field(default_factory=list)  # SQL 文件列表
    has_seed_data: bool = False            # 是否有初始数据
    seed_files: List[str] = field(default_factory=list)    # 初始数据文件
    has_orm_auto_create: bool = False      # ORM 自动建表
    orm_tool: str = ""                     # ORM 工具
    init_commands: List[str] = field(default_factory=list)  # 初始化命令


@dataclass
class ExternalService:
    """外部服务信息"""
    name: str                    # 服务名 (如 redis, mysql)
    category: str               # 分类 (如 database, cache, mq)
    image: str                  # Docker 镜像
    default_port: int           # 默认端口
    env_vars: Dict[str, str] = field(default_factory=dict)  # 环境变量模板


# 外部服务定义
EXTERNAL_SERVICES: Dict[str, ExternalService] = {
    # 数据库
    "mysql": ExternalService("mysql", "database", "mysql:5.7", 3306, {"MYSQL_ROOT_PASSWORD": "root", "MYSQL_DATABASE": "app"}),
    "postgresql": ExternalService("postgresql", "database", "postgres:15", 5432, {"POSTGRES_PASSWORD": "postgres", "POSTGRES_DB": "app"}),
    "mongodb": ExternalService("mongodb", "database", "mongo:6", 27017, {"MONGO_INITDB_ROOT_USERNAME": "admin", "MONGO_INITDB_ROOT_PASSWORD": "password"}),
    "sqlite": ExternalService("sqlite", "database", "", 0),  # 内嵌数据库，无需容器
    "oracle": ExternalService("oracle", "database", "oracle-xe:18", 1521, {"ORACLE_PWD": "oracle"}),
    "sqlserver": ExternalService("sqlserver", "database", "mssql/server:2022-latest", 1433, {"ACCEPT_EULA": "Y", "SA_PASSWORD": "YourPassword123"}),

    # 缓存
    "redis": ExternalService("redis", "cache", "redis:7-alpine", 6379),
    "memcached": ExternalService("memcached", "cache", "memcached:1.6-alpine", 11211),

    # 消息队列
    "kafka": ExternalService("kafka", "messagequeue", "confluentinc/cp-kafka:7.4.0", 9092, {"KAFKA_ADVERTISED_LISTENERS": "PLAINTEXT://kafka:9092"}),
    "rabbitmq": ExternalService("rabbitmq", "messagequeue", "rabbitmq:3-management", 5672, {"RABBITMQ_DEFAULT_USER": "admin", "RABBITMQ_DEFAULT_PASS": "admin"}),
    "rocketmq": ExternalService("rocketmq", "messagequeue", "apache/rocketmq:5.1.4", 9876),
    "activemq": ExternalService("activemq", "messagequeue", "rmohr/activemq:5.15.9", 61616),
    "nats": ExternalService("nats", "messagequeue", "nats:2-alpine", 4222),

    # 搜索引擎
    "elasticsearch": ExternalService("elasticsearch", "search", "elasticsearch:8.11.0", 9200, {"discovery.type": "single-node", "xpack.security.enabled": "false"}),
    "solr": ExternalService("solr", "search", "solr:9-alpine", 8983),

    # 服务发现/配置中心
    "nacos": ExternalService("nacos", "registry", "nacos/nacos-server:v2.2.3", 8848, {
        "MODE": "standalone",
        "SPRING_DATASOURCE_PLATFORM": "mysql",
        "MYSQL_SERVICE_HOST": "mysql",
        "MYSQL_SERVICE_PORT": "3306",
        "MYSQL_SERVICE_DB_NAME": "ry-config",
        "MYSQL_SERVICE_USER": "root",
        "MYSQL_SERVICE_PASSWORD": "root",
    }),
    "consul": ExternalService("consul", "registry", "consul:1.15", 8500),
    "etcd": ExternalService("etcd", "registry", "quay.io/coreos/etcd:v3.5.9", 2379),
    "zookeeper": ExternalService("zookeeper", "registry", "zookeeper:3.8", 2181),

    # 对象存储
    "minio": ExternalService("minio", "storage", "minio/minio:latest", 9000, {"MINIO_ROOT_USER": "minioadmin", "MINIO_ROOT_PASSWORD": "minioadmin"}),

    # 监控
    "prometheus": ExternalService("prometheus", "monitoring", "prom/prometheus:latest", 9090),
    "grafana": ExternalService("grafana", "monitoring", "grafana/grafana:latest", 3000),

    # 链路追踪
    "jaeger": ExternalService("jaeger", "tracing", "jaegertracing/all-in-one:latest", 16686),
    "zipkin": ExternalService("zipkin", "tracing", "openzipkin/zipkin:latest", 9411),

    # 流量防护
    "sentinel": ExternalService("sentinel", "flowcontrol", "", 8858),  # 通常内嵌
}


# 包名到服务的映射（各语言）
PACKAGE_TO_SERVICE: Dict[str, str] = {
    # Python
    "pymysql": "mysql",
    "mysql-connector-python": "mysql",
    "mysqlclient": "mysql",
    "psycopg2": "postgresql",
    "psycopg2-binary": "postgresql",
    "asyncpg": "postgresql",
    "pymongo": "mongodb",
    "motor": "mongodb",  # MongoDB 异步驱动
    "redis": "redis",
    "aioredis": "redis",
    "kafka-python": "kafka",
    "confluent-kafka": "kafka",
    "pika": "rabbitmq",
    "aio-pika": "rabbitmq",
    "celery": "rabbitmq",  # Celery 默认用 RabbitMQ
    "pylibmc": "memcached",
    "pymemcache": "memcached",
    "elasticsearch": "elasticsearch",
    "elasticsearch7": "elasticsearch",
    "elasticsearch8": "elasticsearch",
    "minio": "minio",
    "boto3": "aws",  # AWS SDK
    "oss2": "aliyun",  # 阿里云 OSS
    "nacos-sdk-python": "nacos",
    "python-consul": "consul",
    "prometheus-client": "prometheus",
    "sentry-sdk": "sentry",

    # Node.js
    "mysql": "mysql",
    "mysql2": "mysql",
    "pg": "postgresql",
    "postgres": "postgresql",
    "mongoose": "mongodb",
    "mongodb": "mongodb",
    "ioredis": "redis",
    "redis": "redis",
    "kafkajs": "kafka",
    "kafka-node": "kafka",
    "amqplib": "rabbitmq",
    "amqp": "rabbitmq",
    "bull": "redis",  # Bull 队列基于 Redis
    "bullmq": "redis",
    "memcached": "memcached",
    "@elastic/elasticsearch": "elasticsearch",
    "minio": "minio",
    "aws-sdk": "aws",
    "@aws-sdk/client-s3": "aws",
    "nats": "nats",
    "@grpc/grpc-js": "grpc",
    "grpc": "grpc",

    # Java (Maven artifactId)
    "mysql-connector-java": "mysql",
    "mysql-connector-j": "mysql",
    "postgresql": "postgresql",
    "postgresql-driver": "postgresql",
    "spring-boot-starter-data-mongodb": "mongodb",
    "mongodb-driver": "mongodb",
    "spring-boot-starter-data-redis": "redis",
    "jedis": "redis",
    "lettuce-core": "redis",
    "spring-kafka": "kafka",
    "kafka-clients": "kafka",
    "spring-boot-starter-amqp": "rabbitmq",
    "spring-cloud-starter-stream-kafka": "kafka",
    "spring-cloud-starter-stream-rabbit": "rabbitmq",
    "mybatis-plus-boot-starter": "mysql",  # 通常搭配 MySQL
    "spring-boot-starter-data-elasticsearch": "elasticsearch",
    "elasticsearch-rest-high-level-client": "elasticsearch",
    "spring-cloud-starter-alibaba-nacos-discovery": "nacos",
    "spring-cloud-starter-alibaba-nacos-config": "nacos",
    "spring-cloud-starter-consul-discovery": "consul",
    "spring-cloud-starter-zookeeper-discovery": "zookeeper",
    "spring-cloud-starter-netflix-eureka-client": "eureka",
    "spring-cloud-starter-alibaba-sentinel": "sentinel",
    "minio": "minio",
    "io.minio:minio": "minio",

    # Go
    "github.com/go-sql-driver/mysql": "mysql",
    "github.com/jinzhu/gorm": "mysql",  # GORM 通常搭配 MySQL
    "github.com/lib/pq": "postgresql",
    "github.com/jackc/pgx": "postgresql",
    "go.mongodb.org/mongo-driver": "mongodb",
    "github.com/go-redis/redis": "redis",
    "github.com/redis/go-redis": "redis",
    "github.com/segmentio/kafka-go": "kafka",
    "github.com/Shopify/sarama": "kafka",
    "github.com/streadway/amqp": "rabbitmq",
    "github.com/rabbitmq/amqp091-go": "rabbitmq",
    "github.com/olivere/elastic/v7": "elasticsearch",
    "github.com/elastic/go-elasticsearch/v8": "elasticsearch",
    "github.com/minio/minio-go": "minio",
    "github.com/nats-io/nats.go": "nats",
    "github.com/grpc/grpc-go": "grpc",
    "github.com/etcd/client/v3": "etcd",
    "go.etcd.io/etcd/client/v3": "etcd",

    # .NET
    "MySql.Data": "mysql",
    "MySqlConnector": "mysql",
    "Npgsql": "postgresql",
    "MongoDB.Driver": "mongodb",
    "StackExchange.Redis": "redis",
    "Confluent.Kafka": "kafka",
    "RabbitMQ.Client": "rabbitmq",
    "NEST": "elasticsearch",
    "Elastic.Clients.Elasticsearch": "elasticsearch",
    "Minio": "minio",

    # PHP
    "predis/predis": "redis",
    "php-amqplib/php-amqplib": "rabbitmq",
    "elasticsearch/elasticsearch": "elasticsearch",

    # Ruby
    "redis": "redis",
    "mysql2": "mysql",
    "pg": "postgresql",
    "mongoid": "mongodb",
    "bunny": "rabbitmq",
    "kafka": "kafka",
}


class DependencyDetector:
    """依赖检测器"""

    def __init__(self, repo_dir: str):
        self.repo_dir = repo_dir

    def detect_all(self) -> Dict[str, Any]:
        """检测所有依赖"""
        services = set()

        # 检测各语言依赖文件
        services.update(self._detect_from_requirements_txt())
        services.update(self._detect_from_pyproject_toml())
        services.update(self._detect_from_pom_xml())
        services.update(self._detect_from_build_gradle())
        services.update(self._detect_from_package_json())
        services.update(self._detect_from_go_mod())
        services.update(self._detect_from_go_sum())
        services.update(self._detect_from_cargo_toml())
        services.update(self._detect_from_csproj())
        services.update(self._detect_from_composer_json())
        services.update(self._detect_from_gemfile())
        services.update(self._detect_from_docker_compose())
        services.update(self._detect_from_dockerfile())
        services.update(self._detect_from_config_files())
        services.update(self._detect_from_source_code())

        # 检测数据库初始化方式
        db_init = self._detect_database_init()

        # 构建结果
        result = {
            "external_services": [],
            "service_details": {},
            "database_init": db_init
        }

        for service_name in services:
            if service_name in EXTERNAL_SERVICES:
                service = EXTERNAL_SERVICES[service_name]
                result["external_services"].append(service_name)
                result["service_details"][service_name] = {
                    "category": service.category,
                    "image": service.image,
                    "port": service.default_port,
                    "env_vars": service.env_vars
                }

        return result

    def _detect_database_init(self) -> Dict[str, Any]:
        """检测数据库初始化方式"""
        init_info = DatabaseInitInfo()

        # 1. 检测迁移工具
        self._detect_migration_tools(init_info)

        # 2. 检测 SQL 文件
        self._detect_sql_files(init_info)

        # 3. 检测 ORM 自动建表
        self._detect_orm_auto_create(init_info)

        # 4. 检测种子数据
        self._detect_seed_data(init_info)

        # 5. 生成初始化命令
        self._generate_init_commands(init_info)

        return {
            "has_migrations": init_info.has_migrations,
            "migration_tool": init_info.migration_tool,
            "migration_dir": init_info.migration_dir,
            "has_schema_sql": init_info.has_schema_sql,
            "schema_files": init_info.schema_files,
            "has_seed_data": init_info.has_seed_data,
            "seed_files": init_info.seed_files,
            "has_orm_auto_create": init_info.has_orm_auto_create,
            "orm_tool": init_info.orm_tool,
            "init_commands": init_info.init_commands
        }

    def _detect_migration_tools(self, init_info: DatabaseInitInfo):
        """检测数据库迁移工具"""
        # Alembic (Python SQLAlchemy)
        if os.path.exists(os.path.join(self.repo_dir, "alembic")) or os.path.exists(os.path.join(self.repo_dir, "alembic.ini")):
            init_info.has_migrations = True
            init_info.migration_tool = "alembic"
            init_info.migration_dir = "alembic/versions"
            return

        # Django migrations
        for root, dirs, files in os.walk(self.repo_dir):
            if "migrations" in dirs:
                migration_dir = os.path.join(root, "migrations")
                if os.path.exists(os.path.join(migration_dir, "__init__.py")):
                    init_info.has_migrations = True
                    init_info.migration_tool = "django"
                    init_info.migration_dir = os.path.relpath(migration_dir, self.repo_dir)
                    return

        # Flyway (Java)
        flyway_dirs = ["src/main/resources/db/migration", "db/migration", "flyway"]
        for d in flyway_dirs:
            if os.path.exists(os.path.join(self.repo_dir, d)):
                init_info.has_migrations = True
                init_info.migration_tool = "flyway"
                init_info.migration_dir = d
                return

        # Liquibase (Java)
        liquibase_files = ["liquibase.xml", "changelog.xml", "src/main/resources/db/changelog"]
        for f in liquibase_files:
            if os.path.exists(os.path.join(self.repo_dir, f)):
                init_info.has_migrations = True
                init_info.migration_tool = "liquibase"
                init_info.migration_dir = f
                return

        # Knex.js (Node.js)
        if os.path.exists(os.path.join(self.repo_dir, "knexfile.js")) or os.path.exists(os.path.join(self.repo_dir, "knexfile.ts")):
            init_info.has_migrations = True
            init_info.migration_tool = "knex"
            init_info.migration_dir = "migrations"
            return

        # TypeORM (Node.js)
        if os.path.exists(os.path.join(self.repo_dir, "ormconfig.json")) or os.path.exists(os.path.join(self.repo_dir, "src/migration")):
            init_info.has_migrations = True
            init_info.migration_tool = "typeorm"
            init_info.migration_dir = "src/migration"
            return

        # Prisma (Node.js)
        if os.path.exists(os.path.join(self.repo_dir, "prisma", "schema.prisma")):
            init_info.has_migrations = True
            init_info.migration_tool = "prisma"
            init_info.migration_dir = "prisma/migrations"
            return

        # Go migrations (golang-migrate)
        if os.path.exists(os.path.join(self.repo_dir, "migrations")):
            for f in os.listdir(os.path.join(self.repo_dir, "migrations")):
                if f.endswith(".sql") or f.endswith(".up.sql"):
                    init_info.has_migrations = True
                    init_info.migration_tool = "golang-migrate"
                    init_info.migration_dir = "migrations"
                    return

        # ActiveRecord (Ruby)
        if os.path.exists(os.path.join(self.repo_dir, "db", "migrate")):
            init_info.has_migrations = True
            init_info.migration_tool = "activerecord"
            init_info.migration_dir = "db/migrate"
            return

    def _detect_sql_files(self, init_info: DatabaseInitInfo):
        """检测 SQL 建表和初始化文件"""
        sql_patterns = [
            "init.sql", "schema.sql", "create.sql", "setup.sql",
            "database.sql", "db.sql", "tables.sql",
            "sql/init.sql", "sql/schema.sql", "sql/create.sql",
            "db/init.sql", "db/schema.sql",
            "src/main/resources/schema.sql", "src/main/resources/data.sql",
            "src/main/resources/sql/schema.sql", "src/main/resources/sql/data.sql",
        ]

        # 检查特定文件
        for pattern in sql_patterns:
            sql_path = os.path.join(self.repo_dir, pattern)
            if os.path.exists(sql_path):
                if "data" in pattern or "seed" in pattern or "init" in pattern:
                    init_info.has_seed_data = True
                    init_info.seed_files.append(pattern)
                else:
                    init_info.has_schema_sql = True
                    init_info.schema_files.append(pattern)

        # 扫描 sql 目录
        sql_dirs = ["sql", "db/sql", "database/sql", "src/main/resources/sql"]
        for sql_dir in sql_dirs:
            full_path = os.path.join(self.repo_dir, sql_dir)
            if os.path.isdir(full_path):
                for f in os.listdir(full_path):
                    if f.endswith(".sql"):
                        file_path = os.path.join(sql_dir, f)
                        if any(keyword in f.lower() for keyword in ["seed", "data", "insert", "sample"]):
                            init_info.has_seed_data = True
                            init_info.seed_files.append(file_path)
                        else:
                            init_info.has_schema_sql = True
                            init_info.schema_files.append(file_path)

    def _detect_orm_auto_create(self, init_info: DatabaseInitInfo):
        """检测 ORM 自动建表配置"""
        # SQLAlchemy (Python)
        for root, dirs, files in os.walk(self.repo_dir):
            for f in files:
                if f.endswith(".py"):
                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, errors='ignore') as file:
                            content = file.read(5000)
                            if "create_all" in content or "Base.metadata.create_all" in content:
                                init_info.has_orm_auto_create = True
                                init_info.orm_tool = "sqlalchemy"
                                return
                    except Exception:
                        pass

        # Django (检查 settings.py 中的 DATABASES 配置)
        settings_files = ["settings.py", "config/settings.py", "*/settings.py"]
        for pattern in settings_files:
            for root, dirs, files in os.walk(self.repo_dir):
                if "settings.py" in files:
                    init_info.has_orm_auto_create = True
                    init_info.orm_tool = "django"
                    return

        # TypeORM (Node.js) - synchronize: true
        ormconfig_path = os.path.join(self.repo_dir, "ormconfig.json")
        if os.path.exists(ormconfig_path):
            try:
                with open(ormconfig_path) as f:
                    config = json.load(f)
                    if config.get("synchronize"):
                        init_info.has_orm_auto_create = True
                        init_info.orm_tool = "typeorm"
                        return
            except Exception:
                pass

        # Prisma (Node.js) - prisma db push
        if os.path.exists(os.path.join(self.repo_dir, "prisma", "schema.prisma")):
            init_info.has_orm_auto_create = True
            init_info.orm_tool = "prisma"
            return

        # GORM (Go) - AutoMigrate
        for root, dirs, files in os.walk(self.repo_dir):
            for f in files:
                if f.endswith(".go"):
                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, errors='ignore') as file:
                            content = file.read(5000)
                            if "AutoMigrate" in content:
                                init_info.has_orm_auto_create = True
                                init_info.orm_tool = "gorm"
                                return
                    except Exception:
                        pass

    def _detect_seed_data(self, init_info: DatabaseInitInfo):
        """检测种子数据文件"""
        seed_patterns = [
            "seed.py", "seeds.py", "seed.js", "seeds.js",
            "seed.ts", "seeds.ts", "seed.rb", "seeds.rb",
            "fixtures", "sample-data",
            "db/seeds", "db/seed", "database/seeds",
            "src/seeds", "src/seed",
            "prisma/seed.ts", "prisma/seed.js",
        ]

        for pattern in seed_patterns:
            seed_path = os.path.join(self.repo_dir, pattern)
            if os.path.exists(seed_path):
                init_info.has_seed_data = True
                init_info.seed_files.append(pattern)

        # 检查 package.json 中的 seed 脚本
        pkg_path = os.path.join(self.repo_dir, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path) as f:
                    pkg = json.load(f)
                    scripts = pkg.get("scripts", {})
                    for script_name, script_cmd in scripts.items():
                        if "seed" in script_name.lower():
                            init_info.has_seed_data = True
                            init_info.init_commands.append(f"npm run {script_name}")
            except Exception:
                pass

    def _generate_init_commands(self, init_info: DatabaseInitInfo):
        """生成数据库初始化命令"""
        commands = []

        # 迁移命令
        if init_info.has_migrations:
            tool = init_info.migration_tool
            if tool == "alembic":
                commands.append("alembic upgrade head")
            elif tool == "django":
                commands.append("python manage.py migrate")
            elif tool == "flyway":
                commands.append("flyway migrate")
            elif tool == "liquibase":
                commands.append("liquibase update")
            elif tool == "knex":
                commands.append("npx knex migrate:latest")
            elif tool == "typeorm":
                commands.append("npx typeorm migration:run")
            elif tool == "prisma":
                commands.append("npx prisma migrate deploy")
            elif tool == "golang-migrate":
                commands.append("migrate -path migrations -database $DATABASE_URL up")
            elif tool == "activerecord":
                commands.append("rails db:migrate")

        # ORM 自动建表
        if init_info.has_orm_auto_create and not init_info.has_migrations:
            tool = init_info.orm_tool
            if tool == "prisma":
                commands.append("npx prisma db push")

        # 种子数据
        if init_info.has_seed_data:
            for seed_file in init_info.seed_files:
                if seed_file.endswith(".py"):
                    commands.append(f"python {seed_file}")
                elif seed_file.endswith(".js"):
                    commands.append(f"node {seed_file}")
                elif seed_file.endswith(".ts"):
                    commands.append(f"npx ts-node {seed_file}")

        # SQL 文件执行
        if init_info.has_schema_sql:
            for sql_file in init_info.schema_files:
                commands.append(f"# Execute {sql_file} manually")

        init_info.init_commands = commands

    def _match_package(self, package_name: str) -> Optional[str]:
        """匹配包名到服务"""
        package_lower = package_name.lower().strip()

        # 精确匹配
        if package_lower in PACKAGE_TO_SERVICE:
            return PACKAGE_TO_SERVICE[package_lower]

        # 模糊匹配
        for pkg, service in PACKAGE_TO_SERVICE.items():
            if pkg in package_lower or package_lower in pkg:
                return service

        return None

    def _detect_from_requirements_txt(self) -> Set[str]:
        """从 requirements.txt 检测"""
        services = set()
        req_file = os.path.join(self.repo_dir, "requirements.txt")
        if not os.path.exists(req_file):
            return services

        try:
            with open(req_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        # 提取包名（去掉版本号）
                        package = re.split(r'[><=!~\[]', line)[0].strip()
                        service = self._match_package(package)
                        if service:
                            services.add(service)
        except Exception as e:
            logger.debug("Failed to parse requirements.txt: %s", e)

        return services

    def _detect_from_pyproject_toml(self) -> Set[str]:
        """从 pyproject.toml 检测"""
        services = set()
        toml_file = os.path.join(self.repo_dir, "pyproject.toml")
        if not os.path.exists(toml_file):
            return services

        try:
            with open(toml_file) as f:
                content = f.read()

            # 简单解析 dependencies
            deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
            if deps_match:
                for dep in re.findall(r'"([^"]+)"', deps_match.group(1)):
                    package = re.split(r'[><=!~\[]', dep)[0].strip()
                    service = self._match_package(package)
                    if service:
                        services.add(service)
        except Exception as e:
            logger.debug("Failed to parse pyproject.toml: %s", e)

        return services

    def _detect_from_pom_xml(self) -> Set[str]:
        """从 pom.xml 检测"""
        services = set()

        # 查找所有 pom.xml
        for root, dirs, files in os.walk(self.repo_dir):
            if "pom.xml" in files:
                pom_path = os.path.join(root, "pom.xml")
                try:
                    tree = ET.parse(pom_path)
                    root_elem = tree.getroot()
                    ns = {"m": "http://maven.apache.org/POM/4.0.0"}

                    # 查找所有 dependency
                    for dep in root_elem.findall(".//m:dependency", ns):
                        group_id = dep.find("m:groupId", ns)
                        artifact_id = dep.find("m:artifactId", ns)

                        if artifact_id is not None:
                            artifact = artifact_id.text.strip()
                            service = self._match_package(artifact)
                            if service:
                                services.add(service)

                        # 也检查 groupId
                        if group_id is not None:
                            group = group_id.text.strip()
                            service = self._match_package(group)
                            if service:
                                services.add(service)

                except Exception as e:
                    logger.debug("Failed to parse %s: %s", pom_path, e)

        return services

    def _detect_from_build_gradle(self) -> Set[str]:
        """从 build.gradle 检测"""
        services = set()

        for root, dirs, files in os.walk(self.repo_dir):
            for f in files:
                if f in ("build.gradle", "build.gradle.kts"):
                    gradle_path = os.path.join(root, f)
                    try:
                        with open(gradle_path) as file:
                            content = file.read()

                        # 匹配 implementation, api, compile 等
                        deps = re.findall(r"(?:implementation|api|compile|runtimeOnly)\s+['\"]([^'\"]+)['\"]", content)
                        for dep in deps:
                            # 格式: group:artifact:version
                            parts = dep.split(":")
                            if len(parts) >= 2:
                                artifact = parts[1]
                                service = self._match_package(artifact)
                                if service:
                                    services.add(service)
                            else:
                                service = self._match_package(dep)
                                if service:
                                    services.add(service)

                    except Exception as e:
                        logger.debug("Failed to parse %s: %s", gradle_path, e)

        return services

    def _detect_from_package_json(self) -> Set[str]:
        """从 package.json 检测"""
        services = set()

        for root, dirs, files in os.walk(self.repo_dir):
            if "package.json" in files:
                pkg_path = os.path.join(root, "package.json")
                try:
                    with open(pkg_path) as f:
                        pkg = json.load(f)

                    all_deps = {}
                    all_deps.update(pkg.get("dependencies", {}))
                    all_deps.update(pkg.get("devDependencies", {}))

                    for package in all_deps:
                        service = self._match_package(package)
                        if service:
                            services.add(service)

                except Exception as e:
                    logger.debug("Failed to parse %s: %s", pkg_path, e)

        return services

    def _detect_from_go_mod(self) -> Set[str]:
        """从 go.mod 检测"""
        services = set()
        go_mod = os.path.join(self.repo_dir, "go.mod")
        if not os.path.exists(go_mod):
            return services

        try:
            with open(go_mod) as f:
                content = f.read()

            # 匹配 require 块
            require_match = re.search(r'require\s*\((.*?)\)', content, re.DOTALL)
            if require_match:
                for line in require_match.group(1).split("\n"):
                    line = line.strip()
                    if line and not line.startswith("//"):
                        module = line.split()[0] if line.split() else ""
                        service = self._match_package(module)
                        if service:
                            services.add(service)

            # 也匹配单行 require
            for match in re.finditer(r'require\s+(\S+)', content):
                module = match.group(1)
                service = self._match_package(module)
                if service:
                    services.add(service)

        except Exception as e:
            logger.debug("Failed to parse go.mod: %s", e)

        return services

    def _detect_from_go_sum(self) -> Set[str]:
        """从 go.sum 检测（go.mod 的补充）"""
        services = set()
        go_sum = os.path.join(self.repo_dir, "go.sum")
        if not os.path.exists(go_sum):
            return services

        try:
            with open(go_sum) as f:
                for line in f:
                    parts = line.split()
                    if parts:
                        module = parts[0]
                        service = self._match_package(module)
                        if service:
                            services.add(service)
        except Exception as e:
            logger.debug("Failed to parse go.sum: %s", e)

        return services

    def _detect_from_cargo_toml(self) -> Set[str]:
        """从 Cargo.toml 检测"""
        services = set()
        cargo_file = os.path.join(self.repo_dir, "Cargo.toml")
        if not os.path.exists(cargo_file):
            return services

        try:
            with open(cargo_file) as f:
                content = f.read()

            # 匹配 [dependencies] 块
            deps_match = re.search(r'\[dependencies\](.*?)\[', content, re.DOTALL)
            if deps_match:
                for line in deps_match.group(1).split("\n"):
                    line = line.strip()
                    if "=" in line:
                        package = line.split("=")[0].strip()
                        service = self._match_package(package)
                        if service:
                            services.add(service)

        except Exception as e:
            logger.debug("Failed to parse Cargo.toml: %s", e)

        return services

    def _detect_from_csproj(self) -> Set[str]:
        """从 .csproj 检测"""
        services = set()

        for root, dirs, files in os.walk(self.repo_dir):
            for f in files:
                if f.endswith(".csproj"):
                    csproj_path = os.path.join(root, f)
                    try:
                        tree = ET.parse(csproj_path)
                        root_elem = tree.getroot()

                        for ref in root_elem.findall(".//PackageReference"):
                            include = ref.get("Include", "")
                            service = self._match_package(include)
                            if service:
                                services.add(service)

                    except Exception as e:
                        logger.debug("Failed to parse %s: %s", csproj_path, e)

        return services

    def _detect_from_composer_json(self) -> Set[str]:
        """从 composer.json 检测（PHP）"""
        services = set()
        composer_file = os.path.join(self.repo_dir, "composer.json")
        if not os.path.exists(composer_file):
            return services

        try:
            with open(composer_file) as f:
                composer = json.load(f)

            all_deps = {}
            all_deps.update(composer.get("require", {}))
            all_deps.update(composer.get("require-dev", {}))

            for package in all_deps:
                service = self._match_package(package)
                if service:
                    services.add(service)

        except Exception as e:
            logger.debug("Failed to parse composer.json: %s", e)

        return services

    def _detect_from_gemfile(self) -> Set[str]:
        """从 Gemfile 检测（Ruby）"""
        services = set()
        gemfile = os.path.join(self.repo_dir, "Gemfile")
        if not os.path.exists(gemfile):
            return services

        try:
            with open(gemfile) as f:
                for line in f:
                    match = re.match(r"gem\s+['\"]([^'\"]+)['\"]", line.strip())
                    if match:
                        gem = match.group(1)
                        service = self._match_package(gem)
                        if service:
                            services.add(service)

        except Exception as e:
            logger.debug("Failed to parse Gemfile: %s", e)

        return services

    def _detect_from_docker_compose(self) -> Set[str]:
        """从 docker-compose.yml 检测"""
        services = set()

        for compose_file in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            compose_path = os.path.join(self.repo_dir, compose_file)
            if os.path.exists(compose_path):
                try:
                    with open(compose_path) as f:
                        content = f.read()

                    # 匹配 image 字段
                    for match in re.finditer(r'image:\s*(\S+)', content):
                        image = match.group(1).lower()
                        for service_name, service_info in EXTERNAL_SERVICES.items():
                            if service_info.image and service_info.image.split(":")[0] in image:
                                services.add(service_name)

                except Exception as e:
                    logger.debug("Failed to parse %s: %s", compose_path, e)

        return services

    def _detect_from_dockerfile(self) -> Set[str]:
        """从 Dockerfile 检测"""
        services = set()

        for dockerfile in ["Dockerfile", "Dockerfile.dev", "Dockerfile.prod"]:
            docker_path = os.path.join(self.repo_dir, dockerfile)
            if os.path.exists(docker_path):
                try:
                    with open(docker_path) as f:
                        content = f.read()

                    # 检测 FROM 指令中的镜像
                    for match in re.finditer(r'FROM\s+(\S+)', content):
                        image = match.group(1).lower()
                        for service_name, service_info in EXTERNAL_SERVICES.items():
                            if service_info.image and service_info.image.split(":")[0] in image:
                                services.add(service_name)

                except Exception as e:
                    logger.debug("Failed to parse %s: %s", docker_path, e)

        return services

    def _detect_from_config_files(self) -> Set[str]:
        """从配置文件检测（连接字符串等）"""
        services = set()

        config_patterns = {
            "mysql": [r'jdbc:mysql://', r'MYSQL_', r'mysql://', r'DATABASE_URL.*mysql'],
            "postgresql": [r'jdbc:postgresql://', r'POSTGRES_', r'postgresql://', r'DATABASE_URL.*postgres'],
            "mongodb": [r'mongodb://', r'mongodb\+srv://', r'MONGO_', r'MONGODB_URI'],
            "redis": [r'redis://', r'REDIS_', r'REDIS_URL', r'redis\.host'],
            "kafka": [r'KAFKA_', r'kafka\.bootstrap', r'bootstrap\.servers'],
            "rabbitmq": [r'rabbitmq://', r'AMQP_', r'RABBITMQ_'],
            "elasticsearch": [r'ELASTIC_', r'elastic\.co', r'elasticsearch\.host'],
            "nacos": [r'NACOS_', r'nacos\.server'],
            "consul": [r'CONSUL_', r'consul\.host'],
            "minio": [r'MINIO_', r'minio\.endpoint'],
        }

        config_files = [
            ".env", ".env.example", ".env.local",
            "application.yml", "application.yaml", "application.properties",
            "config.yml", "config.yaml", "config.json",
            "bootstrap.yml", "bootstrap.yaml",
            "appsettings.json", "appsettings.Development.json",
        ]

        for config_file in config_files:
            config_path = os.path.join(self.repo_dir, config_file)
            if os.path.exists(config_path):
                try:
                    with open(config_path) as f:
                        content = f.read()

                    for service_name, patterns in config_patterns.items():
                        for pattern in patterns:
                            if re.search(pattern, content, re.IGNORECASE):
                                services.add(service_name)
                                break

                except Exception as e:
                    logger.debug("Failed to parse %s: %s", config_path, e)

        return services

    def _detect_from_source_code(self) -> Set[str]:
        """从源代码 import 语句检测"""
        services = set()

        import_patterns = {
            "python": {
                "mysql": [r'import\s+(pymysql|mysql\.connector|MySQLdb)', r'from\s+(pymysql|mysql\.connector)'],
                "postgresql": [r'import\s+(psycopg2|asyncpg)', r'from\s+(psycopg2|asyncpg)'],
                "mongodb": [r'import\s+(pymongo|motor)', r'from\s+(pymongo|motor)'],
                "redis": [r'import\s+(redis|aioredis)', r'from\s+(redis|aioredis)'],
                "kafka": [r'import\s+kafka', r'from\s+kafka'],
                "rabbitmq": [r'import\s+pika', r'from\s+pika'],
                "elasticsearch": [r'import\s+elasticsearch', r'from\s+elasticsearch'],
            },
            "javascript": {
                "mysql": [r'require\([\'"]mysql', r'from\s+[\'"]mysql'],
                "postgresql": [r'require\([\'"]pg', r'from\s+[\'"]pg'],
                "mongodb": [r'require\([\'"]mongoose', r'from\s+[\'"]mongoose'],
                "redis": [r'require\([\'"]redis', r'from\s+[\'"]redis'],
                "kafka": [r'require\([\'"]kafka', r'from\s+[\'"]kafka'],
            },
            "go": {
                "mysql": [r'"github\.com/go-sql-driver/mysql"'],
                "postgresql": [r'"github\.com/lib/pq"', r'"github\.com/jackc/pgx"'],
                "mongodb": [r'"go\.mongodb\.org/mongo-driver"'],
                "redis": [r'"github\.com/go-redis/redis"', r'"github\.com/redis/go-redis"'],
                "kafka": [r'"github\.com/segmentio/kafka-go"', r'"github\.com/Shopify/sarama"'],
            }
        }

        # 遍历源代码文件
        for root, dirs, files in os.walk(self.repo_dir):
            # 跳过常见的非源码目录
            dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', 'vendor', 'venv', '__pycache__', 'target', 'build']]

            for file in files:
                ext = os.path.splitext(file)[1]
                lang = None

                if ext == ".py":
                    lang = "python"
                elif ext in (".js", ".ts", ".jsx", ".tsx"):
                    lang = "javascript"
                elif ext == ".go":
                    lang = "go"

                if not lang or lang not in import_patterns:
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, errors='ignore') as f:
                        content = f.read(10000)  # 只读前 10KB

                    for service_name, patterns in import_patterns[lang].items():
                        for pattern in patterns:
                            if re.search(pattern, content):
                                services.add(service_name)
                                break

                except Exception:
                    pass

        return services


def detect_project_dependencies(repo_dir: str) -> Dict[str, Any]:
    """检测项目依赖的便捷函数"""
    detector = DependencyDetector(repo_dir)
    result = detector.detect_all()
    # 补充版本检测
    result["service_versions"] = detect_service_versions(repo_dir)
    # 补充应用端口检测
    result["app_port"] = detect_app_port(repo_dir)
    return result


def detect_app_port(repo_dir: str) -> int:
    """通用端口检测：从应用配置中读取实际运行端口"""
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "target", ".mvn", "__pycache__"}]
        for f in files:
            if f in ("application.yml", "application.yaml"):
                try:
                    with open(os.path.join(root, f)) as fh:
                        content = fh.read()
                    match = re.search(r'\bport:\s*(\d+)', content, re.MULTILINE)
                    if match:
                        port = int(match.group(1))
                        if 0 < port < 65536:
                            logger.info(f"Detected app port from {f}: {port}")
                            return port
                except Exception:
                    continue
    return 8080  # 默认端口


def detect_service_versions(repo_dir: str) -> Dict[str, str]:
    """
    通用版本检测：根据项目依赖文件自动选择 Docker 镜像版本
    返回: {"mysql": "mysql:8.0", "redis": "redis:7-alpine", ...}
    """
    import xml.etree.ElementTree as ET

    versions = {}

    # 检测 pom.xml 中的依赖版本
    pom_files = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "target", ".mvn", "__pycache__"}]
        for f in files:
            if f == "pom.xml":
                pom_files.append(os.path.join(root, f))

    # 收集所有 pom.xml 中的属性和版本
    all_properties = {}
    dependency_versions = {}

    for pom_path in pom_files:
        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()
            ns = {"m": "http://maven.apache.org/POM/4.0.0"}

            # 读取 properties 中的版本号
            props = root.find(".//m:properties", ns)
            if props is not None:
                for prop in props:
                    tag = prop.tag.replace(f'{{{ns["m"]}}}', '')
                    all_properties[tag] = prop.text.strip() if prop.text else ""

            # 读取 dependencies 中的版本号
            deps = root.findall(".//m:dependency", ns)
            for dep in deps:
                group = dep.find("m:groupId", ns)
                artifact = dep.find("m:artifactId", ns)
                version = dep.find("m:version", ns)
                if group is not None and artifact is not None and version is not None:
                    g = group.text.strip() if group.text else ""
                    a = artifact.text.strip() if artifact.text else ""
                    v = version.text.strip() if version.text else ""
                    dependency_versions[f"{g}:{a}"] = v
        except Exception as e:
            logger.debug("Failed to parse pom.xml: %s", e)

    # 替换 properties 中的变量引用
    def resolve_version(version_str: str) -> str:
        """解析 ${property.name} 格式的版本号"""
        if version_str.startswith("${") and version_str.endswith("}"):
            prop_name = version_str[2:-1]
            return all_properties.get(prop_name, version_str)
        return version_str

    # MySQL 版本检测
    mysql_version = None
    for key in ["mysql:mysql-connector-java", "com.mysql:mysql-connector-j", "mysql:mysql-connector-j"]:
        if key in dependency_versions:
            mysql_version = resolve_version(dependency_versions[key])
            break

    if mysql_version:
        major = mysql_version.split(".")[0]
        if major == "5":
            versions["mysql"] = "mysql:5.7"
        elif major == "8":
            # MySQL 8.0+ 使用 caching_sha2_password，需要兼容性配置
            versions["mysql"] = "mysql:8.0"
        else:
            versions["mysql"] = "mysql:8.0"
    else:
        # 默认使用 MySQL 5.7（兼容性最好）
        versions["mysql"] = "mysql:5.7"

    # PostgreSQL 版本检测
    pg_version = None
    for key in ["org.postgresql:postgresql"]:
        if key in dependency_versions:
            pg_version = resolve_version(dependency_versions[key])
            break

    if pg_version:
        major = pg_version.split(".")[0]
        versions["postgresql"] = f"postgres:{major}"
    else:
        versions["postgresql"] = "postgres:15"

    # Redis 版本检测（通过 Spring Boot Starter 或 Redisson）
    redis_version = None
    for key in ["org.redisson:redisson", "redis.clients:jedis", "io.lettuce:lettuce-core"]:
        if key in dependency_versions:
            redis_version = resolve_version(dependency_versions[key])
            break

    if redis_version:
        major = redis_version.split(".")[0]
        versions["redis"] = f"redis:{major}-alpine"
    else:
        versions["redis"] = "redis:7-alpine"

    # MongoDB 版本检测
    mongo_version = None
    for key in ["org.mongodb:mongodb-driver", "org.mongodb:mongodb-driver-sync"]:
        if key in dependency_versions:
            mongo_version = resolve_version(dependency_versions[key])
            break

    if mongo_version:
        major = mongo_version.split(".")[0]
        versions["mongodb"] = f"mongo:{major}"
    else:
        versions["mongodb"] = "mongo:6"

    # Kafka 版本检测
    kafka_version = None
    for key in ["org.apache.kafka:kafka-clients", "org.springframework.kafka:spring-kafka"]:
        if key in dependency_versions:
            kafka_version = resolve_version(dependency_versions[key])
            break

    if kafka_version:
        major_minor = ".".join(kafka_version.split(".")[:2])
        versions["kafka"] = f"confluentinc/cp-kafka:{major_minor}"
    else:
        versions["kafka"] = "confluentinc/cp-kafka:7.5"

    # RabbitMQ 版本检测
    rabbit_version = None
    for key in ["com.rabbitmq:amqp-client"]:
        if key in dependency_versions:
            rabbit_version = resolve_version(dependency_versions[key])
            break

    if rabbit_version:
        major = rabbit_version.split(".")[0]
        versions["rabbitmq"] = f"rabbitmq:{major}-management"
    else:
        versions["rabbitmq"] = "rabbitmq:3-management"

    logger.info("Detected service versions: %s", versions)
    return versions
