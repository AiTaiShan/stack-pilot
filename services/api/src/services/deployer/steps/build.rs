#![allow(dead_code)]
use tracing::info;
use uuid::Uuid;
use sea_orm::{EntityTrait, ActiveModelTrait, Set};
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity, ActiveModel as DeploymentActiveModel};
use crate::services::deployer::docker::DockerService;

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 3: 构建镜像 - 部署 {}", deployment_id);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

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
    let project_type = scan_result.get("project_type").and_then(|v| v.as_str()).unwrap_or("single");

    let repo_name = dep.git_url
        .as_ref()
        .and_then(|u| u.rsplit('/').next())
        .unwrap_or("app")
        .replace(".git", "")
        .to_lowercase();

    let commit_hash = dep.commit_hash.as_deref().filter(|s| !s.is_empty()).unwrap_or("latest");
    let tag_len = 8.min(commit_hash.len());
    let tag_suffix = if tag_len > 0 { &commit_hash[..tag_len] } else { "latest" };
    let tag = format!("stackpilot/{}:{}", repo_name, tag_suffix);

    let docker_service = DockerService::new("");

    // ── 按项目类型分发构建策略 ──
    match project_type {
        "multi-module-java" | "multi-module-java-with-frontend" | "spring-cloud" => {
            // 多模块 Java：Maven 整体构建 → 为每个可执行模块构建镜像
            run_maven_build(&repo_dir).await?;
            let images = build_multi_module_images(&repo_dir, &repo_name, tag_suffix, &scan_result, &docker_service).await;

            // 持久化第一个镜像 tag（兼容单镜像字段）
            let primary_tag = images.first().cloned().unwrap_or(tag);
            persist_image_tag(&db, deployment_id, &primary_tag).await?;
            // 保存所有镜像 tag 到 config
            persist_all_image_tags(&db, deployment_id, &images).await?;
            info!("多模块构建完成，共 {} 个镜像", images.len());
        }
        "microservices" | "microservices-with-frontend" => {
            // 微服务：有 Java 服务时先 Maven 构建，再为每个服务构建镜像
            let services = scan_result.get("services").and_then(|v| v.as_array());
            let has_java = services.map(|ss| ss.iter().any(|s| {
                s.get("language").and_then(|v| v.as_str()) == Some("java")
                    && s.get("type").and_then(|v| v.as_str()) != Some("common")
            })).unwrap_or(false);

            if has_java {
                run_maven_build(&repo_dir).await?;
            }

            let images = build_microservices_images(&repo_dir, &repo_name, tag_suffix, &scan_result, &docker_service).await;

            let primary_tag = images.first().cloned().unwrap_or(tag);
            persist_image_tag(&db, deployment_id, &primary_tag).await?;
            // 保存所有镜像 tag 到 config
            persist_all_image_tags(&db, deployment_id, &images).await?;
            info!("微服务构建完成，共 {} 个镜像", images.len());
        }
        _ => {
            // 单体项目
            cleanup_old_images(&repo_name, &tag).await;

            if language == "java" {
                run_maven_build(&repo_dir).await?;
            }

            docker_service.build_image(&repo_dir, &tag, "Dockerfile").await?;
            persist_image_tag(&db, deployment_id, &tag).await?;
            info!("单体项目构建完成: {}", tag);
        }
    }

    Ok(())
}

/// 多模块 Java 项目：为每个可执行子模块构建 Docker 镜像
async fn build_multi_module_images(
    repo_dir: &std::path::Path,
    repo_name: &str,
    tag_suffix: &str,
    scan_result: &serde_json::Map<String, serde_json::Value>,
    docker_service: &DockerService,
) -> Vec<String> {
    let services = match scan_result.get("services").and_then(|v| v.as_array()) {
        Some(s) => s,
        None => {
            info!("多模块项目无 services 信息");
            return Vec::new();
        }
    };

    let mut images = Vec::new();

    for svc in services {
        let svc_type = svc.get("type").and_then(|v| v.as_str()).unwrap_or("service");
        if svc_type == "common" || svc_type == "library" {
            continue;
        }

        let svc_dir = svc.get("dir").and_then(|v| v.as_str()).unwrap_or("");
        let svc_name = svc.get("name").and_then(|v| v.as_str()).unwrap_or(svc_dir);
        let svc_port = svc.get("port").and_then(|v| v.as_u64()).unwrap_or(8080);

        if svc_dir.is_empty() {
            continue;
        }

        let svc_path = repo_dir.join(svc_dir);
        if !svc_path.exists() {
            info!("模块 {} 目录不存在，跳过", svc_name);
            continue;
        }

        // 检查或生成 Dockerfile
        let dockerfile_path = svc_path.join("Dockerfile");
        let target_dir = svc_path.join("target");

        if !dockerfile_path.exists() {
            // 如果没有 Dockerfile，检查是否有 target 目录和 jar 文件
            if target_dir.exists() {
                if let Some(jar_file) = find_executable_jar(&target_dir) {
                    // 有可执行 jar，生成指定 jar 名的 Dockerfile
                    let dockerfile_content = format!(
                        r#"FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY target/{jar} app.jar
EXPOSE {port}
CMD ["java", "-jar", "app.jar"]
"#,
                        jar = jar_file,
                        port = svc_port
                    );
                    let _ = tokio::fs::write(&dockerfile_path, &dockerfile_content).await;
                } else {
                    // 无可执行 jar，生成通用 Dockerfile（使用通配符）
                    let dockerfile_content = format!(
                        r#"FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY target/*.jar app.jar
EXPOSE {port}
CMD ["java", "-jar", "app.jar"]
"#,
                        port = svc_port
                    );
                    let _ = tokio::fs::write(&dockerfile_path, &dockerfile_content).await;
                }
            } else {
                info!("模块 {} 无 target 目录且无 Dockerfile，跳过", svc_name);
                continue;
            }
        }

        // 构建镜像
        let image_tag = format!("stackpilot/{}-{}:{}", repo_name, svc_name, tag_suffix);
        match docker_service.build_image(&svc_path, &image_tag, "Dockerfile").await {
            Ok(_) => {
                info!("模块 {} 镜像构建完成: {}", svc_name, image_tag);
                images.push(image_tag);
            }
            Err(e) => {
                info!("模块 {} 镜像构建失败: {}", svc_name, e);
            }
        }
    }

    images
}

/// 微服务项目：为每个服务构建 Docker 镜像
async fn build_microservices_images(
    repo_dir: &std::path::Path,
    repo_name: &str,
    tag_suffix: &str,
    scan_result: &serde_json::Map<String, serde_json::Value>,
    docker_service: &DockerService,
) -> Vec<String> {
    let services = match scan_result.get("services").and_then(|v| v.as_array()) {
        Some(s) => s,
        None => {
            info!("微服务项目无 services 信息");
            return Vec::new();
        }
    };

    let mut images = Vec::new();

    for svc in services {
        let svc_type = svc.get("type").and_then(|v| v.as_str()).unwrap_or("service");
        if svc_type == "common" || svc_type == "library" {
            continue;
        }

        let svc_dir = svc.get("dir").and_then(|v| v.as_str()).unwrap_or("");
        let svc_name = svc.get("name").and_then(|v| v.as_str()).unwrap_or(svc_dir);
        let svc_language = svc.get("language").and_then(|v| v.as_str()).unwrap_or("unknown");

        if svc_dir.is_empty() {
            continue;
        }

        let svc_path = repo_dir.join(svc_dir);
        if !svc_path.exists() {
            info!("服务 {} 目录不存在，跳过", svc_name);
            continue;
        }

        // Java 服务：检查是否有可执行 jar，有则更新 Dockerfile 指定 jar 名
        if svc_language == "java" {
            let target_dir = svc_path.join("target");
            if let Some(jar_file) = find_executable_jar(&target_dir) {
                let dockerfile_path = svc_path.join("Dockerfile");
                let dockerfile_content = format!(
                    r#"FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY target/{jar} app.jar
EXPOSE {port}
CMD ["java", "-jar", "app.jar"]
"#,
                    jar = jar_file,
                    port = svc.get("port").and_then(|v| v.as_u64()).unwrap_or(8080)
                );
                let _ = tokio::fs::write(&dockerfile_path, &dockerfile_content).await;
            }
        }

        let image_tag = format!("stackpilot/{}-{}:{}", repo_name, svc_name, tag_suffix);
        match docker_service.build_image(&svc_path, &image_tag, "Dockerfile").await {
            Ok(_) => {
                info!("服务 {} 镜像构建完成: {}", svc_name, image_tag);
                images.push(image_tag);
            }
            Err(e) => {
                info!("服务 {} 镜像构建失败: {}", svc_name, e);
            }
        }
    }

    images
}

/// 在 target 目录中查找可执行 jar（排除 sources/javadoc/tests）
fn find_executable_jar(target_dir: &std::path::Path) -> Option<String> {
    let entries = std::fs::read_dir(target_dir).ok()?;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if !name.ends_with(".jar") {
            continue;
        }
        if name.contains("-sources") || name.contains("-javadoc") || name.contains("-tests") {
            continue;
        }
        // 检查是否为可执行 JAR
        let jar_path = entry.path();
        if is_executable_jar(&jar_path) {
            return Some(name);
        }
    }
    // 如果没有找到可执行 JAR，返回第一个普通 JAR
    let entries = std::fs::read_dir(target_dir).ok()?;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.ends_with(".jar") && !name.contains("-sources") && !name.contains("-javadoc") && !name.contains("-tests") {
            return Some(name);
        }
    }
    None
}

/// 检测 JAR 是否为可执行 JAR（检查内部结构）
fn is_executable_jar(jar_path: &std::path::Path) -> bool {
    use std::fs::File;
    use std::io::Read;

    let file = match File::open(jar_path) {
        Ok(f) => f,
        Err(_) => return false,
    };

    let mut archive = match zip::ZipArchive::new(file) {
        Ok(a) => a,
        Err(_) => return false,
    };

    // 检查是否包含 BOOT-INF/（Spring Boot）
    for i in 0..archive.len() {
        let name = match archive.by_index(i) {
            Ok(f) => f.name().to_string(),
            Err(_) => continue,
        };

        if name.starts_with("BOOT-INF/") || name.starts_with("quarkus-app/") {
            return true;
        }

        if name == "META-INF/MANIFEST.MF" {
            let mut content = String::new();
            if let Ok(mut f) = archive.by_index(i) {
                if f.read_to_string(&mut content).is_ok() && content.contains("Main-Class: ") {
                    return true;
                }
            }
        }
    }

    false
}

/// 回退扫描：使用 glob 通配符查找所有 target 目录中的 JAR
fn find_jars_glob(repo_dir: &std::path::Path) -> Vec<String> {
    use glob::glob;

    let pattern = format!("{}/**/target/*.jar", repo_dir.display());
    let mut jars = Vec::new();

    if let Ok(paths) = glob(&pattern) {
        for path in paths.flatten() {
            let name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
            if !name.contains("-sources") && !name.contains("-javadoc") && !name.contains("-tests") {
                jars.push(path.to_string_lossy().to_string());
            }
        }
    }

    jars
}

/// 持久化 image_tag 到数据库
async fn persist_image_tag(
    db: &sea_orm::DatabaseConnection,
    deployment_id: Uuid,
    image_tag: &str,
) -> Result<(), AppError> {
    let dep = DeploymentEntity::find_by_id(deployment_id).one(db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let mut active: DeploymentActiveModel = dep.into();
    active.image_tag = Set(Some(image_tag.to_string()));
    active.update(db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?;
    Ok(())
}

/// 持久化所有镜像 tag 到 config（微服务项目）
async fn persist_all_image_tags(
    db: &sea_orm::DatabaseConnection,
    deployment_id: Uuid,
    images: &[String],
) -> Result<(), AppError> {
    if images.is_empty() {
        return Ok(());
    }

    let dep = DeploymentEntity::find_by_id(deployment_id).one(db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let mut config = dep.config.as_ref()
        .cloned()
        .unwrap_or_default();

    if let serde_json::Value::Object(ref mut map) = config {
        let images_json = serde_json::to_value(images)
            .unwrap_or(serde_json::Value::Array(vec![]));
        map.insert("_all_images".to_string(), images_json);
    }

    let mut active: DeploymentActiveModel = dep.into();
    active.config = Set(Some(config));
    active.update(db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?;

    info!("已保存 {} 个镜像 tag 到 config", images.len());
    Ok(())
}

/// 清理旧的 Docker 镜像
async fn cleanup_old_images(repo_name: &str, exclude_tag: &str) {
    let image_prefix = format!("stackpilot/{}", repo_name);
    let output = tokio::process::Command::new("docker")
        .args(["images", "--format", "{{.Repository}}:{{.Tag}}"])
        .arg("--filter")
        .arg(format!("reference={}*", image_prefix))
        .arg("--sort")
        .arg("created")
        .output()
        .await;

    match output {
        Ok(out) if out.status.success() => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            let images: Vec<&str> = stdout.lines()
                .filter(|l| !l.trim().is_empty())
                .filter(|img| *img != exclude_tag)
                .collect();
            if images.is_empty() {
                return;
            }
            info!("清理 {} 个旧镜像...", images.len());
            for img in &images {
                let _ = tokio::process::Command::new("docker")
                    .args(["rmi", "-f", img]).output().await;
            }
        }
        _ => {}
    }
    let _ = tokio::process::Command::new("docker")
        .args(["image", "prune", "-f"]).output().await;
}

/// Maven 构建（支持 mvnw 回退）
async fn run_maven_build(repo_dir: &std::path::Path) -> Result<(), AppError> {
    info!("执行 Maven 构建...");
    let mvnw_path = repo_dir.join("mvnw");
    let (cmd, args) = if mvnw_path.exists() {
        info!("使用 Maven Wrapper (mvnw)");
        ("./mvnw", vec!["clean", "package", "-DskipTests"])
    } else {
        info!("使用系统 mvn");
        ("mvn", vec!["clean", "package", "-DskipTests"])
    };

    let output = tokio::process::Command::new(cmd)
        .args(&args)
        .current_dir(repo_dir)
        .output()
        .await
        .map_err(|e| AppError::InternalError(format!("Maven 构建启动失败: {}", e)))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let tail = if stderr.len() > 500 { &stderr[stderr.len()-500..] } else { &stderr };
        return Err(AppError::InternalError(format!("Maven 构建失败: {}", tail)));
    }

    info!("Maven 构建完成");
    Ok(())
}
