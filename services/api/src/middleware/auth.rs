#![allow(dead_code)]
use axum::extract::{Request, State};
use axum::http::header::AUTHORIZATION;
use axum::middleware::Next;
use axum::response::Response;

use crate::error::AppError;
use crate::utils::jwt::verify_token;

#[derive(Clone)]
pub struct AuthMiddlewareState {
    pub jwt_secret: String,
}

pub async fn auth_middleware(
    State(state): State<AuthMiddlewareState>,
    request: Request,
    next: Next,
) -> Result<Response, AppError> {
    let auth_header = request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .ok_or_else(|| AppError::AuthError("缺少 Authorization 头".to_string()))?;

    let token = auth_header
        .strip_prefix("Bearer ")
        .ok_or_else(|| AppError::AuthError("无效的 Authorization 格式".to_string()))?;

    let _claims = verify_token(token, &state.jwt_secret)
        .map_err(|_| AppError::AuthError("无效的 Token".to_string()))?;

    Ok(next.run(request).await)
}

pub async fn optional_auth_middleware(
    State(state): State<AuthMiddlewareState>,
    request: Request,
    next: Next,
) -> Response {
    let auth_header = request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok());

    if let Some(header) = auth_header {
        if let Some(token) = header.strip_prefix("Bearer ") {
            if let Ok(_claims) = verify_token(token, &state.jwt_secret) {
                // Token 有效，继续处理
            }
        }
    }

    next.run(request).await
}
