"""test_env_review_compose.py — env_review compose 文件读写工具的测试"""
import os
import tempfile
import pytest
from app.services.deployer.services.env_review import (
    read_compose_service_env,
    update_compose_service_env,
    delete_compose_service_env_var,
)


# ========== 测试数据 ==========

SAMPLE_COMPOSE_LIST = """\
version: '3.8'

services:
  app:
    image: myapp:latest
    ports:
      - "8080:8080"
    environment:
      - DB_HOST=localhost
      - DB_PORT=3306
      - REDIS_HOST=localhost

  mysql:
    image: mysql:8
    environment:
      - MYSQL_ROOT_PASSWORD=root123
      - MYSQL_DATABASE=mydb

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
"""

SAMPLE_COMPOSE_DICT = """\
version: '3.8'

services:
  app:
    image: myapp:latest
    ports:
      - "8080:8080"
    environment:
      DB_HOST: localhost
      DB_PORT: 3306
      REDIS_HOST: localhost

  mysql:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: root123
      MYSQL_DATABASE: mydb

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
"""

SAMPLE_COMPOSE_VALUE_WITH_EQUALS = """\
version: '3.8'

services:
  app:
    image: myapp:latest
    environment:
      - DB_URL=postgres://user:pass@host:5432/db?opt=1
      - SIMPLE=value
"""


# ========== Fixtures ==========

@pytest.fixture
def repo_dir_list():
    """list 格式的 compose 文件临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "docker-compose.yml"), "w") as f:
            f.write(SAMPLE_COMPOSE_LIST)
        yield tmpdir


@pytest.fixture
def repo_dir_dict():
    """dict 格式的 compose 文件临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "docker-compose.yml"), "w") as f:
            f.write(SAMPLE_COMPOSE_DICT)
        yield tmpdir


@pytest.fixture
def repo_dir_equals():
    """包含等号值的 compose 文件临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "docker-compose.yml"), "w") as f:
            f.write(SAMPLE_COMPOSE_VALUE_WITH_EQUALS)
        yield tmpdir


@pytest.fixture
def repo_dir_empty():
    """不存在 compose 文件的临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# ================================================================
# 读取测试
# ================================================================

class TestReadComposeServiceEnv:
    """read_compose_service_env 测试"""

    def test_read_list_format(self, repo_dir_list):
        """list 格式：读取所有环境变量"""
        result = read_compose_service_env(repo_dir_list, "app")
        assert "DB_HOST" in result
        assert result["DB_HOST"]["value"] == "localhost"
        assert result["DB_HOST"]["source"] == "docker-compose.yml"
        assert "DB_PORT" in result
        assert result["DB_PORT"]["value"] == "3306"
        assert "REDIS_HOST" in result

    def test_read_list_format_mysql(self, repo_dir_list):
        """list 格式：读取 mysql 服务"""
        result = read_compose_service_env(repo_dir_list, "mysql")
        assert "MYSQL_ROOT_PASSWORD" in result
        assert result["MYSQL_ROOT_PASSWORD"]["value"] == "root123"
        assert "MYSQL_DATABASE" in result
        assert result["MYSQL_DATABASE"]["value"] == "mydb"

    def test_read_dict_format(self, repo_dir_dict):
        """dict 格式：读取所有环境变量"""
        result = read_compose_service_env(repo_dir_dict, "app")
        assert "DB_HOST" in result
        assert result["DB_HOST"]["value"] == "localhost"
        assert result["DB_HOST"]["source"] == "docker-compose.yml"
        assert "DB_PORT" in result
        assert result["DB_PORT"]["value"] == "3306"

    def test_read_dict_format_mysql(self, repo_dir_dict):
        """dict 格式：读取 mysql 服务"""
        result = read_compose_service_env(repo_dir_dict, "mysql")
        assert "MYSQL_ROOT_PASSWORD" in result
        assert result["MYSQL_ROOT_PASSWORD"]["value"] == "root123"

    def test_read_value_with_equals(self, repo_dir_equals):
        """值中包含等号：正确解析"""
        result = read_compose_service_env(repo_dir_equals, "app")
        assert "DB_URL" in result
        # split("=", 1) 只在第一个等号处分割
        assert result["DB_URL"]["value"] == "postgres://user:pass@host:5432/db?opt=1"
        assert "SIMPLE" in result
        assert result["SIMPLE"]["value"] == "value"

    def test_read_nonexistent_service(self, repo_dir_list):
        """读取不存在的服务：返回空 dict"""
        result = read_compose_service_env(repo_dir_list, "nonexistent")
        assert result == {}

    def test_read_service_without_env(self, repo_dir_list):
        """读取没有 environment 的服务：返回空 dict"""
        result = read_compose_service_env(repo_dir_list, "redis")
        assert result == {}

    def test_read_no_compose_file(self, repo_dir_empty):
        """compose 文件不存在：返回空 dict"""
        result = read_compose_service_env(repo_dir_empty, "app")
        assert result == {}


# ================================================================
# 更新测试
# ================================================================

class TestUpdateComposeServiceEnv:
    """update_compose_service_env 测试"""

    def test_update_list_format(self, repo_dir_list):
        """list 格式：更新现有变量"""
        env_vars = {
            "DB_HOST": {"value": "192.168.1.100", "source": "user"},
            "DB_PORT": {"value": "3307", "source": "user"},
        }
        success = update_compose_service_env(repo_dir_list, "app", env_vars)
        assert success is True

        # 验证更新后的内容
        result = read_compose_service_env(repo_dir_list, "app")
        assert result["DB_HOST"]["value"] == "192.168.1.100"
        assert result["DB_PORT"]["value"] == "3307"
        # 未修改的变量保持不变
        assert result["REDIS_HOST"]["value"] == "localhost"

    def test_update_list_format_preserves_format(self, repo_dir_list):
        """list 格式：更新后文件保持 list 格式"""
        env_vars = {"DB_HOST": {"value": "newhost", "source": "user"}}
        update_compose_service_env(repo_dir_list, "app", env_vars)

        with open(os.path.join(repo_dir_list, "docker-compose.yml"), "r") as f:
            content = f.read()

        # environment 后应该是 list 格式（- KEY=VALUE）
        assert "- DB_HOST=newhost" in content
        assert "- DB_PORT=3306" in content

    def test_update_dict_format(self, repo_dir_dict):
        """dict 格式：更新现有变量"""
        env_vars = {
            "DB_HOST": {"value": "192.168.1.100", "source": "user"},
            "DB_PORT": {"value": "3307", "source": "user"},
        }
        success = update_compose_service_env(repo_dir_dict, "app", env_vars)
        assert success is True

        result = read_compose_service_env(repo_dir_dict, "app")
        assert result["DB_HOST"]["value"] == "192.168.1.100"
        assert result["DB_PORT"]["value"] == "3307"
        assert result["REDIS_HOST"]["value"] == "localhost"

    def test_update_dict_format_preserves_format(self, repo_dir_dict):
        """dict 格式：更新后文件保持 dict 格式"""
        env_vars = {"DB_HOST": {"value": "newhost", "source": "user"}}
        update_compose_service_env(repo_dir_dict, "app", env_vars)

        with open(os.path.join(repo_dir_dict, "docker-compose.yml"), "r") as f:
            content = f.read()

        # environment 后应该是 dict 格式（KEY: VALUE）
        assert "DB_HOST: newhost" in content
        assert "DB_PORT: 3306" in content

    def test_update_preserves_non_env_content(self, repo_dir_list):
        """更新后保留文件中非 environment 部分的内容"""
        env_vars = {"DB_HOST": {"value": "newhost", "source": "user"}}
        update_compose_service_env(repo_dir_list, "app", env_vars)

        with open(os.path.join(repo_dir_list, "docker-compose.yml"), "r") as f:
            content = f.read()

        # 其他服务不变
        assert "mysql:" in content
        assert "MYSQL_ROOT_PASSWORD=root123" in content
        assert "redis:" in content
        # image 等字段不变
        assert "image: myapp:latest" in content
        assert 'ports:' in content

    def test_update_adds_new_variable(self, repo_dir_list):
        """更新时添加新变量"""
        env_vars = {"NEW_VAR": {"value": "new_value", "source": "user"}}
        success = update_compose_service_env(repo_dir_list, "app", env_vars)
        assert success is True

        result = read_compose_service_env(repo_dir_list, "app")
        assert result["NEW_VAR"]["value"] == "new_value"
        # 原有变量不变
        assert result["DB_HOST"]["value"] == "localhost"

    def test_update_nonexistent_service(self, repo_dir_list):
        """更新不存在的服务：返回 False"""
        env_vars = {"DB_HOST": {"value": "new", "source": "user"}}
        success = update_compose_service_env(repo_dir_list, "nonexistent", env_vars)
        assert success is False

    def test_update_no_compose_file(self, repo_dir_empty):
        """compose 文件不存在：返回 False"""
        env_vars = {"DB_HOST": {"value": "new", "source": "user"}}
        success = update_compose_service_env(repo_dir_empty, "app", env_vars)
        assert success is False


# ================================================================
# 删除测试
# ================================================================

class TestDeleteComposeServiceEnvVar:
    """delete_compose_service_env_var 测试"""

    def test_delete_list_format(self, repo_dir_list):
        """list 格式：删除现有变量"""
        success = delete_compose_service_env_var(repo_dir_list, "app", "DB_HOST")
        assert success is True

        result = read_compose_service_env(repo_dir_list, "app")
        assert "DB_HOST" not in result
        assert "DB_PORT" in result
        assert "REDIS_HOST" in result

    def test_delete_list_format_preserves_format(self, repo_dir_list):
        """list 格式：删除后文件保持 list 格式"""
        delete_compose_service_env_var(repo_dir_list, "app", "DB_HOST")

        with open(os.path.join(repo_dir_list, "docker-compose.yml"), "r") as f:
            content = f.read()

        # 仍然是 list 格式
        assert "- DB_PORT=3306" in content
        assert "- REDIS_HOST=localhost" in content
        assert "DB_HOST" not in content

    def test_delete_dict_format(self, repo_dir_dict):
        """dict 格式：删除现有变量"""
        success = delete_compose_service_env_var(repo_dir_dict, "app", "DB_HOST")
        assert success is True

        result = read_compose_service_env(repo_dir_dict, "app")
        assert "DB_HOST" not in result
        assert "DB_PORT" in result
        assert "REDIS_HOST" in result

    def test_delete_dict_format_preserves_format(self, repo_dir_dict):
        """dict 格式：删除后文件保持 dict 格式"""
        delete_compose_service_env_var(repo_dir_dict, "app", "DB_HOST")

        with open(os.path.join(repo_dir_dict, "docker-compose.yml"), "r") as f:
            content = f.read()

        # 仍然是 dict 格式
        assert "DB_PORT: 3306" in content
        assert "REDIS_HOST: localhost" in content
        assert "DB_HOST" not in content

    def test_delete_nonexistent_var_in_list(self, repo_dir_list):
        """list 格式：删除不存在的变量，返回 False"""
        success = delete_compose_service_env_var(repo_dir_list, "app", "NONEXISTENT")
        assert success is False

        # 文件内容不应被修改
        result = read_compose_service_env(repo_dir_list, "app")
        assert "DB_HOST" in result
        assert "DB_PORT" in result
        assert "REDIS_HOST" in result

    def test_delete_nonexistent_var_in_dict(self, repo_dir_dict):
        """dict 格式：删除不存在的变量，返回 False"""
        success = delete_compose_service_env_var(repo_dir_dict, "app", "NONEXISTENT")
        assert success is False

        result = read_compose_service_env(repo_dir_dict, "app")
        assert "DB_HOST" in result
        assert "DB_PORT" in result

    def test_delete_nonexistent_service(self, repo_dir_list):
        """删除不存在的服务中的变量：返回 False"""
        success = delete_compose_service_env_var(repo_dir_list, "nonexistent", "DB_HOST")
        assert success is False

    def test_delete_no_compose_file(self, repo_dir_empty):
        """compose 文件不存在：返回 False"""
        success = delete_compose_service_env_var(repo_dir_empty, "app", "DB_HOST")
        assert success is False

    def test_delete_preserves_other_services(self, repo_dir_list):
        """删除操作不影响其他服务"""
        delete_compose_service_env_var(repo_dir_list, "app", "DB_HOST")

        result_mysql = read_compose_service_env(repo_dir_list, "mysql")
        assert "MYSQL_ROOT_PASSWORD" in result_mysql
        assert result_mysql["MYSQL_ROOT_PASSWORD"]["value"] == "root123"


# ================================================================
# 格式保留集成测试
# ================================================================

class TestFormatPreservation:
    """验证正则替换保留文件原始格式"""

    def test_update_then_read_roundtrip_list(self, repo_dir_list):
        """list 格式：更新后再读取，数据一致"""
        env_vars = {
            "DB_HOST": {"value": "newhost", "source": "user"},
            "NEW_VAR": {"value": "newval", "source": "user"},
        }
        update_compose_service_env(repo_dir_list, "app", env_vars)
        result = read_compose_service_env(repo_dir_list, "app")

        assert result["DB_HOST"]["value"] == "newhost"
        assert result["DB_PORT"]["value"] == "3306"
        assert result["REDIS_HOST"]["value"] == "localhost"
        assert result["NEW_VAR"]["value"] == "newval"

    def test_update_then_read_roundtrip_dict(self, repo_dir_dict):
        """dict 格式：更新后再读取，数据一致"""
        env_vars = {
            "DB_HOST": {"value": "newhost", "source": "user"},
            "NEW_VAR": {"value": "newval", "source": "user"},
        }
        update_compose_service_env(repo_dir_dict, "app", env_vars)
        result = read_compose_service_env(repo_dir_dict, "app")

        assert result["DB_HOST"]["value"] == "newhost"
        assert result["DB_PORT"]["value"] == "3306"
        assert result["NEW_VAR"]["value"] == "newval"

    def test_delete_then_read_roundtrip(self, repo_dir_list):
        """删除后再读取，数据一致"""
        delete_compose_service_env_var(repo_dir_list, "app", "DB_PORT")
        result = read_compose_service_env(repo_dir_list, "app")

        assert "DB_HOST" in result
        assert "DB_PORT" not in result
        assert "REDIS_HOST" in result

    def test_preserves_version_line(self, repo_dir_list):
        """保留 version 行"""
        env_vars = {"DB_HOST": {"value": "new", "source": "user"}}
        update_compose_service_env(repo_dir_list, "app", env_vars)

        with open(os.path.join(repo_dir_list, "docker-compose.yml"), "r") as f:
            content = f.read()

        assert "version: '3.8'" in content

    def test_value_with_equals_sign(self, repo_dir_equals):
        """值中包含等号：更新后正确保留"""
        env_vars = {"DB_URL": {"value": "postgres://host/db?ssl=true&timeout=30", "source": "user"}}
        success = update_compose_service_env(repo_dir_equals, "app", env_vars)
        assert success is True

        result = read_compose_service_env(repo_dir_equals, "app")
        assert result["DB_URL"]["value"] == "postgres://host/db?ssl=true&timeout=30"
