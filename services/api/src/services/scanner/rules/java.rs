#![allow(dead_code)]
use async_trait::async_trait;
use regex::Regex;
use super::base::{BaseRule, DetectionResult};
use super::context::ProjectContext;
use crate::error::AppError;

pub struct JavaRule;

#[async_trait]
impl BaseRule for JavaRule {
    fn language_id(&self) -> &str {
        "java"
    }

    fn detect_language(&self, files: &[String]) -> f32 {
        if files.iter().any(|f| f == "pom.xml" || f == "build.gradle" || f == "build.gradle.kts") {
            return 0.9;
        }
        if files.iter().any(|f| f.ends_with(".java")) {
            return 0.4;
        }
        0.0
    }

    async fn detect(&self, ctx: &ProjectContext) -> Result<Option<DetectionResult>, AppError> {
        let has_pom = ctx.read_text("pom.xml").await.is_some();
        let has_gradle = ctx.read_text("build.gradle").await.is_some()
            || ctx.read_text("build.gradle.kts").await.is_some();

        if !has_pom && !has_gradle {
            return Ok(None);
        }

        // ── 框架检测 ──
        let mut framework = None;
        if has_pom {
            if let Some(content) = ctx.read_text("pom.xml").await {
                framework = detect_framework_from_pom(&content);

                // 根 pom 无框架时，递归扫描子模块 pom
                if framework.is_none() {
                    let modules = extract_maven_modules(&content);
                    for mod_name in &modules {
                        let mod_pom = format!("{}/pom.xml", mod_name);
                        if let Some(mod_content) = ctx.read_text(&mod_pom).await {
                            if let Some(fw) = detect_framework_from_pom(&mod_content) {
                                framework = Some(fw);
                                break;
                            }
                        }
                    }
                }
            }
        } else if has_gradle {
            if let Some(content) = ctx.read_text("build.gradle").await {
                framework = detect_framework_from_gradle(&content);
            }
            if framework.is_none() {
                if let Some(content) = ctx.read_text("build.gradle.kts").await {
                    framework = detect_framework_from_gradle(&content);
                }
            }
        }

        // ── 版本检测（三级回退） ──
        let version = if has_pom {
            if let Some(content) = ctx.read_text("pom.xml").await {
                extract_java_version(&content)
            } else {
                None
            }
        } else {
            None
        };

        // ── 端口检测 ──
        let port = detect_server_port(ctx).await;

        Ok(Some(DetectionResult {
            language: "java".to_string(),
            framework,
            version,
            port: Some(port),
            confidence: if has_pom { 0.9 } else { 0.85 },
        }))
    }
}

/// 从 pom.xml 检测框架（支持 mybatis-spring-boot、spring-boot、quarkus、micronaut、dropwizard、vertx、play）
fn detect_framework_from_pom(content: &str) -> Option<String> {
    let lower = content.to_lowercase();

    if lower.contains("mybatis-spring-boot") {
        return Some("mybatis".to_string());
    }
    if lower.contains("spring-boot-starter")
        || lower.contains("spring-boot-maven-plugin")
        || lower.contains("org.springframework.boot")
    {
        return Some("spring-boot".to_string());
    }
    if lower.contains("quarkus") {
        return Some("quarkus".to_string());
    }
    if lower.contains("micronaut") {
        return Some("micronaut".to_string());
    }
    if lower.contains("dropwizard") {
        return Some("dropwizard".to_string());
    }
    if lower.contains("io.vertx") {
        return Some("vertx".to_string());
    }
    if lower.contains("com.typesafe.play") {
        return Some("play".to_string());
    }

    None
}

/// 从 build.gradle 检测框架
fn detect_framework_from_gradle(content: &str) -> Option<String> {
    let lower = content.to_lowercase();

    if lower.contains("mybatis-spring-boot") {
        return Some("mybatis".to_string());
    }
    if lower.contains("org.springframework.boot") || lower.contains("spring-boot") {
        return Some("spring-boot".to_string());
    }
    if lower.contains("quarkus") {
        return Some("quarkus".to_string());
    }

    None
}

/// 从 pom.xml 提取 Java 版本（三级回退：java.version → maven.compiler.source → maven.compiler.target）
fn extract_java_version(content: &str) -> Option<String> {
    let re = Regex::new(r#"<java\.version>([^<]+)</java\.version>"#).ok()?;
    if let Some(caps) = re.captures(content) {
        return Some(caps[1].trim().to_string());
    }

    let re = Regex::new(r#"<maven\.compiler\.source>([^<]+)</maven\.compiler\.source>"#).ok()?;
    if let Some(caps) = re.captures(content) {
        return Some(caps[1].trim().to_string());
    }

    let re = Regex::new(r#"<maven\.compiler\.target>([^<]+)</maven\.compiler\.target>"#).ok()?;
    if let Some(caps) = re.captures(content) {
        return Some(caps[1].trim().to_string());
    }

    None
}

/// 从 application.yml / application.properties 检测端口（支持子模块）
async fn detect_server_port(ctx: &ProjectContext) -> u16 {
    let config_paths = vec![
        "src/main/resources/application.properties",
        "src/main/resources/application.yml",
        "src/main/resources/application.yaml",
        "src/main/resources/application-dev.properties",
        "src/main/resources/application-dev.yml",
        "src/main/resources/bootstrap.properties",
        "src/main/resources/bootstrap.yml",
    ];

    for path in &config_paths {
        if let Some(content) = ctx.read_text(path).await {
            if let Some(port) = parse_port_from_config(&content) {
                return port;
            }
        }
    }

    // 扫描子模块的 resources 目录
    if let Ok((_, dirs)) = ctx.list_dir(".").await {
        for dir in &dirs {
            let sub_paths = vec![
                format!("{}/src/main/resources/application.properties", dir),
                format!("{}/src/main/resources/application.yml", dir),
                format!("{}/src/main/resources/application.yaml", dir),
                format!("{}/src/main/resources/application-dev.properties", dir),
                format!("{}/src/main/resources/application-dev.yml", dir),
                format!("{}/src/main/resources/bootstrap.properties", dir),
                format!("{}/src/main/resources/bootstrap.yml", dir),
            ];
            for path in &sub_paths {
                if let Some(content) = ctx.read_text(path).await {
                    if let Some(port) = parse_port_from_config(&content) {
                        return port;
                    }
                }
            }
        }
    }

    8080
}

/// 从配置文件内容解析端口
fn parse_port_from_config(content: &str) -> Option<u16> {
    // properties 格式: server.port=8081
    let re = Regex::new(r"(?m)^server\.port\s*=\s*(\d+)").ok()?;
    if let Some(caps) = re.captures(content) {
        return caps[1].parse().ok();
    }

    // yml 格式: port: 8081（在 server: 块下）
    let re = Regex::new(r"(?m)^\s+port:\s*(\d+)").ok()?;
    if let Some(caps) = re.captures(content) {
        return caps[1].parse().ok();
    }

    None
}

/// 从 pom.xml 内容中提取 <modules> 标签下的模块名
fn extract_maven_modules(content: &str) -> Vec<String> {
    let mut modules = Vec::new();
    let mut in_modules = false;

    for line in content.lines() {
        let trimmed = line.trim();

        if trimmed.contains("<modules>") {
            in_modules = true;
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
