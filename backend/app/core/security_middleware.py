import time
import logging
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件 - 按 IP 限制每分钟请求数"""

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests: dict = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = datetime.now(timezone.utc)

        # 清理一分钟前的请求记录
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if (now - req_time).total_seconds() < 60
        ]

        # 检查是否超过限制
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            logger.warning(f"速率限制触发: IP={client_ip}, 请求数={len(self.requests[client_ip])}")
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"}
            )

        # 记录当前请求
        self.requests[client_ip].append(now)

        response = await call_next(request)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全响应头中间件"""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # 添加安全响应头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        # 获取客户端 IP
        client_ip = request.client.host if request.client else "unknown"

        # 记录请求开始
        logger.info(f"请求开始: {request.method} {request.url.path} - 客户端IP: {client_ip}")

        # 处理请求
        response = await call_next(request)

        # 计算耗时
        process_time = time.time() - start_time

        # 记录请求完成
        logger.info(
            f"请求完成: {request.method} {request.url.path} "
            f"- 状态码: {response.status_code} "
            f"- 耗时: {process_time:.3f}s "
            f"- 客户端IP: {client_ip}"
        )

        return response
