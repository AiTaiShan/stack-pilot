use sea_orm::{ConnectOptions, Database, DatabaseConnection};
use tracing::info;

use crate::config::AppConfig;
use crate::error::AppError;

pub async fn get_db(config: &AppConfig) -> Result<DatabaseConnection, AppError> {
    info!("连接数据库...");

    let mut opt = ConnectOptions::new(&config.database_url);
    opt.max_connections(100)
        .min_connections(5)
        .connect_timeout(std::time::Duration::from_secs(8))
        .acquire_timeout(std::time::Duration::from_secs(8))
        .idle_timeout(std::time::Duration::from_secs(8));

    Database::connect(opt)
        .await
        .map_err(|e| AppError::DatabaseError(e.to_string()))
}
