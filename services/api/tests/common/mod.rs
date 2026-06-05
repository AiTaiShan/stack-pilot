use sea_orm::{Database, DatabaseConnection};

pub async fn setup_db() -> DatabaseConnection {
    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgresql://user:password@localhost:15432/stackpilot_test".to_string());
    Database::connect(&db_url).await.expect("无法连接测试数据库")
}

pub fn auth_header(token: &str) -> reqwest::header::HeaderMap {
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert("Authorization", format!("Bearer {}", token).parse().unwrap());
    headers
}
