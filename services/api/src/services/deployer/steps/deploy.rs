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

    // 从 config 读取 repo_dir（由 clone 步骤写入）
    let config = dep.config.as_ref()
        .and_then(|c| c.as_object())
        .cloned()
        .unwrap_or_default();

    let repo_dir_str = config.get("_repo_dir")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let repo_dir = std::path::PathBuf::from(repo_dir_str);

    if !repo_dir.exists() {
        return Err(AppError::NotFound(format!("仓库目录不存在: {}", repo_dir_str)));
    }

    // 从 image_tag 字段读取镜像 tag（由 build 步骤写入）
    let image_tag = dep.image_tag.as_deref().unwrap_or("stackpilot/app:latest");

    // 从 scan_result 读取端口
    let port = config.get("scan_result")
        .and_then(|s| s.get("port"))
        .and_then(|v| v.as_u64())
        .unwrap_or(8080) as u16;

    match platform {
        "docker" => {
            info!("使用 docker-compose 部署，工作目录: {:?}", repo_dir);
            let output = tokio::process::Command::new("docker")
                .args(["compose", "up", "-d"])
                .current_dir(&repo_dir)
                .output()
                .await
                .map_err(|e| AppError::InternalError(format!("docker compose 启动失败: {}", e)))?;

            if !output.status.success() {
                let _stderr = String::from_utf8_lossy(&output.stderr);
                info!("docker compose (新版) 失败，尝试旧版 docker-compose...");
                // 回退到旧版 docker-compose
                let output2 = tokio::process::Command::new("docker-compose")
                    .args(["up", "-d"])
                    .current_dir(&repo_dir)
                    .output()
                    .await;
                match output2 {
                    Ok(out) if out.status.success() => {
                        info!("docker-compose (旧版) 启动成功");
                    }
                    Ok(out) => {
                        let stderr2 = String::from_utf8_lossy(&out.stderr);
                        return Err(AppError::InternalError(format!("docker-compose 启动失败: {}", stderr2)));
                    }
                    Err(e) => {
                        return Err(AppError::InternalError(format!("docker-compose 命令执行失败: {}", e)));
                    }
                }
            }
        }
        "k8s" => {
            info!("使用 Kubernetes 部署，镜像: {}", image_tag);
            let k8s_service = crate::services::deployer::k8s::K8sService::new(None);
            let name = dep.git_url
                .as_ref()
                .and_then(|u| u.rsplit('/').next())
                .unwrap_or("app")
                .replace(".git", "")
                .to_lowercase();
            let namespace = format!("stackpilot-{}", deployment_id);
            k8s_service.create_namespace(&namespace).await?;
            k8s_service.create_deployment(&namespace, &name, image_tag, 1, port, None).await?;
            k8s_service.create_service(&namespace, &name, port, port, "LoadBalancer").await?;
        }
        _ => {
            return Err(AppError::ValidationError(format!("不支持的部署平台: {}", platform)));
        }
    }

    info!("部署完成");
    Ok(())
}
