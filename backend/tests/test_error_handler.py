"""错误处理模块测试"""

import pytest
from app.core.error_handler import (
    AppError, ErrorCode, ErrorSeverity,
    handle_error, with_retry, RetryConfig,
    ErrorHandler, RETRY_CONFIGS
)


def test_app_error():
    """测试 AppError 异常类"""
    error = AppError(
        code=ErrorCode.NETWORK_ERROR,
        message="网络错误",
        details={"host": "example.com"},
        severity=ErrorSeverity.MEDIUM,
        retryable=True
    )
    assert error.code == ErrorCode.NETWORK_ERROR
    assert error.message == "网络错误"
    assert error.retryable is True
    assert error.severity == ErrorSeverity.MEDIUM

    error_dict = error.to_dict()
    assert error_dict["code"] == 1001
    assert error_dict["message"] == "网络错误"
    assert error_dict["severity"] == "medium"
    assert "timestamp" in error_dict


def test_error_code_enum():
    """测试错误码枚举"""
    assert ErrorCode.SUCCESS.value == 0
    assert ErrorCode.NETWORK_ERROR.value == 1001
    assert ErrorCode.GIT_ERROR.value == 6001
    assert ErrorCode.DOCKER_ERROR.value == 6002
    assert ErrorCode.K8S_ERROR.value == 6003
    assert ErrorCode.UNKNOWN_ERROR.value == 9999


def test_retry_config():
    """测试重试配置"""
    config = RetryConfig(max_retries=5, delay=2.0, backoff=3.0)
    assert config.max_retries == 5
    assert config.delay == 2.0
    assert config.backoff == 3.0
    assert ErrorCode.NETWORK_ERROR in config.retryable_codes
    assert ErrorCode.PERMISSION_ERROR not in config.retryable_codes


def test_retry_configs_presets():
    """测试预设重试配置"""
    assert "git" in RETRY_CONFIGS
    assert "docker" in RETRY_CONFIGS
    assert "k8s" in RETRY_CONFIGS
    assert RETRY_CONFIGS["git"].max_retries >= 1


@pytest.mark.asyncio
async def test_handle_error_decorator_success():
    """测试 handle_error 装饰器 — 正常执行"""
    @handle_error
    async def success_func():
        return "success"

    result = await success_func()
    assert result == "success"


@pytest.mark.asyncio
async def test_handle_error_decorator_timeout():
    """测试 handle_error 装饰器 — 超时转 AppError"""
    @handle_error
    async def timeout_func():
        raise TimeoutError()

    with pytest.raises(AppError) as exc_info:
        await timeout_func()
    assert exc_info.value.code == ErrorCode.TIMEOUT_ERROR


@pytest.mark.asyncio
async def test_handle_error_decorator_connection():
    """测试 handle_error 装饰器 — 连接错误转 AppError"""
    @handle_error
    async def connection_func():
        raise ConnectionError()

    with pytest.raises(AppError) as exc_info:
        await connection_func()
    assert exc_info.value.code == ErrorCode.CONNECTION_ERROR


@pytest.mark.asyncio
async def test_handle_error_decorator_value_error():
    """测试 handle_error 装饰器 — ValueError 转 VALIDATION_ERROR"""
    @handle_error
    async def value_func():
        raise ValueError("参数无效")

    with pytest.raises(AppError) as exc_info:
        await value_func()
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_handle_error_decorator_app_error_passthrough():
    """测试 handle_error 装饰器 — AppError 直接透传"""
    @handle_error
    async def app_error_func():
        raise AppError(code=ErrorCode.NOT_FOUND, message="不存在")

    with pytest.raises(AppError) as exc_info:
        await app_error_func()
    assert exc_info.value.code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_with_retry_success_after_failures():
    """测试 with_retry 装饰器 — 失败后重试成功"""
    attempt_count = 0

    @with_retry("api")
    async def failing_then_success():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise AppError(code=ErrorCode.NETWORK_ERROR, message="网络错误", retryable=True)
        return "success"

    result = await failing_then_success()
    assert result == "success"
    assert attempt_count == 3


@pytest.mark.asyncio
async def test_with_retry_non_retryable():
    """测试 with_retry — 不可重试错误直接抛出"""
    @with_retry("api")
    async def non_retryable():
        raise AppError(code=ErrorCode.PERMISSION_ERROR, message="权限不足", retryable=False)

    with pytest.raises(AppError) as exc_info:
        await non_retryable()
    assert exc_info.value.code == ErrorCode.PERMISSION_ERROR


@pytest.mark.asyncio
async def test_with_retry_exhausted():
    """测试 with_retry — 重试次数用尽后抛出"""
    @with_retry("api")
    async def always_fail():
        raise AppError(code=ErrorCode.NETWORK_ERROR, message="网络错误", retryable=True)

    with pytest.raises(AppError) as exc_info:
        await always_fail()
    assert exc_info.value.code == ErrorCode.NETWORK_ERROR


def test_error_handler_handle():
    """测试 ErrorHandler.handle 同步方法"""
    handler = ErrorHandler()
    error = AppError(code=ErrorCode.INTERNAL_ERROR, message="内部错误")
    result = handler.handle(error)
    assert result.code == ErrorCode.INTERNAL_ERROR


def test_error_handler_callbacks():
    """测试 ErrorHandler 回调机制"""
    handler = ErrorHandler()
    callback_called = False

    def my_callback(error):
        nonlocal callback_called
        callback_called = True

    handler.error_callbacks.append(my_callback)

    error = AppError(code=ErrorCode.INTERNAL_ERROR, message="内部错误")
    handler.handle(error)
    assert callback_called is True
