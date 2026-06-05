use axum::http::StatusCode;
use stackpilot_backend::error::AppError;

#[test]
fn test_error_status_codes() {
    let db_error = AppError::DatabaseError("test".to_string());
    assert_eq!(db_error.status_code(), StatusCode::INTERNAL_SERVER_ERROR);

    let auth_error = AppError::AuthError("test".to_string());
    assert_eq!(auth_error.status_code(), StatusCode::UNAUTHORIZED);

    let not_found = AppError::NotFound("test".to_string());
    assert_eq!(not_found.status_code(), StatusCode::NOT_FOUND);

    let validation = AppError::ValidationError("test".to_string());
    assert_eq!(validation.status_code(), StatusCode::BAD_REQUEST);

    let internal = AppError::InternalError("test".to_string());
    assert_eq!(internal.status_code(), StatusCode::INTERNAL_SERVER_ERROR);
}

#[test]
fn test_error_messages() {
    let error = AppError::DatabaseError("连接失败".to_string());
    assert!(error.to_string().contains("连接失败"));

    let error = AppError::AuthError("认证失败".to_string());
    assert!(error.to_string().contains("认证失败"));

    let error = AppError::NotFound("资源不存在".to_string());
    assert!(error.to_string().contains("资源不存在"));

    let error = AppError::ValidationError("参数无效".to_string());
    assert!(error.to_string().contains("参数无效"));
}
