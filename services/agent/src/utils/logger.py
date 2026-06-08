import logging
import logging.handlers
import os
import sys


def setup_logging(log_level: str = "INFO", log_dir: str = "logs"):
    """初始化日志系统：控制台 + 按天切分的文件日志"""

    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)

    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 清除已有 handler（防止重复初始化）
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件输出：按天切分，保留 30 天
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "agent.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
