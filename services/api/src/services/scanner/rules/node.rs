use async_trait::async_trait;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct NodeRule;

#[async_trait]
impl BaseRule for NodeRule {
    fn language_id(&self) -> &str {
        "node"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f == "package.json") {
            return 0.9;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let content = ctx.read_text("package.json").await;
        if content.is_none() {
            return Ok(None);
        }

        let content = content.unwrap();
        let package: serde_json::Value = serde_json::from_str(&content)
            .map_err(|e| AppError::ValidationError(format!("package.json 解析失败: {}", e)))?;

        let framework = if let Some(deps) = package.get("dependencies") {
            if deps.get("express").is_some() {
                Some("express".to_string())
            } else if deps.get("fastify").is_some() {
                Some("fastify".to_string())
            } else if deps.get("koa").is_some() {
                Some("koa".to_string())
            } else {
                None
            }
        } else {
            None
        };

        Ok(Some(DetectionResult {
            language: "node".to_string(),
            framework,
            version: None,
            port: Some(3000),
            confidence: 0.9,
        }))
    }
}
