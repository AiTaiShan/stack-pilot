#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成测试 -- 8 种语言探测器 + 模板 + 非功能测试

依赖 fixtures/scanner/ 目录下的夹具项目。
"""

import pytest
import os
import time
from app.services.scanner.detector import detect
from app.services.scanner.templates import (
    node_template, python_template, go_template,
    java_template, rust_template, php_template,
    ruby_template, dotnet_template
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "scanner")


def _fixture_path(name):
    return os.path.join(FIXTURES_DIR, name)


# ───────── 单体项目检测 ─────────

@pytest.mark.parametrize("fixture,exp_type,exp_lang,exp_entry", [
    ("node-single", "single", "node", "index.js"),
    ("python-single", "single", "python", "app.py"),
    ("go-single", "single", "go", "main.go"),
    ("java-single", "single", "java", None),
    ("rust-single", "single", "rust", "src/main.rs"),
    ("php-single", "single", "php", "index.php"),
    ("ruby-single", "single", "ruby", "config.ru"),
    ("dotnet-single", "single", "dotnet", "Program.cs"),
])
def test_single_language_detection(fixture, exp_type, exp_lang, exp_entry):
    """验证每个语言的单体项目检测结果"""
    path = _fixture_path(fixture)
    if not os.path.isdir(path):
        pytest.skip(f"Fixture {fixture} not found")
    result = detect(path)
    assert result.project_type == exp_type, (
        f"{fixture}: expected project_type={exp_type}, got {result.project_type}"
    )
    assert result.language == exp_lang, (
        f"{fixture}: expected language={exp_lang}, got {result.language}"
    )
    if exp_entry:
        assert result.entry_point == exp_entry, (
            f"{fixture}: expected entry_point={exp_entry}, got {result.entry_point}"
        )


# ───────── 组合项目检测 ─────────

def test_spring_cloud_multi_module():
    """验证 Spring Cloud 多模块项目检测"""
    path = _fixture_path("spring-cloud-multi-module")
    if not os.path.isdir(path):
        pytest.skip("Fixture not found")
    result = detect(path)
    assert result.project_type == "multi-module-java", (
        f"expected multi-module-java, got {result.project_type}"
    )
    assert len(result.services) >= 2, (
        f"expected >=2 services, got {len(result.services)}"
    )


def test_microservices():
    """验证微服务项目检测"""
    path = _fixture_path("microservices")
    if not os.path.isdir(path):
        pytest.skip("Fixture not found")
    result = detect(path)
    assert result.project_type == "microservices", (
        f"expected microservices, got {result.project_type}"
    )
    assert len(result.services) >= 2, (
        f"expected >=2 services, got {len(result.services)}"
    )


def test_monorepo():
    """验证前后端分离项目检测"""
    path = _fixture_path("monorepo")
    if not os.path.isdir(path):
        pytest.skip("Fixture not found")
    result = detect(path)
    assert result.project_type == "monorepo", (
        f"expected monorepo, got {result.project_type}"
    )
    assert result.frontend is not None, "frontend should not be None"
    assert result.backend is not None, "backend should not be None"


# ───────── 模板生成测试 ─────────

def test_template_generation_for_all_languages():
    """验证所有语言模板正确生成包含 EXPOSE 指令的 Dockerfile"""
    templates = [
        (node_template, 3000),
        (python_template, 8000),
        (go_template, 8080),
        (java_template, 8080),
        (rust_template, 8080),
        (php_template, 80),
        (ruby_template, 3000),
        (dotnet_template, 5000),
    ]
    for mod, port in templates:
        lang_name = getattr(mod, "__name__", str(mod))
        df = mod.generate(
            port=port,
            build_cmd="build",
            start_cmd="start",
            framework=""
        )
        assert "EXPOSE" in df, f"{lang_name}: no EXPOSE instruction"
        assert str(port) in df, f"{lang_name}: port {port} not in Dockerfile"


# ───────── 非功能测试 ─────────

def test_key_files_size_limit(tmpdir):
    """验证 key_files 总大小不超过 20KB"""
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        f.write('{"name": "test"}')
    result = detect(str(tmpdir))
    total_size = sum(len(str(v)) for v in result.key_files.values())
    assert total_size <= 20480, (
        f"key_files total size {total_size} exceeds 20KB"
    )


def test_nonfunctional_performance(tmpdir):
    """验证检测性能：100 个文件的项目在 3 秒内完成"""
    for i in range(100):
        tmpdir.join(f"file_{i}.txt").write("x" * 100)
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        f.write('{"name": "test"}')
    start = time.time()
    detect(str(tmpdir))
    elapsed = time.time() - start
    assert elapsed < 3.0, f"detect took {elapsed:.3f}s, expected < 3.0s"


def test_nonfunctional_robustness(tmpdir):
    """验证对二进制/损坏文件的健壮性"""
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        f.write('{"name": "test"}')
    with open(os.path.join(str(tmpdir), "go.mod"), "w") as f:
        f.write("module test\n")
    with open(os.path.join(str(tmpdir), "Cargo.toml"), "wb") as f:
        f.write(b"\x00\x01\x02")
    with open(os.path.join(str(tmpdir), "src"), "wb") as f:
        f.write(b"\x00")
    result = detect(str(tmpdir))
    # 即使有损坏文件，也应成功检测到 node
    assert result.language == "node", (
        f"expected node, got {result.language}"
    )
