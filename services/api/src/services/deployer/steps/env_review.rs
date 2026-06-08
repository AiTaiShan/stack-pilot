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

    // 3. 扫描项目配置文件中的 ${...} 占位符和待填写值（对齐 Python 版）
    let config_vars = scan_config_placeholders(&repo_dir).await;
    if !config_vars.is_empty() {
        info!("从配置文件扫描到 {} 个待填写的环境变量占位符", config_vars.len());
        for (key, value) in config_vars {
            env_vars.entry(key).or_insert(value);
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

/// 扫描项目配置文件中的 ${...} 占位符和待填写值（对齐 Python 版 _generate_service_env_vars）
/// 扫描 application.yml/properties/.env 等文件，提取需要用户填写的环境变量
async fn scan_config_placeholders(repo_dir: &std::path::Path) -> HashMap<String, String> {
    use regex::Regex;

    let mut vars = HashMap::new();
    let mut seen = std::collections::HashSet::new();

    let skip_dirs = [".git", "node_modules", "target", ".mvn", "__pycache__",
                     ".stackpilot", "dist", "build", ".idea", "vendor"];

    let config_extensions = [".properties", ".yml", ".yaml", ".env"];

    // Spring 占位符模式: ${VAR_NAME} 或 ${VAR_NAME:default}（支持点号如 spring.profiles.active）
    let re_placeholder = Regex::new(r"\$\{([A-Za-z_][A-Za-z0-9_.]*)(?::[^}]*)?\}").ok();
    // 待填写模式: CHANGE_ME, TODO, xxx, your_xxx
    let re_todo = Regex::new(r"(?i)(CHANGE_ME|TODO|xxx|your_\w+)").ok();
    // 连接串中的占位符: jdbc:mysql://localhost:3306/db 中的密码等
    let re_conn = Regex::new(r"(?i)(PASSWORD|SECRET|TOKEN|API_KEY)\s*[:=]\s*(\$\{[^}]+\}|CHANGE_ME|TODO|xxx)").ok();

    // 递归扫描目录
    let mut dirs_to_scan = vec![repo_dir.to_path_buf()];
    while let Some(dir) = dirs_to_scan.pop() {
        let entries = match std::fs::read_dir(&dir) {
            Ok(e) => e,
            Err(_) => continue,
        };

        for entry in entries.flatten() {
            let path = entry.path();
            let name = entry.file_name().to_string_lossy().to_string();

            if path.is_dir() {
                if !skip_dirs.contains(&name.as_str()) && !name.starts_with('.') {
                    dirs_to_scan.push(path);
                }
                continue;
            }

            // 只扫描配置文件
            let is_config = config_extensions.iter().any(|ext| name.ends_with(ext));
            if !is_config {
                continue;
            }

            let content = match std::fs::read_to_string(&path) {
                Ok(c) => c,
                Err(_) => continue,
            };

            let rel_path = path.strip_prefix(repo_dir)
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or(name);

            for (line_no, line) in content.lines().enumerate() {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with("//") {
                    continue;
                }

                // 提取 ${VAR_NAME} 占位符
                if let Some(ref re) = re_placeholder {
                    for caps in re.captures_iter(line) {
                        let var_name = caps[1].to_string();
                        if seen.insert(var_name.clone()) {
                            vars.insert(var_name.clone(), format!("${{{}}}", var_name));
                            info!("  配置占位符: {} (文件: {}:{})", var_name, rel_path, line_no + 1);
                        }
                    }
                }

                // 提取 CHANGE_ME/TODO 等待填写的值
                if let Some(ref re) = re_todo {
                    if re.is_match(line) {
                        // 从行中提取 key
                        if let Some((key, _)) = trimmed.split_once(|c| c == ':' || c == '=') {
                            let key = key.trim().trim_matches('"').trim_matches('\'');
                            if !key.is_empty() && key.len() < 80 && !key.contains(' ') {
                                if seen.insert(key.to_string()) {
                                    vars.insert(key.to_string(), "CHANGE_ME".to_string());
                                    info!("  待填写值: {} (文件: {}:{})", key, rel_path, line_no + 1);
                                }
                            }
                        }
                    }
                }

                // 提取连接串中的敏感占位符
                if let Some(ref re) = re_conn {
                    for caps in re.captures_iter(line) {
                        let var_name = caps[1].to_uppercase();
                        if seen.insert(var_name.clone()) {
                            vars.insert(var_name.clone(), "CHANGE_ME".to_string());
                            info!("  连接串占位符: {} (文件: {}:{})", var_name, rel_path, line_no + 1);
                        }
                    }
                }
            }
        }
    }

    vars
}
