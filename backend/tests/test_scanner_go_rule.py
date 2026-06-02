import os
import pytest
from app.services.scanner.rules.go_rule import GoRule
from app.services.scanner.rules.context import ProjectContext


def test_detect_language_with_go_mod():
    assert GoRule.detect_language(["go.mod"]) >= 0.5


def test_detect_language_without_go_mod():
    assert GoRule.detect_language(["package.json"]) < 0.5


def test_detect_basic_go_app(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n")
    main_path = os.path.join(str(tmpdir), "main.go")
    with open(main_path, "w") as f:
        f.write("package main\n\nfunc main() {}\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["language"] == "go"
    assert result["entry_point"] == "main.go"
    assert result["package_manager"] == "go_mod"
    assert result["build_command"] == "go build -o main ."
    assert result["start_command"] == "./main"
    assert result["port"] == 8080


def test_detect_gin_framework(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.0\n)\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["framework"] == "gin"


def test_detect_echo_framework(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n\nrequire github.com/labstack/echo/v4 v4.11.0\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["framework"] == "echo"


def test_detect_fiber_framework(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n\nrequire github.com/gofiber/fiber/v2 v2.50.0\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["framework"] == "fiber"


def test_detect_no_framework(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["framework"] == ""


def test_detect_entry_point_no_main_go(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n")
    cmd_dir = os.path.join(str(tmpdir), "cmd", "app")
    os.makedirs(cmd_dir)
    main_path = os.path.join(cmd_dir, "main.go")
    with open(main_path, "w") as f:
        f.write("package main\n\nfunc main() {}\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["entry_point"] == "cmd/app/main.go"


def test_detect_main_go_without_package_main(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n")
    main_path = os.path.join(str(tmpdir), "main.go")
    with open(main_path, "w") as f:
        f.write("package utils\n\nfunc Helper() {}\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["entry_point"] != "main.go"


def test_detect_go_sum(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n")
    sum_path = os.path.join(str(tmpdir), "go.sum")
    with open(sum_path, "w") as f:
        f.write("github.com/foo/bar v1.0.0 h1:abc=\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["package_manager"] == "go_mod"


def test_detect_no_main_go_at_all(tmpdir):
    mod_path = os.path.join(str(tmpdir), "go.mod")
    with open(mod_path, "w") as f:
        f.write("module myapp\n\ngo 1.21\n")
    util_path = os.path.join(str(tmpdir), "utils.go")
    with open(util_path, "w") as f:
        f.write("package utils\n")
    ctx = ProjectContext(str(tmpdir))
    result = GoRule.detect(ctx)
    assert result["entry_point"] is None


def test_language_id():
    assert GoRule.language_id() == "go"


def test_get_template_name():
    assert GoRule.get_template_name() == "go_template"
