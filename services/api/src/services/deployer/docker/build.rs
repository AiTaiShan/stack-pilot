#![allow(dead_code)]
use std::collections::HashMap;
use std::path::PathBuf;
use tracing::info;
use crate::error::AppError;

pub struct DockerService {
    pub(crate) registry_url: String,
}

impl DockerService {
    pub fn new(registry_url: &str) -> Self {
        Self {
            registry_url: registry_url.to_string(),
        }
    }

    /// 构建 Docker 镜像
    pub async fn build_image(
        &self,
        path: &PathBuf,
        tag: &str,
        dockerfile: &str,
    ) -> Result<String, AppError> {
        self.build_image_with_args(path, tag, dockerfile, None).await
    }

    /// 构建 Docker 镜像（支持 build_args）
    pub async fn build_image_with_args(
        &self,
        path: &PathBuf,
        tag: &str,
        dockerfile: &str,
        build_args: Option<&HashMap<String, String>>,
    ) -> Result<String, AppError> {
        info!("构建 Docker 镜像: {} from {:?}", tag, path);

        let dockerfile_path = path.join(dockerfile);
        if !dockerfile_path.exists() {
            return Err(AppError::NotFound(format!("Dockerfile 不存在: {:?}", dockerfile_path)));
        }

        let max_retries = 3u32;
        for attempt in 0..=max_retries {
            let mut cmd = tokio::process::Command::new("docker");
            cmd.arg("build")
                .arg("-t")
                .arg(tag)
                .arg("-f")
                .arg(dockerfile);

            // 添加 build_args
            if let Some(args) = build_args {
                for (key, value) in args {
                    cmd.arg("--build-arg").arg(format!("{}={}", key, value));
                }
            }

            cmd.arg(".").current_dir(path);

            let output_result = tokio::time::timeout(
                std::time::Duration::from_secs(600),
                cmd.output(),
            )
            .await;

            match output_result {
                Ok(Ok(output)) if output.status.success() => {
                    info!("镜像构建完成: {}", tag);
                    return Ok(tag.to_string());
                }
                Ok(Ok(output)) => {
                    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
                    if attempt >= max_retries {
                        return Err(AppError::DockerError {
                            code: "BUILD_FAILED".to_string(),
                            message: format!("Docker 构建失败 (重试 {} 次): {}", max_retries, stderr),
                        });
                    }
                    let wait_secs = 5 * (attempt + 1) as u64;
                    info!("构建失败，{}秒后重试 (第{}/{}次): {}", wait_secs, attempt + 1, max_retries, stderr);
                    tokio::time::sleep(std::time::Duration::from_secs(wait_secs)).await;
                }
                Ok(Err(e)) => {
                    if attempt >= max_retries {
                        return Err(AppError::DockerError {
                            code: "BUILD_FAILED".to_string(),
                            message: format!("Docker 命令执行失败 (重试 {} 次): {}", max_retries, e),
                        });
                    }
                    let wait_secs = 5 * (attempt + 1) as u64;
                    info!("构建命令异常，{}秒后重试 (第{}/{}次): {}", wait_secs, attempt + 1, max_retries, e);
                    tokio::time::sleep(std::time::Duration::from_secs(wait_secs)).await;
                }
                Err(_) => {
                    return Err(AppError::DockerError {
                        code: "BUILD_TIMEOUT".to_string(),
                        message: "构建超时 (600s)".to_string(),
                    });
                }
            }
        }

        Err(AppError::DockerError {
            code: "BUILD_FAILED".to_string(),
            message: "重试耗尽".to_string(),
        })
    }

    pub async fn build_compose(
        &self,
        path: &PathBuf,
    ) -> Result<(), AppError> {
        info!("使用 docker-compose 构建: {:?}", path);

        let output = tokio::process::Command::new("docker-compose")
            .arg("build")
            .current_dir(path)
            .output()
            .await
            .map_err(|e| AppError::InternalError(format!("docker-compose 命令执行失败: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(AppError::InternalError(format!("docker-compose 构建失败: {}", stderr)));
        }

        info!("docker-compose 构建完成");
        Ok(())
    }
}
