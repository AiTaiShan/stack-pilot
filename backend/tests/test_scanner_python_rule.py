import os
import pytest
from app.services.scanner.rules.python_rule import PythonRule
from app.services.scanner.rules.context import ProjectContext


def test_detect_language_with_requirements_txt():
    assert PythonRule.detect_language(["requirements.txt"]) >= 0.5


def test_detect_language_with_pyproject_toml():
    assert PythonRule.detect_language(["pyproject.toml"]) >= 0.5


def test_detect_language_with_setup_py():
    assert PythonRule.detect_language(["setup.py"]) >= 0.5


def test_detect_language_without_python_files():
    assert PythonRule.detect_language(["package.json"]) < 0.5


def test_detect_django_framework(tmpdir):
    manage_py = os.path.join(str(tmpdir), "manage.py")
    with open(manage_py, "w") as f:
        f.write("#!/usr/bin/env python\nif __name__ == '__main__': ...")
    req_path = os.path.join(str(tmpdir), "requirements.txt")
    with open(req_path, "w") as f:
        f.write("django\n")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["framework"] == "django"
    assert result["entry_point"] == "manage.py"
    assert result["start_command"] == "python manage.py runserver 0.0.0.0:8000"


def test_detect_fastapi_framework(tmpdir):
    req_path = os.path.join(str(tmpdir), "requirements.txt")
    with open(req_path, "w") as f:
        f.write("fastapi\nuvicorn\n")
    main_path = os.path.join(str(tmpdir), "main.py")
    with open(main_path, "w") as f:
        f.write("from fastapi import FastAPI\napp = FastAPI()\n")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["framework"] == "fastapi"
    assert result["entry_point"] == "main.py"
    assert result["start_command"] == "uvicorn main:app --host 0.0.0.0 --port 8000"


def test_detect_flask_framework(tmpdir):
    req_path = os.path.join(str(tmpdir), "requirements.txt")
    with open(req_path, "w") as f:
        f.write("flask\n")
    app_path = os.path.join(str(tmpdir), "app.py")
    with open(app_path, "w") as f:
        f.write("from flask import Flask\napp = Flask(__name__)\n")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["framework"] == "flask"
    assert result["entry_point"] == "app.py"


def test_detect_entry_point_main(tmpdir):
    with open(os.path.join(str(tmpdir), "main.py"), "w") as f:
        f.write("print('hello')")
    with open(os.path.join(str(tmpdir), "requirements.txt"), "w") as f:
        f.write("")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["entry_point"] == "main.py"
    assert result["start_command"] == "python main.py"


def test_detect_entry_point_app(tmpdir):
    with open(os.path.join(str(tmpdir), "app.py"), "w") as f:
        f.write("from flask import Flask")
    with open(os.path.join(str(tmpdir), "requirements.txt"), "w") as f:
        f.write("")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["entry_point"] == "app.py"


def test_detect_entry_point_manage(tmpdir):
    with open(os.path.join(str(tmpdir), "manage.py"), "w") as f:
        f.write("django manage")
    with open(os.path.join(str(tmpdir), "requirements.txt"), "w") as f:
        f.write("")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["entry_point"] == "manage.py"


def test_detect_poetry_package_manager(tmpdir):
    with open(os.path.join(str(tmpdir), "pyproject.toml"), "w") as f:
        f.write("[tool.poetry]\nname = 'test'\n")
    with open(os.path.join(str(tmpdir), "poetry.lock"), "w") as f:
        f.write("")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["package_manager"] == "poetry"
    assert result["build_command"] == "poetry install"


def test_detect_pipenv_package_manager(tmpdir):
    with open(os.path.join(str(tmpdir), "Pipfile"), "w") as f:
        f.write("[packages]\n")
    with open(os.path.join(str(tmpdir), "Pipfile.lock"), "w") as f:
        f.write("")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["package_manager"] == "pipenv"
    assert result["build_command"] == "pipenv install"


def test_detect_default_pip_package_manager(tmpdir):
    with open(os.path.join(str(tmpdir), "requirements.txt"), "w") as f:
        f.write("")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["package_manager"] == "pip"


def test_default_port(tmpdir):
    with open(os.path.join(str(tmpdir), "requirements.txt"), "w") as f:
        f.write("")
    ctx = ProjectContext(str(tmpdir))
    result = PythonRule.detect(ctx)
    assert result["port"] == 8000


def test_language_id():
    assert PythonRule.language_id() == "python"


def test_get_template_name():
    assert PythonRule.get_template_name() == "python_template"
