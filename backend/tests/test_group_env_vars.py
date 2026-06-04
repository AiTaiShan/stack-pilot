import os
import tempfile
import pytest
from app.services.deployer.steps.review_step import _group_env_vars_by_service


@pytest.fixture
def repo_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_group_env_vars_with_pending(repo_dir):
    pending = [
        {"name": "DB_HOST", "file": "application.yml", "line": 5, "style": "spring"},
        {"name": "REDIS_HOST", "file": "application.yml", "line": 10, "style": "spring"},
    ]
    deps = {"external_services": []}
    result = _group_env_vars_by_service(repo_dir, pending, deps)
    assert "app" in result
    assert "DB_HOST" in result["app"]["env_vars"]
    assert "REDIS_HOST" in result["app"]["env_vars"]


def test_group_env_vars_with_deps(repo_dir):
    pending = [{"name": "DB_HOST", "file": "application.yml", "line": 5, "style": "spring"}]
    deps = {"external_services": ["mysql"]}

    # 创建模拟的 docker-compose.yml
    compose_content = """version: '3.8'
services:
  mysql:
    image: mysql:8
    environment:
      - MYSQL_ROOT_PASSWORD=root123
"""
    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose_content)

    result = _group_env_vars_by_service(repo_dir, pending, deps)
    assert "app" in result
    assert "mysql" in result
    assert "MYSQL_ROOT_PASSWORD" in result["mysql"]["env_vars"]


def test_group_env_vars_empty_pending(repo_dir):
    pending = []
    deps = {"external_services": []}
    result = _group_env_vars_by_service(repo_dir, pending, deps)
    assert "app" in result
    assert result["app"]["env_vars"] == {}


def test_group_env_vars_source_info(repo_dir):
    pending = [
        {"name": "DB_HOST", "file": "src/application.yml", "line": 5, "style": "spring"},
    ]
    deps = {"external_services": []}
    result = _group_env_vars_by_service(repo_dir, pending, deps)
    assert result["app"]["env_vars"]["DB_HOST"]["source"] == "src/application.yml:5"


def test_group_env_vars_multiple_services(repo_dir):
    pending = [{"name": "DB_HOST", "file": "application.yml", "line": 5, "style": "spring"}]
    deps = {"external_services": ["mysql", "redis"]}

    compose_content = """version: '3.8'
services:
  mysql:
    image: mysql:8
    environment:
      - MYSQL_ROOT_PASSWORD=root123
  redis:
    image: redis:7-alpine
    environment:
      - REDIS_PASSWORD=redis123
"""
    with open(os.path.join(repo_dir, "docker-compose.yml"), "w") as f:
        f.write(compose_content)

    result = _group_env_vars_by_service(repo_dir, pending, deps)
    assert "app" in result
    assert "mysql" in result
    assert "redis" in result
    assert "MYSQL_ROOT_PASSWORD" in result["mysql"]["env_vars"]
    assert "REDIS_PASSWORD" in result["redis"]["env_vars"]
