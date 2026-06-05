use axum::Router;
use axum::http::HeaderMap;
use axum::routing::{get, put, delete};
use axum::extract::{Path, State};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;

use crate::error::AppError;
use crate::services::user::UserService;
use crate::utils::jwt::verify_token;

#[derive(Clone)]
pub struct UsersState {
    pub user_service: Arc<UserService>,
    pub jwt_secret: String,
}

#[derive(Deserialize)]
pub struct UpdateUserRequest {
    pub username: Option<String>,
    pub email: Option<String>,
    pub phone: Option<String>,
    pub avatar: Option<String>,
}

#[derive(Deserialize)]
pub struct UpdatePasswordRequest {
    pub old_password: String,
    pub new_password: String,
}

fn extract_user_id(headers: &HeaderMap, jwt_secret: &str) -> Result<String, AppError> {
    let auth_header = headers
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .ok_or_else(|| AppError::AuthError("缺少 Authorization 头".to_string()))?;
    let token = auth_header
        .strip_prefix("Bearer ")
        .ok_or_else(|| AppError::AuthError("无效的 Authorization 格式".to_string()))?;
    let claims = verify_token(token, jwt_secret)
        .map_err(|_| AppError::AuthError("无效的 Token".to_string()))?;
    Ok(claims.sub)
}

pub async fn get_current_user(
    State(state): State<UsersState>,
    headers: HeaderMap,
) -> Json<Value> {
    let user_id = match extract_user_id(&headers, &state.jwt_secret) {
        Ok(id) => id,
        Err(e) => return Json(json!({"code": 401, "message": e.to_string()})),
    };
    match state.user_service.get(&user_id).await {
        Ok(Some(user)) => Json(json!({
            "code": 200,
            "data": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active
            }
        })),
        Ok(None) => Json(json!({"code": 404, "message": "用户不存在"})),
        Err(e) => Json(json!({"code": 500, "message": e.to_string()})),
    }
}

pub async fn update_current_user(
    State(state): State<UsersState>,
    headers: HeaderMap,
    Json(payload): Json<UpdateUserRequest>,
) -> Json<Value> {
    let user_id = match extract_user_id(&headers, &state.jwt_secret) {
        Ok(id) => id,
        Err(e) => return Json(json!({"code": 401, "message": e.to_string()})),
    };
    match state.user_service.update(
        &user_id,
        payload.username.as_deref(),
        payload.email.as_deref(),
        payload.phone.as_deref(),
        payload.avatar.as_deref(),
    ).await {
        Ok(user) => Json(json!({
            "code": 200,
            "message": "用户信息更新成功",
            "data": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active
            }
        })),
        Err(e) => Json(json!({"code": 500, "message": e.to_string()})),
    }
}

pub async fn list_users(
    State(state): State<UsersState>,
) -> Json<Value> {
    match state.user_service.list().await {
        Ok(users) => Json(json!({
            "code": 200,
            "message": "success",
            "data": {
                "items": users,
                "total": users.len()
            }
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("获取用户列表失败: {}", e)
        })),
    }
}

pub async fn get_user(
    State(state): State<UsersState>,
    Path(id): Path<String>,
) -> Json<Value> {
    match state.user_service.get(&id).await {
        Ok(Some(user)) => Json(json!({
            "code": 200,
            "message": "success",
            "data": user
        })),
        Ok(None) => Json(json!({
            "code": 404,
            "message": "用户不存在"
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("获取用户失败: {}", e)
        })),
    }
}

pub async fn update_user(
    State(state): State<UsersState>,
    Path(id): Path<String>,
    Json(payload): Json<UpdateUserRequest>,
) -> Json<Value> {
    match state.user_service.update(
        &id,
        payload.username.as_deref(),
        payload.email.as_deref(),
        payload.phone.as_deref(),
        payload.avatar.as_deref(),
    ).await {
        Ok(user) => Json(json!({
            "code": 200,
            "message": "用户更新成功",
            "data": user
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("更新用户失败: {}", e)
        })),
    }
}

pub async fn update_password(
    State(state): State<UsersState>,
    Path(id): Path<String>,
    Json(payload): Json<UpdatePasswordRequest>,
) -> Json<Value> {
    match state.user_service.update_password(&id, &payload.old_password, &payload.new_password).await {
        Ok(_) => Json(json!({
            "code": 200,
            "message": "密码更新成功"
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("更新密码失败: {}", e)
        })),
    }
}

pub async fn delete_user(
    State(state): State<UsersState>,
    Path(id): Path<String>,
) -> Json<Value> {
    match state.user_service.delete(&id).await {
        Ok(_) => Json(json!({
            "code": 200,
            "message": "用户删除成功"
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("删除用户失败: {}", e)
        })),
    }
}

pub fn routes(state: UsersState) -> Router {
    Router::new()
        .route("/users/me", get(get_current_user).put(update_current_user))
        .route("/users", get(list_users))
        .route("/users/:id", get(get_user).put(update_user).delete(delete_user))
        .route("/users/:id/password", put(update_password))
        .with_state(state)
}
