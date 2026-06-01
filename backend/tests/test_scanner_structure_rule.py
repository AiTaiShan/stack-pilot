import os
import pytest
from app.services.scanner.rules.structure_rule import (
    detect_project_type,
    detect_multi_module_java,
    detect_microservices,
    detect_monorepo,
)


def test_detect_project_type_single():
    files = ["package.json", "README.md"]
    dirs = ["src", "test"]
    assert detect_project_type(files, dirs) == "single"


def test_detect_project_type_monorepo(tmpdir):
    frontend = tmpdir.mkdir("frontend")
    backend = tmpdir.mkdir("backend")
    frontend.join("package.json").write("{}")
    backend.join("requirements.txt").write("")
    result = detect_monorepo(str(tmpdir))
    assert result is not None
    assert result["type"] == "monorepo"
    assert result["frontend"]["language"] == "node"
    assert result["backend"]["language"] == "python"


def test_detect_microservices(tmpdir):
    svcs = tmpdir.mkdir("services")
    svc_a = svcs.mkdir("user-service")
    svc_b = svcs.mkdir("order-service")
    svc_a.join("package.json").write("{}")
    svc_b.join("package.json").write("{}")
    result = detect_microservices(str(tmpdir))
    assert result is not None
    assert len(result["services"]) >= 2


def test_detect_multi_module_java(tmpdir):
    pom = tmpdir.join("pom.xml")
    pom.write("""<project>
  <groupId>com.test</groupId>
  <artifactId>parent</artifactId>
  <version>1.0</version>
  <packaging>pom</packaging>
  <modules>
    <module>user-service</module>
    <module>order-service</module>
  </modules>
</project>""")
    user = tmpdir.mkdir("user-service")
    user.join("pom.xml").write("<project><artifactId>user</artifactId></project>")
    user.mkdir("src").mkdir("main").mkdir("java")
    order = tmpdir.mkdir("order-service")
    order.join("pom.xml").write("<project><artifactId>order</artifactId></project>")
    order.mkdir("src").mkdir("main").mkdir("java")
    result = detect_multi_module_java(str(tmpdir))
    assert result is not None
    assert result["type"] == "multi-module-java"
    assert len(result["services"]) >= 2


def test_detect_none_match(tmpdir):
    files = ["README.md"]
    dirs = ["docs"]
    assert detect_project_type(files, dirs) == "single"
    assert detect_microservices(str(tmpdir)) is None
    assert detect_monorepo(str(tmpdir)) is None
    assert detect_multi_module_java(str(tmpdir)) is None
