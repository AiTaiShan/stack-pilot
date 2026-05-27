import pytest
import os
import json
import tempfile
from app.services.scanner.scanner_service import ScannerService


def test_scan_tech_stack_nodejs():
    """测试Node.js项目识别"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建模拟的package.json
        package_json = {
            "name": "test-app",
            "dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"},
            "devDependencies": {"vite": "^5.0.0"}
        }
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump(package_json, f)

        scanner = ScannerService()
        result = scanner.scan_tech_stack(tmpdir)

        assert result["language"] == "javascript"
        assert result["framework"] == "react"
        assert result["package_manager"] == "npm"
        assert "react" in result["dependencies"]


def test_scan_tech_stack_python():
    """测试Python项目识别"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建模拟的requirements.txt
        with open(os.path.join(tmpdir, "requirements.txt"), "w") as f:
            f.write("fastapi==0.104.1\nuvicorn==0.24.0\nsqlalchemy==2.0.23\n")

        scanner = ScannerService()
        result = scanner.scan_tech_stack(tmpdir)

        assert result["language"] == "python"
        assert result["framework"] == "fastapi"
        assert result["package_manager"] == "pip"
        assert "fastapi" in result["dependencies"]


def test_scan_tech_stack_java():
    """测试Java项目识别"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write("<project></project>")

        scanner = ScannerService()
        result = scanner.scan_tech_stack(tmpdir)

        assert result["language"] == "java"
        assert result["build_tool"] == "maven"


def test_scan_tech_stack_go():
    """测试Go项目识别"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "go.mod"), "w") as f:
            f.write("module test\n")

        scanner = ScannerService()
        result = scanner.scan_tech_stack(tmpdir)

        assert result["language"] == "go"
        assert result["build_tool"] == "go"


def test_scan_config_files():
    """测试配置文件扫描"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, ".env"), "w") as f:
            f.write("DEBUG=true\n")
        with open(os.path.join(tmpdir, "Dockerfile"), "w") as f:
            f.write("FROM python:3.11\n")

        scanner = ScannerService()
        result = scanner.scan_config_files(tmpdir)

        assert ".env" in result
        assert "Dockerfile" in result
        assert result[".env"] == "DEBUG=true\n"
