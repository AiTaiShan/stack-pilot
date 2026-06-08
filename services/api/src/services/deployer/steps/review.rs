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

    // ── 1. Dockerfile 不存在时，根据项目类型选择生成策略 ──
    let is_single = !matches!(project_type,
        "multi-module-java" | "multi-module-java-with-frontend" | "spring-cloud"
        | "microservices" | "microservices-with-frontend"
    );

    match project_type {
        "multi-module-java" | "multi-module-java-with-frontend" | "spring-cloud" => {
            // 多模块 Java 项目：为每个子模块生成独立 Dockerfile（不在根目录生成）
            generate_multi_module_dockerfiles(&repo_dir, &scan_result, version).await;
        }
        "microservices" | "microservices-with-frontend" => {
            // 微服务项目：为每个服务按语言生成 Dockerfile
            generate_microservices_dockerfiles(&repo_dir, &scan_result, version).await;
        }
        _ => {
            // 单体项目：在根目录生成单个 Dockerfile
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
        }
    }

    // ── 2. AI 审核 Dockerfile（仅单体项目审核根目录 Dockerfile） ──
    let agent_url = std::env::var("AGENT_SERVICE_URL")
        .unwrap_or_else(|_| "http://localhost:8066".to_string());
    let agent_client = AgentClient::new(&agent_url);

    let healthy = agent_client.health_check().await.unwrap_or(false);
    if !healthy {
        info!("Agent 服务不可用，跳过 AI 审核");
    } else if is_single {
        // 单体项目：审核根目录 Dockerfile
        let dockerfile_path = repo_dir.join("Dockerfile");
        if dockerfile_path.exists() {
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
    } else {
        info!("多模块/微服务项目，跳过根目录 Dockerfile 审核（子模块 Dockerfile 已独立生成）");
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
            let compose_content = generate_single_compose(repo_name, &image_tag, port, &external_services);
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

/// 多模块 Java 项目：为每个子模块生成独立 Dockerfile
/// 根目录的 Maven 构建会在各模块的 target/ 下生成 jar
/// 每个模块的 Dockerfile 只需 COPY target/*.jar app.jar
async fn generate_multi_module_dockerfiles(
    repo_dir: &std::path::Path,
    scan_result: &serde_json::Map<String, serde_json::Value>,
    java_version: &str,
) {
    let services = scan_result.get("services")
        .and_then(|v| v.as_array());

    let services = match services {
        Some(s) => s,
        None => {
            info!("多模块项目但无 services 信息，跳过子模块 Dockerfile 生成");
            return;
        }
    };

    let version_num: i32 = java_version.parse().unwrap_or(17);

    for svc in services {
        let svc_type = svc.get("type").and_then(|v| v.as_str()).unwrap_or("service");
        if svc_type == "common" || svc_type == "library" {
            continue;
        }

        let svc_dir = svc.get("dir").and_then(|v| v.as_str()).unwrap_or("");
        let svc_port = svc.get("port").and_then(|v| v.as_u64()).unwrap_or(8080) as u16;
        let svc_name = svc.get("name").and_then(|v| v.as_str()).unwrap_or(svc_dir);

        if svc_dir.is_empty() {
            continue;
        }

        let dockerfile_path = repo_dir.join(svc_dir).join("Dockerfile");
        if dockerfile_path.exists() {
            info!("子模块 {} Dockerfile 已存在，跳过", svc_name);
            continue;
        }

        let content = format!(
            r#"FROM eclipse-temurin:{version}-jre-alpine
WORKDIR /app
COPY target/*.jar app.jar
EXPOSE {port}
CMD ["java", "-jar", "app.jar"]
"#,
            version = version_num,
            port = svc_port
        );

        if let Err(e) = tokio::fs::write(&dockerfile_path, &content).await {
            info!("子模块 {} Dockerfile 写入失败: {}", svc_name, e);
        } else {
            info!("子模块 {} Dockerfile 已生成: {:?}", svc_name, dockerfile_path);
        }
    }
}

/// 微服务项目：为每个服务按语言生成 Dockerfile
async fn generate_microservices_dockerfiles(
    repo_dir: &std::path::Path,
    scan_result: &serde_json::Map<String, serde_json::Value>,
    default_version: &str,
) {
    let services = scan_result.get("services")
        .and_then(|v| v.as_array());

    let services = match services {
        Some(s) => s,
        None => {
            info!("微服务项目但无 services 信息，跳过服务 Dockerfile 生成");
            return;
        }
    };

    for svc in services {
        let svc_type = svc.get("type").and_then(|v| v.as_str()).unwrap_or("service");
        if svc_type == "common" || svc_type == "library" {
            continue;
        }

        let svc_dir = svc.get("dir").and_then(|v| v.as_str()).unwrap_or("");
        let svc_port = svc.get("port").and_then(|v| v.as_u64()).unwrap_or(8080) as u16;
        let svc_name = svc.get("name").and_then(|v| v.as_str()).unwrap_or(svc_dir);
        let svc_language = svc.get("language").and_then(|v| v.as_str()).unwrap_or("unknown");
        let svc_framework = svc.get("framework").and_then(|v| v.as_str()).unwrap_or("");

        if svc_dir.is_empty() {
            continue;
        }

        let dockerfile_path = repo_dir.join(svc_dir).join("Dockerfile");
        if dockerfile_path.exists() {
            info!("服务 {} Dockerfile 已存在，跳过", svc_name);
            continue;
        }

        let content = match svc_language {
            "java" => {
                let version_num: i32 = default_version.parse().unwrap_or(17);
                format!(
                    r#"FROM eclipse-temurin:{version}-jre-alpine
WORKDIR /app
COPY target/*.jar app.jar
EXPOSE {port}
CMD ["java", "-jar", "app.jar"]
"#,
                    version = version_num,
                    port = svc_port
                )
            }
            "node" | "javascript" | "typescript" => {
                format!(
                    r#"FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE {port}
CMD ["npm", "start"]
"#,
                    port = svc_port
                )
            }
            "python" => {
                format!(
                    r#"FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {port}
CMD ["python", "main.py"]
"#,
                    port = svc_port
                )
            }
            "go" => {
                format!(
                    r#"FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o app .

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/app .
EXPOSE {port}
CMD ["./app"]
"#,
                    port = svc_port
                )
            }
            _ => {
                info!("服务 {} 语言 {} 无模板，跳过 Dockerfile 生成", svc_name, svc_language);
                continue;
            }
        };

        if let Err(e) = tokio::fs::write(&dockerfile_path, &content).await {
            info!("服务 {} Dockerfile 写入失败: {}", svc_name, e);
        } else {
            info!("服务 {} Dockerfile 已生成: {:?}", svc_name, dockerfile_path);
        }
    }
}
