use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;
use thiserror::Error;
use chrono::Utc;

#[derive(Error, Debug)]
pub enum AppError {
    #[error("认证失败: {0}")]
    AuthError(String),

    #[error("资源未找到: {0}")]
    NotFound(String),

    #[error("验证错误: {0}")]
    ValidationError(String),

    #[error("数据库错误: {0}")]
    DatabaseError(String),

    #[error("Git 操作失败: {message}")]
    #[allow(dead_code)]
    GitError { code: String, message: String },

    #[error("Docker 操作失败: {message}")]
    DockerError { code: String, message: String },

    #[error("K8s 操作失败: {message}")]
    #[allow(dead_code)]
    K8sError { code: String, message: String },

    #[error("Agent 服务调用失败: {0}")]
    #[allow(dead_code)]
    AgentError(String),

    #[error("网络错误: {0}")]
    #[allow(dead_code)]
    NetworkError(String),

    #[error("LLM 调用失败: {0}")]
    #[allow(dead_code)]
    LLMError(String),

    #[error("请求过于频繁")]
    #[allow(dead_code)]
    RateLimitError,

    #[error("部署已取消")]
    DeploymentCancelled,

    #[error("密码哈希错误: {0}")]
    PasswordHashError(String),

    #[error("内部错误: {0}")]
    InternalError(String),
}

#[derive(Debug, Clone, serde::Serialize)]
pub enum Severity {
    LOW,
    MEDIUM,
    HIGH,
    CRITICAL,
}

impl AppError {
    pub fn status_code(&self) -> StatusCode {
        match self {
            AppError::AuthError(_) => StatusCode::UNAUTHORIZED,
            AppError::NotFound(_) => StatusCode::NOT_FOUND,
            AppError::ValidationError(_) => StatusCode::BAD_REQUEST,
            AppError::DatabaseError(_) => StatusCode::INTERNAL_SERVER_ERROR,
            AppError::GitError { .. } => StatusCode::INTERNAL_SERVER_ERROR,
            AppError::DockerError { .. } => StatusCode::INTERNAL_SERVER_ERROR,
            AppError::K8sError { .. } => StatusCode::INTERNAL_SERVER_ERROR,
            AppError::AgentError(_) => StatusCode::BAD_GATEWAY,
            AppError::NetworkError(_) => StatusCode::SERVICE_UNAVAILABLE,
            AppError::LLMError(_) => StatusCode::INTERNAL_SERVER_ERROR,
            AppError::RateLimitError => StatusCode::TOO_MANY_REQUESTS,
            AppError::DeploymentCancelled => StatusCode::CONFLICT,
            AppError::PasswordHashError(_) => StatusCode::INTERNAL_SERVER_ERROR,
            AppError::InternalError(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    pub fn severity(&self) -> Severity {
        match self {
            AppError::AuthError(_) => Severity::MEDIUM,
            AppError::NotFound(_) => Severity::LOW,
            AppError::ValidationError(_) => Severity::LOW,
            AppError::DatabaseError(_) => Severity::CRITICAL,
            AppError::GitError { .. } => Severity::HIGH,
            AppError::DockerError { .. } => Severity::HIGH,
            AppError::K8sError { .. } => Severity::HIGH,
            AppError::AgentError(_) => Severity::MEDIUM,
            AppError::NetworkError(_) => Severity::HIGH,
            AppError::LLMError(_) => Severity::MEDIUM,
            AppError::RateLimitError => Severity::LOW,
            AppError::DeploymentCancelled => Severity::LOW,
            AppError::PasswordHashError(_) => Severity::CRITICAL,
            AppError::InternalError(_) => Severity::CRITICAL,
        }
    }

    pub fn error_code(&self) -> u16 {
        match self {
            AppError::AuthError(_) => 40101,
            AppError::NotFound(_) => 40401,
            AppError::ValidationError(_) => 40001,
            AppError::DatabaseError(_) => 50001,
            AppError::GitError { .. } => 50002,
            AppError::DockerError { .. } => 50003,
            AppError::K8sError { .. } => 50004,
            AppError::AgentError(_) => 50201,
            AppError::NetworkError(_) => 50301,
            AppError::LLMError(_) => 50005,
            AppError::RateLimitError => 42901,
            AppError::DeploymentCancelled => 40901,
            AppError::PasswordHashError(_) => 50006,
            AppError::InternalError(_) => 50000,
        }
    }

    pub fn retryable(&self) -> bool {
        matches!(self,
            AppError::GitError { .. } |
            AppError::DockerError { .. } |
            AppError::K8sError { .. } |
            AppError::NetworkError(_) |
            AppError::AgentError(_)
        )
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let status = self.status_code();
        let body = Json(json!({
            "code": self.error_code(),
            "message": self.to_string(),
            "severity": format!("{:?}", self.severity()),
            "retryable": self.retryable(),
            "timestamp": Utc::now().format("%Y-%m-%dT%H:%M:%S%.fZ").to_string(),
        }));
        (status, body).into_response()
    }
}
