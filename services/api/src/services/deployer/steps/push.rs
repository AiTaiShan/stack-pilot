use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};
use crate::services::deployer::docker::DockerService;

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 5: 推送镜像 - 部署 {}", deployment_id);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let image_tag = dep.image_tag.as_deref().unwrap_or("stackpilot/app:latest");

    let registry_url = std::env::var("DOCKER_REGISTRY_URL").unwrap_or_default();
    let docker_service = DockerService::new(&registry_url);
    docker_service.push_image(image_tag).await?;

    info!("镜像推送完成");
    Ok(())
}
