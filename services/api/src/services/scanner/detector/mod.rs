#![allow(dead_code)]
use std::path::PathBuf;
use tracing::info;
use crate::error::AppError;
use super::rules::context::ProjectContext;
use super::rules::structure::{ProjectStructure, detect_structure};
use super::rules::base::{BaseRule, DetectionResult};
use super::rules::node::NodeRule;
use super::rules::python::PythonRule;
use super::rules::go::GoRule;
use super::rules::java::JavaRule;
use super::rules::rust::RustRule;
use super::rules::ruby::RubyRule;
use super::rules::php::PhpRule;
use super::rules::dotnet::DotnetRule;
use super::dependency::package_parser::{detect_dependencies, DependencyInfo};

/// 单个服务的检测结果
#[derive(Debug, Clone)]
pub struct ServiceDetectionResult {
    /// 服务目录名
    pub service_name: String,
    /// 服务目录路径
    pub service_dir: PathBuf,
    /// 检测到的语言信息
    pub detection: DetectionResult,
}

/// 扫描结果
#[derive(Debug)]
pub struct ScanResult {
    /// 项目类型: single / microservices / monorepo / spring-cloud / multi-module-java
    pub project_type: String,
    /// 主语言
    pub language: Option<String>,
    /// 框架
    pub framework: Option<String>,
    /// 版本
    pub version: Option<String>,
    /// 端口
    pub port: Option<u16>,
    /// 外部依赖信息
    pub dependencies: DependencyInfo,
    /// 微服务/monorepo 下多个服务的检测结果
    pub services: Vec<ServiceDetectionResult>,
}

/// 获取所有 8 种语言规则
fn all_rules() -> Vec<Box<dyn BaseRule>> {
    vec![
        Box::new(NodeRule),
        Box::new(PythonRule),
        Box::new(GoRule),
        Box::new(JavaRule),
        Box::new(RustRule),
        Box::new(RubyRule),
        Box::new(PhpRule),
        Box::new(DotnetRule),
    ]
}

/// 在给定目录中执行单应用检测（遍历所有语言规则）
async fn detect_single_app(ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
    let (files, _dirs) = ctx.list_dir(".").await
        .map_err(|e| AppError::InternalError(format!("读取目录失败: {}", e)))?;

    let rules = all_rules();
    let mut best_match: Option<DetectionResult> = None;
    let mut best_confidence = 0.0_f32;

    for rule in &rules {
        let confidence = rule.detect_language(&files);
        if confidence > best_confidence {
            if let Ok(Some(result)) = rule.detect(ctx).await {
                best_confidence = confidence;
                best_match = Some(result);
            }
        }
    }

    Ok(best_match)
}

/// 检测微服务架构中的各个子服务
async fn detect_microservices(ctx: &ProjectContext) -> Result<Vec<ServiceDetectionResult>, AppError> {
    let (_, dirs) = ctx.list_dir(".").await
        .map_err(|e| AppError::InternalError(format!("读取项目目录失败: {}", e)))?;

    let mut results = Vec::new();

    for dir_name in &dirs {
        let sub_ctx = ProjectContext::new(ctx.dir_path.join(dir_name));

        // 检查子目录是否包含项目文件
        let (sub_files, _) = match sub_ctx.list_dir(".").await {
            Ok(r) => r,
            Err(_) => continue,
        };

        let has_project_file = sub_files.iter().any(|f| {
            f == "package.json" || f == "pom.xml" || f == "go.mod"
                || f == "Cargo.toml" || f == "Gemfile" || f == "composer.json"
                || f == "requirements.txt" || f == "build.gradle"
        });

        if has_project_file {
            if let Ok(Some(detection)) = detect_single_app(&sub_ctx).await {
                results.push(ServiceDetectionResult {
                    service_name: dir_name.clone(),
                    service_dir: ctx.dir_path.join(dir_name),
                    detection,
                });
            }
        }
    }

    Ok(results)
}

/// 检测多模块 Java 项目
async fn detect_multi_module_java(ctx: &ProjectContext) -> Result<Vec<ServiceDetectionResult>, AppError> {
    // 多模块 Java 项目通过 pom.xml 中的 <modules> 标签定义子模块
    let pom_content = match ctx.read_text("pom.xml").await {
        Some(c) => c,
        None => return Ok(Vec::new()),
    };

    let (_, dirs) = ctx.list_dir(".").await
        .map_err(|e| AppError::InternalError(format!("读取项目目录失败: {}", e)))?;

    let mut results = Vec::new();

    // 从 pom.xml 中提取模块名
    let module_names = extract_maven_modules(&pom_content);

    // 如果从 pom.xml 解析到了模块名，按名匹配；否则扫描所有含 pom.xml 的子目录
    if !module_names.is_empty() {
        for module_name in &module_names {
            let module_dir = ctx.dir_path.join(module_name);
            if module_dir.is_dir() {
                let sub_ctx = ProjectContext::new(module_dir.clone());
                if let Ok(Some(detection)) = detect_single_app(&sub_ctx).await {
                    results.push(ServiceDetectionResult {
                        service_name: module_name.clone(),
                        service_dir: module_dir,
                        detection,
                    });
                }
            }
        }
    } else {
        // 回退：扫描所有包含 pom.xml 或 build.gradle 的子目录
        for dir_name in &dirs {
            let sub_dir = ctx.dir_path.join(dir_name);
            if sub_dir.join("pom.xml").exists() || sub_dir.join("build.gradle").exists() {
                let sub_ctx = ProjectContext::new(sub_dir.clone());
                if let Ok(Some(detection)) = detect_single_app(&sub_ctx).await {
                    results.push(ServiceDetectionResult {
                        service_name: dir_name.clone(),
                        service_dir: sub_dir,
                        detection,
                    });
                }
            }
        }
    }

    Ok(results)
}

/// 从 pom.xml 内容中提取 <modules> 标签下的模块名
fn extract_maven_modules(pom_content: &str) -> Vec<String> {
    let mut modules = Vec::new();
    let mut in_modules = false;

    for line in pom_content.lines() {
        let trimmed = line.trim();

        if trimmed.contains("<modules>") {
            in_modules = true;
            // 检查 <modules> 和 </modules> 在同一行的情况
            if trimmed.contains("</modules>") {
                in_modules = false;
            }
            continue;
        }

        if trimmed.contains("</modules>") {
            in_modules = false;
            continue;
        }

        if in_modules {
            // 提取 <module>name</module>
            if let Some(start) = trimmed.find("<module>") {
                if let Some(end) = trimmed.find("</module>") {
                    let name = &trimmed[start + "<module>".len()..end];
                    modules.push(name.trim().to_string());
                }
            }
        }
    }

    modules
}

/// 主检测入口：按项目结构类型路由到不同的检测策略
pub async fn detect(repo_dir: &PathBuf) -> Result<ScanResult, AppError> {
    let ctx = ProjectContext::new(repo_dir.clone());

    // Step 1: 检测项目结构
    let structure = detect_structure(&ctx).await?;

    // Step 2: 根据结构类型分发检测
    let (project_type, main_result, services) = match structure {
        ProjectStructure::SpringCloud => {
            let services = detect_microservices(&ctx).await?;
            let main_result = detect_single_app(&ctx).await?;
            ("spring-cloud".to_string(), main_result, services)
        }
        ProjectStructure::MultiModuleJava => {
            let services = detect_multi_module_java(&ctx).await?;
            let main_result = detect_single_app(&ctx).await?;
            ("multi-module-java".to_string(), main_result, services)
        }
        ProjectStructure::Microservices => {
            let services = detect_microservices(&ctx).await?;
            let main_result = detect_single_app(&ctx).await?;
            ("microservices".to_string(), main_result, services)
        }
        ProjectStructure::Monorepo => {
            let services = detect_microservices(&ctx).await?;
            let main_result = detect_single_app(&ctx).await?;
            ("monorepo".to_string(), main_result, services)
        }
        ProjectStructure::SingleApp => {
            let main_result = detect_single_app(&ctx).await?;
            ("single".to_string(), main_result, Vec::new())
        }
    };

    // Step 2b: 检测前端目录，升级项目类型
    let project_type = if let Some(fe_dir) = super::rules::structure::detect_frontend_dir(&ctx).await {
        info!("检测到前端目录: {}，升级项目类型", fe_dir);
        match project_type.as_str() {
            "microservices" => "microservices-with-frontend".to_string(),
            "multi-module-java" | "spring-cloud" => "multi-module-java-with-frontend".to_string(),
            "monorepo" => "monorepo".to_string(), // monorepo 已包含前端
            "single" => "single-with-frontend".to_string(),
            other => other.to_string(),
        }
    } else {
        project_type
    };

    // Step 3: 检测外部依赖
    let dependencies = detect_dependencies(repo_dir).await;

    // Step 4: 组装结果（优先使用主目录检测结果，否则使用第一个子服务的结果）
    let detection = main_result
        .or_else(|| services.first().map(|s| s.detection.clone()));

    Ok(ScanResult {
        project_type,
        language: detection.as_ref().map(|r| r.language.clone()),
        framework: detection.as_ref().and_then(|r| r.framework.clone()),
        version: detection.as_ref().and_then(|r| r.version.clone()),
        port: detection.as_ref().and_then(|r| r.port),
        dependencies,
        services,
    })
}
