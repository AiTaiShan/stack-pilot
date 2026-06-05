use axum::Router;
use axum::routing::get;
use axum::extract::{State, Path};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;

use crate::services::config::ConfigService;

#[derive(Clone)]
pub struct ConfigState {
    pub config_service: Arc<ConfigService>,
}

#[derive(Deserialize)]
pub struct CreateConfigRequest {
    pub key: String,
    pub value: String,
    pub value_type: Option<String>,
    pub description: Option<String>,
    pub is_sensitive: Option<bool>,
}

#[derive(Deserialize)]
pub struct UpdateConfigRequest {
    pub value: Option<String>,
    pub value_type: Option<String>,
    pub description: Option<String>,
    pub is_sensitive: Option<bool>,
}

pub async fn list_configs(State(state): State<ConfigState>) -> Json<Value> {
    match state.config_service.list().await {
        Ok(items) => { let total = items.len(); Json(json!({"code": 200, "data": {"items": items, "total": total}})) }
        Err(e) => Json(json!({"code": 500, "message": e.to_string()})),
    }
}

pub async fn get_config(State(state): State<ConfigState>, Path(key): Path<String>) -> Json<Value> {
    match state.config_service.get(&key).await {
        Ok(Some(item)) => Json(json!({"code": 200, "data": item})),
        Ok(None) => Json(json!({"code": 404, "message": "配置项不存在"})),
        Err(e) => Json(json!({"code": 500, "message": e.to_string()})),
    }
}

pub async fn create_config(State(state): State<ConfigState>, Json(req): Json<CreateConfigRequest>) -> Json<Value> {
    match state.config_service.create(
        &req.key, &req.value, req.value_type.as_deref(),
        req.description.as_deref(), req.is_sensitive,
    ).await {
        Ok(item) => Json(json!({"code": 200, "data": item})),
        Err(e) => Json(json!({"code": 400, "message": e.to_string()})),
    }
}

pub async fn update_config(State(state): State<ConfigState>, Path(key): Path<String>, Json(req): Json<UpdateConfigRequest>) -> Json<Value> {
    match state.config_service.update(
        &key, req.value.as_deref(), req.value_type.as_deref(),
        req.description.as_deref(), req.is_sensitive,
    ).await {
        Ok(item) => Json(json!({"code": 200, "data": item})),
        Err(e) => Json(json!({"code": 400, "message": e.to_string()})),
    }
}

pub async fn delete_config(State(state): State<ConfigState>, Path(key): Path<String>) -> Json<Value> {
    match state.config_service.delete(&key).await {
        Ok(()) => Json(json!({"code": 200, "message": "删除成功"})),
        Err(e) => Json(json!({"code": 400, "message": e.to_string()})),
    }
}

pub fn routes(state: ConfigState) -> Router {
    Router::new()
        .route("/configs", get(list_configs).post(create_config))
        .route("/configs/{key}", get(get_config).put(update_config).delete(delete_config))
        .with_state(state)
}
