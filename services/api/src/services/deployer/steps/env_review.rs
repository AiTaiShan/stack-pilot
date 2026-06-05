use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 5: 环境变量审核 - 部署 {}", deployment_id);

    let _dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let temp_dir = format!("/tmp/stackpilot/{}", deployment_id);
    let repo_dir = std::path::PathBuf::from(&temp_dir);

    // 检查是否有 .env 文件需要审核
    let env_path = repo_dir.join(".env");
    if !env_path.exists() {
        info!("没有 .env 文件，跳过环境变量审核");
        return Ok(());
    }

    // 检查 Agent 服务
    let agent_url = std::env::var("AGENT_SERVICE_URL").unwrap_or_else(|_| "http://localhost:8081".to_string());
    let agent_client = crate::services::agent::AgentClient::new(&agent_url);

    let healthy = agent_client.health_check().await.unwrap_or(false);
    if !healthy {
        info!("Agent 服务不可用，跳过环境变量 AI 审核");
        return Ok(());
    }

    // 读取 .env 文件
    let env_content = tokio::fs::read_to_string(&env_path).await
        .map_err(|e| AppError::InternalError(format!("读取 .env 失败: {}", e)))?;

    let env_vars: std::collections::HashMap<String, String> = env_content
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                return None;
            }
            let mut parts = line.splitn(2, '=');
            let key = parts.next()?.trim().to_string();
            let value = parts.next().unwrap_or("").trim().to_string();
            Some((key, value))
        })
        .collect();

    if env_vars.is_empty() {
        info!("没有环境变量需要审核");
        return Ok(());
    }

    let project_info = crate::services::agent::ProjectInfo {
        language: "unknown".to_string(),
        framework: "unknown".to_string(),
        version: "latest".to_string(),
        port: 8080,
        project_type: "single".to_string(),
    };

    match agent_client.review_env(project_info, env_vars).await {
        Ok(result) => {
            info!("环境变量审核结果: {}", result.status);
            for issue in &result.issues {
                info!("  [{}] {}: {}", issue.severity, issue.category, issue.description);
            }
        }
        Err(e) => {
            info!("环境变量审核失败: {}", e);
        }
    }

    info!("环境变量审核完成");
    Ok(())
}
