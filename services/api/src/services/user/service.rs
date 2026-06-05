use uuid::Uuid;
use sea_orm::{EntityTrait, QueryFilter, ColumnTrait, ActiveModelTrait, Set};
use serde::Serialize;
use tracing::info;

use crate::error::AppError;
use crate::models::user::{self, Entity as UserEntity, ActiveModel as UserActiveModel};

pub struct UserService {
    db: sea_orm::DatabaseConnection,
}

impl UserService {
    pub fn new(db: sea_orm::DatabaseConnection) -> Self {
        Self { db }
    }

    pub async fn get(&self, id: &str) -> Result<Option<UserInfo>, AppError> {
        let uuid = Uuid::parse_str(id)
            .map_err(|e| AppError::ValidationError(format!("无效的用户 ID: {}", e)))?;

        let user = UserEntity::find_by_id(uuid)
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        Ok(user.map(|u| UserInfo {
            id: u.id.to_string(),
            username: u.username,
            email: u.email,
            role: u.role,
            is_active: u.is_active.unwrap_or(true),
        }))
    }

    pub async fn get_by_username(&self, username: &str) -> Result<Option<UserInfo>, AppError> {
        let user = UserEntity::find()
            .filter(user::Column::Username.eq(username))
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        Ok(user.map(|u| UserInfo {
            id: u.id.to_string(),
            username: u.username,
            email: u.email,
            role: u.role,
            is_active: u.is_active.unwrap_or(true),
        }))
    }

    pub async fn get_model_by_username(&self, username: &str) -> Result<Option<crate::models::user::Model>, AppError> {
        let user = UserEntity::find()
            .filter(user::Column::Username.eq(username))
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;
        Ok(user)
    }

    pub async fn get_by_email(&self, email: &str) -> Result<Option<UserInfo>, AppError> {
        let user = UserEntity::find()
            .filter(user::Column::Email.eq(email))
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        Ok(user.map(|u| UserInfo {
            id: u.id.to_string(),
            username: u.username,
            email: u.email,
            role: u.role,
            is_active: u.is_active.unwrap_or(true),
        }))
    }

    pub async fn list(&self) -> Result<Vec<UserInfo>, AppError> {
        let users = UserEntity::find()
            .all(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        Ok(users.into_iter().map(|u| UserInfo {
            id: u.id.to_string(),
            username: u.username,
            email: u.email,
            role: u.role,
            is_active: u.is_active.unwrap_or(true),
        }).collect())
    }

    pub async fn create(
        &self,
        username: &str,
        email: &str,
        password_hash: &str,
    ) -> Result<UserInfo, AppError> {
        // 检查用户名是否已存在
        if self.get_by_username(username).await?.is_some() {
            return Err(AppError::ValidationError("用户名已存在".to_string()));
        }

        // 检查邮箱是否已存在
        if self.get_by_email(email).await?.is_some() {
            return Err(AppError::ValidationError("邮箱已被注册".to_string()));
        }

        let user = UserActiveModel {
            id: Set(Uuid::new_v4()),
            username: Set(username.to_string()),
            email: Set(email.to_string()),
            password_hash: Set(password_hash.to_string()),
            role: Set("user".to_string()),
            phone: Set(None),
            avatar: Set(None),
            is_active: Set(Some(true)),
            last_login_at: Set(None),
            ..Default::default()
        };

        let result = user.insert(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("用户创建成功: {}", result.username);

        Ok(UserInfo {
            id: result.id.to_string(),
            username: result.username,
            email: result.email,
            role: result.role,
            is_active: result.is_active.unwrap_or(true),
        })
    }

    pub async fn update(
        &self,
        id: &str,
        username: Option<&str>,
        email: Option<&str>,
        phone: Option<&str>,
        avatar: Option<&str>,
    ) -> Result<UserInfo, AppError> {
        let uuid = Uuid::parse_str(id)
            .map_err(|e| AppError::ValidationError(format!("无效的用户 ID: {}", e)))?;

        let user = UserEntity::find_by_id(uuid)
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("用户不存在".to_string()))?;

        let mut active_model: UserActiveModel = user.into();

        if let Some(u) = username {
            active_model.username = Set(u.to_string());
        }
        if let Some(e) = email {
            active_model.email = Set(e.to_string());
        }
        if let Some(p) = phone {
            active_model.phone = Set(Some(p.to_string()));
        }
        if let Some(a) = avatar {
            active_model.avatar = Set(Some(a.to_string()));
        }

        let result = active_model.update(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("用户更新成功: {}", result.id);

        Ok(UserInfo {
            id: result.id.to_string(),
            username: result.username,
            email: result.email,
            role: result.role,
            is_active: result.is_active.unwrap_or(true),
        })
    }

    pub async fn update_password(
        &self,
        id: &str,
        old_password: &str,
        new_password: &str,
    ) -> Result<(), AppError> {
        let uuid = Uuid::parse_str(id)
            .map_err(|e| AppError::ValidationError(format!("无效的用户 ID: {}", e)))?;

        let user = UserEntity::find_by_id(uuid)
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("用户不存在".to_string()))?;

        // TODO: 验证旧密码哈希
        // TODO: 对新密码进行哈希处理
        let mut active_model: UserActiveModel = user.into();
        active_model.password_hash = Set(new_password.to_string());

        active_model.update(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("密码更新成功: {}", id);
        Ok(())
    }

    pub async fn delete(&self, id: &str) -> Result<(), AppError> {
        let uuid = Uuid::parse_str(id)
            .map_err(|e| AppError::ValidationError(format!("无效的用户 ID: {}", e)))?;

        let user = UserEntity::find_by_id(uuid)
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("用户不存在".to_string()))?;

        let active_model: UserActiveModel = user.into();
        active_model.delete(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("用户已删除: {}", id);
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct UserInfo {
    pub id: String,
    pub username: String,
    pub email: String,
    pub role: String,
    pub is_active: bool,
}
