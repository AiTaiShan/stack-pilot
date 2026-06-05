use async_trait::async_trait;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct RustRule;

#[async_trait]
impl BaseRule for RustRule {
    fn language_id(&self) -> &str {
        "rust"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f == "Cargo.toml") {
            return 0.9;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let content = ctx.read_text("Cargo.toml").await;
        if content.is_none() {
            return Ok(None);
        }

        let content = content.unwrap();

        let framework = if content.contains("actix-web") {
            Some("actix".to_string())
        } else if content.contains("axum") {
            Some("axum".to_string())
        } else if content.contains("rocket") {
            Some("rocket".to_string())
        } else {
            None
        };

        Ok(Some(DetectionResult {
            language: "rust".to_string(),
            framework,
            version: None,
            port: Some(8080),
            confidence: 0.9,
        }))
    }
}
