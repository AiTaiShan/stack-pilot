import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.main import app
from app.core.security_middleware import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
)


@pytest.fixture
def client():
    """测试客户端 - 每次创建新实例避免速率限制状态共享"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def rate_limit_app():
    """带速率限制的独立应用"""
    test_app = FastAPI()

    @test_app.get("/")
    async def root():
        return {"status": "ok"}

    # 添加中间件
    test_app.add_middleware(RequestLoggingMiddleware)
    test_app.add_middleware(RateLimitMiddleware, requests_per_minute=5)
    test_app.add_middleware(SecurityHeadersMiddleware)

    return test_app


class TestSecurityHeaders:
    """安全响应头测试"""

    def test_security_headers_present(self, client):
        """验证响应包含所有安全头"""
        response = client.get("/")

        # 验证安全响应头
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" in response.headers["Strict-Transport-Security"]
        assert response.headers["Content-Security-Policy"] == "default-src 'self'"

    def test_security_headers_on_health_endpoint(self, client):
        """验证健康检查端点也有安全头"""
        response = client.get("/health")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"


class TestRateLimit:
    """速率限制测试"""

    def test_rate_limit_not_exceeded(self, rate_limit_app):
        """正常请求通过"""
        with TestClient(rate_limit_app) as client:
            # 发送 3 个请求，应该全部成功
            for i in range(3):
                response = client.get("/")
                assert response.status_code == 200

    def test_rate_limit_exceeded(self, rate_limit_app):
        """超过速率限制返回 429"""
        with TestClient(rate_limit_app) as client:
            # 发送超过限制的请求（限制为 5）
            for i in range(6):
                response = client.get("/")

            # 最后一个请求应该返回 429
            assert response.status_code == 429
            assert "请求过于频繁" in response.json()["detail"]


class TestRequestLogging:
    """请求日志测试"""

    def test_request_logging(self, caplog):
        """验证请求日志记录"""
        # 创建独立的应用
        test_app = FastAPI()

        @test_app.get("/")
        async def root():
            return {"status": "ok"}

        test_app.add_middleware(RequestLoggingMiddleware)

        with TestClient(test_app) as client:
            with caplog.at_level("INFO"):
                response = client.get("/")

        # 验证日志包含请求信息
        assert any("请求开始: GET /" in record.message for record in caplog.records)
        assert any("请求完成: GET /" in record.message for record in caplog.records)
        assert any("状态码: 200" in record.message for record in caplog.records)
