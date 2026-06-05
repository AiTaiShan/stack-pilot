use axum::Router;
use axum::routing::post;
use axum::extract::State;
use axum::Json;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::Arc;

use crate::services::auth::AuthService;

#[derive(Clone)]
pub struct AuthState {
    pub auth_service: Arc<AuthService>,
}

#[derive(Deserialize)]
pub struct LoginRequest {
    pub username: String,
    pub password: String,
}

#[derive(Deserialize)]
pub struct RegisterRequest {
    pub username: String,
    pub email: String,
    pub password: String,
}

#[derive(Deserialize)]
pub struct RefreshRequest {
    pub refresh_token: String,
}

#[derive(Serialize)]
pub struct LoginResponse {
    pub token: String,
    pub refresh_token: String,
    pub user: UserInfoResponse,
}

#[derive(Serialize)]
pub struct UserInfoResponse {
    pub id: String,
    pub username: String,
    pub role: String,
}

pub async fn login(
    State(state): State<AuthState>,
    Json(payload): Json<LoginRequest>,
) -> Json<Value> {
    match state.auth_service.login(&payload.username, &payload.password).await {
        Ok((token, refresh_token, user)) => Json(json!({
            "code": 200,
            "message": "登录成功",
            "data": {
                "token": token,
                "refresh_token": refresh_token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role
                }
            }
        })),
        Err(e) => Json(json!({
            "code": 401,
            "message": format!("登录失败: {}", e)
        })),
    }
}

pub async fn register(
    State(state): State<AuthState>,
    Json(payload): Json<RegisterRequest>,
) -> Json<Value> {
    match state.auth_service.register(&payload.username, &payload.email, &payload.password).await {
        Ok((token, refresh_token, user)) => Json(json!({
            "code": 200,
            "message": "注册成功",
            "data": {
                "token": token,
                "refresh_token": refresh_token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role
                }
            }
        })),
        Err(e) => Json(json!({
            "code": 400,
            "message": format!("注册失败: {}", e)
        })),
    }
}

pub async fn refresh(
    State(state): State<AuthState>,
    Json(payload): Json<RefreshRequest>,
) -> Json<Value> {
    match state.auth_service.refresh_access_token(&payload.refresh_token).await {
        Ok((token, refresh_token)) => Json(json!({
            "code": 200,
            "message": "刷新成功",
            "data": {
                "token": token,
                "refresh_token": refresh_token
            }
        })),
        Err(e) => Json(json!({
            "code": 401,
            "message": format!("刷新失败: {}", e)
        })),
    }
}

pub fn routes(state: AuthState) -> Router {
    Router::new()
        .route("/auth/login", post(login))
        .route("/auth/register", post(register))
        .route("/auth/refresh", post(refresh))
        .with_state(state)
}
