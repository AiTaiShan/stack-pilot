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
    info!("步骤 3: 构建镜像 - 部署 {}", deployment_id);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let temp_dir = format!("/tmp/stackpilot/{}", deployment_id);
    let repo_dir = std::path::PathBuf::from(&temp_dir);

    let repo_name = dep.git_url
        .as_ref()
        .and_then(|u| u.rsplit('/').next())
        .unwrap_or("app")
        .replace(".git", "")
        .to_lowercase();

    let commit_hash = dep.commit_hash.as_deref().unwrap_or("latest");
    let tag = format!("stackpilot/{}:{}", repo_name, &commit_hash[..8.min(commit_hash.len())]);

    let docker_service = DockerService::new("");
    docker_service.build_image(&repo_dir, &tag, "Dockerfile").await?;

    info!("镜像构建完成: {}", tag);
    Ok(())
}
