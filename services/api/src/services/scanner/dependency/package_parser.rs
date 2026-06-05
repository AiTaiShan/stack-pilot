#![allow(dead_code)]
use std::collections::HashMap;
use std::path::PathBuf;
use tokio::fs;
use super::service_map::{ExternalService, get_external_services};

/// 数据库初始化信息
#[derive(Debug, Clone, serde::Serialize)]
pub struct DatabaseInitInfo {
    pub has_migrations: bool,
    pub migration_tool: String,
    pub migration_dir: String,
    pub has_schema_sql: bool,
    pub schema_files: Vec<String>,
    pub has_seed_data: bool,
    pub seed_files: Vec<String>,
    pub has_orm_auto_create: bool,
    pub orm_tool: String,
    pub init_commands: Vec<String>,
}

impl Default for DatabaseInitInfo {
    fn default() -> Self {
        Self {
            has_migrations: false,
            migration_tool: String::new(),
            migration_dir: String::new(),
            has_schema_sql: false,
            schema_files: Vec::new(),
            has_seed_data: false,
            seed_files: Vec::new(),
            has_orm_auto_create: false,
            orm_tool: String::new(),
            init_commands: Vec::new(),
        }
    }
}

#[derive(Debug)]
pub struct DependencyInfo {
    pub external_services: Vec<String>,
    pub service_details: HashMap<String, ExternalService>,
    pub database_init: DatabaseInitInfo,
    pub service_versions: HashMap<String, String>,
    pub app_port: u16,
}

/// 从依赖文件内容中检测外部服务
fn detect_from_content(content: &str, services: &HashMap<String, ExternalService>) -> Vec<String> {
    let mut detected = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for (key, service) in services {
        // 跳过别名（如 postgres 和 postgresql 指向同一个实际服务）
        let canonical_name = match key.as_str() {
            "postgres" => "postgresql",
            other => other,
        };
        if seen.contains(canonical_name) {
            continue;
        }

        for detection_key in &service.detection_keys {
            if content.contains(detection_key) {
                seen.insert(canonical_name);
                detected.push(canonical_name.to_string());
                break;
            }
        }
    }

    detected
}

/// 从 docker-compose 文件中检测外部服务（匹配 image 字段）
async fn detect_from_docker_compose(
    repo_dir: &PathBuf,
    services: &HashMap<String, ExternalService>,
) -> Vec<String> {
    let compose_files = [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ];

    let mut detected = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for compose_name in &compose_files {
        let path = repo_dir.join(compose_name);
        let content = match fs::read_to_string(&path).await {
            Ok(c) => c,
            Err(_) => continue,
        };

        for line in content.lines() {
            let trimmed = line.trim();
            // 匹配 "image: xxx" 格式
            if let Some(image_part) = trimmed.strip_prefix("image:") {
                let image = image_part.trim().trim_matches('"').trim_matches('\'').to_lowercase();
                for (key, service) in services {
                    if service.image.is_empty() {
                        continue;
                    }
                    let image_prefix = service.image.split(':').next().unwrap_or("");
                    if !image_prefix.is_empty() && image.contains(image_prefix) {
                        let canonical = match key.as_str() {
                            "postgres" => "postgresql",
                            other => other,
                        };
                        if seen.insert(canonical.to_string()) {
                            detected.push(canonical.to_string());
                        }
                    }
                }
            }
        }
    }

    detected
}

/// 从 Dockerfile 中检测外部服务（匹配 FROM 指令）
async fn detect_from_dockerfile(
    repo_dir: &PathBuf,
    services: &HashMap<String, ExternalService>,
) -> Vec<String> {
    let dockerfiles = ["Dockerfile", "Dockerfile.dev", "Dockerfile.prod"];

    let mut detected = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for df_name in &dockerfiles {
        let path = repo_dir.join(df_name);
        let content = match fs::read_to_string(&path).await {
            Ok(c) => c,
            Err(_) => continue,
        };

        for line in content.lines() {
            let trimmed = line.trim().to_uppercase();
            // 匹配 "FROM xxx" 指令
            if let Some(from_part) = trimmed.strip_prefix("FROM ") {
                let image = from_part.split_whitespace().next().unwrap_or("").to_lowercase();
                for (key, service) in services {
                    if service.image.is_empty() {
                        continue;
                    }
                    let image_prefix = service.image.split(':').next().unwrap_or("");
                    if !image_prefix.is_empty() && image.contains(image_prefix) {
                        let canonical = match key.as_str() {
                            "postgres" => "postgresql",
                            other => other,
                        };
                        if seen.insert(canonical.to_string()) {
                            detected.push(canonical.to_string());
                        }
                    }
                }
            }
        }
    }

    detected
}

/// 从配置文件中检测外部服务（连接字符串、环境变量前缀等）
async fn detect_from_config_files(repo_dir: &PathBuf) -> Vec<String> {
    let config_files = [
        ".env", ".env.example", ".env.local",
        "application.yml", "application.yaml", "application.properties",
        "config.yml", "config.yaml", "config.json",
        "bootstrap.yml", "bootstrap.yaml",
        "appsettings.json", "appsettings.Development.json",
    ];

    // 服务名 → 检测模式列表
    let patterns: Vec<(&str, Vec<&str>)> = vec![
        ("mysql", vec!["jdbc:mysql://", "MYSQL_", "mysql://"]),
        ("postgresql", vec!["jdbc:postgresql://", "POSTGRES_", "postgresql://"]),
        ("mongodb", vec!["mongodb://", "mongodb+srv://", "MONGO_", "MONGODB_URI"]),
        ("redis", vec!["redis://", "REDIS_", "REDIS_URL"]),
        ("kafka", vec!["KAFKA_", "kafka.bootstrap", "bootstrap.servers"]),
        ("rabbitmq", vec!["rabbitmq://", "AMQP_", "RABBITMQ_"]),
        ("elasticsearch", vec!["ELASTIC_", "elasticsearch.host"]),
        ("nacos", vec!["NACOS_", "nacos.server"]),
        ("consul", vec!["CONSUL_", "consul.host"]),
        ("minio", vec!["MINIO_", "minio.endpoint"]),
    ];

    let mut detected = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for cfg_name in &config_files {
        let path = repo_dir.join(cfg_name);
        let content = match fs::read_to_string(&path).await {
            Ok(c) => c.to_lowercase(),
            Err(_) => continue,
        };

        for (service_name, service_patterns) in &patterns {
            if seen.contains(*service_name) {
                continue;
            }
            for pattern in service_patterns {
                if content.contains(&pattern.to_lowercase()) {
                    seen.insert(service_name.to_string());
                    detected.push(service_name.to_string());
                    break;
                }
            }
        }
    }

    detected
}

/// 从源代码 import/require 语句检测外部服务
async fn detect_from_source_code(repo_dir: &PathBuf) -> Vec<String> {
    // 各语言的 import 模式 → 服务名
    let python_patterns: Vec<(&str, &str)> = vec![
        ("pymysql", "mysql"), ("mysql.connector", "mysql"), ("MySQLdb", "mysql"),
        ("psycopg2", "postgresql"), ("asyncpg", "postgresql"),
        ("pymongo", "mongodb"), ("motor", "mongodb"),
        ("redis", "redis"), ("aioredis", "redis"),
        ("kafka", "kafka"),
        ("pika", "rabbitmq"),
        ("elasticsearch", "elasticsearch"),
    ];
    let js_patterns: Vec<(&str, &str)> = vec![
        ("mysql", "mysql"), ("mysql2", "mysql"),
        ("pg", "postgresql"), ("postgres", "postgresql"),
        ("mongoose", "mongodb"), ("mongodb", "mongodb"),
        ("ioredis", "redis"), ("redis", "redis"),
        ("kafkajs", "kafka"), ("kafka-node", "kafka"),
        ("amqplib", "rabbitmq"),
        ("@elastic/elasticsearch", "elasticsearch"),
    ];
    let go_patterns: Vec<(&str, &str)> = vec![
        ("go-sql-driver/mysql", "mysql"),
        ("lib/pq", "postgresql"), ("jackc/pgx", "postgresql"),
        ("mongo-driver", "mongodb"),
        ("go-redis", "redis"), ("redis/go-redis", "redis"),
        ("segmentio/kafka-go", "kafka"), ("Shopify/sarama", "kafka"),
        ("streadway/amqp", "rabbitmq"),
        ("olivere/elastic", "elasticsearch"),
    ];

    let skip_dirs = ["node_modules", ".git", "vendor", "venv", "__pycache__", "target", "build", ".stackpilot"];
    let mut detected = Vec::new();
    let mut seen = std::collections::HashSet::new();

    // 递归遍历源代码文件（限制深度避免过慢）
    scan_source_dir(repo_dir, &python_patterns, &js_patterns, &go_patterns,
                    &skip_dirs, &mut detected, &mut seen, 0).await;

    detected.sort();
    detected.dedup();
    detected
}

fn scan_source_dir<'a>(
    dir: &'a PathBuf,
    python_patterns: &'a [(&str, &str)],
    js_patterns: &'a [(&str, &str)],
    go_patterns: &'a [(&str, &str)],
    skip_dirs: &'a [&str],
    detected: &'a mut Vec<String>,
    seen: &'a mut std::collections::HashSet<String>,
    depth: u32,
) -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send + 'a>> {
    Box::pin(async move {
        if depth > 4 {
            return;
        }
        let mut entries = match fs::read_dir(dir).await {
            Ok(e) => e,
            Err(_) => return,
        };
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = entry.file_name().to_string_lossy().to_string();
            let path = entry.path();
            if path.is_dir() {
                if skip_dirs.contains(&name.as_str()) {
                    continue;
                }
                scan_source_dir(&path, python_patterns, js_patterns, go_patterns,
                                skip_dirs, detected, seen, depth + 1).await;
            } else {
                // 只读前 10KB
                let content = match fs::read(&path).await {
                    Ok(bytes) => {
                        let len = bytes.len().min(10240);
                        String::from_utf8_lossy(&bytes[..len]).to_lowercase()
                    }
                    Err(_) => continue,
                };
                let patterns = if name.ends_with(".py") {
                    python_patterns
                } else if name.ends_with(".js") || name.ends_with(".ts")
                    || name.ends_with(".jsx") || name.ends_with(".tsx") {
                    js_patterns
                } else if name.ends_with(".go") {
                    go_patterns
                } else {
                    continue;
                };
                for (keyword, service) in patterns {
                    if content.contains(keyword) && seen.insert(service.to_string()) {
                        detected.push(service.to_string());
                    }
                }
            }
        }
    })
}

/// 检测数据库初始化方式（迁移工具、SQL 文件、ORM 自动建表、种子数据）
async fn detect_database_init(repo_dir: &PathBuf) -> DatabaseInitInfo {
    let mut info = DatabaseInitInfo::default();

    // 1. 检测迁移工具
    detect_migration_tools(repo_dir, &mut info).await;

    // 2. 检测 SQL 文件
    detect_sql_files(repo_dir, &mut info).await;

    // 3. 检测 ORM 自动建表
    detect_orm_auto_create(repo_dir, &mut info).await;

    // 4. 检测种子数据
    detect_seed_data(repo_dir, &mut info).await;

    // 5. 生成初始化命令
    generate_init_commands(&mut info);

    info
}

async fn detect_migration_tools(repo_dir: &PathBuf, info: &mut DatabaseInitInfo) {
    // Alembic (Python SQLAlchemy)
    if repo_dir.join("alembic").is_dir() || repo_dir.join("alembic.ini").exists() {
        info.has_migrations = true;
        info.migration_tool = "alembic".to_string();
        info.migration_dir = "alembic/versions".to_string();
        return;
    }
    // Flyway (Java)
    for d in &["src/main/resources/db/migration", "db/migration", "flyway"] {
        if repo_dir.join(d).is_dir() {
            info.has_migrations = true;
            info.migration_tool = "flyway".to_string();
            info.migration_dir = d.to_string();
            return;
        }
    }
    // Liquibase (Java)
    for f in &["liquibase.xml", "changelog.xml"] {
        if repo_dir.join(f).exists() {
            info.has_migrations = true;
            info.migration_tool = "liquibase".to_string();
            info.migration_dir = f.to_string();
            return;
        }
    }
    // Knex.js (Node.js)
    if repo_dir.join("knexfile.js").exists() || repo_dir.join("knexfile.ts").exists() {
        info.has_migrations = true;
        info.migration_tool = "knex".to_string();
        info.migration_dir = "migrations".to_string();
        return;
    }
    // Prisma (Node.js)
    if repo_dir.join("prisma").join("schema.prisma").exists() {
        info.has_migrations = true;
        info.migration_tool = "prisma".to_string();
        info.migration_dir = "prisma/migrations".to_string();
        return;
    }
    // golang-migrate (Go)
    let migrations_dir = repo_dir.join("migrations");
    if migrations_dir.is_dir() {
        if let Ok(mut entries) = fs::read_dir(&migrations_dir).await {
            while let Ok(Some(entry)) = entries.next_entry().await {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.ends_with(".sql") || name.ends_with(".up.sql") {
                    info.has_migrations = true;
                    info.migration_tool = "golang-migrate".to_string();
                    info.migration_dir = "migrations".to_string();
                    return;
                }
            }
        }
    }
    // ActiveRecord (Ruby)
    if repo_dir.join("db").join("migrate").is_dir() {
        info.has_migrations = true;
        info.migration_tool = "activerecord".to_string();
        info.migration_dir = "db/migrate".to_string();
    }
}

async fn detect_sql_files(repo_dir: &PathBuf, info: &mut DatabaseInitInfo) {
    let sql_patterns = [
        "init.sql", "schema.sql", "create.sql", "setup.sql",
        "database.sql", "db.sql", "tables.sql",
        "sql/init.sql", "sql/schema.sql", "sql/create.sql",
        "db/init.sql", "db/schema.sql",
        "src/main/resources/schema.sql", "src/main/resources/data.sql",
    ];
    for pattern in &sql_patterns {
        let path = repo_dir.join(pattern);
        if path.exists() {
            if pattern.contains("data") || pattern.contains("seed") || pattern.contains("init") {
                info.has_seed_data = true;
                info.seed_files.push(pattern.to_string());
            } else {
                info.has_schema_sql = true;
                info.schema_files.push(pattern.to_string());
            }
        }
    }
}

async fn detect_orm_auto_create(repo_dir: &PathBuf, info: &mut DatabaseInitInfo) {
    // 扫描 Python 文件中的 create_all
    let skip_dirs = [".git", "node_modules", "target", "__pycache__", "venv"];
    if let Ok(mut entries) = fs::read_dir(repo_dir).await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = entry.file_name().to_string_lossy().to_string();
            if entry.path().is_dir() && skip_dirs.contains(&name.as_str()) {
                continue;
            }
            if name.ends_with(".py") {
                if let Ok(content) = fs::read_to_string(entry.path()).await {
                    let snippet = &content[..content.len().min(5000)];
                    if snippet.contains("create_all") || snippet.contains("Base.metadata.create_all") {
                        info.has_orm_auto_create = true;
                        info.orm_tool = "sqlalchemy".to_string();
                        return;
                    }
                }
            }
        }
    }
    // 检查 Prisma
    if repo_dir.join("prisma").join("schema.prisma").exists() {
        info.has_orm_auto_create = true;
        info.orm_tool = "prisma".to_string();
    }
}

async fn detect_seed_data(repo_dir: &PathBuf, info: &mut DatabaseInitInfo) {
    let seed_patterns = [
        "seed.py", "seeds.py", "seed.js", "seeds.js",
        "seed.ts", "seeds.ts", "seed.rb", "seeds.rb",
        "fixtures", "sample-data",
        "db/seeds", "db/seed", "database/seeds",
        "prisma/seed.ts", "prisma/seed.js",
    ];
    for pattern in &seed_patterns {
        if repo_dir.join(pattern).exists() {
            info.has_seed_data = true;
            info.seed_files.push(pattern.to_string());
        }
    }
    // 检查 package.json 中的 seed 脚本
    let pkg_path = repo_dir.join("package.json");
    if let Ok(content) = fs::read_to_string(&pkg_path).await {
        if let Ok(pkg) = serde_json::from_str::<serde_json::Value>(&content) {
            if let Some(scripts) = pkg.get("scripts").and_then(|s| s.as_object()) {
                for (name, _cmd) in scripts {
                    if name.contains("seed") {
                        info.has_seed_data = true;
                        info.init_commands.push(format!("npm run {}", name));
                    }
                }
            }
        }
    }
}

fn generate_init_commands(info: &mut DatabaseInitInfo) {
    let mut commands = Vec::new();
    if info.has_migrations {
        match info.migration_tool.as_str() {
            "alembic" => commands.push("alembic upgrade head".to_string()),
            "flyway" => commands.push("flyway migrate".to_string()),
            "liquibase" => commands.push("liquibase update".to_string()),
            "knex" => commands.push("npx knex migrate:latest".to_string()),
            "prisma" => commands.push("npx prisma migrate deploy".to_string()),
            "golang-migrate" => commands.push("migrate -path migrations -database $DATABASE_URL up".to_string()),
            "activerecord" => commands.push("rails db:migrate".to_string()),
            _ => {}
        }
    }
    if info.has_orm_auto_create && !info.has_migrations && info.orm_tool == "prisma" {
        commands.push("npx prisma db push".to_string());
    }
    info.init_commands.extend(commands);
}

/// 从源代码配置文件中检测应用端口
async fn detect_app_port(repo_dir: &PathBuf) -> u16 {
    let config_files = ["application.yml", "application.yaml"];
    for cfg_name in &config_files {
        let path = repo_dir.join(cfg_name);
        if let Ok(content) = fs::read_to_string(&path).await {
            for line in content.lines() {
                let trimmed = line.trim();
                // 匹配 "port: 8080" 格式
                if trimmed.starts_with("port:") {
                    let val = trimmed.strip_prefix("port:").unwrap().trim();
                    if let Ok(port) = val.parse::<u16>() {
                        if port > 0 {
                            return port;
                        }
                    }
                }
            }
        }
    }
    8080 // 默认端口
}

/// 从 pom.xml 等依赖文件中检测服务版本
async fn detect_service_versions(repo_dir: &PathBuf) -> HashMap<String, String> {
    let mut versions = HashMap::new();

    // 检测 pom.xml 中的依赖版本
    let pom_path = repo_dir.join("pom.xml");
    if let Ok(content) = fs::read_to_string(&pom_path).await {
        // 简单提取版本：查找常见依赖的版本号
        // MySQL 版本
        if content.contains("mysql-connector-java") || content.contains("mysql-connector-j") {
            if content.contains("5.") && (content.contains("mysql-connector-java:5") || content.contains("5.1.")) {
                versions.insert("mysql".to_string(), "mysql:5.7".to_string());
            } else {
                versions.insert("mysql".to_string(), "mysql:8.0".to_string());
            }
        }
        // PostgreSQL 版本
        if content.contains("postgresql") {
            versions.insert("postgresql".to_string(), "postgres:15".to_string());
        }
        // Redis 版本
        if content.contains("jedis") || content.contains("lettuce") || content.contains("redisson") {
            versions.insert("redis".to_string(), "redis:7-alpine".to_string());
        }
        // MongoDB 版本
        if content.contains("mongodb-driver") {
            versions.insert("mongodb".to_string(), "mongo:7".to_string());
        }
        // Kafka 版本
        if content.contains("kafka-clients") || content.contains("spring-kafka") {
            versions.insert("kafka".to_string(), "confluentinc/cp-kafka:7.5".to_string());
        }
        // RabbitMQ 版本
        if content.contains("amqp-client") || content.contains("spring-amqp") {
            versions.insert("rabbitmq".to_string(), "rabbitmq:3-management".to_string());
        }
    }

    versions
}

pub async fn detect_dependencies(repo_dir: &PathBuf) -> DependencyInfo {
    let services = get_external_services();
    let mut all_detected: Vec<String> = Vec::new();

    // 需要检查的依赖文件列表
    let dep_files = [
        "package.json",       // Node.js
        "requirements.txt",   // Python
        "Pipfile",            // Python (pipenv)
        "pyproject.toml",     // Python (poetry/pip)
        "go.mod",             // Go
        "go.sum",             // Go (补充)
        "pom.xml",            // Java (Maven)
        "build.gradle",       // Java (Gradle)
        "build.gradle.kts",   // Java (Gradle Kotlin)
        "Cargo.toml",        // Rust
        "Gemfile",            // Ruby
        "composer.json",      // PHP
        "*.csproj",           // .NET（通过目录扫描）
    ];

    // 扫描已知的依赖文件
    for dep_file in &dep_files {
        if dep_file.contains('*') {
            // 跳过通配符模式，后续单独处理
            continue;
        }
        let file_path = repo_dir.join(dep_file);
        if file_path.exists() {
            if let Ok(content) = fs::read_to_string(&file_path).await {
                let detected = detect_from_content(&content, &services);
                all_detected.extend(detected);
            }
        }
    }

    // 扫描 .csproj 文件（.NET）
    if let Ok(mut entries) = fs::read_dir(repo_dir).await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.ends_with(".csproj") {
                if let Ok(content) = fs::read_to_string(entry.path()).await {
                    let detected = detect_from_content(&content, &services);
                    all_detected.extend(detected);
                }
            }
        }
    }

    // 扫描 docker-compose 文件（匹配 image 字段）
    all_detected.extend(detect_from_docker_compose(repo_dir, &services).await);

    // 扫描 Dockerfile（匹配 FROM 指令）
    all_detected.extend(detect_from_dockerfile(repo_dir, &services).await);

    // 扫描配置文件（连接字符串、环境变量前缀等）
    all_detected.extend(detect_from_config_files(repo_dir).await);

    // 扫描源代码 import/require 语句
    all_detected.extend(detect_from_source_code(repo_dir).await);

    // 去重
    all_detected.sort();
    all_detected.dedup();

    let service_details: HashMap<String, ExternalService> = all_detected
        .iter()
        .filter_map(|name| services.get(name).map(|s| (name.clone(), s.clone())))
        .collect();

    // 检测数据库初始化方式
    let database_init = detect_database_init(repo_dir).await;

    // 检测服务版本
    let service_versions = detect_service_versions(repo_dir).await;

    // 检测应用端口
    let app_port = detect_app_port(repo_dir).await;

    DependencyInfo {
        external_services: all_detected,
        service_details,
        database_init,
        service_versions,
        app_port,
    }
}
