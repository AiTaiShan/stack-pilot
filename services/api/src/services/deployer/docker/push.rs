use tracing::info;
use crate::error::AppError;
use super::build::DockerService;

impl DockerService {
    pub async fn push_image(&self, image_tag: &str) -> Result<String, AppError> {
        info!("推送镜像: {}", image_tag);

        let full_tag = if self.registry_url.is_empty() {
            image_tag.to_string()
        } else {
            format!("{}/{}", self.registry_url, image_tag)
        };

        // 如果有 registry，先 tag
        if !self.registry_url.is_empty() {
            let output = tokio::process::Command::new("docker")
                .arg("tag")
                .arg(image_tag)
                .arg(&full_tag)
                .output()
                .await
                .map_err(|e| AppError::InternalError(format!("Docker tag 失败: {}", e)))?;

            if !output.status.success() {
                let stderr = String::from_utf8_lossy(&output.stderr);
                return Err(AppError::InternalError(format!("Docker tag 失败: {}", stderr)));
            }
        }

        // 带超时+重试的推送
        let max_retries = 3u32;
        for attempt in 0..=max_retries {
            let output_result = tokio::time::timeout(
                std::time::Duration::from_secs(300),
                tokio::process::Command::new("docker")
                    .arg("push")
                    .arg(&full_tag)
                    .output(),
            )
            .await;

            match output_result {
                Ok(Ok(output)) if output.status.success() => {
                    info!("镜像推送完成: {}", full_tag);
                    return Ok(full_tag);
                }
                Ok(Ok(output)) => {
                    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
                    if attempt >= max_retries {
                        return Err(AppError::DockerError {
                            code: "PUSH_FAILED".to_string(),
                            message: format!("Docker 推送失败 (重试 {} 次): {}", max_retries, stderr),
                        });
                    }
                    let wait_secs = 5 * (attempt + 1) as u64;
                    info!("推送失败，{}秒后重试 (第{}/{}次): {}", wait_secs, attempt + 1, max_retries, stderr);
                    tokio::time::sleep(std::time::Duration::from_secs(wait_secs)).await;
                }
                Ok(Err(e)) => {
                    if attempt >= max_retries {
                        return Err(AppError::DockerError {
                            code: "PUSH_FAILED".to_string(),
                            message: format!("Docker push 命令执行失败 (重试 {} 次): {}", max_retries, e),
                        });
                    }
                    let wait_secs = 5 * (attempt + 1) as u64;
                    info!("推送命令异常，{}秒后重试 (第{}/{}次): {}", wait_secs, attempt + 1, max_retries, e);
                    tokio::time::sleep(std::time::Duration::from_secs(wait_secs)).await;
                }
                Err(_) => {
                    return Err(AppError::DockerError {
                        code: "PUSH_TIMEOUT".to_string(),
                        message: "推送超时 (300s)".to_string(),
                    });
                }
            }
        }

        Err(AppError::DockerError {
            code: "PUSH_FAILED".to_string(),
            message: "重试耗尽".to_string(),
        })
    }
}
