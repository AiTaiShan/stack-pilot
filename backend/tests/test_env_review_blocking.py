import threading
import time
import pytest
from unittest.mock import MagicMock, patch
from app.models.deployment import DeploymentStatus

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
