import json
import os
import pytest
from app.services.scanner.rules.php_rule import PhpRule
from app.services.scanner.rules.context import ProjectContext


def test_detect_language_with_composer_json():
    assert PhpRule.detect_language(["composer.json"]) >= 0.5


def test_detect_language_without_composer_json():
    assert PhpRule.detect_language(["package.json"]) < 0.5


def test_detect_basic_php_app(tmpdir):
    with open(os.path.join(str(tmpdir), "composer.json"), "w") as f:
        json.dump({"name": "test/app", "require": {}}, f)
    with open(os.path.join(str(tmpdir), "index.php"), "w") as f:
        f.write("<?php echo 'hello';")
    ctx = ProjectContext(str(tmpdir))
    result = PhpRule.detect(ctx)
    assert result["language"] == "php"
    assert result["entry_point"] == "index.php"
    assert result["package_manager"] == "composer"
    assert result["build_command"] == "composer install --no-dev"
    assert result["start_command"] == "php -S 0.0.0.0:80"
    assert result["port"] == 80


def test_detect_laravel_framework(tmpdir):
    with open(os.path.join(str(tmpdir), "composer.json"), "w") as f:
        json.dump({"require": {"laravel/framework": "10.0.0"}}, f)
    with open(os.path.join(str(tmpdir), "artisan"), "w") as f:
        f.write("<?php\n// Laravel artisan")
    ctx = ProjectContext(str(tmpdir))
    result = PhpRule.detect(ctx)
    assert result["framework"] == "laravel"
    assert result["entry_point"] == "artisan"
    assert result["start_command"] == "php artisan serve"


def test_detect_symfony_framework(tmpdir):
    with open(os.path.join(str(tmpdir), "composer.json"), "w") as f:
        json.dump({"require": {"symfony/framework-bundle": "6.0.0"}}, f)
    ctx = ProjectContext(str(tmpdir))
    result = PhpRule.detect(ctx)
    assert result["framework"] == "symfony"


def test_detect_laravel_without_artisan(tmpdir):
    """composer.json 中有 laravel 依赖但没有 artisan 文件，有 index.php"""
    with open(os.path.join(str(tmpdir), "composer.json"), "w") as f:
        json.dump({"require": {"laravel/framework": "10.0.0"}}, f)
    with open(os.path.join(str(tmpdir), "index.php"), "w") as f:
        f.write("<?php echo 'hello';")
    ctx = ProjectContext(str(tmpdir))
    result = PhpRule.detect(ctx)
    assert result["framework"] == "laravel"
    assert result["entry_point"] == "index.php"
    assert result["start_command"] == "php -S 0.0.0.0:80"


def test_detect_composer_lock(tmpdir):
    with open(os.path.join(str(tmpdir), "composer.json"), "w") as f:
        json.dump({"name": "test/app"}, f)
    with open(os.path.join(str(tmpdir), "composer.lock"), "w") as f:
        json.dump({"packages": []}, f)
    ctx = ProjectContext(str(tmpdir))
    result = PhpRule.detect(ctx)
    assert result["package_manager"] == "composer"


def test_language_id():
    assert PhpRule.language_id() == "php"


def test_get_template_name():
    assert PhpRule.get_template_name() == "php_template"
