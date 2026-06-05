use axum::Router;
use axum::routing::get;
use axum::Json;
use serde_json::{json, Value};

pub async fn health_check() -> Json<Value> {
    Json(json!({
        "status": "healthy",
        "version": "0.1.0"
    }))
}

pub fn routes() -> Router {
    Router::new()
        .route("/health", get(health_check))
}
