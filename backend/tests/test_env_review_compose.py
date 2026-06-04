import os
import tempfile
import pytest
from app.services.deployer.services.env_review import (
    read_compose_service_env,
    update_compose_service_env,
    delete_compose_service_env_var,
)

SAMPLE_COMPOSE = """version: '3.8'

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

@pytest.fixture
def repo_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "docker-compose.yml"), "w") as f:
            f.write(SAMPLE_COMPOSE)
        yield tmpdir

def test_read_compose_service_env(repo_dir):
    result = read_compose_service_env(repo_dir, "app")
    assert "DB_HOST" in result
    assert result["DB_HOST"]["value"] == "localhost"
    assert result["DB_HOST"]["source"] == "docker-compose.yml"

def test_read_compose_service_env_mysql(repo_dir):
    result = read_compose_service_env(repo_dir, "mysql")
    assert "MYSQL_ROOT_PASSWORD" in result
    assert result["MYSQL_ROOT_PASSWORD"]["value"] == "root123"

def test_update_compose_service_env(repo_dir):
    env_vars = {
        "DB_HOST": {"value": "192.168.1.100", "source": "user"},
        "DB_PORT": {"value": "3307", "source": "user"},
    }
    success = update_compose_service_env(repo_dir, "app", env_vars)
    assert success is True

    # 验证更新后的内容
    result = read_compose_service_env(repo_dir, "app")
    assert result["DB_HOST"]["value"] == "192.168.1.100"
    assert result["DB_PORT"]["value"] == "3307"

def test_delete_compose_service_env_var(repo_dir):
    success = delete_compose_service_env_var(repo_dir, "app", "DB_HOST")
    assert success is True

    # 验证删除后的内容
    result = read_compose_service_env(repo_dir, "app")
    assert "DB_HOST" not in result
    assert "DB_PORT" in result
