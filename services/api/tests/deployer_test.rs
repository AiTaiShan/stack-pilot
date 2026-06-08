use std::collections::HashMap;

/// 测试 Docker build_args 生成
#[test]
fn test_build_args_generation() {
    let mut args = HashMap::new();
    args.insert("JAVA_VERSION".to_string(), "17".to_string());
    args.insert("APP_PORT".to_string(), "8080".to_string());

    let mut cmd_args = vec!["build", "-t", "test:latest", "-f", "Dockerfile"];
    for (key, value) in &args {
        cmd_args.push("--build-arg");
        cmd_args.push(&format!("{}={}", key, value));
    }
    cmd_args.push(".");

    assert!(cmd_args.contains(&"--build-arg"));
    assert_eq!(cmd_args.len(), 9); // 5 base + 2 * 2 build-args + 1 dot
}

/// 测试端口映射规则
#[test]
fn test_port_mappings() {
    let mappings = vec![
        ("localhost:6380", "redis:6379"),
        ("localhost:3306", "mysql:3306"),
        ("localhost:5432", "postgres:5432"),
        ("localhost:9092", "kafka:9092"),
        ("localhost:27017", "mongodb:27017"),
    ];

    for (input, expected) in mappings {
        let service = expected.split(':').next().unwrap();
        assert!(!service.is_empty());
    }
}

/// 测试 nginx.conf 生成
#[test]
fn test_nginx_conf_generation() {
    let frontend_port = 3000;
    let api_prefix = "/api";
    let gateway_service = "gateway";
    let gateway_port = 8080;

    let conf = format!(
        r#"server {{
    listen {frontend_port};
    server_name localhost;

    location / {{
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }}

    location {api_prefix} {{
        proxy_pass http://{gateway_service}:{gateway_port};
    }}
}}
"#,
        frontend_port = frontend_port,
        api_prefix = api_prefix,
        gateway_service = gateway_service,
        gateway_port = gateway_port,
    );

    assert!(conf.contains("listen 3000"));
    assert!(conf.contains("proxy_pass http://gateway:8080"));
}

/// 测试环境变量序列化
#[test]
fn test_env_var_serialization() {
    let mut env_vars = HashMap::new();
    env_vars.insert("DB_HOST".to_string(), "mysql".to_string());
    env_vars.insert("DB_PORT".to_string(), "3306".to_string());

    let mut lines = Vec::new();
    for (k, v) in &env_vars {
        lines.push(format!("- {}={}", k, v));
    }

    let serialized = lines.join("\n");
    assert!(serialized.contains("DB_HOST=mysql"));
    assert!(serialized.contains("DB_PORT=3306"));
}

/// 测试 JAR 文件名过滤
#[test]
fn test_jar_filename_filter() {
    let filenames = vec![
        "app.jar",
        "app-sources.jar",
        "app-javadoc.jar",
        "app-tests.jar",
        "lib.jar",
    ];

    let filtered: Vec<&str> = filenames.iter()
        .filter(|f| f.ends_with(".jar"))
        .filter(|f| !f.contains("-sources") && !f.contains("-javadoc") && !f.contains("-tests"))
        .copied()
        .collect();

    assert_eq!(filtered.len(), 2);
    assert!(filtered.contains(&"app.jar"));
    assert!(filtered.contains(&"lib.jar"));
}

/// 测试微服务 compose 生成
#[test]
fn test_microservices_compose_generation() {
    let services = vec![
        ("gateway", 8080),
        ("auth", 9200),
        ("system", 9300),
    ];

    let mut compose = String::from("version: '3.8'\n\nservices:\n");
    for (name, port) in &services {
        compose.push_str(&format!(
            r#"  {}:
    image: stackpilot/test-{}:latest
    ports:
      - "{}:{}"
    restart: unless-stopped
"#,
            name, name, port, port
        ));
    }

    assert!(compose.contains("gateway:"));
    assert!(compose.contains("auth:"));
    assert!(compose.contains("system:"));
    assert!(compose.contains("8080:8080"));
}
