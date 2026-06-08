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

    // 从 deployment.config 读取 scan_result
    let config = dep.config.as_ref()
        .and_then(|c| c.as_object())
        .cloned()
        .unwrap_or_default();

    let scan_result = config.get("scan_result")
        .and_then(|v| v.as_object())
        .cloned()
        .unwrap_or_default();

    let repo_dir_str = config.get("_repo_dir")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let repo_dir = std::path::PathBuf::from(repo_dir_str);

    if !repo_dir.exists() {
        return Err(AppError::NotFound(format!("仓库目录不存在: {}", repo_dir_str)));
    }

    let language = scan_result.get("language").and_then(|v| v.as_str()).unwrap_or("unknown");
    let project_type = scan_result.get("project_type").and_then(|v| v.as_str()).unwrap_or("single");

    let repo_name = dep.git_url
        .as_ref()
        .and_then(|u| u.rsplit('/').next())
        .unwrap_or("app")
        .replace(".git", "")
        .to_lowercase();

    let commit_hash = dep.commit_hash.as_deref().unwrap_or("latest");
    let tag = format!("stackpilot/{}:{}", repo_name, &commit_hash[..8.min(commit_hash.len())]);

    // ── 1. 清理旧镜像 ──
    cleanup_old_images(&repo_name).await;

    // ── 2. Java 项目：先执行 Maven 构建 ──
    if language == "java" || project_type.contains("java") || project_type.contains("spring") {
        run_maven_build(&repo_dir, deployment_id).await?;
    }

    // ── 3. Docker 构建 ──
    let docker_service = DockerService::new("");
    docker_service.build_image(&repo_dir, &tag, "Dockerfile").await?;

    info!("镜像构建完成: {}", tag);
    Ok(())
}

/// 清理旧的 Docker 镜像，防止磁盘空间膨胀
async fn cleanup_old_images(repo_name: &str) {
    let image_prefix = format!("stackpilot/{}", repo_name);

    // 列出所有相关镜像
    let output = tokio::process::Command::new("docker")
        .args(["images", "--format", "{{.Repository}}:{{.Tag}}"])
        .arg("--filter")
        .arg(format!("reference={}*", image_prefix))
        .arg("--sort")
        .arg("created")
        .output()
        .await;

    match output {
        Ok(out) if out.status.success() => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            let images: Vec<&str> = stdout.lines().filter(|l| !l.trim().is_empty()).collect();

            if images.is_empty() {
                info!("无旧镜像需要清理");
                return;
            }

            info!("清理 {} 个旧镜像...", images.len());
            for img in &images {
                info!("  删除镜像: {}", img);
                let _ = tokio::process::Command::new("docker")
                    .args(["rmi", "-f", img])
                    .output()
                    .await;
            }
            info!("旧镜像清理完成");
        }
        _ => {
            info!("镜像清理跳过（docker images 命令失败）");
        }
    }

    // 清理悬空镜像
    let _ = tokio::process::Command::new("docker")
        .args(["image", "prune", "-f"])
        .output()
        .await;
}

/// Java 项目：执行 Maven 构建
async fn run_maven_build(repo_dir: &std::path::Path, deployment_id: Uuid) -> Result<(), AppError> {
    info!("Java 项目检测到，执行 Maven 构建...");

    // 优先使用 mvnw（Maven Wrapper），回退到 mvn
    let mvnw_path = repo_dir.join("mvnw");
    let (cmd, args) = if mvnw_path.exists() {
        info!("使用 Maven Wrapper (mvnw)");
        ("./mvnw", vec!["clean", "package", "-DskipTests"])
    } else {
        info!("使用系统 mvn");
        ("mvn", vec!["clean", "package", "-DskipTests"])
    };

    let output = tokio::process::Command::new(cmd)
        .args(&args)
        .current_dir(repo_dir)
        .output()
        .await
        .map_err(|e| AppError::InternalError(format!("Maven 构建启动失败: {}", e)))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        // 只取最后 500 字符避免日志过长
        let tail_stderr = if stderr.len() > 500 { &stderr[stderr.len()-500..] } else { &stderr };
        let tail_stdout = if stdout.len() > 500 { &stdout[stdout.len()-500..] } else { &stdout };
        return Err(AppError::InternalError(format!(
            "Maven 构建失败:\nstdout: {}\nstderr: {}", tail_stdout, tail_stderr
        )));
    }

    info!("Maven 构建完成 - 部署 {}", deployment_id);
    Ok(())
}
