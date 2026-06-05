use reqwest::Client;
use tracing::info;
use crate::error::AppError;
use super::types::*;

pub struct AgentClient {
    base_url: String,
    client: Client,
}

impl AgentClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.to_string(),
            client: Client::new(),
        }
    }

    pub async fn review_dockerfile(
        &self,
        project_info: ProjectInfo,
        dockerfile_content: String,
    ) -> Result<ReviewResponse, AppError> {
        let request = ReviewDockerfileRequest {
            project_info,
            dockerfile_content,
        };

        self.post("/api/v1/review/dockerfile", &request).await
    }

    pub async fn review_compose(
        &self,
        project_info: ProjectInfo,
        compose_content: String,
    ) -> Result<ReviewResponse, AppError> {
        let request = ReviewComposeRequest {
            project_info,
            compose_content,
        };

        self.post("/api/v1/review/compose", &request).await
    }

    pub async fn review_env(
        &self,
        project_info: ProjectInfo,
        env_vars: std::collections::HashMap<String, String>,
    ) -> Result<ReviewResponse, AppError> {
        let request = ReviewEnvRequest {
            project_info,
            env_vars,
        };

        self.post("/api/v1/review/env", &request).await
    }

    pub async fn diagnose_error(
        &self,
        error_message: &str,
        step_name: &str,
        project_type: &str,
        logs: &[String],
    ) -> Result<DiagnosisResponse, AppError> {
        let req = DiagnoseRequest {
            error_message: error_message.to_string(),
            step_name: step_name.to_string(),
            project_type: project_type.to_string(),
            logs: logs.to_vec(),
        };
        self.post("/api/v1/review/diagnose", &req).await
    }

    pub async fn health_check(&self) -> Result<bool, AppError> {
        let url = format!("{}/api/v1/health", self.base_url);
        info!("检查 Agent 服务健康状态: {}", url);

        let response = self.client
            .get(&url)
            .send()
            .await
            .map_err(|e| AppError::InternalError(format!("Agent 服务请求失败: {}", e)))?;

        Ok(response.status().is_success())
    }

    async fn post<T: serde::Serialize, R: serde::de::DeserializeOwned>(
        &self,
        path: &str,
        body: &T,
    ) -> Result<R, AppError> {
        let url = format!("{}{}", self.base_url, path);
        info!("调用 Agent 服务: {}", url);

        let response = self.client
            .post(&url)
            .json(body)
            .send()
            .await
            .map_err(|e| AppError::InternalError(format!("Agent 服务请求失败: {}", e)))?;

        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().await.unwrap_or_default();
            return Err(AppError::InternalError(format!(
                "Agent 服务返回错误: {} - {}",
                status, text
            )));
        }

        response.json::<R>().await
            .map_err(|e| AppError::InternalError(format!("Agent 服务响应解析失败: {}", e)))
    }
}
