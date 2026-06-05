use async_trait::async_trait;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct JavaRule;

#[async_trait]
impl BaseRule for JavaRule {
    fn language_id(&self) -> &str {
        "java"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f == "pom.xml" || f == "build.gradle" || f == "build.gradle.kts") {
            return 0.9;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let pom_content = ctx.read_text("pom.xml").await;

        if let Some(content) = pom_content {
            let framework = if content.contains("spring-boot") {
                Some("spring-boot".to_string())
            } else if content.contains("quarkus") {
                Some("quarkus".to_string())
            } else {
                None
            };

            return Ok(Some(DetectionResult {
                language: "java".to_string(),
                framework,
                version: None,
                port: Some(8080),
                confidence: 0.9,
            }));
        }

        let has_gradle = ctx.read_text("build.gradle").await.is_some()
            || ctx.read_text("build.gradle.kts").await.is_some();

        if has_gradle {
            return Ok(Some(DetectionResult {
                language: "java".to_string(),
                framework: None,
                version: None,
                port: Some(8080),
                confidence: 0.85,
            }));
        }

        Ok(None)
    }
}
