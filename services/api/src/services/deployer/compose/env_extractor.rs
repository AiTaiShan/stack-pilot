#![allow(dead_code)]
use std::path::Path;
use tracing::info;
use crate::error::AppError;

/// 环境变量信息
#[derive(Debug, Clone, serde::Serialize)]
pub struct EnvVarInfo {
    pub name: String,
    pub value: String,
    pub file: String,
    pub line: usize,
    pub source: String,
}

/// 从配置文件中提取环境变量
pub async fn extract_env_vars(
    repo_dir: &Path,
    style: &str,  // "spring" 或 "generic"
) -> Result<Vec<EnvVarInfo>, AppError> {
    let skip_dirs: Vec<&str> = vec![
        ".git", "node_modules", "target", ".mvn", "__pycache__",
        ".stackpilot", "dist", "build", ".idea", ".vscode",
    ];

    let mut env_vars = Vec::new();

    scan_dir_for_env_vars(repo_dir, repo_dir, &skip_dirs, style, &mut env_vars).await?;

    info!("提取到 {} 个环境变量 (style={})", env_vars.len(), style);
    Ok(env_vars)
}

/// 递归扫描目录提取环境变量
async fn scan_dir_for_env_vars(
    base_dir: &Path,
    current_dir: &Path,
    skip_dirs: &[&str],
    style: &str,
    env_vars: &mut Vec<EnvVarInfo>,
) -> Result<(), AppError> {
    let mut entries = tokio::fs::read_dir(current_dir).await
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
            Box::pin(scan_dir_for_env_vars(base_dir, &path, skip_dirs, style, env_vars)).await?;
            continue;
        }

        // 只处理配置文件
        let is_config_file = file_name.ends_with(".properties")
            || file_name.ends_with(".yml")
            || file_name.ends_with(".yaml")
            || file_name.ends_with(".env");

        if !is_config_file {
            continue;
        }

        // 读取文件内容
        let content = match tokio::fs::read_to_string(&path).await {
            Ok(c) => c,
            Err(_) => continue,
        };

        let rel_path = path.strip_prefix(base_dir)
            .unwrap_or(&path)
            .to_string_lossy()
            .to_string();

        // 根据风格提取环境变量
        let vars = match style {
            "spring" => extract_spring_env_vars(&content, &rel_path),
            _ => extract_generic_env_vars(&content, &rel_path),
        };

        env_vars.extend(vars);
    }

    Ok(())
}

/// 提取 Spring 风格的环境变量（${...} 占位符）
fn extract_spring_env_vars(content: &str, file_path: &str) -> Vec<EnvVarInfo> {
    use regex::Regex;

    let re = Regex::new(r"\$\{([^}]+)\}").unwrap();
    let mut vars = Vec::new();

    for (line_num, line) in content.lines().enumerate() {
        for cap in re.captures_iter(line) {
            if let Some(var_match) = cap.get(1) {
                let var_expr = var_match.as_str();

                // 跳过 Spring 内置变量
                if var_expr.starts_with("spring.") || var_expr.starts_with("logging.") {
                    continue;
                }

                // 解析变量名和默认值
                let (name, default_value) = if let Some((name, default)) = var_expr.split_once(':') {
                    (name.to_string(), default.to_string())
                } else {
                    (var_expr.to_string(), String::new())
                };

                // 跳过已有值的变量
                if !default_value.is_empty() && !default_value.contains("CHANGE_ME") && !default_value.contains("TODO") {
                    continue;
                }

                vars.push(EnvVarInfo {
                    name,
                    value: default_value,
                    file: file_path.to_string(),
                    line: line_num + 1,
                    source: format!("{}:{}", file_path, line_num + 1),
                });
            }
        }
    }

    vars
}

/// 提取通用风格的环境变量（KEY=VALUE 或 KEY: VALUE）
fn extract_generic_env_vars(content: &str, file_path: &str) -> Vec<EnvVarInfo> {
    use regex::Regex;

    // 匹配 KEY=VALUE 或 KEY: VALUE 格式
    let re = Regex::new(r#"^([A-Z_][A-Z0-9_]*)[=:](.+)$"#).unwrap();
    let mut vars = Vec::new();

    for (line_num, line) in content.lines().enumerate() {
        let trimmed = line.trim();

        // 跳过注释
        if trimmed.starts_with('#') || trimmed.starts_with("//") {
            continue;
        }

        if let Some(cap) = re.captures(trimmed) {
            if let (Some(name_match), Some(value_match)) = (cap.get(1), cap.get(2)) {
                let name = name_match.as_str().to_string();
                let value = value_match.as_str().trim().to_string();

                // 跳过空值或占位符
                if value.is_empty() || value == "CHANGE_ME" || value == "TODO" || value == "xxx" {
                    vars.push(EnvVarInfo {
                        name,
                        value,
                        file: file_path.to_string(),
                        line: line_num + 1,
                        source: format!("{}:{}", file_path, line_num + 1),
                    });
                }
            }
        }
    }

    vars
}
