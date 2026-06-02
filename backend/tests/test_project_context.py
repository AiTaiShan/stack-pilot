"""ProjectContext 缓存层测试"""
import json
import os
import tempfile
import pytest
from app.services.scanner.rules.context import ProjectContext


@pytest.fixture
def sample_project(tmpdir):
    """创建一个包含多种文件的示例项目"""
    # package.json
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        json.dump({"name": "test", "dependencies": {"express": "4.0"}}, f)

    # app.js
    with open(os.path.join(str(tmpdir), "app.js"), "w") as f:
        f.write("console.log('hello')")

    # sub directory with file
    sub = tmpdir.mkdir("src")
    sub.join("main.ts").write("export default {}")

    return str(tmpdir)


def test_read_text_caching(sample_project):
    ctx = ProjectContext(sample_project)
    # 第一次读取
    content1 = ctx.read_text("app.js")
    # 第二次读取应该返回缓存
    content2 = ctx.read_text("app.js")
    assert content1 == "console.log('hello')"
    assert content1 is content2  # 同一对象引用 = 缓存命中


def test_read_json_caching(sample_project):
    ctx = ProjectContext(sample_project)
    data1 = ctx.read_json("package.json")
    data2 = ctx.read_json("package.json")
    assert data1["name"] == "test"
    assert data1 is data2


def test_read_json_invalid(tmpdir):
    with open(os.path.join(str(tmpdir), "bad.json"), "w") as f:
        f.write("{invalid json}")
    ctx = ProjectContext(str(tmpdir))
    result = ctx.read_json("bad.json")
    assert result is None
    assert len(ctx.warnings) == 1
    assert "JSON 解析失败" in ctx.warnings[0]


def test_read_toml(tmp_path):
    toml_content = '[tool.poetry]\nname = "test"\n'
    (tmp_path / "pyproject.toml").write_text(toml_content)
    ctx = ProjectContext(str(tmp_path))
    result = ctx.read_toml("pyproject.toml")
    assert result is not None
    assert result["tool"]["poetry"]["name"] == "test"


def test_read_toml_missing(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    result = ctx.read_toml("missing.toml")
    assert result is None
    assert ctx.warnings == []  # FileNotFoundError 不产生 warning


def test_read_xml(tmp_path):
    xml_content = '<project><artifactId>myapp</artifactId></project>'
    (tmp_path / "pom.xml").write_text(xml_content)
    ctx = ProjectContext(str(tmp_path))
    root = ctx.read_xml("pom.xml")
    assert root is not None
    assert root.find(".//artifactId").text == "myapp"


def test_read_xml_missing(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    result = ctx.read_xml("missing.xml")
    assert result is None


def test_exists(sample_project):
    ctx = ProjectContext(sample_project)
    assert ctx.exists("package.json") is True
    assert ctx.exists("missing.txt") is False


def test_list_dir(sample_project):
    ctx = ProjectContext(sample_project)
    files, dirs = ctx.list_dir(".")
    assert "package.json" in files
    assert "app.js" in files
    assert "src" in dirs


def test_list_dir_caching(sample_project):
    ctx = ProjectContext(sample_project)
    result1 = ctx.list_dir(".")
    result2 = ctx.list_dir(".")
    assert result1 is result2


def test_glob(sample_project):
    ctx = ProjectContext(sample_project)
    js_files = ctx.glob("*.js")
    assert "app.js" in js_files


def test_glob_recursive(sample_project):
    ctx = ProjectContext(sample_project)
    all_ts = ctx.glob("**/*.ts")
    assert any("main.ts" in f for f in all_ts)


def test_walk(sample_project):
    ctx = ProjectContext(sample_project)
    all_files, all_dirs = ctx.walk()
    assert "package.json" in all_files
    assert any("main.ts" in f for f in all_files)


def test_warnings_collection(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    ctx.add_warning("test warning 1")
    ctx.add_warning("test warning 2")
    assert len(ctx.warnings) == 2
    assert "test warning 1" in ctx.warnings


def test_is_file(sample_project):
    ctx = ProjectContext(sample_project)
    assert ctx.is_file("package.json") is True
    assert ctx.is_file("src") is False


def test_is_dir(sample_project):
    ctx = ProjectContext(sample_project)
    assert ctx.is_dir("src") is True
    assert ctx.is_dir("package.json") is False
