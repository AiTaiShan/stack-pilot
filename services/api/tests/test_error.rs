use axum::http::StatusCode;
use stackpilot_backend::error::AppError;

#[test]
fn test_auth_error_status() {
    let err = AppError::AuthError("test".to_string());
    assert_eq!(err.status_code(), StatusCode::UNAUTHORIZED);
    assert_eq!(err.error_code(), 40101);
    assert!(!err.retryable());
}

#[test]
fn test_not_found_error_status() {
    let err = AppError::NotFound("test".to_string());
    assert_eq!(err.status_code(), StatusCode::NOT_FOUND);
    assert_eq!(err.error_code(), 40401);
    assert!(!err.retryable());
}

#[test]
fn test_validation_error_status() {
    let err = AppError::ValidationError("test".to_string());
    assert_eq!(err.status_code(), StatusCode::BAD_REQUEST);
    assert_eq!(err.error_code(), 40001);
    assert!(!err.retryable());
}

#[test]
fn test_database_error_status() {
    let err = AppError::DatabaseError("test".to_string());
    assert_eq!(err.status_code(), StatusCode::INTERNAL_SERVER_ERROR);
    assert_eq!(err.error_code(), 50001);
    assert!(!err.retryable());
}

#[test]
fn test_git_error_retryable() {
    let err = AppError::GitError { code: "TEST".to_string(), message: "test".to_string() };
    assert_eq!(err.status_code(), StatusCode::INTERNAL_SERVER_ERROR);
    assert!(err.retryable());
}

#[test]
fn test_docker_error_retryable() {
    let err = AppError::DockerError { code: "TEST".to_string(), message: "test".to_string() };
    assert!(err.retryable());
}

#[test]
fn test_k8s_error_retryable() {
    let err = AppError::K8sError { code: "TEST".to_string(), message: "test".to_string() };
    assert!(err.retryable());
}

#[test]
fn test_network_error_retryable() {
    let err = AppError::NetworkError("test".to_string());
    assert!(err.retryable());
}

#[test]
fn test_agent_error_retryable() {
    let err = AppError::AgentError("test".to_string());
    assert!(err.retryable());
}

#[test]
fn test_rate_limit_error() {
    let err = AppError::RateLimitError;
    assert_eq!(err.status_code(), StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(err.error_code(), 42901);
    assert!(!err.retryable());
}

#[test]
fn test_deployment_cancelled() {
    let err = AppError::DeploymentCancelled;
    assert_eq!(err.status_code(), StatusCode::CONFLICT);
    assert_eq!(err.error_code(), 40901);
    assert!(!err.retryable());
}

#[test]
fn test_password_hash_error() {
    let err = AppError::PasswordHashError("test".to_string());
    assert_eq!(err.status_code(), StatusCode::INTERNAL_SERVER_ERROR);
    assert_eq!(err.error_code(), 50006);
    assert!(!err.retryable());
}
