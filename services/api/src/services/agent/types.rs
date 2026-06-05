use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectInfo {
    pub language: String,
    pub framework: String,
    pub version: String,
    pub port: u16,
    pub project_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReviewDockerfileRequest {
    pub project_info: ProjectInfo,
    pub dockerfile_content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReviewComposeRequest {
    pub project_info: ProjectInfo,
    pub compose_content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReviewEnvRequest {
    pub project_info: ProjectInfo,
    pub env_vars: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReviewIssue {
    pub category: String,
    pub severity: String,
    pub description: String,
    pub file_path: String,
    pub fix_suggestion: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReviewResponse {
    pub status: String,
    pub issues: Vec<ReviewIssue>,
    pub fixed_content: Option<String>,
    pub suggestions: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiagnoseRequest {
    pub error_message: String,
    pub step_name: String,
    pub project_type: String,
    pub logs: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DiagnosisResponse {
    pub diagnosis: String,
    pub suggestions: Vec<String>,
    pub retryable: bool,
}
