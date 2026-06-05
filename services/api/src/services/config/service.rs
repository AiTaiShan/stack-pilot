use sea_orm::{EntityTrait, QueryFilter, ColumnTrait, ActiveModelTrait, Set};
use uuid::Uuid;
use crate::error::AppError;
use crate::models::system_config::{self, Entity as ConfigEntity, ActiveModel as ConfigActiveModel};

const SENSITIVE_MASK: &str = "******";

pub struct ConfigService {
    db: sea_orm::DatabaseConnection,
}

impl ConfigService {
    pub fn new(db: sea_orm::DatabaseConnection) -> Self {
        Self { db }
    }

    pub async fn list(&self) -> Result<Vec<ConfigItem>, AppError> {
        let configs = ConfigEntity::find().all(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;
        Ok(configs.into_iter().map(|c| self.to_item(&c, true)).collect())
    }

    pub async fn get(&self, key: &str) -> Result<Option<ConfigItem>, AppError> {
        let config = ConfigEntity::find()
            .filter(system_config::Column::Key.eq(key))
            .one(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;
        Ok(config.map(|c| self.to_item(&c, true)))
    }

    pub async fn create(
        &self,
        key: &str,
        value: &str,
        value_type: Option<&str>,
        description: Option<&str>,
        is_sensitive: Option<bool>,
    ) -> Result<ConfigItem, AppError> {
        if self.get_raw(key).await?.is_some() {
            return Err(AppError::ValidationError(format!("配置项 '{}' 已存在", key)));
        }
        let now = chrono::Utc::now().naive_utc();
        let config = ConfigActiveModel {
            id: Set(Uuid::new_v4()),
            key: Set(key.to_string()),
            value: Set(value.to_string()),
            value_type: Set(value_type.unwrap_or("string").to_string()),
            description: Set(description.map(|s| s.to_string())),
            default_value: Set(None),
            validation_rule: Set(None),
            is_sensitive: Set(is_sensitive.unwrap_or(false)),
            created_at: Set(now),
            updated_at: Set(now),
        };
        let result = config.insert(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;
        Ok(self.to_item(&result, false))
    }

    pub async fn update(
        &self,
        key: &str,
        value: Option<&str>,
        value_type: Option<&str>,
        description: Option<&str>,
        is_sensitive: Option<bool>,
    ) -> Result<ConfigItem, AppError> {
        let config = ConfigEntity::find()
            .filter(system_config::Column::Key.eq(key))
            .one(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound(format!("配置项 '{}' 不存在", key)))?;
        let mut active: ConfigActiveModel = config.into();
        if let Some(v) = value { active.value = Set(v.to_string()); }
        if let Some(vt) = value_type { active.value_type = Set(vt.to_string()); }
        if let Some(d) = description { active.description = Set(Some(d.to_string())); }
        if let Some(s) = is_sensitive { active.is_sensitive = Set(s); }
        active.updated_at = Set(chrono::Utc::now().naive_utc());
        let result = active.update(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;
        Ok(self.to_item(&result, false))
    }

    pub async fn delete(&self, key: &str) -> Result<(), AppError> {
        let config = ConfigEntity::find()
            .filter(system_config::Column::Key.eq(key))
            .one(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound(format!("配置项 '{}' 不存在", key)))?;
        let active: ConfigActiveModel = config.into();
        active.delete(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;
        Ok(())
    }

    /// 获取原始配置（内部用，不遮蔽）
    async fn get_raw(&self, key: &str) -> Result<Option<system_config::Model>, AppError> {
        ConfigEntity::find()
            .filter(system_config::Column::Key.eq(key))
            .one(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))
    }

    /// 将数据库模型转为返回结构，敏感值遮蔽
    fn to_item(&self, model: &system_config::Model, mask_sensitive: bool) -> ConfigItem {
        let value = if mask_sensitive && model.is_sensitive {
            SENSITIVE_MASK.to_string()
        } else {
            model.value.clone()
        };
        ConfigItem {
            id: model.id.to_string(),
            key: model.key.clone(),
            value,
            value_type: model.value_type.clone(),
            description: model.description.clone(),
            default_value: model.default_value.clone(),
            validation_rule: model.validation_rule.clone(),
            is_sensitive: model.is_sensitive,
        }
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ConfigItem {
    pub id: String,
    pub key: String,
    pub value: String,
    pub value_type: String,
    pub description: Option<String>,
    pub default_value: Option<String>,
    pub validation_rule: Option<String>,
    pub is_sensitive: bool,
}
