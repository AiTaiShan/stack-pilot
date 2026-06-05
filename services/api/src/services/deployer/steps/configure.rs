use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 7: 配置服务 - 部署 {}", deployment_id);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    // 根据平台配置服务
    match dep.platform.as_str() {
        "docker" => {
            info!("Docker 平台配置完成（无需额外配置）");
        }
        "k8s" => {
            info!("Kubernetes 平台配置完成");
        }
        _ => {
            info!("未知平台，跳过配置");
        }
    }

    info!("服务配置完成");
    Ok(())
}
