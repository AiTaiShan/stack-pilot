import json
import os
import pytest
from app.services.scanner.rules.node_rule import NodeRule
from app.services.scanner.rules.context import ProjectContext


def test_detect_language_with_package_json():
    assert NodeRule.detect_language(["package.json"]) >= 0.5


def test_detect_language_without_package_json():
    assert NodeRule.detect_language(["requirements.txt"]) < 0.5


def test_detect_basic_node_app(tmpdir):
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        json.dump({"name": "test", "scripts": {"start": "node index.js"}}, f)
    with open(os.path.join(str(tmpdir), "index.js"), "w") as f:
        f.write("console.log('hello')")
    ctx = ProjectContext(str(tmpdir))
    result = NodeRule.detect(ctx)
    assert result["language"] == "node"
    assert result["entry_point"] == "index.js"
    assert result["package_manager"] == "npm"


def test_detect_nextjs_framework(tmpdir):
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        json.dump({"dependencies": {"next": "14.0.0"}}, f)
    ctx = ProjectContext(str(tmpdir))
    result = NodeRule.detect(ctx)
    assert result["framework"] == "next"


def test_detect_express_framework(tmpdir):
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        json.dump({"dependencies": {"express": "4.18.0"}}, f)
    with open(os.path.join(str(tmpdir), "app.js"), "w") as f:
        f.write("const express = require('express')")
    ctx = ProjectContext(str(tmpdir))
    result = NodeRule.detect(ctx)
    assert result["framework"] == "express"
    assert result["entry_point"] == "app.js"


def test_detect_pnpm_package_manager(tmpdir):
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        json.dump({"name": "test"}, f)
    with open(os.path.join(str(tmpdir), "pnpm-lock.yaml"), "w") as f:
        f.write("lockfileVersion: '6.0'")
    ctx = ProjectContext(str(tmpdir))
    result = NodeRule.detect(ctx)
    assert result["package_manager"] == "pnpm"


def test_detect_yarn_package_manager(tmpdir):
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        json.dump({"name": "test"}, f)
    with open(os.path.join(str(tmpdir), "yarn.lock"), "w") as f:
        f.write("# yarn lockfile")
    ctx = ProjectContext(str(tmpdir))
    result = NodeRule.detect(ctx)
    assert result["package_manager"] == "yarn"


def test_detect_port_from_framework(tmpdir):
    with open(os.path.join(str(tmpdir), "package.json"), "w") as f:
        json.dump({"dependencies": {"next": "14.0.0"}}, f)
    ctx = ProjectContext(str(tmpdir))
    result = NodeRule.detect(ctx)
    assert result["port"] == 3000  # Next.js 默认


def test_language_id():
    assert NodeRule.language_id() == "node"


def test_get_template_name():
    assert NodeRule.get_template_name() == "node_template"
