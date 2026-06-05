use async_trait::async_trait;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct RubyRule;

#[async_trait]
impl BaseRule for RubyRule {
    fn language_id(&self) -> &str {
        "ruby"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f == "Gemfile") {
            return 0.9;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let content = ctx.read_text("Gemfile").await;
        if content.is_none() {
            return Ok(None);
        }

        let content = content.unwrap();

        let framework = if content.contains("rails") {
            Some("rails".to_string())
        } else if content.contains("sinatra") {
            Some("sinatra".to_string())
        } else {
            None
        };

        Ok(Some(DetectionResult {
            language: "ruby".to_string(),
            framework,
            version: None,
            port: Some(3000),
            confidence: 0.9,
        }))
    }
}
