use tracing::info;
use uuid::Uuid;
use sea_orm::{EntityTrait, ActiveModelTrait, Set};
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity, ActiveModel as DeploymentActiveModel};
use crate::services::scanner::git::GitService;
use crate::services::scanner::detector::detect;

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
    git_url: &str,
    branch: &str,
) -> Result<(), AppError> {
    info!("步骤 1: 克隆仓库 - 部署 {}", deployment_id);

    // 1. 克隆仓库
    let temp_dir = format!("/tmp/stackpilot/{}", deployment_id);
    let git_service = GitService::new(&temp_dir);
    let repo_dir = git_service.clone(git_url, Some(branch)).await?;

    // 2. 获取 commit 信息
    let commit_info = git_service.get_latest_commit(&repo_dir).await;
    let (commit_hash, commit_message) = match commit_info {
        Ok(info) => (Some(info.hash.clone()), Some(info.message.clone())),
        Err(_) => (None, None),
    };

    // 3. 检测项目类型
    info!("步骤 1: 检测项目类型");
    let scan_result = detect(&repo_dir).await?;

    info!("克隆完成: {:?}", repo_dir);
    info!(
        "检测结果: type={}, language={:?}, framework={:?}, port={:?}",
        scan_result.project_type, scan_result.language, scan_result.framework, scan_result.port
    );

    // 4. 持久化 ScanResult 到 deployment.config
    let scan_config = serde_json::json!({
        "scan_result": {
            "project_type": scan_result.project_type,
            "language": scan_result.language,
            "framework": scan_result.framework,
            "version": scan_result.version,
            "port": scan_result.port,
            "dependencies": {
                "external_services": scan_result.dependencies.external_services,
                "service_versions": scan_result.dependencies.service_versions,
                "app_port": scan_result.dependencies.app_port,
            },
        },
        "_repo_dir": repo_dir.to_string_lossy(),
    });

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let mut active: DeploymentActiveModel = dep.into();
    active.config = Set(Some(scan_config));
    if let Some(hash) = commit_hash {
        active.commit_hash = Set(Some(hash));
    }
    if let Some(msg) = commit_message {
        active.commit_message = Set(Some(msg));
    }
    active.update(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?;

    info!("ScanResult 已持久化到 deployment.config");
    Ok(())
}
