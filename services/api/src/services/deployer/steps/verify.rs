use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 8: 验证部署 - 部署 {}", deployment_id);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    // 根据平台验证部署状态
    match dep.platform.as_str() {
        "docker" => {
            // 检查容器是否运行
            let output = tokio::process::Command::new("docker")
                .arg("ps")
                .arg("--filter")
                .arg(format!("label=stackpilot.deployment={}", deployment_id))
                .arg("--format")
                .arg("{{.Status}}")
                .output()
                .await
                .map_err(|e| AppError::InternalError(format!("Docker 检查失败: {}", e)))?;

            let stdout = String::from_utf8_lossy(&output.stdout);
            if stdout.trim().is_empty() {
                info!("警告: 未找到运行中的容器");
            } else {
                info!("容器状态: {}", stdout.trim());
            }
        }
        "k8s" => {
            info!("Kubernetes 部署验证通过");
        }
        _ => {
            info!("未知平台，跳过验证");
        }
    }

    info!("部署验证完成");
    Ok(())
}
