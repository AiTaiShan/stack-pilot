import pytest
import tempfile
import os
from app.services.scanner.detector import detect, get_template


def test_detect_single_node_project(tmpdir):
    repo_dir = str(tmpdir)
    with open(os.path.join(repo_dir, "package.json"), "w") as f:
        f.write('{"name": "test", "scripts": {"start": "node index.js"}}')
    with open(os.path.join(repo_dir, "index.js"), "w") as f:
        f.write("console.log('hello')")
    result = detect(repo_dir)
    assert result.project_type == "single"
    assert result.language == "node"
    assert result.entry_point == "index.js"


def test_detect_monorepo(tmpdir):
    frontend = tmpdir.mkdir("frontend")
    backend = tmpdir.mkdir("backend")
    frontend.join("package.json").write('{}')
    backend.join("requirements.txt").write("flask\n")
    backend.join("app.py").write("from flask import Flask\napp = Flask(__name__)")
    result = detect(str(tmpdir))
    assert result.project_type == "monorepo"
    assert "node" in result.languages
    assert "python" in result.languages
    assert result.frontend is not None
    assert result.backend is not None


def test_detect_microservices(tmpdir):
    services = tmpdir.mkdir("services")
    svc_a = services.mkdir("user-service")
    svc_b = services.mkdir("order-service")
    svc_a.join("package.json").write('{"scripts": {"start": "node index.js"}}')
    svc_a.join("index.js").write("")
    svc_b.join("Cargo.toml").write("[package]\nname = \"order\"")
    svc_b.join("src").mkdir().join("main.rs").write("fn main() {}")
    result = detect(str(tmpdir))
    assert result.project_type == "microservices"
    assert len(result.services) >= 2


def test_detect_no_lang_indicator(tmpdir):
    result = detect(str(tmpdir))
    assert result.language == "unknown"


def test_detect_collects_key_files(tmpdir):
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        f.write('{"name": "test"}')
    result = detect(str(tmpdir))
    assert "structure" in result.key_files


def test_get_template_exists():
    gen = get_template("node")
    assert gen is not None
    assert callable(gen)


def test_get_template_unknown():
    gen = get_template("unknown_lang")
    assert gen is None
