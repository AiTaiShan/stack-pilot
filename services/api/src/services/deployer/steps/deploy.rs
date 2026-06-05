use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
    platform: &str,
) -> Result<(), AppError> {
    info!("步骤 6: 部署应用 - 部署 {} - 平台 {}", deployment_id, platform);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let temp_dir = format!("/tmp/stackpilot/{}", deployment_id);
    let repo_dir = std::path::PathBuf::from(&temp_dir);

    match platform {
        "docker" => {
            info!("使用 docker-compose 部署");
            let output = tokio::process::Command::new("docker-compose")
                .arg("up")
                .arg("-d")
                .current_dir(&repo_dir)
                .output()
                .await
                .map_err(|e| AppError::InternalError(format!("docker-compose 启动失败: {}", e)))?;

            if !output.status.success() {
                let stderr = String::from_utf8_lossy(&output.stderr);
                return Err(AppError::InternalError(format!("docker-compose 启动失败: {}", stderr)));
            }
        }
        "k8s" => {
            info!("使用 Kubernetes 部署");
            let k8s_service = crate::services::deployer::k8s::K8sService::new(None);
            let name = dep.git_url
                .as_ref()
                .and_then(|u| u.rsplit('/').next())
                .unwrap_or("app")
                .replace(".git", "")
                .to_lowercase();
            let namespace = format!("stackpilot-{}", deployment_id);
            k8s_service.create_namespace(&namespace).await?;
            k8s_service.create_deployment(&namespace, &name, "latest", 1, 8080, None).await?;
            k8s_service.create_service(&namespace, &name, 8080, 8080, "LoadBalancer").await?;
        }
        _ => {
            return Err(AppError::ValidationError(format!("不支持的部署平台: {}", platform)));
        }
    }

    info!("部署完成");
    Ok(())
}
