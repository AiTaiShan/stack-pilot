use async_trait::async_trait;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct DotnetRule;

#[async_trait]
impl BaseRule for DotnetRule {
    fn language_id(&self) -> &str {
        "dotnet"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f.ends_with(".csproj") || f.ends_with(".sln")) {
            return 0.9;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let (files, _dirs) = ctx.list_dir(".").await.map_err(|e| {
            AppError::InternalError(format!("读取项目目录失败: {}", e))
        })?;

        let has_csproj = files.iter().any(|f| f.ends_with(".csproj"));
        if !has_csproj {
            return Ok(None);
        }

        Ok(Some(DetectionResult {
            language: "dotnet".to_string(),
            framework: Some("aspnet".to_string()),
            version: None,
            port: Some(5000),
            confidence: 0.85,
        }))
    }
}
