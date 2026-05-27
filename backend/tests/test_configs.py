import pytest
import uuid
from unittest.mock import MagicMock
from app.services.config.config_service import ConfigService, SENSITIVE_MASK
from app.core.error_handler import AppError


def _make_config_row(key, value, value_type="string", description=None,
                     is_sensitive=False, default_value=None, validation_rule=None):
    """创建一个模拟的 SystemConfig 行"""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.key = key
    row.value = value
    row.value_type = value_type
    row.description = description
    row.is_sensitive = is_sensitive
    row.default_value = default_value
    row.validation_rule = validation_rule
    row.created_at = "2026-01-01T00:00:00"
    row.updated_at = "2026-01-01T00:00:00"
    return row


def _mock_db(existing_rows=None):
    """创建一个 mock Session，模拟查询已有行"""
    existing = {r.key: r for r in (existing_rows or [])}
    db = MagicMock()

    def query_filter(key):
        row = existing.get(key)
        query_mock = MagicMock()
        query_mock.first.return_value = row
        return query_mock

    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = list(existing.values())

    # 让 filter(key==...) 返回正确的行
    original_query = db.query

    class QueryProxy:
        def __init__(self):
            self._rows = existing

        def __call__(self, model):
            return self

        def filter(self, *args, **kwargs):
            # 尝试从 filter 条件中提取 key
            return self

        def first(self):
            return None

        def all(self):
            return list(self._rows.values())

        def like(self, pattern):
            prefix = pattern.rstrip("%")
            matched = [r for r in self._rows.values() if r.key.startswith(prefix)]
            proxy = MagicMock()
            proxy.all.return_value = matched
            return proxy

    # 简化：直接在 service 层面 mock db.query
    return db


# ── test_get_config_found ──────────────────────────────────────

def test_get_config_found():
    """测试获取已存在的配置"""
    row = _make_config_row("app.name", "StackPilot", is_sensitive=False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    result = service.get_config("app.name")

    assert result is not None
    assert result["key"] == "app.name"
    assert result["value"] == "StackPilot"


# ── test_get_config_not_found ──────────────────────────────────

def test_get_config_not_found():
    """测试获取不存在的配置返回 None"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    service = ConfigService(db)
    result = service.get_config("nonexistent")

    assert result is None


# ── test_set_config_create ─────────────────────────────────────

def test_set_config_create():
    """测试新建配置（key 不存在时创建）"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    service = ConfigService(db)
    # set_config 内部 commit/refresh 后返回 _to_dict，需要模拟 refresh
    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = "2026-01-01T00:00:00"
        obj.updated_at = "2026-01-01T00:00:00"
    db.refresh.side_effect = fake_refresh

    result = service.set_config("new.key", "new_value", value_type="string", description="desc")

    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert result["key"] == "new.key"
    assert result["value"] == "new_value"


# ── test_set_config_update ─────────────────────────────────────

def test_set_config_update():
    """测试更新已有配置"""
    row = _make_config_row("app.name", "OldName")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    result = service.set_config("app.name", "NewName", value_type="string")

    assert row.value == "NewName"
    db.commit.assert_called_once()
    assert result["value"] == "NewName"


# ── test_delete_config ─────────────────────────────────────────

def test_delete_config():
    """测试删除配置"""
    row = _make_config_row("to.delete", "bye")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    result = service.delete_config("to.delete")

    assert result is True
    db.delete.assert_called_once_with(row)
    db.commit.assert_called_once()


def test_delete_config_not_found():
    """测试删除不存在的配置返回 False"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    service = ConfigService(db)
    result = service.delete_config("nonexistent")

    assert result is False


# ── test_get_all_configs ───────────────────────────────────────

def test_get_all_configs():
    """测试获取全部配置，敏感值被遮蔽"""
    rows = [
        _make_config_row("app.name", "StackPilot", is_sensitive=False),
        _make_config_row("app.secret", "s3cret!", is_sensitive=True),
    ]
    db = MagicMock()
    db.query.return_value.all.return_value = rows

    service = ConfigService(db)
    items = service.get_all_configs()

    assert len(items) == 2
    # 非敏感值保持原样
    name_item = next(i for i in items if i["key"] == "app.name")
    assert name_item["value"] == "StackPilot"
    # 敏感值被遮蔽
    secret_item = next(i for i in items if i["key"] == "app.secret")
    assert secret_item["value"] == SENSITIVE_MASK


# ── test_validate_config_required ──────────────────────────────

def test_validate_config_required():
    """测试 required 验证：值为 None 时抛出错误"""
    row = _make_config_row("app.required_field", "val",
                           validation_rule={"required": True})
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    with pytest.raises(AppError) as exc_info:
        service.validate_config("app.required_field", None)
    assert "必填" in exc_info.value.message


def test_validate_config_required_pass():
    """测试 required 验证通过"""
    row = _make_config_row("app.required_field", "val",
                           validation_rule={"required": True})
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    assert service.validate_config("app.required_field", "some_value") is True


# ── test_validate_config_min_max ───────────────────────────────

def test_validate_config_min():
    """测试 min 验证：值小于最小值时抛出错误"""
    row = _make_config_row("app.port", 8080,
                           validation_rule={"min": 1, "max": 65535})
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    with pytest.raises(AppError) as exc_info:
        service.validate_config("app.port", 0)
    assert "不能小于" in exc_info.value.message


def test_validate_config_max():
    """测试 max 验证：值大于最大值时抛出错误"""
    row = _make_config_row("app.port", 8080,
                           validation_rule={"min": 1, "max": 65535})
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    with pytest.raises(AppError) as exc_info:
        service.validate_config("app.port", 70000)
    assert "不能大于" in exc_info.value.message


def test_validate_config_in_range():
    """测试值在范围内时验证通过"""
    row = _make_config_row("app.port", 8080,
                           validation_rule={"min": 1, "max": 65535})
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    assert service.validate_config("app.port", 8080) is True


def test_validate_config_enum():
    """测试 enum 验证"""
    row = _make_config_row("app.env", "dev",
                           validation_rule={"enum": ["dev", "staging", "prod"]})
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    service = ConfigService(db)
    with pytest.raises(AppError) as exc_info:
        service.validate_config("app.env", "test")
    assert "必须是" in exc_info.value.message

    assert service.validate_config("app.env", "prod") is True


def test_validate_config_not_found():
    """测试验证不存在的配置时抛出 NOT_FOUND 错误"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    service = ConfigService(db)
    with pytest.raises(AppError) as exc_info:
        service.validate_config("nonexistent", "value")
    assert exc_info.value.code.name == "NOT_FOUND"
