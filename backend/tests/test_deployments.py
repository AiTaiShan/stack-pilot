import uuid
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.models.deployment import (
    Deployment,
    DeploymentCheckpoint,
    DeploymentLog,
    DeploymentStatus,
    DeploymentStep,
)
from app.core.error_handler import (
    AppError,
    ErrorCode,
    ErrorSeverity,
    RetryConfig,
    RETRY_CONFIGS,
    error_handler,
    handle_error,
    with_retry,
)


# ========== 枚举测试 ==========

def test_deployment_status_enum():
    """验证部署状态枚举值"""
    assert DeploymentStatus.PENDING.value == "pending"
    assert DeploymentStatus.RUNNING.value == "running"
    assert DeploymentStatus.PAUSED.value == "paused"
    assert DeploymentStatus.CANCELLED.value == "cancelled"
    assert DeploymentStatus.SUCCESS.value == "success"
    assert DeploymentStatus.FAILED.value == "failed"
    assert DeploymentStatus.ROLLING_BACK.value == "rolling_back"
    assert DeploymentStatus.ROLLED_BACK.value == "rolled_back"
    assert len(DeploymentStatus) == 8


def test_deployment_step_enum():
    """验证部署步骤枚举值"""
    assert DeploymentStep.CLONE.value == "clone"
    assert DeploymentStep.GENERATE_REVIEW.value == "generate_review"
    assert DeploymentStep.BUILD.value == "build"
    assert DeploymentStep.ENV_REVIEW.value == "env_review"
    assert DeploymentStep.PUSH.value == "push"
    assert DeploymentStep.DEPLOY.value == "deploy"
    assert DeploymentStep.CONFIGURE.value == "configure"
    assert DeploymentStep.VERIFY.value == "verify"
    assert len(DeploymentStep) == 8


# ========== 进度计算测试 ==========

def test_calculate_progress():
    """验证进度计算"""
    from app.services.deployer.deployment_manager import DeploymentManager

    manager = DeploymentManager(db=MagicMock())

    assert manager._calculate_progress(0) == 0     # 未开始
    assert manager._calculate_progress(1) == 10     # clone 完成
    assert manager._calculate_progress(2) == 35     # generate_review 完成
    assert manager._calculate_progress(3) == 55     # build 完成
    assert manager._calculate_progress(4) == 65     # env_review 完成
    assert manager._calculate_progress(5) == 75     # push 完成
    assert manager._calculate_progress(6) == 85     # deploy 完成
    assert manager._calculate_progress(7) == 100    # verify 完成
    assert manager._calculate_progress(8) == 100    # 超出范围


# ========== 错误码测试 ==========

def test_error_code_enum():
    """验证错误码枚举"""
    assert ErrorCode.SUCCESS == 0
    assert ErrorCode.NETWORK_ERROR == 1001
    assert ErrorCode.TIMEOUT_ERROR == 1002
    assert ErrorCode.CONNECTION_ERROR == 1003
    assert ErrorCode.AUTH_ERROR == 2001
    assert ErrorCode.TOKEN_EXPIRED == 2002
    assert ErrorCode.INVALID_CREDENTIALS == 2003
    assert ErrorCode.PERMISSION_ERROR == 3001
    assert ErrorCode.FORBIDDEN == 3002
    assert ErrorCode.NOT_FOUND == 4001
    assert ErrorCode.ALREADY_EXISTS == 4002
    assert ErrorCode.RESOURCE_EXHAUSTED == 4003
    assert ErrorCode.VALIDATION_ERROR == 5001
    assert ErrorCode.INVALID_PARAM == 5002
    assert ErrorCode.GIT_ERROR == 6001
    assert ErrorCode.DOCKER_ERROR == 6002
    assert ErrorCode.K8S_ERROR == 6003
    assert ErrorCode.CLOUD_API_ERROR == 6004
    assert ErrorCode.INTERNAL_ERROR == 9001
    assert ErrorCode.UNKNOWN_ERROR == 9999


# ========== AppError 测试 ==========

def test_app_error():
    """验证 AppError 异常类"""
    error = AppError(
        code=ErrorCode.GIT_ERROR,
        message="test git error",
        details={"url": "https://example.com/repo.git"},
        severity=ErrorSeverity.HIGH,
        retryable=True,
    )

    assert error.code == ErrorCode.GIT_ERROR
    assert error.message == "test git error"
    assert error.details == {"url": "https://example.com/repo.git"}
    assert error.severity == ErrorSeverity.HIGH
    assert error.retryable is True
    assert isinstance(error.timestamp, datetime)
    assert error.timestamp.tzinfo == timezone.utc

    error_dict = error.to_dict()
    assert error_dict["code"] == 6001
    assert error_dict["message"] == "test git error"
    assert error_dict["severity"] == "high"
    assert error_dict["retryable"] is True
    assert "timestamp" in error_dict


# ========== RetryConfig 测试 ==========

def test_retry_config():
    """验证重试配置"""
    config = RetryConfig()
    assert config.max_retries == 3
    assert config.delay == 1.0
    assert config.backoff == 2.0
    assert config.max_delay == 30.0
    assert ErrorCode.NETWORK_ERROR.value in [c.value for c in config.retryable_codes]
    assert ErrorCode.GIT_ERROR.value in [c.value for c in config.retryable_codes]

    # 验证预配置
    assert "git" in RETRY_CONFIGS
    assert "docker" in RETRY_CONFIGS
    assert "k8s" in RETRY_CONFIGS
    assert "cloud" in RETRY_CONFIGS
    assert "api" in RETRY_CONFIGS
    assert RETRY_CONFIGS["git"].max_retries == 3
    assert RETRY_CONFIGS["cloud"].max_retries == 5


# ========== handle_error 装饰器测试 ==========

def test_handle_error_decorator():
    """验证错误处理装饰器"""

    @handle_error
    def func_raises_file_not_found():
        raise FileNotFoundError("file not found")

    @handle_error
    def func_raises_permission_error():
        raise PermissionError("no permission")

    @handle_error
    def func_raises_timeout_error():
        raise TimeoutError("timeout")

    @handle_error
    def func_raises_connection_error():
        raise ConnectionError("connection failed")

    @handle_error
    def func_raises_value_error():
        raise ValueError("invalid value")

    @handle_error
    def func_raises_generic_error():
        raise RuntimeError("something went wrong")

    @handle_error
    def func_raises_app_error():
        raise AppError(code=ErrorCode.GIT_ERROR, message="git error")

    @handle_error
    def func_success():
        return "ok"

    # AppError 直接传递
    with pytest.raises(AppError) as exc_info:
        func_raises_app_error()
    assert exc_info.value.code == ErrorCode.GIT_ERROR

    # FileNotFoundError -> NOT_FOUND
    with pytest.raises(AppError) as exc_info:
        func_raises_file_not_found()
    assert exc_info.value.code == ErrorCode.NOT_FOUND

    # PermissionError -> PERMISSION_ERROR
    with pytest.raises(AppError) as exc_info:
        func_raises_permission_error()
    assert exc_info.value.code == ErrorCode.PERMISSION_ERROR

    # TimeoutError -> TIMEOUT_ERROR
    with pytest.raises(AppError) as exc_info:
        func_raises_timeout_error()
    assert exc_info.value.code == ErrorCode.TIMEOUT_ERROR

    # ConnectionError -> CONNECTION_ERROR
    with pytest.raises(AppError) as exc_info:
        func_raises_connection_error()
    assert exc_info.value.code == ErrorCode.CONNECTION_ERROR

    # ValueError -> VALIDATION_ERROR
    with pytest.raises(AppError) as exc_info:
        func_raises_value_error()
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    # RuntimeError -> INTERNAL_ERROR
    with pytest.raises(AppError) as exc_info:
        func_raises_generic_error()
    assert exc_info.value.code == ErrorCode.INTERNAL_ERROR

    # 正常执行
    assert func_success() == "ok"


# ========== with_retry 装饰器测试 ==========

def test_with_retry_decorator():
    """验证重试装饰器"""
    call_count = 0

    @with_retry(config_name="api")
    def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise AppError(
                code=ErrorCode.NETWORK_ERROR,
                message="network error",
                retryable=True,
            )
        return "success"

    result = flaky_func()
    assert result == "success"
    assert call_count == 3


def test_with_retry_non_retryable():
    """验证不可重试的错误不重试"""
    call_count = 0

    @with_retry(config_name="api")
    def non_retryable_func():
        nonlocal call_count
        call_count += 1
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message="validation error",
            retryable=False,
        )

    with pytest.raises(AppError):
        non_retryable_func()
    assert call_count == 1  # 只调用了一次


# ========== 取消/暂停/恢复测试 ==========

def test_cancel_deployment():
    """验证取消部署"""
    mock_db = MagicMock()
    from app.services.deployer.deployment_manager import DeploymentManager

    manager = DeploymentManager(db=mock_db)

    # 场景1：取消活跃的部署（通过 cancel_flag）
    deployment_id = str(uuid.uuid4())
    cancel_event = threading.Event()
    manager.cancel_flags[deployment_id] = cancel_event

    result = manager.cancel_deployment(deployment_id)
    assert result is True
    assert cancel_event.is_set()

    # 场景2：取消数据库中 PENDING 状态的部署
    deployment_id2 = str(uuid.uuid4())
    mock_deployment = MagicMock()
    mock_deployment.status = DeploymentStatus.PENDING
    mock_db.query.return_value.filter.return_value.first.return_value = mock_deployment

    result = manager.cancel_deployment(deployment_id2)
    assert result is True
    assert mock_deployment.status == DeploymentStatus.CANCELLED


def test_pause_deployment():
    """验证暂停部署"""
    mock_db = MagicMock()
    from app.services.deployer.deployment_manager import DeploymentManager

    manager = DeploymentManager(db=mock_db)

    # 场景1：暂停活跃的部署
    deployment_id = str(uuid.uuid4())
    pause_event = threading.Event()
    manager.pause_flags[deployment_id] = pause_event

    result = manager.pause_deployment(deployment_id)
    assert result is True
    assert pause_event.is_set()

    # 场景2：暂停数据库中 RUNNING 状态的部署
    deployment_id2 = str(uuid.uuid4())
    mock_deployment = MagicMock()
    mock_deployment.status = DeploymentStatus.RUNNING
    mock_db.query.return_value.filter.return_value.first.return_value = mock_deployment

    result = manager.pause_deployment(deployment_id2)
    assert result is True
    assert mock_deployment.status == DeploymentStatus.PAUSED


def test_resume_deployment():
    """验证恢复部署"""
    mock_db = MagicMock()
    from app.services.deployer.deployment_manager import DeploymentManager

    manager = DeploymentManager(db=mock_db)

    # 场景1：恢复 PAUSED 状态的部署
    deployment_id = str(uuid.uuid4())
    mock_deployment = MagicMock()
    mock_deployment.status = DeploymentStatus.PAUSED
    mock_deployment.can_resume = 1
    mock_deployment.id = uuid.UUID(deployment_id)
    mock_deployment.git_url = "https://example.com/repo.git"

    mock_checkpoint = MagicMock()
    mock_checkpoint.step = DeploymentStep.BUILD.value
    mock_checkpoint.step_index = 1

    mock_db.query.return_value.filter.return_value.first.return_value = mock_deployment
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_checkpoint

    # 用 patch 避免实际启动线程
    with patch.object(threading, "Thread") as mock_thread:
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        result = manager.resume_deployment(deployment_id)

    assert result is True
    assert mock_deployment.status == DeploymentStatus.RUNNING

    # 场景2：不存在的部署
    mock_db.query.return_value.filter.return_value.first.return_value = None
    result = manager.resume_deployment(str(uuid.uuid4()))
    assert result is False
