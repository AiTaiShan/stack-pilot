use uuid::Uuid;
use tracing::info;
use serde::Serialize;
use crate::error::AppError;
use crate::utils::jwt::{create_access_token, create_refresh_token, verify_token, Claims};
use crate::services::user::UserService;

pub struct AuthService {
    jwt_secret: String,
    jwt_expire_minutes: i64,
    refresh_token_days: i64,
    user_service: UserService,
}

impl AuthService {
    pub fn new(jwt_secret: &str, jwt_expire_minutes: i64, refresh_token_days: i64, user_service: UserService) -> Self {
        Self {
            jwt_secret: jwt_secret.to_string(),
            jwt_expire_minutes,
            refresh_token_days,
            user_service,
        }
    }

    pub fn create_access_token(&self, user_id: Uuid) -> Result<String, AppError> {
        create_access_token(user_id, &self.jwt_secret, self.jwt_expire_minutes)
    }

    pub fn create_refresh_token(&self, user_id: Uuid) -> Result<String, AppError> {
        create_refresh_token(user_id, &self.jwt_secret, self.refresh_token_days)
    }

    pub fn verify_token(&self, token: &str) -> Result<Claims, AppError> {
        verify_token(token, &self.jwt_secret)
    }

    pub async fn login(
        &self,
        username: &str,
        password: &str,
    ) -> Result<(String, String, UserInfo), AppError> {
        info!("用户登录: {}", username);

        // 获取完整用户模型（含 password_hash）
        let user_model = self.user_service.get_model_by_username(username).await?
            .ok_or_else(|| AppError::AuthError("用户名或密码错误".to_string()))?;

        if !user_model.is_active.unwrap_or(true) {
            return Err(AppError::AuthError("用户已被禁用".to_string()));
        }

        // 验证密码哈希
        let is_valid = bcrypt::verify(password, &user_model.password_hash)
            .map_err(|e| AppError::PasswordHashError(e.to_string()))?;

        if !is_valid {
            return Err(AppError::AuthError("用户名或密码错误".to_string()));
        }

        let access_token = self.create_access_token(user_model.id)?;
        let refresh_token = self.create_refresh_token(user_model.id)?;

        Ok((access_token, refresh_token, UserInfo {
            id: user_model.id.to_string(),
            username: user_model.username,
            role: user_model.role,
        }))
    }

    pub async fn refresh_access_token(&self, refresh_token: &str) -> Result<(String, String), AppError> {
        let claims = verify_token(refresh_token, &self.jwt_secret)
            .map_err(|_| AppError::AuthError("无效的 refresh token".to_string()))?;

        if claims.token_type != "refresh" {
            return Err(AppError::AuthError("token 类型错误".to_string()));
        }

        let user_id = Uuid::parse_str(&claims.sub)
            .map_err(|_| AppError::AuthError("无效的用户 ID".to_string()))?;

        let new_access = create_access_token(user_id, &self.jwt_secret, self.jwt_expire_minutes)?;
        let new_refresh = create_refresh_token(user_id, &self.jwt_secret, self.refresh_token_days)?;

        Ok((new_access, new_refresh))
    }

    pub async fn register(
        &self,
        username: &str,
        email: &str,
        password: &str,
    ) -> Result<(String, String, UserInfo), AppError> {
        info!("用户注册: {} ({})", username, email);

        let password_hash = bcrypt::hash(password, 12)
            .map_err(|e| AppError::PasswordHashError(e.to_string()))?;

        let user = self.user_service.create(username, email, &password_hash).await?;

        let access_token = self.create_access_token(Uuid::parse_str(&user.id).map_err(|e| AppError::InternalError(e.to_string()))?)?;
        let refresh_token = self.create_refresh_token(Uuid::parse_str(&user.id).map_err(|e| AppError::InternalError(e.to_string()))?)?;

        Ok((access_token, refresh_token, UserInfo {
            id: user.id,
            username: user.username,
            role: user.role,
        }))
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct UserInfo {
    pub id: String,
    pub username: String,
    pub role: String,
}
