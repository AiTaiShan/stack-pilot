#![allow(dead_code)]
use reqwest::Client;
use std::time::Duration;
use tracing::info;
use crate::error::AppError;
use super::types::*;

pub struct AgentClient {
    base_url: String,
    client: Client,
}

impl AgentClient {
    pub fn new(base_url: &str) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(120))
            .connect_timeout(Duration::from_secs(10))
            .build()
            .unwrap_or_else(|_| Client::new());
        Self {
            base_url: base_url.to_string(),
            client,
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

    /// 部署失败诊断（编排流程）
    pub async fn deploy_diagnose(
        &self,
        request: DeployDiagnoseRequest,
    ) -> Result<DeployDiagnoseResponse, AppError> {
        self.post("/api/v1/deploy/diagnose", &request).await
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
