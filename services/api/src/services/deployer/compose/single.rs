use std::path::PathBuf;
use tracing::info;
use crate::error::AppError;
use crate::services::scanner::dependency::ExternalService;

pub fn generate_single_compose(
    repo_name: &str,
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
                    service.name,
                    service.image,
                    service.default_port,
                    service.default_port,
                    service.name,
                    service.name
                ));
            }
            "cache" => {
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
            "messagequeue" => {
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
            _ => {}
        }
    }

    compose.push_str("\nvolumes:\n");
    for service in services {
        if service.category == "database" {
            compose.push_str(&format!("  {}_data:\n", service.name));
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
