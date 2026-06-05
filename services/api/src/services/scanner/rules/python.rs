use async_trait::async_trait;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct PythonRule;

#[async_trait]
impl BaseRule for PythonRule {
    fn language_id(&self) -> &str {
        "python"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f == "requirements.txt" || f == "pyproject.toml") {
            return 0.9;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let has_requirements = ctx.read_text("requirements.txt").await.is_some();
        let has_pyproject = ctx.read_text("pyproject.toml").await.is_some();

        if !has_requirements && !has_pyproject {
            return Ok(None);
        }

        let framework = if has_requirements {
            let content = ctx.read_text("requirements.txt").await.unwrap_or_default();
            if content.contains("fastapi") {
                Some("fastapi".to_string())
            } else if content.contains("flask") {
                Some("flask".to_string())
            } else if content.contains("django") {
                Some("django".to_string())
            } else {
                None
            }
        } else {
            None
        };

        Ok(Some(DetectionResult {
            language: "python".to_string(),
            framework,
            version: Some("3.11".to_string()),
            port: Some(8000),
            confidence: 0.9,
        }))
    }
}
