use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 2: AI 审核 - 部署 {}", deployment_id);

    let _dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let temp_dir = format!("/tmp/stackpilot/{}", deployment_id);
    let repo_dir = std::path::PathBuf::from(&temp_dir);

    // 检查 Agent 服务健康状态
    let agent_url = std::env::var("AGENT_SERVICE_URL").unwrap_or_else(|_| "http://localhost:8081".to_string());
    let agent_client = crate::services::agent::AgentClient::new(&agent_url);

    let healthy = agent_client.health_check().await.unwrap_or(false);
    if !healthy {
        info!("Agent 服务不可用，跳过 AI 审核");
        return Ok(());
    }

    // 审核 Dockerfile
    let dockerfile_path = repo_dir.join("Dockerfile");
    if dockerfile_path.exists() {
        let content = tokio::fs::read_to_string(&dockerfile_path).await
            .map_err(|e| AppError::InternalError(format!("读取 Dockerfile 失败: {}", e)))?;

        let project_info = crate::services::agent::ProjectInfo {
            language: "unknown".to_string(),
            framework: "unknown".to_string(),
            version: "latest".to_string(),
            port: 8080,
            project_type: "single".to_string(),
        };

        match agent_client.review_dockerfile(project_info, content).await {
            Ok(result) => {
                info!("Dockerfile 审核结果: {}", result.status);
                if result.status == "needs_fix" {
                    if let Some(fixed) = result.fixed_content {
                        tokio::fs::write(&dockerfile_path, fixed).await
                            .map_err(|e| AppError::InternalError(format!("写入 Dockerfile 失败: {}", e)))?;
                        info!("Dockerfile 已自动修复");
                    }
                }
            }
            Err(e) => {
                info!("Dockerfile 审核失败: {}", e);
            }
        }
    }

    info!("审核完成");
    Ok(())
}
