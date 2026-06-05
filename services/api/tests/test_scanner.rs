use std::path::PathBuf;
use stackpilot_backend::services::scanner::rules::go::GoRule;
use stackpilot_backend::services::scanner::rules::java::JavaRule;
use stackpilot_backend::services::scanner::rules::rust::RustRule;
use stackpilot_backend::services::scanner::rules::ruby::RubyRule;
use stackpilot_backend::services::scanner::rules::php::PhpRule;
use stackpilot_backend::services::scanner::rules::dotnet::DotnetRule;
use stackpilot_backend::services::scanner::rules::base::BaseRule;
use stackpilot_backend::services::scanner::rules::context::ProjectContext;

fn create_temp_dir_with_files(files: &[(&str, &str)]) -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    for (name, content) in files {
        let path = dir.path().join(name);
        if let Some(parent) = path.parent() { std::fs::create_dir_all(parent).unwrap(); }
        std::fs::write(&path, content).unwrap();
    }
    dir
}

fn make_ctx(dir: &tempfile::TempDir) -> ProjectContext {
    ProjectContext::new(PathBuf::from(dir.path()))
}

#[tokio::test]
async fn test_detect_go_gin() {
    let dir = create_temp_dir_with_files(&[("go.mod", "module test\n\ngo 1.21\n\nrequire github.com/gin-gonic/gin v1.9.1\n")]);
    let rule = GoRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    let r = result.unwrap();
    assert_eq!(r.language, "go");
    assert_eq!(r.framework, Some("gin".to_string()));
    assert_eq!(r.port, Some(8080));
}

#[tokio::test]
async fn test_detect_go_echo() {
    let dir = create_temp_dir_with_files(&[("go.mod", "module test\n\ngo 1.21\n\nrequire github.com/labstack/echo v4.11.0\n")]);
    let rule = GoRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    assert_eq!(result.unwrap().framework, Some("echo".to_string()));
}

#[tokio::test]
async fn test_detect_java_spring_boot() {
    let dir = create_temp_dir_with_files(&[("pom.xml", r#"<project><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId></parent></project>"#)]);
    let rule = JavaRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    assert_eq!(result.unwrap().framework, Some("spring-boot".to_string()));
}

#[tokio::test]
async fn test_detect_java_gradle() {
    let dir = create_temp_dir_with_files(&[("build.gradle", "plugins { id 'org.springframework.boot' version '3.0' }\n")]);
    let rule = JavaRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    assert_eq!(result.unwrap().language, "java");
}

#[tokio::test]
async fn test_detect_rust_actix() {
    let dir = create_temp_dir_with_files(&[("Cargo.toml", "[dependencies]\nactix-web = \"4\"\n")]);
    let rule = RustRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    assert_eq!(result.unwrap().framework, Some("actix".to_string()));
}

#[tokio::test]
async fn test_detect_rust_axum() {
    let dir = create_temp_dir_with_files(&[("Cargo.toml", "[dependencies]\naxum = \"0.7\"\n")]);
    let rule = RustRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    assert_eq!(result.unwrap().framework, Some("axum".to_string()));
}

#[tokio::test]
async fn test_detect_ruby_rails() {
    let dir = create_temp_dir_with_files(&[("Gemfile", "source 'https://rubygems.org'\ngem 'rails', '~> 7.0'\n")]);
    let rule = RubyRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    let r = result.unwrap();
    assert_eq!(r.framework, Some("rails".to_string()));
    assert_eq!(r.port, Some(3000));
}

#[tokio::test]
async fn test_detect_php_laravel() {
    let dir = create_temp_dir_with_files(&[("composer.json", r#"{"require":{"laravel/framework":"^10.0"}}"#)]);
    let rule = PhpRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    let r = result.unwrap();
    assert_eq!(r.framework, Some("laravel".to_string()));
    assert_eq!(r.port, Some(8000));
}

#[tokio::test]
async fn test_detect_no_match() {
    let dir = create_temp_dir_with_files(&[("README.md", "# Test\n")]);
    let rule = GoRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_none());
}

#[tokio::test]
async fn test_detect_dotnet() {
    let dir = create_temp_dir_with_files(&[("app.csproj", r#"<Project Sdk="Microsoft.NET.Sdk.Web"></Project>"#)]);
    let rule = DotnetRule;
    let ctx = make_ctx(&dir);
    let result = rule.detect(&ctx).await.unwrap();
    assert!(result.is_some());
    let r = result.unwrap();
    assert_eq!(r.language, "dotnet");
    assert_eq!(r.port, Some(5000));
}
