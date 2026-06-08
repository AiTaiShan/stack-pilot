use tracing::{info, warn};
use uuid::Uuid;
use sea_orm::{EntityTrait, ActiveModelTrait, Set};
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity, ActiveModel as DeploymentActiveModel};
use crate::services::deployer::compose::microservices::generate_microservices_compose;
use crate::services::scanner::dependency::service_map::ExternalService;

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
    platform: &str,
) -> Result<(), AppError> {
    info!("步骤 6: 部署应用 - 部署 {} - 平台 {}", deployment_id, platform);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    // 从 config 读取 repo_dir（由 clone 步骤写入）
    let config = dep.config.as_ref()
        .and_then(|c| c.as_object())
        .cloned()
        .unwrap_or_default();

    let repo_dir_str = config.get("_repo_dir")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let repo_dir = std::path::PathBuf::from(repo_dir_str);

    if !repo_dir.exists() {
        return Err(AppError::NotFound(format!("仓库目录不存在: {}", repo_dir_str)));
    }

    // 从 image_tag 字段读取镜像 tag（由 build 步骤写入）
    let image_tag = dep.image_tag.as_deref().unwrap_or("stackpilot/app:latest");

    // 从 scan_result 读取项目类型和端口
    let scan_result = config.get("scan_result")
        .and_then(|s| s.as_object())
        .cloned()
        .unwrap_or_default();
    let project_type = scan_result.get("project_type")
        .and_then(|v| v.as_str())
        .unwrap_or("single");
    let port = scan_result.get("port")
        .and_then(|v| v.as_u64())
        .unwrap_or(8080) as u16;

    // 读取所有镜像 tag（微服务项目）
    let all_images: Vec<String> = config.get("_all_images")
        .and_then(|v| serde_json::from_value(v.clone()).ok())
        .unwrap_or_else(|| vec![image_tag.to_string()]);

    // 获取 repo_name
    let repo_name = dep.git_url
        .as_ref()
        .and_then(|u| u.rsplit('/').next())
        .unwrap_or("app")
        .replace(".git", "")
        .to_lowercase();

    match platform {
        "docker" | "local" => {
            // 检查是否需要生成微服务 compose（微服务项目总是覆盖）
            let compose_file = repo_dir.join("docker-compose.yml");
            if project_type == "microservices" || project_type == "microservices-with-frontend" || project_type == "spring-cloud" {
                info!("生成微服务 docker-compose.yml");

                let external_services: Vec<ExternalService> = scan_result
                    .get("dependencies")
                    .and_then(|d| d.get("external_services"))
                    .and_then(|v| serde_json::from_value(v.clone()).ok())
                    .unwrap_or_default();

                let compose_content = generate_microservices_compose(
                    &repo_name,
                    &all_images,
                    &scan_result,
                    &external_services,
                );

                tokio::fs::write(&compose_file, &compose_content).await
                    .map_err(|e| AppError::InternalError(format!("写入 docker-compose.yml 失败: {}", e)))?;
                info!("微服务 docker-compose.yml 已生成");
            }

            info!("使用 docker-compose 部署，工作目录: {:?}", repo_dir);

            // 预拉取外部镜像（避免 up 时超时）
            info!("预拉取外部镜像...");
            let pull_result = tokio::process::Command::new("docker")
                .args(["compose", "pull"])
                .current_dir(&repo_dir)
                .output()
                .await;

            match pull_result {
                Ok(out) if out.status.success() => {
                    info!("镜像预拉取完成");
                }
                Ok(out) => {
                    let stderr = String::from_utf8_lossy(&out.stderr);
                    warn!("镜像预拉取失败，继续尝试启动: {}", stderr);
                }
                Err(e) => {
                    warn!("镜像预拉取命令执行失败，继续尝试启动: {}", e);
                }
            }

            // 启动服务
            let output = tokio::process::Command::new("docker")
                .args(["compose", "up", "-d"])
                .current_dir(&repo_dir)
                .output()
                .await
                .map_err(|e| AppError::InternalError(format!("docker compose 启动失败: {}", e)))?;

            if !output.status.success() {
                let stderr = String::from_utf8_lossy(&output.stderr);
                info!("docker compose (新版) 失败，尝试旧版 docker-compose...");
                // 回退到旧版 docker-compose
                let output2 = tokio::process::Command::new("docker-compose")
                    .args(["up", "-d"])
                    .current_dir(&repo_dir)
                    .output()
                    .await;
                match output2 {
                    Ok(out) if out.status.success() => {
                        info!("docker-compose (旧版) 启动成功");
                    }
                    Ok(out) => {
                        let stderr2 = String::from_utf8_lossy(&out.stderr);
                        return Err(AppError::InternalError(format!("docker-compose 启动失败: {}", stderr2)));
                    }
                    Err(e) => {
                        return Err(AppError::InternalError(format!("docker-compose 命令执行失败: {}", e)));
                    }
                }
            }

            // 获取 deploy_url 从运行的容器
            info!("获取部署 URL...");
            match get_deploy_url_from_containers(&repo_name, &scan_result).await {
                Some(deploy_url) => {
                    info!("部署 URL: {}", deploy_url);
                    // 更新数据库
                    if let Some(dep) = DeploymentEntity::find_by_id(deployment_id).one(&db).await.ok().flatten() {
                        let mut am: DeploymentActiveModel = dep.into();
                        am.deploy_url = Set(Some(deploy_url.clone()));
                        am.update(&db).await.ok();
                    }
                }
                None => {
                    warn!("无法获取部署 URL，使用默认端口");
                    let deploy_url = format!("http://localhost:{}", port);
                    if let Some(dep) = DeploymentEntity::find_by_id(deployment_id).one(&db).await.ok().flatten() {
                        let mut am: DeploymentActiveModel = dep.into();
                        am.deploy_url = Set(Some(deploy_url.clone()));
                        am.update(&db).await.ok();
                    }
                }
            }
        }
        "k8s" => {
            info!("使用 Kubernetes 部署，镜像: {}", image_tag);
            let k8s_service = crate::services::deployer::k8s::K8sService::new(None);
            let namespace = format!("stackpilot-{}", deployment_id);
            k8s_service.create_namespace(&namespace).await?;
            k8s_service.create_deployment(&namespace, &repo_name, image_tag, 1, port, None).await?;
            k8s_service.create_service(&namespace, &repo_name, port, port, "LoadBalancer").await?;

            // K8s 部署 URL
            let deploy_url = format!("http://{}.{}", repo_name, namespace);
            if let Some(dep) = DeploymentEntity::find_by_id(deployment_id).one(&db).await.ok().flatten() {
                let mut am: DeploymentActiveModel = dep.into();
                am.deploy_url = Set(Some(deploy_url.clone()));
                am.update(&db).await.ok();
            }
        }
        _ => {
            return Err(AppError::ValidationError(format!("不支持的部署平台: {}", platform)));
        }
    }

    info!("部署完成");
    Ok(())
}

/// 从运行的容器获取部署 URL
async fn get_deploy_url_from_containers(
    repo_name: &str,
    scan_result: &serde_json::Map<String, serde_json::Value>,
) -> Option<String> {
    // 1. 获取基础设施端口（数据库、缓存等）
    let mut infra_ports = std::collections::HashSet::new();
    if let Some(external_services) = scan_result.get("external_services").and_then(|v| v.as_array()) {
        for svc in external_services {
            let category = svc.get("category").and_then(|v| v.as_str()).unwrap_or("");
            if category == "database" || category == "cache" || category == "mq" || category == "search" || category == "storage" {
                if let Some(port) = svc.get("port").and_then(|v| v.as_u64()) {
                    infra_ports.insert(port as u16);
                }
            }
        }
    }

    // 2. 从运行的容器获取端口映射
    let project_name = format!("stackpilot-{}", repo_name);
    let output = tokio::process::Command::new("docker")
        .args(["ps", "--filter", &format!("name={}", project_name), "--format", "{{.Names}}:{{.Ports}}"])
        .output()
        .await;

    match output {
        Ok(out) if out.status.success() => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            for line in stdout.lines() {
                if line.is_empty() {
                    continue;
                }
                // 解析端口映射，格式如: 0.0.0.0:8080->8080/tcp
                let port_regex = regex::Regex::new(r"0\.0\.0\.0:(\d+)->").ok()?;
                for cap in port_regex.captures_iter(line) {
                    if let Some(port_str) = cap.get(1) {
                        if let Ok(port) = port_str.as_str().parse::<u16>() {
                            // 过滤掉基础设施端口
                            if !infra_ports.contains(&port) {
                                return Some(format!("http://localhost:{}", port));
                            }
                        }
                    }
                }
            }
            None
        }
        _ => None,
    }
}
