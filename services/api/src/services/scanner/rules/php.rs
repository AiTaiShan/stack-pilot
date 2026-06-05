use async_trait::async_trait;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct PhpRule;

#[async_trait]
impl BaseRule for PhpRule {
    fn language_id(&self) -> &str {
        "php"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f == "composer.json") {
            return 0.9;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let content = ctx.read_text("composer.json").await;
        if content.is_none() {
            return Ok(None);
        }

        let content = content.unwrap();

        let framework = if content.contains("laravel") {
            Some("laravel".to_string())
        } else if content.contains("symfony") {
            Some("symfony".to_string())
        } else {
            None
        };

        Ok(Some(DetectionResult {
            language: "php".to_string(),
            framework,
            version: None,
            port: Some(8000),
            confidence: 0.9,
        }))
    }
}
