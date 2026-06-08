use std::collections::HashMap;
use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};
use crate::services::agent::{AgentClient, ProjectInfo};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 4: 环境变量审核 - 部署 {}", deployment_id);

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
        info!("仓库目录不存在，跳过环境变量审核");
        return Ok(());
    }

    // 收集环境变量：先读 .env，再用 compose 覆盖（compose 优先级更高）
    let mut env_vars: HashMap<String, String> = HashMap::new();

    // 1. 从 .env 文件读取（基础层）
    let env_path = repo_dir.join(".env");
    if env_path.exists() {
        let env_content = tokio::fs::read_to_string(&env_path).await
            .map_err(|e| AppError::InternalError(format!("读取 .env 失败: {}", e)))?;

        for line in env_content.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            // 去除 export 前缀
            let line = line.strip_prefix("export ").unwrap_or(line);
            if let Some((key, value)) = line.split_once('=') {
                let value = value.trim().trim_matches('"').trim_matches('\'');
                env_vars.insert(key.trim().to_string(), value.to_string());
            }
        }
        info!("从 .env 文件读取到 {} 个环境变量", env_vars.len());
    }

    // 2. 从 docker-compose.yml 的 environment 字段读取（覆盖层，优先级更高）
    let compose_path = repo_dir.join("docker-compose.yml");
    if compose_path.exists() {
        let compose_content = tokio::fs::read_to_string(&compose_path).await
            .map_err(|e| AppError::InternalError(format!("读取 docker-compose.yml 失败: {}", e)))?;

        let compose_vars = extract_env_from_compose(&compose_content);
        if !compose_vars.is_empty() {
            info!("从 docker-compose.yml 读取到 {} 个环境变量（覆盖 .env 同名变量）", compose_vars.len());
            // compose 中的环境变量覆盖 .env 中的同名值（Docker Compose 标准行为）
            for (key, value) in compose_vars {
                env_vars.insert(key, value);
            }
        }
    }

    if env_vars.is_empty() {
        info!("没有环境变量需要审核");
        return Ok(());
    }

    info!("共收集到 {} 个环境变量待审核", env_vars.len());

    // 构建 ProjectInfo
    let language = scan_result.get("language").and_then(|v| v.as_str()).unwrap_or("unknown");
    let framework = scan_result.get("framework").and_then(|v| v.as_str()).unwrap_or("unknown");
    let version = scan_result.get("version").and_then(|v| v.as_str()).unwrap_or("latest");
    let port = scan_result.get("port").and_then(|v| v.as_u64()).unwrap_or(8080) as u16;
    let project_type = scan_result.get("project_type").and_then(|v| v.as_str()).unwrap_or("single");

    let project_info = ProjectInfo {
        language: language.to_string(),
        framework: framework.to_string(),
        version: version.to_string(),
        port,
        project_type: project_type.to_string(),
    };

    // 调用 Agent 审核
    let agent_url = std::env::var("AGENT_SERVICE_URL")
        .unwrap_or_else(|_| "http://localhost:8066".to_string());
    let agent_client = AgentClient::new(&agent_url);

    let healthy = agent_client.health_check().await.unwrap_or(false);
    if !healthy {
        info!("Agent 服务不可用，跳过环境变量 AI 审核");
        return Ok(());
    }

    // 对敏感值脱敏后发送给 Agent（密码、密钥等 key 包含敏感关键词时值替换为 ***）
    let sensitive_keys = ["password", "secret", "token", "key", "credential", "auth", "api_key", "apikey"];
    let sanitized_vars: HashMap<String, String> = env_vars.iter().map(|(k, v)| {
        let lower = k.to_lowercase();
        let is_sensitive = sensitive_keys.iter().any(|s| lower.contains(s));
        if is_sensitive {
            (k.clone(), "***".to_string())
        } else {
            (k.clone(), v.clone())
        }
    }).collect();

    match agent_client.review_env(project_info, sanitized_vars).await {
        Ok(result) => {
            info!("环境变量审核结果: {}", result.status);
            for issue in &result.issues {
                info!("  [{}] {}: {}", issue.severity, issue.category, issue.description);
            }
        }
        Err(e) => {
            info!("环境变量审核失败（继续部署）: {}", e);
        }
    }

    info!("步骤 4 完成: 环境变量审核");
    Ok(())
}

/// 从 docker-compose.yml 内容中提取所有 service 的 environment 变量
fn extract_env_from_compose(content: &str) -> HashMap<String, String> {
    let mut env_vars = HashMap::new();

    let yaml: serde_yaml::Value = match serde_yaml::from_str(content) {
        Ok(v) => v,
        Err(e) => {
            info!("解析 docker-compose.yml 失败: {}", e);
            return env_vars;
        }
    };

    // 遍历 services.*.environment
    if let Some(services) = yaml.get("services").and_then(|v| v.as_mapping()) {
        for (_svc_name, svc_def) in services {
            if let Some(env) = svc_def.get("environment") {
                match env {
                    // environment 是 mapping: { KEY: VALUE }
                    serde_yaml::Value::Mapping(map) => {
                        for (k, v) in map {
                            if let (serde_yaml::Value::String(key), serde_yaml::Value::String(val)) = (k, v) {
                                env_vars.insert(key.clone(), val.clone());
                            } else if let serde_yaml::Value::String(key) = k {
                                // value 可能是数字等非字符串类型
                                env_vars.insert(key.clone(), format!("{:?}", v));
                            }
                        }
                    }
                    // environment 是 sequence: [ "KEY=VALUE", ... ]
                    serde_yaml::Value::Sequence(seq) => {
                        for item in seq {
                            if let serde_yaml::Value::String(s) = item {
                                if let Some((key, value)) = s.split_once('=') {
                                    env_vars.insert(
                                        key.trim().to_string(),
                                        value.trim().trim_matches('"').trim_matches('\'').to_string(),
                                    );
                                }
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    env_vars
}
