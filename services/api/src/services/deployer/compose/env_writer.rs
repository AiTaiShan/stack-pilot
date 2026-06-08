#![allow(dead_code)]
use std::path::Path;
use tracing::{info, warn};
use crate::error::AppError;

/// 从 docker-compose.yml 读取指定服务的环境变量
pub async fn read_compose_service_env(
    repo_dir: &Path,
    service_name: &str,
) -> Result<std::collections::HashMap<String, String>, AppError> {
    let compose_path = repo_dir.join("docker-compose.yml");
    if !compose_path.exists() {
        return Ok(std::collections::HashMap::new());
    }

    let content = tokio::fs::read_to_string(&compose_path).await
        .map_err(|e| AppError::InternalError(format!("读取 docker-compose.yml 失败: {}", e)))?;

    let compose: serde_yaml::Value = serde_yaml::from_str(&content)
        .map_err(|e| AppError::InternalError(format!("解析 docker-compose.yml 失败: {}", e)))?;

    let mut result = std::collections::HashMap::new();

    if let Some(services) = compose.get("services").and_then(|v| v.as_mapping()) {
        if let Some(service) = services.get(&serde_yaml::Value::String(service_name.to_string())) {
            if let Some(environment) = service.get("environment") {
                if let Some(env_map) = environment.as_mapping() {
                    // dict 格式: KEY: VALUE
                    for (k, v) in env_map {
                        if let (Some(key), Some(val)) = (k.as_str(), v.as_str()) {
                            result.insert(key.to_string(), val.to_string());
                        }
                    }
                } else if let Some(env_list) = environment.as_sequence() {
                    // list 格式: KEY=VALUE
                    for item in env_list {
                        if let Some(s) = item.as_str() {
                            if let Some((k, v)) = s.split_once('=') {
                                result.insert(k.to_string(), v.to_string());
                            }
                        }
                    }
                }
            }
        }
    }

    Ok(result)
}

/// 更新 docker-compose.yml 中指定服务的环境变量
pub async fn update_compose_service_env(
    repo_dir: &Path,
    service_name: &str,
    env_vars: &std::collections::HashMap<String, String>,
) -> Result<bool, AppError> {
    let compose_path = repo_dir.join("docker-compose.yml");
    if !compose_path.exists() {
        return Ok(false);
    }

    let content = tokio::fs::read_to_string(&compose_path).await
        .map_err(|e| AppError::InternalError(format!("读取 docker-compose.yml 失败: {}", e)))?;

    // 解析现有环境变量
    let mut current_env = read_compose_service_env(repo_dir, service_name).await?;

    // 合并更新
    for (k, v) in env_vars {
        current_env.insert(k.clone(), v.clone());
    }

    // 使用正则替换 environment 段落
    let new_content = replace_env_section(&content, service_name, &current_env)?;

    tokio::fs::write(&compose_path, &new_content).await
        .map_err(|e| AppError::InternalError(format!("写入 docker-compose.yml 失败: {}", e)))?;

    info!("更新服务 {} 的环境变量: {} 个变量", service_name, current_env.len());
    Ok(true)
}

/// 删除 docker-compose.yml 中指定服务的指定环境变量
pub async fn delete_compose_service_env_var(
    repo_dir: &Path,
    service_name: &str,
    var_name: &str,
) -> Result<bool, AppError> {
    let compose_path = repo_dir.join("docker-compose.yml");
    if !compose_path.exists() {
        return Ok(false);
    }

    let content = tokio::fs::read_to_string(&compose_path).await
        .map_err(|e| AppError::InternalError(format!("读取 docker-compose.yml 失败: {}", e)))?;

    // 解析现有环境变量
    let mut current_env = read_compose_service_env(repo_dir, service_name).await?;

    // 检查变量是否存在
    if !current_env.contains_key(var_name) {
        return Ok(false);
    }

    // 删除变量
    current_env.remove(var_name);

    // 使用正则替换 environment 段落
    let new_content = replace_env_section(&content, service_name, &current_env)?;

    tokio::fs::write(&compose_path, &new_content).await
        .map_err(|e| AppError::InternalError(format!("写入 docker-compose.yml 失败: {}", e)))?;

    info!("删除服务 {} 的环境变量: {}", service_name, var_name);
    Ok(true)
}

/// 读取 docker-compose.yml 文件内容
pub async fn read_compose_file(repo_dir: &Path) -> Result<String, AppError> {
    let compose_path = repo_dir.join("docker-compose.yml");
    if !compose_path.exists() {
        return Err(AppError::NotFound("docker-compose.yml 不存在".to_string()));
    }

    tokio::fs::read_to_string(&compose_path).await
        .map_err(|e| AppError::InternalError(format!("读取 docker-compose.yml 失败: {}", e)))
}

/// 写入 docker-compose.yml 文件内容
pub async fn write_compose_file(repo_dir: &Path, content: &str) -> Result<bool, AppError> {
    // 验证 YAML 格式
    let _: serde_yaml::Value = serde_yaml::from_str(content)
        .map_err(|e| AppError::ValidationError(format!("无效的 YAML 格式: {}", e)))?;

    let compose_path = repo_dir.join("docker-compose.yml");
    tokio::fs::write(&compose_path, content).await
        .map_err(|e| AppError::InternalError(format!("写入 docker-compose.yml 失败: {}", e)))?;

    Ok(true)
}

/// 使用正则替换 environment 段落
fn replace_env_section(
    content: &str,
    service_name: &str,
    env_vars: &std::collections::HashMap<String, String>,
) -> Result<String, AppError> {
    use regex::Regex;

    // 解析 YAML 获取服务顺序和格式
    let compose: serde_yaml::Value = serde_yaml::from_str(content)
        .map_err(|e| AppError::InternalError(format!("解析 docker-compose.yml 失败: {}", e)))?;

    let services = compose.get("services")
        .and_then(|v| v.as_mapping())
        .ok_or_else(|| AppError::ValidationError("docker-compose.yml 中没有 services".to_string()))?;

    // 找到目标服务的索引
    let service_keys: Vec<String> = services.keys()
        .filter_map(|k| k.as_str().map(|s| s.to_string()))
        .collect();
    let service_idx = service_keys.iter().position(|s| s == service_name)
        .ok_or_else(|| AppError::NotFound(format!("服务 {} 不存在", service_name)))?;

    // 使用正则找到所有 environment 段落
    let re = Regex::new(r"(?m)^([ \t]*)environment:[ \t]*\n((?:\1 .+\n?)*)")
        .map_err(|e| AppError::InternalError(format!("正则编译失败: {}", e)))?;

    let matches: Vec<_> = re.find_iter(content).collect();

    if service_idx >= matches.len() {
        warn!("服务 {} 的 environment 段落未找到", service_name);
        return Ok(content.to_string());
    }

    let target_match = matches[service_idx];

    // 获取基础缩进
    let cap = re.captures_iter(content).nth(service_idx).unwrap();
    let base_indent = cap.get(1).map(|m| m.as_str()).unwrap_or("    ");
    let item_indent = format!("{}  ", base_indent);

    // 序列化环境变量
    let mut env_lines = Vec::new();
    for (k, v) in env_vars {
        env_lines.push(format!("{}- {}={}", item_indent, k, v));
    }
    let new_env_text = env_lines.join("\n");

    // 构建替换文本
    let replacement = format!("{}environment:\n{}\n", base_indent, new_env_text);

    // 替换
    let mut result = String::new();
    result.push_str(&content[..target_match.start()]);
    result.push_str(&replacement);
    result.push_str(&content[target_match.end()..]);

    Ok(result)
}
