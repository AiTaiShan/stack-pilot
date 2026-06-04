"""test_compose_file_integration.py — compose 文件审核流程集成测试

测试完整的 API 端到端流程：
1. 使用真实文件 I/O（tmp_path）而非 mock 读写函数
2. 测试完整的 GET → PUT → GET 审核流程
3. 测试 YAML 验证、文件不存在等边界场景
4. 测试环境变量审核确认流程

注意：由于 SQLite 不支持 PostgreSQL UUID 类型的参数比较，
数据库查询层使用 MagicMock 覆盖（与 test_compose_file_api.py 相同策略），
但 compose 文件的读写使用真实文件系统操作，是真正的集成测试。
"""
import os
import uuid
import tempfile
from unittest.mock import MagicMock

import pytest
import yaml

from app.models.deployment import Deployment, DeploymentStatus


# ========== 辅助函数 ==========

def _make_deployment(deployment_id=None, config=None, status=None):
    """创建一个模拟的 Deployment 对象，config 中指向真实临时目录"""
    dep = MagicMock()
    dep.id = deployment_id or uuid.uuid4()
    dep.config = config or {}
    dep.status = status or DeploymentStatus.WAITING_REVIEW
    return dep


def _override_db_query(client, db, deployment):
    """用 mock 覆盖 db.query，让 Deployment 查询返回指定对象"""
    original_query = db.query

    def mock_query(model):
        if model == Deployment:
            mock_result = MagicMock()
            mock_result.first.return_value = deployment
            mock_result.filter.return_value.first.return_value = deployment
            return mock_result
        return original_query(model)

    db.query = mock_query


def _write_compose_file(tmpdir, content=None):
    """在临时目录中创建 docker-compose.yml 文件"""
    if content is None:
        content = (
            "version: '3.8'\n"
            "services:\n"
            "  app:\n"
            "    image: myapp:latest\n"
            "    ports:\n"
            "      - '8080:80'\n"
            "    environment:\n"
            "      - DB_HOST=localhost\n"
            "      - DB_PORT=5432\n"
            "      - APP_ENV=production\n"
        )
    compose_path = os.path.join(tmpdir, "docker-compose.yml")
    with open(compose_path, "w") as f:
        f.write(content)
    return content


# ========== 集成测试 1: 完整的 compose 文件审核流程 ==========

class TestFullComposeFileReviewFlow:
    """测试完整的 compose 文件审核流程"""

    def test_full_compose_file_review_flow(self, client, db):
        """测试完整的 compose 文件审核流程：
        1. 创建临时目录和初始 compose 文件
        2. GET 获取 compose 文件内容
        3. PUT 修改并保存 compose 文件
        4. GET 再次读取，验证修改已保存到磁盘
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            original_content = _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            # 1. GET 获取 compose 文件内容
            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200
            assert "myapp:latest" in data["data"]["content"]
            assert "DB_HOST=localhost" in data["data"]["content"]

            # 2. PUT 修改 compose 文件内容
            modified_content = (
                "version: '3.8'\n"
                "services:\n"
                "  app:\n"
                "    image: myapp:v2.0\n"
                "    ports:\n"
                "      - '8080:80'\n"
                "    environment:\n"
                "      - DB_HOST=db-server\n"
                "      - DB_PORT=5432\n"
                "      - APP_ENV=staging\n"
                "      - NEW_VAR=hello\n"
            )
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": modified_content},
            )
            assert response.status_code == 200
            assert response.json()["data"]["saved"] is True

            # 3. 验证文件在磁盘上已被更新
            compose_path = os.path.join(tmpdir, "docker-compose.yml")
            with open(compose_path, "r") as f:
                disk_content = f.read()
            assert disk_content == modified_content
            assert "myapp:v2.0" in disk_content
            assert "DB_HOST=db-server" in disk_content

            # 4. GET 再次读取，确认返回修改后的内容
            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")
            assert response.status_code == 200
            assert response.json()["data"]["content"] == modified_content

    def test_full_flow_with_env_review_confirmation(self, client, db):
        """测试完整的环境变量审核确认流程：
        1. 创建处于 waiting_review 状态的部署
        2. 修改 compose 文件中的环境变量
        3. 确认环境变量审核
        4. 验证 config 中的 env_vars_confirmed 标志
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
                status=DeploymentStatus.WAITING_REVIEW,
            )
            _override_db_query(client, db, deployment)

            # 1. 修改环境变量
            modified_content = (
                "version: '3.8'\n"
                "services:\n"
                "  app:\n"
                "    image: myapp:latest\n"
                "    ports:\n"
                "      - '8080:80'\n"
                "    environment:\n"
                "      - DB_HOST=new-db-server\n"
                "      - DB_PORT=3306\n"
                "      - APP_ENV=production\n"
            )
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": modified_content},
            )
            assert response.status_code == 200

            # 2. 确认环境变量审核
            response = client.post(f"/api/v1/deployments/{deployment_id}/confirm-env-vars")
            # confirm-env-vars 端点应可达（不返回 404/405）
            assert response.status_code != 404
            assert response.status_code != 405

            # 3. 验证 config 中的标志已设置
            config = deployment.config or {}
            assert config.get("env_vars_confirmed") is True


# ========== 集成测试 2: YAML 验证 ==========

class TestYamlValidation:
    """测试 YAML 格式验证"""

    def test_invalid_yaml_rejected(self, client, db):
        """测试无效的 YAML 被拒绝，返回 400 错误"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            # 保存无效的 YAML
            invalid_yaml = "version: '3.8'\nservices:\n  app:\n    image: test\n    invalid: ["
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": invalid_yaml},
            )
            assert response.status_code == 400
            assert "invalid" in response.json()["detail"].lower()

            # 验证原始文件未被破坏
            compose_path = os.path.join(tmpdir, "docker-compose.yml")
            with open(compose_path, "r") as f:
                content = f.read()
            assert content == original

    def test_empty_content_rejected(self, client, db):
        """测试空内容被拒绝"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": ""},
            )
            assert response.status_code == 400

    def test_missing_content_field_rejected(self, client, db):
        """测试请求体缺少 content 字段被拒绝"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={},
            )
            assert response.status_code == 400
            assert "content" in response.json()["detail"].lower()

    def test_valid_yaml_accepted(self, client, db):
        """测试各种有效的 YAML 被接受"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            valid_yaml = (
                "version: '3.8'\n"
                "services:\n"
                "  web:\n"
                "    image: nginx:alpine\n"
                "    ports:\n"
                "      - '443:443'\n"
                "  db:\n"
                "    image: postgres:15\n"
                "    environment:\n"
                "      POSTGRES_PASSWORD: secret\n"
            )
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": valid_yaml},
            )
            assert response.status_code == 200
            assert response.json()["data"]["saved"] is True

            # 验证内容已被正确保存并可读取
            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")
            assert response.status_code == 200
            content = response.json()["data"]["content"]
            assert "nginx:alpine" in content
            assert "postgres:15" in content


# ========== 集成测试 3: 文件不存在场景 ==========

class TestComposeFileNotFound:
    """测试 compose 文件不存在时的处理"""

    def test_compose_file_not_found_on_get(self, client, db):
        """测试获取不存在的 compose 文件时返回 404"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 不创建 docker-compose.yml 文件
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")
            assert response.status_code == 404

    def test_deployment_not_found(self, client, db):
        """测试部署记录不存在时返回 404"""
        _override_db_query(client, db, None)
        fake_id = str(uuid.uuid4())

        # GET
        response = client.get(f"/api/v1/deployments/{fake_id}/compose-file")
        assert response.status_code == 404

        # PUT
        response = client.put(
            f"/api/v1/deployments/{fake_id}/compose-file",
            json={"content": "version: '3.8'\nservices: {}"},
        )
        assert response.status_code == 404

    def test_deleted_compose_file_returns_404(self, client, db):
        """测试 compose 文件被删除后返回 404"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            # 先确认可以读取
            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")
            assert response.status_code == 200

            # 删除文件
            compose_path = os.path.join(tmpdir, "docker-compose.yml")
            os.remove(compose_path)

            # 再次读取应返回 404
            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")
            assert response.status_code == 404

    def test_compose_file_not_found_on_put_creates_new(self, client, db):
        """测试 PUT 时如果文件不存在，应创建新文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 不创建初始文件
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            new_content = "version: '3.8'\nservices:\n  app:\n    image: new-image\n"
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": new_content},
            )
            # write_compose_file 使用 open("w") 创建新文件
            assert response.status_code == 200
            assert response.json()["data"]["saved"] is True

            # 验证文件已被创建
            compose_path = os.path.join(tmpdir, "docker-compose.yml")
            assert os.path.exists(compose_path)
            with open(compose_path, "r") as f:
                assert f.read() == new_content


# ========== 集成测试 4: 多次读写的鲁棒性 ==========

class TestRobustness:
    """测试多次读写的鲁棒性"""

    def test_multiple_read_write_cycles(self, client, db):
        """测试多次读写不会损坏文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            # 多次写入不同内容
            for i in range(5):
                content = (
                    f"version: '3.8'\n"
                    f"services:\n"
                    f"  app:\n"
                    f"    image: myapp:v{i}\n"
                    f"    environment:\n"
                    f"      - ITERATION={i}\n"
                )
                response = client.put(
                    f"/api/v1/deployments/{deployment_id}/compose-file",
                    json={"content": content},
                )
                assert response.status_code == 200

                # 每次写入后读取验证
                response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")
                assert response.status_code == 200
                read_content = response.json()["data"]["content"]
                assert f"myapp:v{i}" in read_content
                assert f"ITERATION={i}" in read_content

    def test_compose_with_complex_yaml(self, client, db):
        """测试包含复杂 YAML 结构的 compose 文件能正确读写"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_compose_file(tmpdir)
            deployment_id = uuid.uuid4()
            deployment = _make_deployment(
                deployment_id=deployment_id,
                config={"_repo_dir": tmpdir},
            )
            _override_db_query(client, db, deployment)

            complex_yaml = """version: '3.8'
services:
  web:
    image: nginx:alpine
    ports:
      - "8080:80"
      - "8443:443"
    volumes:
      - ./html:/usr/share/nginx/html
    environment:
      NGINX_HOST: localhost
      NGINX_PORT: "80"
    depends_on:
      - api
    networks:
      - frontend
  api:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgres://user:pass@db:5432/mydb
      REDIS_URL: redis://redis:6379
      SECRET_KEY: "my secret: with colon"
    networks:
      - frontend
      - backend
  db:
    image: postgres:15
    volumes:
      - db_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: mydb
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    networks:
      - backend
volumes:
  db_data:
networks:
  frontend:
  backend:
"""
            response = client.put(
                f"/api/v1/deployments/{deployment_id}/compose-file",
                json={"content": complex_yaml},
            )
            assert response.status_code == 200
            assert response.json()["data"]["saved"] is True

            # 读取并验证 YAML 可被正确解析
            response = client.get(f"/api/v1/deployments/{deployment_id}/compose-file")
            assert response.status_code == 200
            content = response.json()["data"]["content"]

            parsed = yaml.safe_load(content)
            assert "services" in parsed
            assert "web" in parsed["services"]
            assert "api" in parsed["services"]
            assert "db" in parsed["services"]
            assert "volumes" in parsed
            assert "networks" in parsed

            # 验证包含冒号的值被正确保留
            api_env = parsed["services"]["api"]["environment"]
            assert api_env["DATABASE_URL"] == "postgres://user:pass@db:5432/mydb"
