use stackpilot_backend::config::AppConfig;

#[test]
fn test_config_default_values() {
    // 清理所有可能被 .env 加载的环境变量
    std::env::remove_var("DATABASE_URL");
    std::env::remove_var("JWT_SECRET");
    std::env::remove_var("SERVER_PORT");
    std::env::remove_var("AGENT_SERVICE_URL");
    std::env::remove_var("JWT_ALGORITHM");
    std::env::remove_var("JWT_EXPIRE_MINUTES");
    std::env::remove_var("REFRESH_TOKEN_DAYS");
    std::env::remove_var("CORS_ORIGINS");
    std::env::remove_var("APP_NAME");
    std::env::remove_var("DEBUG");

    let config = AppConfig::from_env();

    assert_eq!(config.server_port, 9099);
    assert_eq!(config.agent_service_url, "http://localhost:8066");
    assert_eq!(config.jwt_secret, "your-secret-key-here");
    assert_eq!(config.jwt_algorithm, "HS256");
    assert_eq!(config.jwt_expire_minutes, 120);
    assert_eq!(config.refresh_token_days, 7);
}

#[test]
fn test_config_custom_values() {
    std::env::set_var("DATABASE_URL", "postgresql://test:test@localhost/test");
    std::env::set_var("JWT_SECRET", "test-secret");
    std::env::set_var("SERVER_PORT", "8080");
    std::env::set_var("AGENT_SERVICE_URL", "http://custom:8066");

    let config = AppConfig::from_env();

    assert_eq!(config.database_url, "postgresql://test:test@localhost/test");
    assert_eq!(config.jwt_secret, "test-secret");
    assert_eq!(config.server_port, 8080);
    assert_eq!(config.agent_service_url, "http://custom:8066");

    // 清理
    std::env::remove_var("DATABASE_URL");
    std::env::remove_var("JWT_SECRET");
    std::env::remove_var("SERVER_PORT");
    std::env::remove_var("AGENT_SERVICE_URL");
}

#[test]
fn test_config_invalid_port_fallback() {
    std::env::set_var("SERVER_PORT", "invalid");

    let config = AppConfig::from_env();

    // 解析失败时应使用默认值 9099
    assert_eq!(config.server_port, 9099);

    std::env::remove_var("SERVER_PORT");
}
