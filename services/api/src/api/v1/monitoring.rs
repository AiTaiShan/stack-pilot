use axum::Router;
use axum::routing::get;
use axum::extract::State;
use axum::Json;
use serde_json::{json, Value};
use std::sync::Arc;

use crate::services::monitoring::MonitoringService;

#[derive(Clone)]
pub struct MonitoringState {
    pub monitoring_service: Arc<MonitoringService>,
}

pub async fn get_system_status(
    State(state): State<MonitoringState>,
) -> Json<Value> {
    match state.monitoring_service.get_system_status().await {
        Ok(status) => Json(json!({
            "code": 200,
            "message": "success",
            "data": status
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("获取系统状态失败: {}", e)
        })),
    }
}

pub async fn get_deployment_stats(
    State(state): State<MonitoringState>,
) -> Json<Value> {
    match state.monitoring_service.get_deployment_stats().await {
        Ok(stats) => Json(json!({
            "code": 200,
            "message": "success",
            "data": stats
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("获取部署统计失败: {}", e)
        })),
    }
}

pub fn routes(state: MonitoringState) -> Router {
    Router::new()
        .route("/monitoring/status", get(get_system_status))
        .route("/monitoring/stats", get(get_deployment_stats))
        .with_state(state)
}
