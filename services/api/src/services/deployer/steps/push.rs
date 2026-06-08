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

    // 优先从 image_tag 字段读取（build 步骤写入），回退到 config
    let image_tag = dep.image_tag.clone()
        .or_else(|| {
            dep.config.as_ref()
                .and_then(|c| c.as_object())
                .and_then(|config| config.get("scan_result"))
                .and_then(|s| s.get("image_tag"))
                .and_then(|v| v.as_str())
                .map(String::from)
        })
        .unwrap_or_else(|| "stackpilot/app:latest".to_string());

    let registry_url = std::env::var("DOCKER_REGISTRY_URL").unwrap_or_default();

    if registry_url.is_empty() {
        info!("未配置 DOCKER_REGISTRY_URL，跳过镜像推送");
        return Ok(());
    }

    info!("推送镜像 {} 到 {}", image_tag, registry_url);
    let docker_service = DockerService::new(&registry_url);
    docker_service.push_image(&image_tag).await?;

    info!("步骤 5 完成: 镜像推送");
    Ok(())
}
