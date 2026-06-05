use async_trait::async_trait;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct GoRule;

#[async_trait]
impl BaseRule for GoRule {
    fn language_id(&self) -> &str {
        "go"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f == "go.mod") {
            return 0.9;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let content = ctx.read_text("go.mod").await;
        if content.is_none() {
            return Ok(None);
        }

        let content = content.unwrap();

        let version = content
            .lines()
            .find(|l| l.starts_with("go "))
            .map(|l| l.trim_start_matches("go ").trim().to_string());

        let framework = if content.contains("gin-gonic/gin") {
            Some("gin".to_string())
        } else if content.contains("labstack/echo") {
            Some("echo".to_string())
        } else if content.contains("gofiber/fiber") {
            Some("fiber".to_string())
        } else {
            None
        };

        Ok(Some(DetectionResult {
            language: "go".to_string(),
            framework,
            version,
            port: Some(8080),
            confidence: 0.9,
        }))
    }
}
