#![allow(dead_code)]
use std::path::Path;
use tracing::info;
use crate::error::AppError;

/// 端口映射规则
struct PortMapping {
    pattern: &'static str,
    replacement: &'static str,
    service_name: &'static str,
}

/// 获取端口映射规则
fn get_port_mappings() -> Vec<PortMapping> {
    vec![
        // Redis: docker-compose 中 6380:6379，容器内用 6379
        PortMapping { pattern: r"localhost:6380", replacement: "redis:6379", service_name: "redis" },
        PortMapping { pattern: r"127\.0\.0\.1:6380", replacement: "redis:6379", service_name: "redis" },
        // Minio: docker-compose 中 9002:9000，容器内用 9000
        PortMapping { pattern: r"localhost:9002", replacement: "minio:9000", service_name: "minio" },
        PortMapping { pattern: r"127\.0\.0\.1:9002", replacement: "minio:9000", service_name: "minio" },
        // Minio Console: 9003:9001
        PortMapping { pattern: r"localhost:9003", replacement: "minio:9001", service_name: "minio" },
        PortMapping { pattern: r"127\.0\.0\.1:9003", replacement: "minio:9001", service_name: "minio" },
        // MySQL 内外一致
        PortMapping { pattern: r"localhost:3306", replacement: "mysql:3306", service_name: "mysql" },
        PortMapping { pattern: r"127\.0\.0\.1:3306", replacement: "mysql:3306", service_name: "mysql" },
        // PostgreSQL 内外一致
        PortMapping { pattern: r"localhost:5432", replacement: "postgres:5432", service_name: "postgresql" },
        PortMapping { pattern: r"127\.0\.0\.1:5432", replacement: "postgres:5432", service_name: "postgresql" },
        // Kafka 内外一致
        PortMapping { pattern: r"localhost:9092", replacement: "kafka:9092", service_name: "kafka" },
        PortMapping { pattern: r"127\.0\.0\.1:9092", replacement: "kafka:9092", service_name: "kafka" },
        // Zookeeper 内外一致
        PortMapping { pattern: r"localhost:2181", replacement: "zookeeper:2181", service_name: "zookeeper" },
        PortMapping { pattern: r"127\.0\.0\.1:2181", replacement: "zookeeper:2181", service_name: "zookeeper" },
        // Elasticsearch
        PortMapping { pattern: r"localhost:9200", replacement: "elasticsearch:9200", service_name: "elasticsearch" },
        PortMapping { pattern: r"127\.0\.0\.1:9200", replacement: "elasticsearch:9200", service_name: "elasticsearch" },
        // MongoDB
        PortMapping { pattern: r"localhost:27017", replacement: "mongodb:27017", service_name: "mongodb" },
        PortMapping { pattern: r"127\.0\.0\.1:27017", replacement: "mongodb:27017", service_name: "mongodb" },
        // RabbitMQ
        PortMapping { pattern: r"localhost:5672", replacement: "rabbitmq:5672", service_name: "rabbitmq" },
        PortMapping { pattern: r"127\.0\.0\.1:5672", replacement: "rabbitmq:5672", service_name: "rabbitmq" },
        // Nacos
        PortMapping { pattern: r"localhost:8848", replacement: "nacos:8848", service_name: "nacos" },
        PortMapping { pattern: r"127\.0\.0\.1:8848", replacement: "nacos:8848", service_name: "nacos" },
        // NATS
        PortMapping { pattern: r"localhost:4222", replacement: "nats:4222", service_name: "nats" },
        PortMapping { pattern: r"127\.0\.0\.1:4222", replacement: "nats:4222", service_name: "nats" },
    ]
}

/// 将项目配置文件中的 localhost 替换为 Docker 服务名
pub async fn adapt_config_for_docker(
    repo_dir: &Path,
    external_services: &[String],
) -> Result<Vec<String>, AppError> {
    if external_services.is_empty() {
        return Ok(Vec::new());
    }

    let mappings = get_port_mappings();

    // 只保留已检测到的外部服务相关的映射
    let active_mappings: Vec<&PortMapping> = mappings.iter()
        .filter(|m| external_services.contains(&m.service_name.to_string()))
        .collect();

    if active_mappings.is_empty() {
        return Ok(Vec::new());
    }

    let skip_dirs: Vec<&str> = vec![
        ".git", "node_modules", "target", ".mvn", "__pycache__",
        ".stackpilot", "dist", "build", ".idea", ".vscode",
    ];

    let mut adapted_files = Vec::new();

    // 递归扫描配置文件
    let mut entries = tokio::fs::read_dir(repo_dir).await
        .map_err(|e| AppError::InternalError(format!("读取目录失败: {}", e)))?;

    while let Some(entry) = entries.next_entry().await
        .map_err(|e| AppError::InternalError(format!("读取目录项失败: {}", e)))?
    {
        let path = entry.path();
        let file_name = entry.file_name().to_string_lossy().to_string();

        if path.is_dir() {
            if skip_dirs.contains(&file_name.as_str()) || file_name.starts_with('.') {
                continue;
            }
            // 递归处理子目录
            let sub_files = Box::pin(adapt_config_for_docker(&path, external_services)).await?;
            adapted_files.extend(sub_files);
            continue;
        }

        // 只处理配置文件
        if !file_name.ends_with(".properties")
            && !file_name.ends_with(".yml")
            && !file_name.ends_with(".yaml")
            && !file_name.ends_with(".env")
        {
            continue;
        }

        // 读取文件内容
        let content = match tokio::fs::read_to_string(&path).await {
            Ok(c) => c,
            Err(_) => continue,
        };

        let mut new_content = content.clone();

        // 应用替换规则
        for mapping in &active_mappings {
            let re = match regex::Regex::new(mapping.pattern) {
                Ok(r) => r,
                Err(_) => continue,
            };
            new_content = re.replace_all(&new_content, mapping.replacement).to_string();
        }

        // 如果内容有变化，写回文件
        if new_content != content {
            tokio::fs::write(&path, &new_content).await
                .map_err(|e| AppError::InternalError(format!("写入文件失败: {}", e)))?;
            let rel_path = path.strip_prefix(repo_dir)
                .unwrap_or(&path)
                .to_string_lossy()
                .to_string();
            adapted_files.push(rel_path);
        }
    }

    if !adapted_files.is_empty() {
        info!("已适配配置文件: {:?}", adapted_files);
    }

    Ok(adapted_files)
}
