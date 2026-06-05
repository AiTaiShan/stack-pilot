use async_trait::async_trait;
use super::context::ProjectContext;
use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct DetectionResult {
    pub language: String,
    pub framework: Option<String>,
    pub version: Option<String>,
    pub port: Option<u16>,
    pub confidence: f32,
}

#[async_trait]
pub trait BaseRule: Send + Sync {
    fn language_id(&self) -> &str;
    fn detect_language(&self, files: &[String]) -> f32;
    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError>;
}
