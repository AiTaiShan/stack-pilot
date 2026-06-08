use axum::Router;
use axum::http::HeaderMap;
use axum::routing::{get, post, delete};
use axum::extract::{Path, State};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use uuid::Uuid;
use std::sync::Arc;
use sea_orm::{EntityTrait, ColumnTrait, QueryFilter, QueryOrder, ActiveModelTrait, Set};

use crate::error::AppError;
use crate::services::deployer::manager::DeploymentStateManager;
use crate::models::deployment::{self, Entity as DeploymentEntity, DeploymentStatus};
use crate::models::deployment_log::{self, Entity as DeploymentLogEntity};
use crate::utils::jwt::verify_token;

#[derive(Clone)]
pub struct DeploymentsState {
    pub manager: Arc<DeploymentStateManager>,
    pub db: sea_orm::DatabaseConnection,
    pub jwt_secret: String,
}

#[derive(Deserialize)]
pub struct CreateDeploymentRequest {
    pub project_id: String,
    pub git_url: Option<String>,
    pub branch: Option<String>,
    pub platform: Option<String>,
    #[allow(dead_code)]
    pub config: Option<Value>,
}

#[derive(Deserialize)]
pub struct UpdateComposeRequest {
    pub content: String,
}

#[derive(Deserialize)]
pub struct ConfirmEnvVarsRequest {
    pub env_vars: std::collections::HashMap<String, String>,
}

fn extract_user_id(headers: &HeaderMap, jwt_secret: &str) -> Result<String, AppError> {
    let auth_header = headers
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .ok_or_else(|| AppError::AuthError("缺少 Authorization 头".to_string()))?;
    let token = auth_header
        .strip_prefix("Bearer ")
        .ok_or_else(|| AppError::AuthError("无效的 Authorization 格式".to_string()))?;
    let claims = verify_token(token, jwt_secret)
        .map_err(|_| AppError::AuthError("无效的 Token".to_string()))?;
    Ok(claims.sub)
}

// GET /deployments — 列表
pub async fn list_deployments(
    State(state): State<DeploymentsState>,
    headers: HeaderMap,
) -> Json<Value> {
    let _user_id = match extract_user_id(&headers, &state.jwt_secret) {
        Ok(id) => id,
        Err(e) => return Json(json!({"code": 401, "message": e.to_string()})),
    };

    match DeploymentEntity::find()
        .order_by_desc(deployment::Column::CreatedAt)
        .all(&state.db)
        .await
    {
        Ok(items) => {
            let data: Vec<Value> = items.iter().map(|d| {
                json!({
                    "id": d.id.to_string(),
                    "project_id": d.project_id.to_string(),
                    "status": serde_json::to_value(&d.status).unwrap_or(json!("pending")),
                    "current_step": d.current_step.as_ref().map(|s| serde_json::to_value(s).unwrap_or(json!(null))),
                    "progress": d.progress,
                    "platform": d.platform,
                    "branch": d.branch,
                    "error_message": d.error_message,
                    "created_at": d.created_at.unwrap_or_default().format("%Y-%m-%dT%H:%M:%S%.fZ").to_string(),
                    "updated_at": d.updated_at.unwrap_or_default().format("%Y-%m-%dT%H:%M:%S%.fZ").to_string(),
                })
            }).collect();
            Json(json!({
                "code": 200,
                "data": { "items": data, "total": data.len() }
            }))
        }
        Err(e) => Json(json!({"code": 500, "message": format!("获取部署列表失败: {}", e)})),
    }
}

// POST /deployments — 创建
pub async fn create_deployment(
    State(state): State<DeploymentsState>,
    headers: HeaderMap,
    Json(payload): Json<CreateDeploymentRequest>,
) -> Json<Value> {
    let user_id = match extract_user_id(&headers, &state.jwt_secret) {
        Ok(id) => id,
        Err(e) => return Json(json!({"code": 401, "message": e.to_string()})),
    };

    let project_id = match Uuid::parse_str(&payload.project_id) {
        Ok(id) => id,
        Err(_) => return Json(json!({"code": 400, "message": "无效的 project_id"})),
    };

    let deployment_id = Uuid::new_v4();
    let branch = payload.branch.unwrap_or_else(|| "main".to_string());
    let platform = payload.platform.unwrap_or_else(|| "docker".to_string());

    // 在数据库中创建部署记录
    let user_uuid = Uuid::parse_str(&user_id).unwrap_or_default();
    let new_dep = deployment::ActiveModel {
        id: Set(deployment_id),
        project_id: Set(project_id),
        user_id: Set(Some(user_uuid)),
        status: Set(DeploymentStatus::Pending),
        current_step: Set(None),
        progress: Set(0),
        platform: Set(platform.clone()),
        config: Set(payload.config),
        git_url: Set(payload.git_url.clone()),
        branch: Set(Some(branch.clone())),
        image_tag: Set(None),
        deploy_url: Set(None),
        commit_hash: Set(None),
        commit_message: Set(None),
        error_message: Set(None),
        error_details: Set(None),
        can_resume: Set(Some(0)),
        resume_data: Set(None),
        duration: Set(None),
        started_at: Set(None),
        completed_at: Set(None),
        updated_at: Set(Some(chrono::Utc::now().naive_utc())),
        created_at: Set(Some(chrono::Utc::now().naive_utc())),
    };

    match new_dep.insert(&state.db).await {
        Ok(dep) => {
            // 启动异步部署任务
            let git_url = dep.git_url.clone().unwrap_or_default();
            if let Err(e) = state.manager.create_deployment(deployment_id, git_url, branch.clone(), platform.clone()).await {
                return Json(json!({"code": 500, "message": format!("启动部署任务失败: {}", e)}));
            }
            Json(json!({
                "code": 200,
                "message": "部署已创建",
                "data": {
                    "id": dep.id.to_string(),
                    "status": "running",
                    "branch": branch,
                    "platform": platform
                }
            }))
        }
        Err(e) => Json(json!({"code": 500, "message": format!("创建部署记录失败: {}", e)})),
    }
}

// GET /deployments/{id} — 详情
pub async fn get_deployment(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match DeploymentEntity::find_by_id(uuid).one(&state.db).await {
        Ok(Some(dep)) => Json(json!({
            "code": 200,
            "data": {
                "id": dep.id.to_string(),
                "project_id": dep.project_id.to_string(),
                "user_id": dep.user_id.map(|u| u.to_string()),
                "status": serde_json::to_value(&dep.status).unwrap_or(json!("pending")),
                "current_step": dep.current_step.as_ref().map(|s| serde_json::to_value(s).unwrap_or(json!(null))),
                "progress": dep.progress,
                "platform": dep.platform,
                "git_url": dep.git_url,
                "branch": dep.branch,
                "image_tag": dep.image_tag,
                "deploy_url": dep.deploy_url,
                "commit_hash": dep.commit_hash,
                "commit_message": dep.commit_message,
                "error_message": dep.error_message,
                "can_resume": dep.can_resume,
                "duration": dep.duration,
                "started_at": dep.started_at.map(|t| t.format("%Y-%m-%dT%H:%M:%S%.fZ").to_string()),
                "completed_at": dep.completed_at.map(|t| t.format("%Y-%m-%dT%H:%M:%S%.fZ").to_string()),
                "created_at": dep.created_at.unwrap_or_default().format("%Y-%m-%dT%H:%M:%S%.fZ").to_string(),
                "updated_at": dep.updated_at.unwrap_or_default().format("%Y-%m-%dT%H:%M:%S%.fZ").to_string(),
            }
        })),
        Ok(None) => Json(json!({"code": 404, "message": "部署不存在"})),
        Err(e) => Json(json!({"code": 500, "message": format!("获取部署详情失败: {}", e)})),
    }
}

// GET /deployments/{id}/status — 状态
pub async fn get_deployment_status(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match DeploymentEntity::find_by_id(uuid).one(&state.db).await {
        Ok(Some(dep)) => Json(json!({
            "code": 200,
            "data": {
                "id": dep.id.to_string(),
                "status": serde_json::to_value(&dep.status).unwrap_or(json!("pending")),
                "current_step": dep.current_step.as_ref().map(|s| serde_json::to_value(s).unwrap_or(json!(null))),
                "progress": dep.progress,
                "error_message": dep.error_message,
                "is_active": state.manager.is_active(&uuid).await,
            }
        })),
        Ok(None) => Json(json!({"code": 404, "message": "部署不存在"})),
        Err(e) => Json(json!({"code": 500, "message": format!("获取部署状态失败: {}", e)})),
    }
}

// GET /deployments/{id}/logs — 日志
pub async fn get_deployment_logs(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match DeploymentLogEntity::find()
        .filter(deployment_log::Column::DeploymentId.eq(uuid))
        .order_by_asc(deployment_log::Column::CreatedAt)
        .all(&state.db)
        .await
    {
        Ok(logs) => {
            let data: Vec<Value> = logs.iter().map(|l| {
                json!({
                    "id": l.id.to_string(),
                    "level": l.level,
                    "message": l.message,
                    "created_at": l.created_at.unwrap_or_default().format("%Y-%m-%dT%H:%M:%S%.fZ").to_string(),
                })
            }).collect();
            Json(json!({
                "code": 200,
                "data": { "items": data, "total": data.len() }
            }))
        }
        Err(e) => Json(json!({"code": 500, "message": format!("获取部署日志失败: {}", e)})),
    }
}

// POST /deployments/{id}/cancel — 取消
pub async fn cancel_deployment(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match state.manager.cancel_deployment(&uuid).await {
        Ok(()) => {
            // 更新数据库状态
            if let Ok(Some(dep)) = DeploymentEntity::find_by_id(uuid).one(&state.db).await {
                let mut am: deployment::ActiveModel = dep.into();
                am.status = Set(DeploymentStatus::Cancelled);
                am.completed_at = Set(Some(chrono::Utc::now().naive_utc()));
                am.updated_at = Set(Some(chrono::Utc::now().naive_utc()));
                am.update(&state.db).await.ok();
            }
            Json(json!({"code": 200, "message": "部署已取消", "data": { "id": id } }))
        }
        Err(e) => Json(json!({"code": 404, "message": format!("取消部署失败: {}", e)})),
    }
}

// POST /deployments/{id}/pause — 暂停
pub async fn pause_deployment(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match state.manager.pause_deployment(&uuid).await {
        Ok(()) => Json(json!({"code": 200, "message": "部署已暂停", "data": { "id": id } })),
        Err(e) => Json(json!({"code": 404, "message": format!("暂停部署失败: {}", e)})),
    }
}

// POST /deployments/{id}/resume — 恢复
pub async fn resume_deployment(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match state.manager.resume_deployment(&uuid).await {
        Ok(()) => Json(json!({"code": 200, "message": "部署已恢复", "data": { "id": id } })),
        Err(e) => Json(json!({"code": 404, "message": format!("恢复部署失败: {}", e)})),
    }
}

// POST /deployments/{id}/rollback — 回滚
pub async fn rollback_deployment(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    // 检查部署是否存在
    match DeploymentEntity::find_by_id(uuid).one(&state.db).await {
        Ok(Some(dep)) => {
            let mut am: deployment::ActiveModel = dep.into();
            am.status = Set(DeploymentStatus::RollingBack);
            am.updated_at = Set(Some(chrono::Utc::now().naive_utc()));
            match am.update(&state.db).await {
                Ok(_) => Json(json!({"code": 200, "message": "回滚已启动", "data": { "id": id } })),
                Err(e) => Json(json!({"code": 500, "message": format!("更新回滚状态失败: {}", e)})),
            }
        }
        Ok(None) => Json(json!({"code": 404, "message": "部署不存在"})),
        Err(e) => Json(json!({"code": 500, "message": format!("查询部署失败: {}", e)})),
    }
}

// GET /deployments/{id}/compose-file — 获取 compose
pub async fn get_compose_file(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match DeploymentEntity::find_by_id(uuid).one(&state.db).await {
        Ok(Some(dep)) => {
            let config = dep.config.unwrap_or(serde_json::Value::Null);
            let compose_content = config.get("compose_content")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            Json(json!({
                "code": 200,
                "data": {
                    "deployment_id": id,
                    "content": compose_content,
                }
            }))
        }
        Ok(None) => Json(json!({"code": 404, "message": "部署不存在"})),
        Err(e) => Json(json!({"code": 500, "message": format!("获取 compose 文件失败: {}", e)})),
    }
}

// PUT /deployments/{id}/compose-file — 更新 compose
pub async fn update_compose_file(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
    Json(payload): Json<UpdateComposeRequest>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match DeploymentEntity::find_by_id(uuid).one(&state.db).await {
        Ok(Some(dep)) => {
            let mut config = dep.config.clone().unwrap_or(serde_json::Value::Object(serde_json::Map::new()));
            if let serde_json::Value::Object(ref mut map) = config {
                map.insert("compose_content".to_string(), serde_json::Value::String(payload.content));
            }
            let mut am: deployment::ActiveModel = dep.into();
            am.config = Set(Some(config));
            am.updated_at = Set(Some(chrono::Utc::now().naive_utc()));
            match am.update(&state.db).await {
                Ok(_) => Json(json!({"code": 200, "message": "compose 文件已更新", "data": { "id": id } })),
                Err(e) => Json(json!({"code": 500, "message": format!("更新 compose 文件失败: {}", e)})),
            }
        }
        Ok(None) => Json(json!({"code": 404, "message": "部署不存在"})),
        Err(e) => Json(json!({"code": 500, "message": format!("查询部署失败: {}", e)})),
    }
}

// POST /deployments/{id}/confirm-env-vars — 确认环境变量
pub async fn confirm_env_vars(
    State(state): State<DeploymentsState>,
    Path(id): Path<String>,
    Json(payload): Json<ConfirmEnvVarsRequest>,
) -> Json<Value> {
    let uuid = match Uuid::parse_str(&id) {
        Ok(u) => u,
        Err(_) => return Json(json!({"code": 400, "message": "无效的部署 ID"})),
    };

    match DeploymentEntity::find_by_id(uuid).one(&state.db).await {
        Ok(Some(dep)) => {
            let mut config = dep.config.clone().unwrap_or(serde_json::Value::Object(serde_json::Map::new()));
            if let serde_json::Value::Object(ref mut map) = config {
                let env_json = serde_json::to_value(&payload.env_vars).unwrap_or(serde_json::Value::Null);
                map.insert("env_vars".to_string(), env_json);
            }
            let mut am: deployment::ActiveModel = dep.into();
            am.config = Set(Some(config));
            am.status = Set(DeploymentStatus::Running);
            am.updated_at = Set(Some(chrono::Utc::now().naive_utc()));
            match am.update(&state.db).await {
                Ok(_) => Json(json!({"code": 200, "message": "环境变量已确认", "data": { "id": id } })),
                Err(e) => Json(json!({"code": 500, "message": format!("确认环境变量失败: {}", e)})),
            }
        }
        Ok(None) => Json(json!({"code": 404, "message": "部署不存在"})),
        Err(e) => Json(json!({"code": 500, "message": format!("查询部署失败: {}", e)})),
    }
}

// DELETE /deployments/all — 删除所有
pub async fn delete_all_deployments(
    State(state): State<DeploymentsState>,
) -> Json<Value> {
    // 先取消所有活跃部署
    let active_ids: Vec<Uuid> = {
        let active = state.manager.active_read().await;
        active.keys().cloned().collect()
    };
    for id in &active_ids {
        state.manager.cancel_deployment(id).await.ok();
    }

    // 删除所有数据库记录
    match DeploymentEntity::delete_many().exec(&state.db).await {
        Ok(result) => Json(json!({
            "code": 200,
            "message": "所有部署已删除",
            "data": { "deleted_count": result.rows_affected }
        })),
        Err(e) => Json(json!({"code": 500, "message": format!("删除部署失败: {}", e)})),
    }
}

pub fn routes() -> Router<DeploymentsState> {
    Router::new()
        .route("/deployments", get(list_deployments).post(create_deployment))
        .route("/deployments/all", delete(delete_all_deployments))
        .route("/deployments/:id", get(get_deployment))
        .route("/deployments/:id/status", get(get_deployment_status))
        .route("/deployments/:id/logs", get(get_deployment_logs))
        .route("/deployments/:id/cancel", post(cancel_deployment))
        .route("/deployments/:id/pause", post(pause_deployment))
        .route("/deployments/:id/resume", post(resume_deployment))
        .route("/deployments/:id/rollback", post(rollback_deployment))
        .route("/deployments/:id/compose-file", get(get_compose_file).put(update_compose_file))
        .route("/deployments/:id/confirm-env-vars", post(confirm_env_vars))
}
