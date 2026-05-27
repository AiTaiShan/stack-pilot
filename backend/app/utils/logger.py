"""日志工具模块 — 提供 JSON 格式日志和统一的日志配置。"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """将日志记录格式化为 JSON 字符串。"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 如果有异常信息，附加 exception 字段
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = self.formatException(record.exc_info)

        # 如果有自定义上下文，附加 context 字段
        if hasattr(record, "context") and record.context is not None:
            log_data["context"] = record.context

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """配置根日志器：控制台 + 文件处理器。

    Args:
        level: 日志级别，默认 "INFO"。
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加处理器
    if root_logger.handlers:
        return

    formatter = JSONFormatter()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器（写入 logs/app.log）
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器。

    Args:
        name: 日志器名称，通常使用 ``__name__``。

    Returns:
        logging.Logger 实例。
    """
    return logging.getLogger(name)
