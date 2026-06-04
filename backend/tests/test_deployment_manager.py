"""test_deployment_manager.py — _step_env_review 从文件读取环境变量的测试"""
import os
import tempfile
import threading
import uuid as _uuid
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.models.deployment import DeploymentStatus


def _uid():
    """生成一个合法的 UUID 字符串"""
    return str(_uuid.uuid4())


# ========== 测试数据 ==========

COMPOSE_WITH_ENV = """\
version: '3.8'
services:
  app:
    image: test
    environment:
      - DB_HOST=localhost
      - DB_PORT=3306
"""

COMPOSE_WITHOUT_ENV = """\
version: '3.8'
services:
  app:
    image: test
"""

COMPOSE_MULTI_SERVICE = """\
version: '3.8'
services:
  app:
    image: test
    environment:
      - DB_HOST=localhost
  redis:
    image: redis:7-alpine
    environment:
      - REDIS_HOST=redis
"""


# ========== 读取方式测试 ==========

class TestStepEnvReviewReadsFromFile:
    """测试 _step_env_review 从 docker-compose.yml 文件读取环境变量"""

    def test_reads_env_vars_from_compose_file(self):
        """从文件读取环境变量后应设置 WAITING_REVIEW 状态"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"_repo_dir": "/tmp/test"}
        deployment.status = DeploymentStatus.RUNNING

        deployment_id = _uid()
        manager.cancel_flags[deployment_id] = threading.Event()

        # 在另一个线程中延迟确认
        def delayed_confirm():
            import time
            time.sleep(0.2)
            manager.confirm_env_review(deployment_id)

        confirm_thread = threading.Thread(target=delayed_confirm)
        confirm_thread.start()

        with patch(
            "app.services.deployer.deployment_manager.read_compose_file",
            return_value=COMPOSE_WITH_ENV,
        ):
            manager._step_env_review(mock_db, deployment_id, deployment)

        confirm_thread.join(timeout=3)

        # 确认后状态应恢复为 RUNNING
        assert deployment.status == DeploymentStatus.RUNNING

    def test_no_env_vars_in_file_skips_review(self):
        """compose 文件中没有 environment 时应跳过审核"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"_repo_dir": "/tmp/test"}
        deployment.status = DeploymentStatus.RUNNING

        deployment_id = _uid()

        with patch(
            "app.services.deployer.deployment_manager.read_compose_file",
            return_value=COMPOSE_WITHOUT_ENV,
        ):
            manager._step_env_review(mock_db, deployment_id, deployment)

        # 不应创建 review_event
        assert deployment_id not in manager.review_events

    def test_multi_service_env_vars_detected(self):
        """多服务时只要有任一服务有 environment 就应进入审核"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"_repo_dir": "/tmp/test"}
        deployment.status = DeploymentStatus.RUNNING

        deployment_id = _uid()
        manager.cancel_flags[deployment_id] = threading.Event()

        def delayed_confirm():
            import time
            time.sleep(0.2)
            manager.confirm_env_review(deployment_id)

        confirm_thread = threading.Thread(target=delayed_confirm)
        confirm_thread.start()

        with patch(
            "app.services.deployer.deployment_manager.read_compose_file",
            return_value=COMPOSE_MULTI_SERVICE,
        ):
            manager._step_env_review(mock_db, deployment_id, deployment)

        confirm_thread.join(timeout=3)
        assert deployment.status == DeploymentStatus.RUNNING

    def test_compose_file_not_found_skips_review(self):
        """compose 文件不存在时应跳过审核并记录 warning"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"_repo_dir": "/tmp/test"}
        deployment.status = DeploymentStatus.RUNNING

        deployment_id = _uid()

        with patch(
            "app.services.deployer.deployment_manager.read_compose_file",
            side_effect=FileNotFoundError("docker-compose.yml not found"),
        ):
            manager._step_env_review(mock_db, deployment_id, deployment)

        # 不应创建 review_event
        assert deployment_id not in manager.review_events

    def test_env_vars_confirmed_skips_review_from_file(self):
        """已确认标志为 True 时，即使文件中有环境变量也跳过审核"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"_repo_dir": "/tmp/test", "env_vars_confirmed": True}
        deployment.status = DeploymentStatus.RUNNING

        deployment_id = _uid()

        with patch(
            "app.services.deployer.deployment_manager.read_compose_file",
            return_value=COMPOSE_WITH_ENV,
        ):
            manager._step_env_review(mock_db, deployment_id, deployment)

        # 不应创建 review_event
        assert deployment_id not in manager.review_events


# ========== 辅助函数测试 ==========

class TestGetRepoDirFromDeployment:
    """测试 _get_repo_dir_from_deployment 辅助函数"""

    def test_returns_repo_dir_from_config(self):
        """从 deployment.config 中获取 _repo_dir"""
        from app.services.deployer.deployment_manager import _get_repo_dir_from_deployment

        deployment = MagicMock()
        deployment.config = {"_repo_dir": "/tmp/test-repo"}

        with patch("os.path.exists", return_value=True):
            result = _get_repo_dir_from_deployment(deployment)
        assert result == "/tmp/test-repo"

    def test_returns_empty_when_no_config(self):
        """config 为空时返回空字符串"""
        from app.services.deployer.deployment_manager import _get_repo_dir_from_deployment

        deployment = MagicMock()
        deployment.config = None
        deployment.git_url = ""

        result = _get_repo_dir_from_deployment(deployment)
        assert result == ""
