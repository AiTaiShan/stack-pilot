#![allow(dead_code)]
use tracing::info;
use crate::error::AppError;
use super::build::DockerService;

impl DockerService {
    pub async fn cleanup_old_images(&self, repo_name: &str) -> Result<(), AppError> {
        info!("清理旧镜像: {}", repo_name);

        let image_prefix = format!("stackpilot/{}", repo_name);

        let output = tokio::process::Command::new("docker")
            .arg("images")
            .arg("--format")
            .arg("{{.Repository}}:{{.Tag}}")
            .arg("--filter")
            .arg(format!("reference={}*", image_prefix))
            .output()
            .await
            .map_err(|e| AppError::InternalError(format!("Docker images 命令失败: {}", e)))?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let images: Vec<&str> = stdout.lines().collect();

        if images.len() <= 1 {
            info!("没有需要清理的旧镜像");
            return Ok(());
        }

        // 保留最新的，删除其他的
        for image in &images[1..] {
            let _ = tokio::process::Command::new("docker")
                .arg("rmi")
                .arg("-f")
                .arg(image)
                .output()
                .await;
        }

        info!("旧镜像清理完成");
        Ok(())
    }
}
