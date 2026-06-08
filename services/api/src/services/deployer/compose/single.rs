#![allow(dead_code)]
use std::path::PathBuf;
use tracing::info;
use crate::error::AppError;
use crate::services::scanner::dependency::service_map::ExternalService;

pub fn generate_single_compose(
    _repo_name: &str,
    image_tag: &str,
    services: &[ExternalService],
) -> String {
    let mut compose = format!(
        r#"version: '3.8'

services:
  app:
    image: {}
    ports:
      - "8080:8080"
    restart: unless-stopped
"#,
        image_tag
    );

    let mut volumes = Vec::new();

    for service in services {
        match service.category.as_str() {
            "database" => {
                compose.push_str(&format!(
                    r#"
  {}:
    image: {}
    ports:
      - "{}:{}"
    volumes:
      - {}_data:/var/lib/{}-data
    restart: unless-stopped
"#,
                    service.name, service.image, service.default_port, service.default_port,
                    service.name, service.name
                ));
                volumes.push(format!("{}_data", service.name));
            }
            "cache" | "search" | "storage" | "monitoring" | "registry" | "gateway"
            | "auth" | "secrets" | "scheduler" | "testing" | "rpc" | "messagequeue" => {
                compose.push_str(&format!(
                    r#"
  {}:
    image: {}
    ports:
      - "{}:{}"
    restart: unless-stopped
"#,
                    service.name, service.image, service.default_port, service.default_port
                ));
            }
            _ => {
                // 未知类别也生成基础配置
                compose.push_str(&format!(
                    r#"
  {}:
    image: {}
    ports:
      - "{}:{}"
    restart: unless-stopped
"#,
                    service.name, service.image, service.default_port, service.default_port
                ));
            }
        }
    }

    if !volumes.is_empty() {
        compose.push_str("\nvolumes:\n");
        for vol in &volumes {
            compose.push_str(&format!("  {}:\n", vol));
        }
    }

    compose
}

pub async fn write_compose_file(
    repo_dir: &PathBuf,
    content: &str,
) -> Result<(), AppError> {
    let path = repo_dir.join("docker-compose.yml");
    info!("写入 docker-compose.yml: {:?}", path);

    tokio::fs::write(&path, content).await
        .map_err(|e| AppError::InternalError(format!("写入 docker-compose.yml 失败: {}", e)))?;

    info!("docker-compose.yml 写入完成");
    Ok(())
}
