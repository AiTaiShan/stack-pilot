import enum
import time
import logging
import functools
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ErrorCode(enum.IntEnum):
    SUCCESS = 0
    NETWORK_ERROR = 1001
    TIMEOUT_ERROR = 1002
    CONNECTION_ERROR = 1003
    AUTH_ERROR = 2001
    TOKEN_EXPIRED = 2002
    INVALID_CREDENTIALS = 2003
    PERMISSION_ERROR = 3001
    FORBIDDEN = 3002
    NOT_FOUND = 4001
    ALREADY_EXISTS = 4002
    RESOURCE_EXHAUSTED = 4003
    VALIDATION_ERROR = 5001
    INVALID_PARAM = 5002
    GIT_ERROR = 6001
    DOCKER_ERROR = 6002
    K8S_ERROR = 6003
    CLOUD_API_ERROR = 6004
    INTERNAL_ERROR = 9001
    UNKNOWN_ERROR = 9999


class ErrorSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RetryConfig:
    max_retries: int = 3
    delay: float = 1.0
    backoff: float = 2.0
    max_delay: float = 30.0
    retryable_codes: List[int] = field(default_factory=lambda: [
        ErrorCode.NETWORK_ERROR,
        ErrorCode.TIMEOUT_ERROR,
        ErrorCode.CONNECTION_ERROR,
        ErrorCode.GIT_ERROR,
        ErrorCode.DOCKER_ERROR,
        ErrorCode.K8S_ERROR,
        ErrorCode.CLOUD_API_ERROR,
    ])


RETRY_CONFIGS: Dict[str, RetryConfig] = {
    "git": RetryConfig(
        max_retries=3,
        delay=1.0,
        backoff=2.0,
        max_delay=30.0,
        retryable_codes=[ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT_ERROR, ErrorCode.CONNECTION_ERROR, ErrorCode.GIT_ERROR],
    ),
    "docker": RetryConfig(
        max_retries=3,
        delay=2.0,
        backoff=2.0,
        max_delay=60.0,
        retryable_codes=[ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT_ERROR, ErrorCode.CONNECTION_ERROR, ErrorCode.DOCKER_ERROR],
    ),
    "k8s": RetryConfig(
        max_retries=3,
        delay=2.0,
        backoff=2.0,
        max_delay=60.0,
        retryable_codes=[ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT_ERROR, ErrorCode.CONNECTION_ERROR, ErrorCode.K8S_ERROR],
    ),
    "cloud": RetryConfig(
        max_retries=5,
        delay=1.0,
        backoff=1.5,
        max_delay=30.0,
        retryable_codes=[ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT_ERROR, ErrorCode.CONNECTION_ERROR, ErrorCode.CLOUD_API_ERROR],
    ),
    "api": RetryConfig(
        max_retries=3,
        delay=0.5,
        backoff=2.0,
        max_delay=10.0,
        retryable_codes=[ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT_ERROR, ErrorCode.CONNECTION_ERROR],
    ),
}


class AppError(Exception):
    """应用自定义异常"""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        retryable: bool = False,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.severity = severity
        self.retryable = retryable
        self.timestamp = datetime.now(timezone.utc)
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
            "severity": self.severity.value,
            "retryable": self.retryable,
            "timestamp": self.timestamp.isoformat(),
        }


class ErrorHandler:
    """全局错误处理器"""

    def __init__(self):
        self.error_callbacks: List[Callable] = []
        self.notification_service = None

    def handle(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> AppError:
        if isinstance(error, AppError):
            app_error = error
        else:
            app_error = AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message=str(error),
                details=context or {},
                severity=ErrorSeverity.HIGH,
                retryable=False,
            )

        self._log_error(app_error, context)

        for callback in self.error_callbacks:
            try:
                callback(app_error)
            except Exception:
                pass

        return app_error

    def _log_error(self, error: AppError, context: Optional[Dict[str, Any]] = None):
        log_data = error.to_dict()
        if context:
            log_data["context"] = context

        if error.severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
            logger.error("AppError: %s", log_data)
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning("AppError: %s", log_data)
        else:
            logger.info("AppError: %s", log_data)

    def _send_notification(self, error: AppError):
        if self.notification_service:
            try:
                self.notification_service.notify(error.to_dict())
            except Exception:
                logger.exception("Failed to send error notification")


error_handler = ErrorHandler()


def handle_error(func):
    """装饰器：捕获异常并转换为 AppError"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AppError:
            raise
        except FileNotFoundError as e:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message=str(e),
                severity=ErrorSeverity.MEDIUM,
            )
        except PermissionError as e:
            raise AppError(
                code=ErrorCode.PERMISSION_ERROR,
                message=str(e),
                severity=ErrorSeverity.HIGH,
            )
        except TimeoutError as e:
            raise AppError(
                code=ErrorCode.TIMEOUT_ERROR,
                message=str(e),
                severity=ErrorSeverity.MEDIUM,
                retryable=True,
            )
        except ConnectionError as e:
            raise AppError(
                code=ErrorCode.CONNECTION_ERROR,
                message=str(e),
                severity=ErrorSeverity.MEDIUM,
                retryable=True,
            )
        except ValueError as e:
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
                severity=ErrorSeverity.LOW,
            )
        except Exception as e:
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message=str(e),
                severity=ErrorSeverity.HIGH,
            )

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppError:
            raise
        except FileNotFoundError as e:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message=str(e),
                severity=ErrorSeverity.MEDIUM,
            )
        except PermissionError as e:
            raise AppError(
                code=ErrorCode.PERMISSION_ERROR,
                message=str(e),
                severity=ErrorSeverity.HIGH,
            )
        except TimeoutError as e:
            raise AppError(
                code=ErrorCode.TIMEOUT_ERROR,
                message=str(e),
                severity=ErrorSeverity.MEDIUM,
                retryable=True,
            )
        except ConnectionError as e:
            raise AppError(
                code=ErrorCode.CONNECTION_ERROR,
                message=str(e),
                severity=ErrorSeverity.MEDIUM,
                retryable=True,
            )
        except ValueError as e:
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
                severity=ErrorSeverity.LOW,
            )
        except Exception as e:
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message=str(e),
                severity=ErrorSeverity.HIGH,
            )

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return wrapper


def with_retry(config_name: str = "api"):
    """装饰器：指数退避重试"""
    def decorator(func):
        config = RETRY_CONFIGS.get(config_name, RETRY_CONFIGS["api"])

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            delay = config.delay

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except AppError as e:
                    last_error = e
                    if not e.retryable or e.code.value not in [c.value for c in config.retryable_codes]:
                        raise
                    if attempt < config.max_retries:
                        logger.warning(
                            "Retry attempt %d/%d for %s after %.1fs: %s",
                            attempt + 1,
                            config.max_retries,
                            func.__name__,
                            delay,
                            str(e),
                        )
                        time.sleep(delay)
                        delay = min(delay * config.backoff, config.max_delay)
                except Exception as e:
                    last_error = AppError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message=str(e),
                        severity=ErrorSeverity.HIGH,
                        retryable=False,
                    )
                    raise last_error

            if last_error:
                raise last_error

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_error = None
            delay = config.delay

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except AppError as e:
                    last_error = e
                    if not e.retryable or e.code.value not in [c.value for c in config.retryable_codes]:
                        raise
                    if attempt < config.max_retries:
                        logger.warning(
                            "Retry attempt %d/%d for %s after %.1fs: %s",
                            attempt + 1,
                            config.max_retries,
                            func.__name__,
                            delay,
                            str(e),
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * config.backoff, config.max_delay)
                except Exception as e:
                    last_error = AppError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message=str(e),
                        severity=ErrorSeverity.HIGH,
                        retryable=False,
                    )
                    raise last_error

            if last_error:
                raise last_error

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
