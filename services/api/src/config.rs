use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub database_url: String,
    pub redis_url: String,
    pub jwt_secret: String,
    pub jwt_algorithm: String,
    pub jwt_expire_minutes: i64,
    pub refresh_token_days: i64,
    pub cors_origins: Vec<String>,
    pub agent_service_url: String,
    pub server_port: u16,
    pub app_name: String,
    pub debug: bool,
    pub llm_provider: String,
    pub llm_api_key: String,
    pub llm_model: String,
    pub llm_base_url: String,
}

impl AppConfig {
    pub fn from_env() -> Self {
        // 优先读取项目根目录 .env，回退到当前目录 .env
        let root_env = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().map(|p| p.join(".env"));
        if let Some(path) = root_env.as_ref().filter(|p| p.exists()) {
            dotenvy::from_path(path).ok();
        } else {
            dotenvy::dotenv().ok();
        }

        let cors_origins: Vec<String> = std::env::var("CORS_ORIGINS")
            .unwrap_or_else(|_| "http://localhost:5173,http://localhost:5174".to_string())
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();

        Self {
            database_url: std::env::var("DATABASE_URL")
                .unwrap_or_else(|_| "postgresql://user:password@localhost:15432/stackpilot".to_string()),
            redis_url: std::env::var("REDIS_URL")
                .unwrap_or_else(|_| "redis://localhost:16379".to_string()),
            jwt_secret: std::env::var("JWT_SECRET")
                .unwrap_or_else(|_| "your-secret-key-here".to_string()),
            jwt_algorithm: std::env::var("JWT_ALGORITHM")
                .unwrap_or_else(|_| "HS256".to_string()),
            jwt_expire_minutes: std::env::var("JWT_EXPIRE_MINUTES")
                .unwrap_or_else(|_| "120".to_string())
                .parse()
                .unwrap_or(120),
            refresh_token_days: std::env::var("REFRESH_TOKEN_DAYS")
                .unwrap_or_else(|_| "7".to_string())
                .parse()
                .unwrap_or(7),
            cors_origins,
            agent_service_url: std::env::var("AGENT_SERVICE_URL")
                .unwrap_or_else(|_| "http://localhost:9091".to_string()),
            server_port: std::env::var("SERVER_PORT")
                .unwrap_or_else(|_| "9099".to_string())
                .parse()
                .unwrap_or(9099),
            app_name: std::env::var("APP_NAME")
                .unwrap_or_else(|_| "StackPilot".to_string()),
            debug: std::env::var("DEBUG")
                .unwrap_or_else(|_| "true".to_string())
                .parse()
                .unwrap_or(true),
            llm_provider: std::env::var("LLM_PROVIDER")
                .unwrap_or_else(|_| "dashscope".to_string()),
            llm_api_key: std::env::var("LLM_API_KEY")
                .unwrap_or_default(),
            llm_model: std::env::var("LLM_MODEL")
                .unwrap_or_else(|_| "qwen-plus".to_string()),
            llm_base_url: std::env::var("LLM_BASE_URL")
                .unwrap_or_else(|_| "https://dashscope.aliyuncs.com/compatible-mode/v1".to_string()),
        }
    }
}
