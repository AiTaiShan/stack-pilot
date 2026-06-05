use tracing::info;
use uuid::Uuid;
use crate::error::AppError;
use crate::services::scanner::git::GitService;
use crate::services::scanner::detector::detect;

pub async fn execute(
    _db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
    git_url: &str,
    branch: &str,
) -> Result<(), AppError> {
    info!("步骤 1: 克隆仓库 - 部署 {}", deployment_id);

    let temp_dir = format!("/tmp/stackpilot/{}", deployment_id);
    let git_service = GitService::new(&temp_dir);
    let repo_dir = git_service.clone(git_url, Some(branch)).await?;

    info!("步骤 1: 检测项目类型");
    let scan_result = detect(&repo_dir).await?;

    info!("克隆完成: {:?}", repo_dir);
    info!(
        "检测结果: language={:?}, framework={:?}",
        scan_result.language, scan_result.framework
    );

    Ok(())
}
