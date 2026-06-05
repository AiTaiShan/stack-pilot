#![allow(dead_code)]
use std::path::Path;
use super::context::ProjectContext;
use crate::error::AppError;

/// 项目结构类型
#[derive(Debug, Clone, PartialEq)]
pub enum ProjectStructure {
    /// Spring Cloud 微服务
    SpringCloud,
    /// 多模块 Java 项目（如若依）
    MultiModuleJava,
    /// 通用微服务架构
    Microservices,
    /// Monorepo（前后端分离等）
    Monorepo,
    /// 单体应用
    SingleApp,
}

/// 检测项目结构类型
///
/// 检测优先级：
/// 1. Spring Cloud（pom.xml 含 spring-cloud-dependencies）
/// 2. 多模块 Java（pom.xml 含 <modules>）
/// 3. Monorepo（packages/ 或 apps/ 目录，或 workspaces 配置）
/// 4. 微服务（多个子目录各含不同语言的项目文件）
/// 5. 单体应用（默认）
pub async fn detect_structure(ctx: &ProjectContext) -> Result<ProjectStructure, AppError> {
    // 1. 检测 Spring Cloud / 多模块 Java
    if let Some(content) = ctx.read_text("pom.xml").await {
        if content.contains("spring-cloud-dependencies")
            || content.contains("spring-cloud-starter-")
        {
            return Ok(ProjectStructure::SpringCloud);
        }
        if content.contains("<modules>") {
            return Ok(ProjectStructure::MultiModuleJava);
        }
    }

    // 2. 检测 Monorepo
    let (_, dirs) = ctx.list_dir(".").await.map_err(|e| {
        AppError::InternalError(format!("读取项目根目录失败: {}", e))
    })?;

    if dirs.iter().any(|d| d == "packages" || d == "apps") {
        return Ok(ProjectStructure::Monorepo);
    }

    if let Some(pkg) = ctx.read_text("package.json").await {
        if pkg.contains("\"workspaces\"") {
            return Ok(ProjectStructure::Monorepo);
        }
    }

    // 3. 检测微服务（多个子目录各含项目文件）
    let mut service_count = 0;
    for dir_name in &dirs {
        let sub_files = match ctx.list_dir(dir_name).await {
            Ok((files, _)) => files,
            Err(_) => continue,
        };
        let has_project_file = sub_files.iter().any(|f| {
            f == "package.json" || f == "pom.xml" || f == "go.mod" || f == "Cargo.toml"
        });
        if has_project_file {
            service_count += 1;
        }
    }

    if service_count >= 2 {
        return Ok(ProjectStructure::Microservices);
    }

    // 4. 默认单体应用
    Ok(ProjectStructure::SingleApp)
}

/// 同步版本的结构检测（用于不支持 async 的场景）
pub fn detect_structure_sync(repo_dir: &Path) -> ProjectStructure {
    let pom = repo_dir.join("pom.xml");
    if pom.exists() {
        if let Ok(content) = std::fs::read_to_string(&pom) {
            if content.contains("spring-cloud-dependencies")
                || content.contains("spring-cloud-starter-")
            {
                return ProjectStructure::SpringCloud;
            }
            if content.contains("<modules>") {
                return ProjectStructure::MultiModuleJava;
            }
        }
    }

    if repo_dir.join("packages").is_dir() || repo_dir.join("apps").is_dir() {
        return ProjectStructure::Monorepo;
    }

    if let Ok(pkg) = std::fs::read_to_string(repo_dir.join("package.json")) {
        if pkg.contains("\"workspaces\"") {
            return ProjectStructure::Monorepo;
        }
    }

    if let Ok(entries) = std::fs::read_dir(repo_dir) {
        let mut count = 0;
        for entry in entries.flatten() {
            if entry.path().is_dir() {
                let p = entry.path();
                if p.join("package.json").exists()
                    || p.join("pom.xml").exists()
                    || p.join("go.mod").exists()
                {
                    count += 1;
                }
            }
        }
        if count >= 2 {
            return ProjectStructure::Microservices;
        }
    }

    ProjectStructure::SingleApp
}
