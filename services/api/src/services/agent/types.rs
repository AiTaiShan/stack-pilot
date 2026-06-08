#![allow(dead_code)]
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
pub struct DeployDiagnoseRequest {
    pub deployment_id: String,
    pub failed_step: String,
    pub project_type: String,
    pub language: String,
    pub framework: String,
    pub dockerfile_content: Option<String>,
    pub compose_content: Option<String>,
    pub logs: Vec<String>,
    pub retry_count: i32,
    pub max_retries: i32,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DeployDiagnoseResponse {
    pub diagnosis: String,
    pub suggestions: Vec<String>,
    pub failure_category: String,
    pub fixable_by_agent: bool,
    pub fixed_content: Option<String>,
    pub fixed_file_type: Option<String>,
    pub retry_count: i32,
}
