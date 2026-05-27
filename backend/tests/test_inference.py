"""依赖推理引擎测试"""

import pytest
from app.services.inference.inference_service import (
    InferenceService,
    RuleEngine,
    LLMProvider,
)


class TestRuleEngine:
    """RuleEngine 规则引擎测试"""

    def test_rule_engine_python_fastapi(self):
        """Python+FastAPI 项目应推断出 postgresql 和 redis"""
        engine = RuleEngine()
        result = engine.analyze(
            dependencies=["fastapi", "uvicorn"],
            language="python",
            framework="fastapi",
        )
        assert "postgresql" in result["database"]
        assert "redis" in result["cache"]

    def test_rule_engine_javascript_express(self):
        """JS+Express 应推断出 postgresql 和 redis"""
        engine = RuleEngine()
        result = engine.analyze(
            dependencies=["express", "cors"],
            language="javascript",
            framework="express",
        )
        assert "postgresql" in result["database"]
        assert "redis" in result["cache"]

    def test_rule_engine_db_packages(self):
        """含 psycopg2 的依赖应推断出 postgresql"""
        engine = RuleEngine()
        result = engine.analyze(
            dependencies=["psycopg2", "flask"],
            language="python",
            framework="flask",
        )
        assert "postgresql" in result["database"]

    def test_rule_engine_cache_packages(self):
        """含 redis 的依赖应推断出 redis"""
        engine = RuleEngine()
        result = engine.analyze(
            dependencies=["redis", "fastapi"],
            language="python",
            framework="fastapi",
        )
        assert "redis" in result["cache"]

    def test_rule_engine_deduplication(self):
        """框架和依赖包同时推断出相同资源时应去重"""
        engine = RuleEngine()
        result = engine.analyze(
            dependencies=["psycopg2", "redis", "fastapi"],
            language="python",
            framework="fastapi",
        )
        # postgresql 同时由框架规则和 psycopg2 推断，应去重
        assert result["database"].count("postgresql") == 1
        assert result["cache"].count("redis") == 1

    def test_rule_engine_mongodb_package(self):
        """含 pymongo 的依赖应推断出 mongodb"""
        engine = RuleEngine()
        result = engine.analyze(
            dependencies=["pymongo", "flask"],
            language="python",
            framework="flask",
        )
        assert "mongodb" in result["database"]

    def test_rule_engine_queue_packages(self):
        """含 celery 的依赖应推断出 rabbitmq"""
        engine = RuleEngine()
        result = engine.analyze(
            dependencies=["celery", "fastapi"],
            language="python",
            framework="fastapi",
        )
        assert "rabbitmq" in result["queue"]

    def test_rule_engine_empty_dependencies(self):
        """空依赖列表应返回空资源"""
        engine = RuleEngine()
        result = engine.analyze(dependencies=[], language=None, framework=None)
        assert result == {
            "database": [],
            "cache": [],
            "queue": [],
            "storage": [],
            "compute": [],
        }


class TestInferenceService:
    """InferenceService 推理服务测试"""

    def test_analyze_dependencies_no_llm(self):
        """无 LLM provider 时只用规则引擎"""
        service = InferenceService()
        tech_stack = {
            "language": "python",
            "framework": "fastapi",
            "dependencies": ["fastapi", "uvicorn", "psycopg2", "redis"],
        }
        result = service.analyze_dependencies(tech_stack)
        assert "postgresql" in result["database"]
        assert "redis" in result["cache"]
        # 没有 LLM，结果仅来自规则引擎
        assert "rabbitmq" not in result.get("queue", [])

    def test_analyze_dependencies_with_llm(self):
        """有 LLM provider 时应合并 LLM 结果"""
        class MockLLMProvider:
            def infer_resources(self, dependencies):
                return {"database": ["mysql"], "cache": [], "queue": [], "storage": ["s3"], "compute": []}

        service = InferenceService(llm_provider=MockLLMProvider())
        tech_stack = {
            "language": "python",
            "framework": "fastapi",
            "dependencies": ["fastapi", "uvicorn"],
        }
        result = service.analyze_dependencies(tech_stack)
        # 规则引擎结果
        assert "postgresql" in result["database"]
        assert "redis" in result["cache"]
        # LLM 增强结果
        assert "mysql" in result["database"]
        assert "s3" in result["storage"]

    def test_analyze_dependencies_llm_failure_fallback(self):
        """LLM 调用失败时应降级到规则引擎结果"""

        class FailingLLMProvider:
            def infer_resources(self, dependencies):
                raise RuntimeError("LLM 服务不可用")

        service = InferenceService(llm_provider=FailingLLMProvider())
        tech_stack = {
            "language": "python",
            "framework": "fastapi",
            "dependencies": ["fastapi", "uvicorn"],
        }
        result = service.analyze_dependencies(tech_stack)
        # 降级后仍应有规则引擎的结果
        assert "postgresql" in result["database"]
        assert "redis" in result["cache"]

    def test_set_llm_provider(self):
        """set_llm_provider 应能动态设置 LLM provider"""
        service = InferenceService()
        assert service.llm_provider is None

        class MockProvider:
            def infer_resources(self, dependencies):
                return {"database": [], "cache": [], "queue": [], "storage": [], "compute": []}

        service.set_llm_provider(MockProvider())
        assert service.llm_provider is not None

    def test_infer_deploy_config(self):
        """验证部署配置推断（端口、健康检查等）"""
        service = InferenceService()
        tech_stack = {
            "language": "python",
            "framework": "fastapi",
            "package_manager": "pip",
            "build_tool": "pip",
            "dependencies": ["fastapi", "uvicorn", "psycopg2", "redis"],
        }
        config = service.infer_deploy_config(tech_stack)

        # 端口
        assert config["port"] == 8000
        # 健康检查路径
        assert config["health_check"] == "/health"
        # 构建命令
        assert "pip install" in config["build_command"]
        # 启动命令
        assert "uvicorn" in config["start_command"]
        # 环境变量
        assert "DATABASE_URL" in config["environment_variables"]
        assert "REDIS_URL" in config["environment_variables"]
        assert config["environment_variables"]["PYTHONUNBUFFERED"] == "1"
        # 资源需求
        assert "cpu" in config["resource_requirements"]
        assert "memory" in config["resource_requirements"]

    def test_infer_deploy_config_javascript(self):
        """验证 JavaScript 项目的部署配置推断"""
        service = InferenceService()
        tech_stack = {
            "language": "javascript",
            "framework": "nextjs",
            "package_manager": "npm",
            "build_tool": "npm",
            "dependencies": ["next", "react", "pg", "redis"],
        }
        config = service.infer_deploy_config(tech_stack)

        assert config["port"] == 3000
        assert config["health_check"] == "/api/health"
        assert "npm run build" in config["build_command"]
        assert "npm start" in config["start_command"]
