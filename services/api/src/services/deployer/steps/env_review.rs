use std::collections::HashMap;
use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};
use crate::services::agent::{AgentClient, ProjectInfo};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 4: 环境变量审核 - 部署 {}", deployment_id);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    // 从 deployment.config 读取 scan_result
    let config = dep.config.as_ref()
        .and_then(|c| c.as_object())
        .cloned()
        .unwrap_or_default();

    let scan_result = config.get("scan_result")
        .and_then(|v| v.as_object())
        .cloned()
        .unwrap_or_default();

    let repo_dir_str = config.get("_repo_dir")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let repo_dir = std::path::PathBuf::from(repo_dir_str);

    if !repo_dir.exists() {
        info!("仓库目录不存在，跳过环境变量审核");
        return Ok(());
    }

    // 收集环境变量：从 .env 文件 + docker-compose.yml
    let mut env_vars: HashMap<String, String> = HashMap::new();

    // 1. 从 .env 文件读取
    let env_path = repo_dir.join(".env");
    if env_path.exists() {
        let env_content = tokio::fs::read_to_string(&env_path).await
            .map_err(|e| AppError::InternalError(format!("读取 .env 失败: {}", e)))?;

        for line in env_content.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some((key, value)) = line.split_once('=') {
                env_vars.insert(key.trim().to_string(), value.trim().to_string());
            }
        }
        info!("从 .env 文件读取到 {} 个环境变量", env_vars.len());
    }

    // 2. 从 docker-compose.yml 的 environment 字段读取
    let compose_path = repo_dir.join("docker-compose.yml");
    if compose_path.exists() {
        let compose_content = tokio::fs::read_to_string(&compose_path).await
            .map_err(|e| AppError::InternalError(format!("读取 docker-compose.yml 失败: {}", e)))?;

        let compose_vars = extract_env_from_compose(&compose_content);
        if !compose_vars.is_empty() {
            info!("从 docker-compose.yml 读取到 {} 个环境变量", compose_vars.len());
            // compose 中的环境变量作为补充，不覆盖 .env 中的值
            for (key, value) in compose_vars {
                env_vars.entry(key).or_insert(value);
            }
        }
    }

    if env_vars.is_empty() {
        info!("没有环境变量需要审核");
        return Ok(());
    }

    info!("共收集到 {} 个环境变量待审核", env_vars.len());

    // 构建 ProjectInfo
    let language = scan_result.get("language").and_then(|v| v.as_str()).unwrap_or("unknown");
    let framework = scan_result.get("framework").and_then(|v| v.as_str()).unwrap_or("unknown");
    let version = scan_result.get("version").and_then(|v| v.as_str()).unwrap_or("latest");
    let port = scan_result.get("port").and_then(|v| v.as_u64()).unwrap_or(8080) as u16;
    let project_type = scan_result.get("project_type").and_then(|v| v.as_str()).unwrap_or("single");

    let project_info = ProjectInfo {
        language: language.to_string(),
        framework: framework.to_string(),
        version: version.to_string(),
        port,
        project_type: project_type.to_string(),
    };

    // 调用 Agent 审核
    let agent_url = std::env::var("AGENT_SERVICE_URL")
        .unwrap_or_else(|_| "http://localhost:8066".to_string());
    let agent_client = AgentClient::new(&agent_url);

    let healthy = agent_client.health_check().await.unwrap_or(false);
    if !healthy {
        info!("Agent 服务不可用，跳过环境变量 AI 审核");
        return Ok(());
    }

    match agent_client.review_env(project_info, env_vars).await {
        Ok(result) => {
            info!("环境变量审核结果: {}", result.status);
            for issue in &result.issues {
                info!("  [{}] {}: {}", issue.severity, issue.category, issue.description);
            }
        }
        Err(e) => {
            info!("环境变量审核失败（继续部署）: {}", e);
        }
    }

    info!("步骤 4 完成: 环境变量审核");
    Ok(())
}

/// 从 docker-compose.yml 内容中提取所有 service 的 environment 变量
fn extract_env_from_compose(content: &str) -> HashMap<String, String> {
    let mut env_vars = HashMap::new();

    // 简单解析 YAML 中的 environment 字段
    // 支持两种格式：
    //   environment:
    //     KEY: VALUE
    //   environment:
    //     - KEY=VALUE
    let mut in_environment = false;
    let mut indent_level = 0;

    for line in content.lines() {
        let trimmed = line.trim();

        // 跳过空行和注释
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        // 检测 environment 块的开始
        if trimmed.starts_with("environment:") {
            in_environment = true;
            indent_level = line.len() - line.trim_start().len();
            continue;
        }

        if in_environment {
            let current_indent = line.len() - line.trim_start().len();
            // 缩进回退说明 environment 块结束
            if current_indent <= indent_level && !trimmed.is_empty() {
                in_environment = false;
                continue;
            }

            // 解析 KEY: VALUE 格式
            if let Some((key, value)) = trimmed.split_once(':') {
                let key = key.trim().to_string();
                let value = value.trim().trim_matches('"').trim_matches('\'').to_string();
                if !key.is_empty() && !key.contains(' ') {
                    env_vars.insert(key, value);
                }
            }
            // 解析 - KEY=VALUE 格式
            else if trimmed.starts_with("- ") {
                let item = trimmed[2..].trim();
                if let Some((key, value)) = item.split_once('=') {
                    let key = key.trim().to_string();
                    let value = value.trim().trim_matches('"').trim_matches('\'').to_string();
                    env_vars.insert(key, value);
                }
            }
        }
    }

    env_vars
}
