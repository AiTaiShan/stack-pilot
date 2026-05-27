"""依赖推理引擎 —— 根据技术栈和依赖包推断资源需求和部署配置"""

from typing import Any, Dict, List, Optional, Protocol
from abc import abstractmethod


class LLMProvider(Protocol):
    """LLM 提供商抽象接口"""

    @abstractmethod
    def infer_resources(self, dependencies: List[str]) -> Dict[str, List[str]]:
        """根据依赖列表推断所需资源"""
        ...


class RuleEngine:
    """基于规则的依赖分析引擎"""

    # 框架级默认资源映射
    FRAMEWORK_RESOURCES: Dict[str, Dict[str, List[str]]] = {
        # Python 框架
        ("python", "django"): {"database": ["postgresql"], "cache": ["redis"]},
        ("python", "flask"): {"database": ["postgresql"], "cache": ["redis"]},
        ("python", "fastapi"): {"database": ["postgresql"], "cache": ["redis"]},
        # JavaScript 框架
        ("javascript", "express"): {"database": ["postgresql"], "cache": ["redis"]},
        ("javascript", "nextjs"): {"database": ["postgresql"], "cache": ["redis"]},
        ("javascript", "react"): {"database": ["postgresql"], "cache": ["redis"]},
        ("javascript", "vue"): {"database": ["postgresql"], "cache": ["redis"]},
        ("javascript", "nuxtjs"): {"database": ["postgresql"], "cache": ["redis"]},
    }

    # 依赖包 → 资源类型映射
    PACKAGE_RESOURCE_MAP: Dict[str, Dict[str, List[str]]] = {
        # 数据库
        "psycopg2": {"database": ["postgresql"]},
        "sqlalchemy": {"database": ["postgresql"]},
        "asyncpg": {"database": ["postgresql"]},
        "mysql-connector": {"database": ["mysql"]},
        "mysqlclient": {"database": ["mysql"]},
        "pymysql": {"database": ["mysql"]},
        "pymongo": {"database": ["mongodb"]},
        "motor": {"database": ["mongodb"]},
        "redis": {"cache": ["redis"]},
        "aioredis": {"cache": ["redis"]},
        "memcached": {"cache": ["memcached"]},
        "celery": {"queue": ["rabbitmq"]},
        "rabbitmq": {"queue": ["rabbitmq"]},
        "kafka": {"queue": ["kafka"]},
        "confluent-kafka": {"queue": ["kafka"]},
        "minio": {"storage": ["minio"]},
        "boto3": {"storage": ["s3"]},
    }

    def analyze(
        self,
        dependencies: List[str],
        language: Optional[str] = None,
        framework: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """分析依赖关系，返回资源需求

        返回格式: {"database": [], "cache": [], "queue": [], "storage": [], "compute": []}
        """
        result: Dict[str, List[str]] = {
            "database": [],
            "cache": [],
            "queue": [],
            "storage": [],
            "compute": [],
        }

        # 1. 根据框架推断默认资源
        if language and framework:
            key = (language, framework)
            if key in self.FRAMEWORK_RESOURCES:
                for category, resources in self.FRAMEWORK_RESOURCES[key].items():
                    for r in resources:
                        if r not in result[category]:
                            result[category].append(r)

        # 2. 根据依赖包推断资源
        dep_set = set(dependencies)
        for package, resources in self.PACKAGE_RESOURCE_MAP.items():
            if package in dep_set:
                for category, items in resources.items():
                    for item in items:
                        if item not in result[category]:
                            result[category].append(item)

        return result


class InferenceService:
    """依赖推理服务 —— 结合规则引擎和 LLM 进行资源推断"""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider
        self.rule_engine = RuleEngine()

    def set_llm_provider(self, provider: LLMProvider) -> None:
        """设置 LLM 提供商"""
        self.llm_provider = provider

    def analyze_dependencies(self, tech_stack: Dict[str, Any]) -> Dict[str, List[str]]:
        """分析依赖关系，先用规则引擎，再用 LLM 增强

        如果 LLM 调用失败，降级到规则引擎结果。
        """
        dependencies = tech_stack.get("dependencies", [])
        language = tech_stack.get("language")
        framework = tech_stack.get("framework")

        # 第一步：规则引擎分析
        rule_result = self.rule_engine.analyze(dependencies, language, framework)

        # 第二步：如果存在 LLM provider，尝试增强分析
        if self.llm_provider is not None:
            try:
                llm_result = self.llm_provider.infer_resources(dependencies)
                # 合并 LLM 结果到规则引擎结果（去重）
                for category, items in llm_result.items():
                    if category in rule_result:
                        for item in items:
                            if item not in rule_result[category]:
                                rule_result[category].append(item)
            except Exception:
                # LLM 调用失败，降级到规则引擎结果
                pass

        return rule_result

    def infer_deploy_config(
        self, tech_stack: Dict[str, Any], resources: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """根据技术栈和资源需求推断部署配置

        返回包含端口、环境变量、健康检查路径、构建命令、启动命令等的配置。
        """
        language = tech_stack.get("language")
        framework = tech_stack.get("framework")
        package_manager = tech_stack.get("package_manager")
        build_tool = tech_stack.get("build_tool")
        dependencies = tech_stack.get("dependencies", [])
        resources = resources or {}

        config: Dict[str, Any] = {
            "port": self._infer_port(framework),
            "health_check": self._infer_health_check(framework),
            "build_command": self._infer_build_command(language, framework, package_manager, build_tool),
            "start_command": self._infer_start_command(language, framework),
            "environment_variables": self._infer_env_vars(tech_stack, resources),
            "resource_requirements": self._infer_resource_requirements(tech_stack),
        }

        return config

    def _infer_port(self, framework: Optional[str]) -> int:
        """根据框架推断默认端口"""
        port_map = {
            "fastapi": 8000,
            "flask": 5000,
            "django": 8000,
            "express": 3000,
            "nextjs": 3000,
            "react": 3000,
            "vue": 8080,
            "nuxtjs": 3000,
        }
        return port_map.get(framework, 8080)

    def _infer_health_check(self, framework: Optional[str]) -> str:
        """根据框架推断健康检查路径"""
        health_check_map = {
            "fastapi": "/health",
            "flask": "/health",
            "django": "/health/",
            "express": "/health",
            "nextjs": "/api/health",
            "react": "/",
            "vue": "/",
            "nuxtjs": "/",
        }
        return health_check_map.get(framework, "/")

    def _infer_build_command(
        self,
        language: Optional[str],
        framework: Optional[str],
        package_manager: Optional[str],
        build_tool: Optional[str],
    ) -> str:
        """推断构建命令"""
        if language == "javascript":
            if framework in ("nextjs", "nuxtjs", "react", "vue"):
                return "npm run build"
            return "npm install"
        elif language == "python":
            return "pip install -r requirements.txt"
        elif language == "java":
            return "mvn package -DskipTests"
        elif language == "go":
            return "go build -o app ."
        return "echo 'no build command'"

    def _infer_start_command(self, language: Optional[str], framework: Optional[str]) -> str:
        """推断启动命令"""
        if language == "python":
            if framework == "fastapi":
                return "uvicorn main:app --host 0.0.0.0 --port 8000"
            elif framework == "flask":
                return "flask run --host=0.0.0.0 --port=5000"
            elif framework == "django":
                return "python manage.py runserver 0.0.0.0:8000"
        elif language == "javascript":
            if framework == "nextjs":
                return "npm start"
            elif framework in ("react", "vue", "nuxtjs"):
                return "npm start"
            return "node index.js"
        elif language == "go":
            return "./app"
        elif language == "java":
            return "java -jar target/app.jar"
        return "echo 'no start command'"

    def _infer_env_vars(
        self, tech_stack: Dict[str, Any], resources: Dict[str, Any]
    ) -> Dict[str, str]:
        """推断所需环境变量"""
        env_vars: Dict[str, str] = {
            "NODE_ENV": "production",
            "PORT": str(self._infer_port(tech_stack.get("framework"))),
        }

        language = tech_stack.get("language")
        if language == "python":
            env_vars["PYTHONUNBUFFERED"] = "1"

        # 根据推断出的资源添加对应的环境变量
        dep_analysis = self.analyze_dependencies(tech_stack)

        if dep_analysis.get("database"):
            db_type = dep_analysis["database"][0]
            env_vars["DATABASE_URL"] = f"{db_type}://user:password@host:5432/dbname"

        if dep_analysis.get("cache"):
            cache_type = dep_analysis["cache"][0]
            if cache_type == "redis":
                env_vars["REDIS_URL"] = "redis://host:6379/0"

        if dep_analysis.get("queue"):
            queue_type = dep_analysis["queue"][0]
            if queue_type == "rabbitmq":
                env_vars["CELERY_BROKER_URL"] = "amqp://user:password@host:5672//"
            elif queue_type == "kafka":
                env_vars["KAFKA_BROKER_URL"] = "host:9092"

        return env_vars

    def _infer_resource_requirements(self, tech_stack: Dict[str, Any]) -> Dict[str, str]:
        """推断基础资源需求"""
        language = tech_stack.get("language")

        # 基础资源需求（根据语言/框架的通用经验值）
        requirements: Dict[str, str] = {
            "cpu": "0.5",
            "memory": "512Mi",
        }

        if language in ("java",):
            requirements["memory"] = "1024Mi"
            requirements["cpu"] = "1.0"
        elif language == "go":
            requirements["memory"] = "256Mi"
            requirements["cpu"] = "0.25"

        return requirements
