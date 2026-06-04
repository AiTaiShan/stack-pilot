"""测试 read_compose_file 和 write_compose_file 函数"""
import pytest
import os
import tempfile
import yaml
from app.services.deployer.services.env_review import read_compose_file, write_compose_file


def test_read_compose_file_success():
    """测试读取存在的 docker-compose.yml 文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        compose_path = os.path.join(tmpdir, "docker-compose.yml")
        with open(compose_path, "w") as f:
            f.write("version: '3.8'\nservices:\n  app:\n    image: test")

        content = read_compose_file(tmpdir)
        assert "version: '3.8'" in content
        assert "services:" in content


def test_read_compose_file_not_found():
    """测试读取不存在的文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(FileNotFoundError):
            read_compose_file(tmpdir)


def test_write_compose_file_success():
    """测试写入有效的 YAML 内容"""
    with tempfile.TemporaryDirectory() as tmpdir:
        compose_path = os.path.join(tmpdir, "docker-compose.yml")
        with open(compose_path, "w") as f:
            f.write("version: '3.8'\nservices: {}")

        new_content = "version: '3.8'\nservices:\n  app:\n    image: test"
        result = write_compose_file(tmpdir, new_content)

        assert result is True
        with open(compose_path, "r") as f:
            assert f.read() == new_content


def test_write_compose_file_invalid_yaml():
    """测试写入无效的 YAML 内容"""
    with tempfile.TemporaryDirectory() as tmpdir:
        compose_path = os.path.join(tmpdir, "docker-compose.yml")
        with open(compose_path, "w") as f:
            f.write("version: '3.8'\nservices: {}")

        invalid_yaml = "version: '3.8'\nservices:\n  app:\n    image: test\n    invalid: ["

        with pytest.raises(yaml.YAMLError):
            write_compose_file(tmpdir, invalid_yaml)

        # 验证原文件内容未被破坏
        with open(compose_path, "r") as f:
            assert f.read() == "version: '3.8'\nservices: {}"
