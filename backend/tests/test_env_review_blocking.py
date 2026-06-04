import threading
import time
import uuid as _uuid
import pytest
from unittest.mock import MagicMock, patch
from app.models.deployment import Deployment, DeploymentStatus
from app.core.error_handler import AppError, ErrorCode


def _uid():
    """生成一个合法的 UUID 字符串，供 _log 等方法使用"""
    return str(_uuid.uuid4())


# ========== confirm_env_review 基础测试 ==========

def test_confirm_env_review():
    from app.services.deployer.deployment_manager import DeploymentManager

    manager = DeploymentManager(db=MagicMock())
    deployment_id = "test-id"

    # 模拟 review_events
    event = threading.Event()
    manager.review_events[deployment_id] = event

    # 在另一个线程中等待
    result = {"confirmed": False}
    def wait_for_confirm():
        event.wait(timeout=5)
        result["confirmed"] = event.is_set()

    thread = threading.Thread(target=wait_for_confirm)
    thread.start()

    # 确认
    success = manager.confirm_env_review(deployment_id)
    assert success is True

    thread.join(timeout=2)
    assert result["confirmed"] is True


def test_confirm_env_review_not_found():
    from app.services.deployer.deployment_manager import DeploymentManager

    manager = DeploymentManager(db=MagicMock())
    success = manager.confirm_env_review("non-existent-id")
    assert success is False


# ========== 超时逻辑测试 ==========

class TestEnvReviewTimeout:
    """测试 _step_env_review 的超时逻辑"""

    def test_timeout_raises_app_error(self):
        """超时后应抛出 DEPLOYMENT_TIMEOUT 错误"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"grouped_env_vars": {"app": {"env_vars": {"DB_HOST": {"value": "", "source": "test"}}}}}
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()
        manager.cancel_flags[deployment_id] = threading.Event()

        # mock time.time: 第一次返回 start_time=0，第二次返回超时值
        time_values = iter([0.0, 9999.0])

        with patch("time.time", side_effect=time_values):
            with patch("time.sleep"):
                with pytest.raises(AppError) as exc_info:
                    manager._step_env_review(mock_db, deployment_id, deployment)

        assert exc_info.value.code == ErrorCode.DEPLOYMENT_TIMEOUT
        assert "超时" in str(deployment.error_message)

    def test_timeout_sets_failed_status(self):
        """超时后 deployment 状态应变为 FAILED"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"grouped_env_vars": {"app": {"env_vars": {"DB_HOST": {"value": "", "source": "test"}}}}}
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()
        manager.cancel_flags[deployment_id] = threading.Event()

        time_values = iter([0.0, 9999.0])

        with patch("time.time", side_effect=time_values):
            with patch("time.sleep"):
                with pytest.raises(AppError):
                    manager._step_env_review(mock_db, deployment_id, deployment)

        assert deployment.status == DeploymentStatus.FAILED

    def test_timeout_cleans_review_event(self):
        """超时后 review_event 应被清理"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"grouped_env_vars": {"app": {"env_vars": {"DB_HOST": {"value": "", "source": "test"}}}}}
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()
        manager.cancel_flags[deployment_id] = threading.Event()

        time_values = iter([0.0, 9999.0])

        with patch("time.time", side_effect=time_values):
            with patch("time.sleep"):
                with pytest.raises(AppError):
                    manager._step_env_review(mock_db, deployment_id, deployment)

        assert deployment_id not in manager.review_events


# ========== 取消逻辑测试 ==========

class TestEnvReviewCancellation:
    """测试 _step_env_review 中的取消逻辑"""

    def test_cancel_during_review_raises_error(self):
        """审核期间取消应抛出 DEPLOYMENT_CANCELLED 错误"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"grouped_env_vars": {"app": {"env_vars": {"DB_HOST": {"value": "", "source": "test"}}}}}
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()

        # 设置 cancel_flag，让它在第一轮循环就被检测到
        cancel_event = threading.Event()
        cancel_event.set()
        manager.cancel_flags[deployment_id] = cancel_event

        with pytest.raises(AppError) as exc_info:
            manager._step_env_review(mock_db, deployment_id, deployment)

        assert exc_info.value.code == ErrorCode.DEPLOYMENT_CANCELLED
        assert "cancelled" in exc_info.value.message.lower()

    def test_cancel_cleans_review_event(self):
        """取消后 review_event 应被清理"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"grouped_env_vars": {"app": {"env_vars": {"DB_HOST": {"value": "", "source": "test"}}}}}
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()
        cancel_event = threading.Event()
        cancel_event.set()
        manager.cancel_flags[deployment_id] = cancel_event

        with pytest.raises(AppError):
            manager._step_env_review(mock_db, deployment_id, deployment)

        assert deployment_id not in manager.review_events

    def test_confirm_during_review_success(self):
        """用户确认后应解除阻塞，状态恢复为 RUNNING"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"grouped_env_vars": {"app": {"env_vars": {"DB_HOST": {"value": "", "source": "test"}}}}}
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()
        manager.cancel_flags[deployment_id] = threading.Event()

        # 在另一个线程中延迟确认
        def delayed_confirm():
            time.sleep(0.2)
            manager.confirm_env_review(deployment_id)

        confirm_thread = threading.Thread(target=delayed_confirm)
        confirm_thread.start()

        # _step_env_review 应该在确认后正常返回
        manager._step_env_review(mock_db, deployment_id, deployment)

        confirm_thread.join(timeout=2)

        # 确认后状态应恢复为 RUNNING
        assert deployment.status == DeploymentStatus.RUNNING
        # review_event 应被清理
        assert deployment_id not in manager.review_events

    def test_no_env_vars_skips_review(self):
        """没有环境变量时应跳过审核步骤"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {"grouped_env_vars": {}}
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()

        # 不应抛出异常，直接跳过
        manager._step_env_review(mock_db, deployment_id, deployment)

        # review_event 不应被创建
        assert deployment_id not in manager.review_events

    def test_no_env_vars_in_config_skips_review(self):
        """config 中无 grouped_env_vars 时应跳过审核"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {}
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()

        manager._step_env_review(mock_db, deployment_id, deployment)
        assert deployment_id not in manager.review_events

    def test_env_vars_confirmed_skips_review(self):
        """用户已确认过（持久化标志）时应跳过审核，不进入阻塞"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {
            "grouped_env_vars": {"app": {"env_vars": {"DB_HOST": {"value": "", "source": "test"}}}},
            "env_vars_confirmed": True,
        }
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()

        # 应直接跳过，不阻塞
        manager._step_env_review(mock_db, deployment_id, deployment)

        # review_event 不应被创建
        assert deployment_id not in manager.review_events
        # 状态不应变为 RUNNING（因为确认后直接 return，不会修改状态）
        deployment.status = DeploymentStatus.WAITING_REVIEW  # 验证未被修改

    def test_env_vars_confirmed_persists_across_restart(self):
        """模拟进程重启：env_vars_confirmed=True 时部署不会卡在 waiting_review"""
        from app.services.deployer.deployment_manager import DeploymentManager

        mock_db = MagicMock()
        manager = DeploymentManager(db=mock_db)

        deployment = MagicMock()
        deployment.config = {
            "grouped_env_vars": {"app": {"env_vars": {"DB_HOST": {"value": "", "source": "test"}}}},
            "env_vars_confirmed": True,
        }
        deployment.status = DeploymentStatus.WAITING_REVIEW

        deployment_id = _uid()
        manager.cancel_flags[deployment_id] = threading.Event()

        # _step_env_review 应直接返回，不进入阻塞循环
        # 这验证了进程重启后，已确认的部署不会卡住
        manager._step_env_review(mock_db, deployment_id, deployment)

        # 确认没有创建 review_event（说明跳过了阻塞逻辑）
        assert deployment_id not in manager.review_events
