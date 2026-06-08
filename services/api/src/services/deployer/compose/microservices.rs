use tracing::info;
use crate::services::scanner::dependency::service_map::ExternalService;

/// 为微服务项目生成 docker-compose.yml
pub fn generate_microservices_compose(
    _repo_name: &str,
    images: &[String],
    scan_result: &serde_json::Map<String, serde_json::Value>,
    external_services: &[ExternalService],
) -> String {
    let mut compose = String::from("version: '3.8'\n\nservices:\n");

    let services = scan_result.get("services")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    // 添加前端服务（如果有）
    let frontend_image = images.iter().find(|img| img.contains("-frontend") || img.contains("-ui"));
    if let Some(frontend_img) = frontend_image {
        let frontend_port = services.iter()
            .find(|s| {
                let lang = s.get("language").and_then(|v| v.as_str()).unwrap_or("");
                let svc_type = s.get("type").and_then(|v| v.as_str()).unwrap_or("");
                lang == "node" || svc_type == "frontend"
            })
            .and_then(|s| s.get("port").and_then(|v| v.as_u64()))
            .unwrap_or(3000);

        compose.push_str(&format!(
            r#"  frontend:
    image: {}
    ports:
      - "{}:{}"
    restart: unless-stopped
    depends_on:
      - gateway

"#,
            frontend_img, frontend_port, frontend_port
        ));
    }

    // 添加后端服务
    for svc in &services {
        let svc_type = svc.get("type").and_then(|v| v.as_str()).unwrap_or("service");
        if svc_type == "common" || svc_type == "library" || svc_type == "frontend" {
            continue;
        }

        let svc_name = svc.get("name").and_then(|v| v.as_str()).unwrap_or("");
        let svc_port = svc.get("port").and_then(|v| v.as_u64()).unwrap_or(8080);

        // 查找对应的镜像
        let image = images.iter().find(|img| {
            img.contains(&format!("-{}", svc_name)) || img.ends_with(&format!(":{}", svc_name))
        });

        if let Some(img) = image {
            let depends_on = if svc_type == "gateway" {
                // gateway 依赖其他服务
                let deps: Vec<&str> = services.iter()
                    .filter(|s| {
                        let t = s.get("type").and_then(|v| v.as_str()).unwrap_or("");
                        t == "service" || t == "api"
                    })
                    .filter_map(|s| s.get("name").and_then(|v| v.as_str()))
                    .collect();
                if deps.is_empty() {
                    String::new()
                } else {
                    let mut deps_str = String::from("    depends_on:\n");
                    for dep in deps {
                        deps_str.push_str(&format!("      - {}\n", dep));
                    }
                    deps_str
                }
            } else {
                String::new()
            };

            compose.push_str(&format!(
                r#"  {}:
    image: {}
    ports:
      - "{}:{}"
    restart: unless-stopped
{}
"#,
                svc_name, img, svc_port, svc_port, depends_on
            ));
        }
    }

    // 添加外部依赖服务
    for ext_svc in external_services {
        let svc_config = get_external_service_config(ext_svc);
        if !svc_config.is_empty() {
            compose.push_str(&svc_config);
        }
    }

    // 添加 volumes
    let has_db = external_services.iter().any(|s| s.category == "database");
    if has_db {
        compose.push_str("\nvolumes:\n");
        for ext_svc in external_services {
            if ext_svc.category == "database" {
                compose.push_str(&format!("  {}_data:\n", ext_svc.name));
            }
        }
    }

    info!("生成微服务 compose: {} 个服务", services.len());
    compose
}

/// 获取外部服务的 compose 配置
fn get_external_service_config(service: &ExternalService) -> String {
    match service.category.as_str() {
        "database" => {
            format!(
                r#"
  {}:
    image: {}
    ports:
      - "{}:{}"
    volumes:
      - {}_data:/var/lib/{}-data
    restart: unless-stopped
"#,
                service.name, service.image, service.default_port, service.default_port,
                service.name, service.name
            )
        }
        "cache" | "search" | "storage" | "monitoring" | "registry" | "gateway"
        | "auth" | "secrets" | "scheduler" | "testing" | "rpc" | "messagequeue" => {
            format!(
                r#"
  {}:
    image: {}
    ports:
      - "{}:{}"
    restart: unless-stopped
"#,
                service.name, service.image, service.default_port, service.default_port
            )
        }
        _ => String::new(),
    }
}
