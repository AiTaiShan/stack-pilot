use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};
use crate::services::agent::{AgentClient, ProjectInfo};
use crate::services::deployer::compose::single::{generate_single_compose, write_compose_file};
use crate::services::scanner::dependency::service_map::get_external_services;

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 2: 生成部署文件 + AI 审核 - 部署 {}", deployment_id);

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
        return Err(AppError::NotFound(format!("仓库目录不存在: {}", repo_dir_str)));
    }

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

    // ── 1. Dockerfile 不存在时，调用模板生成 ──
    let dockerfile_path = repo_dir.join("Dockerfile");
    if !dockerfile_path.exists() {
        info!("Dockerfile 不存在，根据语言 {} 生成模板", language);
        let content = generate_dockerfile_by_language(language, framework, version, port);
        tokio::fs::write(&dockerfile_path, &content).await
            .map_err(|e| AppError::InternalError(format!("写入 Dockerfile 失败: {}", e)))?;
        info!("Dockerfile 已生成");
    } else {
        info!("Dockerfile 已存在，跳过生成");
    }

    // ── 2. AI 审核 Dockerfile ──
    let agent_url = std::env::var("AGENT_SERVICE_URL")
        .unwrap_or_else(|_| "http://localhost:8066".to_string());
    let agent_client = AgentClient::new(&agent_url);

    let healthy = agent_client.health_check().await.unwrap_or(false);
    if !healthy {
        info!("Agent 服务不可用，跳过 AI 审核");
    } else {
        // 审核 Dockerfile
        let dockerfile_content = tokio::fs::read_to_string(&dockerfile_path).await
            .map_err(|e| AppError::InternalError(format!("读取 Dockerfile 失败: {}", e)))?;

        match agent_client.review_dockerfile(project_info.clone(), dockerfile_content).await {
            Ok(result) => {
                info!("Dockerfile 审核结果: {}", result.status);
                if result.status == "needs_fix" {
                    if let Some(fixed) = result.fixed_content {
                        tokio::fs::write(&dockerfile_path, &fixed).await
                            .map_err(|e| AppError::InternalError(format!("写入修复 Dockerfile 失败: {}", e)))?;
                        info!("Dockerfile 已自动修复");
                    }
                }
                for issue in &result.issues {
                    info!("  [{}] {}: {}", issue.severity, issue.category, issue.description);
                }
            }
            Err(e) => {
                info!("Dockerfile 审核失败（继续部署）: {}", e);
            }
        }
    }

    // ── 3. 生成 docker-compose.yml ──
    let compose_path = repo_dir.join("docker-compose.yml");
    if !compose_path.exists() {
        info!("docker-compose.yml 不存在，生成含外部依赖的 compose 文件");

        let external_service_names: Vec<String> = scan_result
            .get("dependencies")
            .and_then(|d| d.get("external_services"))
            .and_then(|v| v.as_array())
            .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
            .unwrap_or_default();

        let all_services = get_external_services();
        let external_services: Vec<_> = external_service_names.iter()
            .filter_map(|name| all_services.get(name).cloned())
            .collect();

        if !external_services.is_empty() {
            let repo_name = repo_dir.file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("app");
            let image_tag = format!("stackpilot/{}:latest", repo_name);
            let compose_content = generate_single_compose(repo_name, &image_tag, &external_services);
            write_compose_file(&repo_dir, &compose_content).await?;
            info!("docker-compose.yml 已生成（含 {} 个外部依赖服务）", external_services.len());
        } else {
            info!("无外部依赖，跳过 compose 生成");
        }
    } else {
        info!("docker-compose.yml 已存在，跳过生成");
    }

    // ── 4. AI 审核 docker-compose.yml ──
    if healthy && compose_path.exists() {
        let compose_content = tokio::fs::read_to_string(&compose_path).await
            .map_err(|e| AppError::InternalError(format!("读取 docker-compose.yml 失败: {}", e)))?;

        match agent_client.review_compose(project_info, compose_content).await {
            Ok(result) => {
                info!("docker-compose.yml 审核结果: {}", result.status);
                if result.status == "needs_fix" {
                    if let Some(fixed) = result.fixed_content {
                        tokio::fs::write(&compose_path, &fixed).await
                            .map_err(|e| AppError::InternalError(format!("写入修复 compose 失败: {}", e)))?;
                        info!("docker-compose.yml 已自动修复");
                    }
                }
                for issue in &result.issues {
                    info!("  [{}] {}: {}", issue.severity, issue.category, issue.description);
                }
            }
            Err(e) => {
                info!("docker-compose.yml 审核失败（继续部署）: {}", e);
            }
        }
    }

    info!("步骤 2 完成: 生成部署文件 + AI 审核");
    Ok(())
}

/// 根据语言和框架生成 Dockerfile
fn generate_dockerfile_by_language(language: &str, framework: &str, version: &str, port: u16) -> String {
    match language {
        "python" => crate::services::scanner::templates::python::generate_python_dockerfile(framework, version, port),
        "node" | "javascript" | "typescript" => crate::services::scanner::templates::node::generate_node_dockerfile(framework, version, port),
        "go" => crate::services::scanner::templates::go::generate_go_dockerfile(framework, version, port),
        "java" => crate::services::scanner::templates::java::generate_java_dockerfile(framework, version, port),
        "rust" => crate::services::scanner::templates::rust::generate_rust_dockerfile(framework, version, port),
        "ruby" => crate::services::scanner::templates::ruby::generate_ruby_dockerfile(framework, version, port),
        "php" => crate::services::scanner::templates::php::generate_php_dockerfile(framework, version, port),
        "dotnet" | "csharp" => crate::services::scanner::templates::dotnet::generate_dotnet_dockerfile(framework, version, port),
        _ => {
            info!("未知语言 {}，使用通用 Dockerfile", language);
            format!(
                r#"FROM ubuntu:22.04

WORKDIR /app

COPY . .

EXPOSE {port}

CMD ["echo", "请根据项目语言配置启动命令"]
"#,
                port = port
            )
        }
    }
}
