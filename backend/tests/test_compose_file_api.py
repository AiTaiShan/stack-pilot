"""test_compose_file_api.py — docker-compose 文件读写 API 端点测试

使用 mock 数据库来避免 SQLite 与 PostgreSQL UUID 类型的兼容性问题。
"""
import uuid
import yaml
import pytest
from unittest.mock import MagicMock, patch
from app.models.deployment import Deployment, DeploymentStatus


def _make_mock_deployment(deployment_id=None, config=None):
    """创建一个模拟的 Deployment 对象"""
    dep = MagicMock()
    dep.id = deployment_id or uuid.uuid4()
    dep.config = config or {"_repo_dir": "/tmp/test"}
    return dep


def _override_db_with_deployment(client, db, deployment):
    """用 mock 的 db 会话覆盖 FastAPI 依赖注入，让查询返回指定 deployment"""
    original_query = db.query

    def mock_query(model):
        if model == Deployment:
            mock_result = MagicMock()
            mock_result.first.return_value = deployment
            mock_result.filter.return_value.first.return_value = deployment
            return mock_result
        return original_query(model)

    db.query = mock_query


# ========== GET /{deployment_id}/compose-file ==========

class TestGetComposeFile:
    """测试获取 docker-compose.yml 文件内容"""

    def test_get_compose_file_success(self, client, db):
        """正常获取 compose 文件内容"""
        deployment_id = uuid.uuid4()
        deployment = _make_mock_deployment(
            deployment_id=deployment_id,
            config={"_repo_dir": "/tmp/test"},
        )
        _override_db_with_deployment(client, db, deployment)

        with patch("app.api.v1.deployments.read_compose_file", return_value="version: '3.8'\nservices:\n  app:\n    image: nginx"):
            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["content"] == "version: '3.8'\nservices:\n  app:\n    image: nginx"

    def test_get_compose_file_not_found(self, client, db):
        """获取不存在的部署的 compose 文件"""
        _override_db_with_deployment(client, db, None)

        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/deployments/{fake_id}/compose-file")
        assert response.status_code == 404

    def test_get_compose_file_file_not_found(self, client, db):
        """compose 文件不存在时返回 404"""
        deployment_id = uuid.uuid4()
        deployment = _make_mock_deployment(
            deployment_id=deployment_id,
            config={"_repo_dir": "/tmp/test"},
        )
        _override_db_with_deployment(client, db, deployment)

        with patch("app.api.v1.deployments.read_compose_file", side_effect=FileNotFoundError("not found")):
            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ========== PUT /{deployment_id}/compose-file ==========

class TestUpdateComposeFile:
    """测试保存 docker-compose.yml 文件内容"""

    def test_put_compose_file_success(self, client, db):
        """正常保存 compose 文件内容"""
        deployment_id = uuid.uuid4()
        deployment = _make_mock_deployment(
            deployment_id=deployment_id,
            config={"_repo_dir": "/tmp/test"},
        )
        _override_db_with_deployment(client, db, deployment)

        with patch("app.api.v1.deployments.write_compose_file", return_value=True):
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": "version: '3.8'\nservices:\n  app:\n    image: nginx"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["saved"] is True

    def test_put_compose_file_not_found(self, client, db):
        """部署不存在时保存 compose 文件返回 404"""
        _override_db_with_deployment(client, db, None)

        fake_id = str(uuid.uuid4())
        response = client.put(
            f"/api/v1/deployments/{fake_id}/compose-file",
            json={"content": "version: '3.8'"},
        )
        assert response.status_code == 404

    def test_put_compose_file_missing_content(self, client, db):
        """请求体缺少 content 字段时返回 400"""
        deployment_id = uuid.uuid4()
        deployment = _make_mock_deployment(
            deployment_id=deployment_id,
            config={"_repo_dir": "/tmp/test"},
        )
        _override_db_with_deployment(client, db, deployment)

        response = client.put(
            f"/api/v1/deployments/{deployment_id}/compose-file",
            json={},
        )
        assert response.status_code == 400
        assert "content" in response.json()["detail"].lower()

    def test_put_compose_file_invalid_yaml(self, client, db):
        """保存无效 YAML 时返回 400"""
        deployment_id = uuid.uuid4()
        deployment = _make_mock_deployment(
            deployment_id=deployment_id,
            config={"_repo_dir": "/tmp/test"},
        )
        _override_db_with_deployment(client, db, deployment)

        with patch("app.api.v1.deployments.write_compose_file", side_effect=yaml.YAMLError("Invalid YAML syntax")):
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": "invalid: yaml: ["},
            )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_put_compose_file_server_error(self, client, db):
        """保存 compose 文件时非 YAML 异常返回 500"""
        deployment_id = uuid.uuid4()
        deployment = _make_mock_deployment(
            deployment_id=deployment_id,
            config={"_repo_dir": "/tmp/test"},
        )
        _override_db_with_deployment(client, db, deployment)

        with patch("app.api.v1.deployments.write_compose_file", side_effect=IOError("Permission denied")):
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": "version: '3.8'"},
            )

        assert response.status_code == 500
        assert "failed to save" in response.json()["detail"].lower()


# ========== 验证旧 env-vars API 已删除 ==========

class TestOldEnvVarsApiRemoved:
    """验证旧的 env-vars API 端点已删除（返回 404 表示路由不存在）"""

    def test_old_get_env_vars_removed(self, client):
        """GET /{deployment_id}/env-vars 应返回 404（端点已删除）"""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/deployments/{fake_id}/env-vars")
        assert response.status_code == 404

    def test_old_put_env_vars_removed(self, client):
        """PUT /{deployment_id}/env-vars 应返回 404（端点已删除）"""
        fake_id = str(uuid.uuid4())
        response = client.put(
            f"/api/v1/deployments/{fake_id}/env-vars?service_name=app",
            json={"DB_HOST": "localhost"},
        )
        assert response.status_code == 404

    def test_old_delete_env_var_removed(self, client):
        """DELETE /{deployment_id}/env-vars/{service_name}/{var_name} 应返回 404（端点已删除）"""
        fake_id = str(uuid.uuid4())
        response = client.delete(
            f"/api/v1/deployments/{fake_id}/env-vars/app/DB_HOST",
        )
        assert response.status_code == 404

    def test_confirm_env_vars_still_exists(self, client, db):
        """POST /{deployment_id}/confirm-env-vars 应仍然存在（不返回 404/405）"""
        deployment_id = uuid.uuid4()
        deployment = _make_mock_deployment(
            deployment_id=deployment_id,
            config={"_repo_dir": "/tmp/test"},
        )
        _override_db_with_deployment(client, db, deployment)

        # confirm-env-vars 端点仍应存在，虽然可能因状态不对返回 400
        # 但不应该返回 404 或 405
        response = client.post(f"/api/v1/deployments/{deployment_id}/confirm-env-vars")
        assert response.status_code != 404
        assert response.status_code != 405
