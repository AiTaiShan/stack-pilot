from sqlalchemy.orm import Session
from app.models.config import SystemConfig
from app.core.error_handler import AppError, ErrorCode


SENSITIVE_MASK = "******"


class ConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_config(self, key: str) -> dict | None:
        """根据 key 获取单个配置，敏感值返回遮蔽值"""
        config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not config:
            return None
        return self._to_dict(config, mask_sensitive=True)

    def get_configs_by_prefix(self, prefix: str) -> list:
        """根据前缀批量获取配置"""
        configs = (
            self.db.query(SystemConfig)
            .filter(SystemConfig.key.like(f"{prefix}%"))
            .all()
        )
        return [self._to_dict(c, mask_sensitive=True) for c in configs]

    def set_config(
        self,
        key: str,
        value,
        value_type: str = "string",
        description: str | None = None,
        is_sensitive: bool = False,
        default_value=None,
        validation_rule=None,
    ) -> dict:
        """创建或更新配置（upsert）"""
        config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if config:
            # 更新
            if value is not None:
                config.value = value
            if value_type is not None:
                config.value_type = value_type
            if description is not None:
                config.description = description
            if is_sensitive is not None:
                config.is_sensitive = is_sensitive
            if default_value is not None:
                config.default_value = default_value
            if validation_rule is not None:
                config.validation_rule = validation_rule
        else:
            # 新建
            config = SystemConfig(
                key=key,
                value=value,
                value_type=value_type,
                description=description,
                is_sensitive=is_sensitive,
                default_value=default_value,
                validation_rule=validation_rule,
            )
            self.db.add(config)

        self.db.commit()
        self.db.refresh(config)
        return self._to_dict(config, mask_sensitive=False)

    def delete_config(self, key: str) -> bool:
        """删除配置"""
        config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        return True

    def get_all_configs(self) -> list:
        """获取全部配置，敏感值返回遮蔽值"""
        configs = self.db.query(SystemConfig).all()
        return [self._to_dict(c, mask_sensitive=True) for c in configs]

    def validate_config(self, key: str, value) -> bool:
        """根据 validation_rule 验证配置值"""
        config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not config:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message=f"配置 '{key}' 不存在",
            )

        rule = config.validation_rule
        if not rule:
            return True

        # required
        if rule.get("required") and value is None:
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"配置 '{key}' 为必填项",
            )

        # enum
        if "enum" in rule:
            allowed = rule["enum"]
            if value not in allowed:
                raise AppError(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"配置 '{key}' 的值必须是 {allowed} 之一",
                )

        # min / max（数值类型）
        if "min" in rule and value is not None:
            if value < rule["min"]:
                raise AppError(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"配置 '{key}' 的值不能小于 {rule['min']}",
                )

        if "max" in rule and value is not None:
            if value > rule["max"]:
                raise AppError(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"配置 '{key}' 的值不能大于 {rule['max']}",
                )

        return True

    def _to_dict(self, config: SystemConfig, mask_sensitive: bool = False) -> dict:
        """将 SystemConfig 转为字典"""
        value = config.value
        if mask_sensitive and config.is_sensitive:
            value = SENSITIVE_MASK

        return {
            "id": str(config.id),
            "key": config.key,
            "value": value,
            "value_type": config.value_type,
            "description": config.description,
            "default_value": config.default_value,
            "validation_rule": config.validation_rule,
            "is_sensitive": config.is_sensitive,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }
