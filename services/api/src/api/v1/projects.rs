use axum::Router;
use axum::routing::{get, post, put, delete};
use axum::extract::{Path, State};
use axum::Json;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::Arc;

use crate::error::AppError;
use crate::services::project::ProjectService;
use crate::services::scanner::git::branch::list_remote_branches;

#[derive(Clone)]
pub struct ProjectsState {
    pub project_service: Arc<ProjectService>,
}

#[derive(Deserialize)]
pub struct CreateProjectRequest {
    pub name: String,
    pub git_url: String,
    pub description: Option<String>,
}

#[derive(Deserialize)]
pub struct UpdateProjectRequest {
    pub name: Option<String>,
    pub description: Option<String>,
}

fn validate_git_url(url: &str) -> Result<(), AppError> {
    if url.starts_with("http://") || url.starts_with("https://") || url.starts_with("git@") {
        Ok(())
    } else {
        Err(AppError::ValidationError("无效的 Git URL".to_string()))
    }
}

pub async fn list_projects(
    State(state): State<ProjectsState>,
) -> Json<Value> {
    match state.project_service.list(None).await {
        Ok(projects) => Json(json!({
            "code": 200,
            "message": "success",
            "data": {
                "items": projects,
                "total": projects.len()
            }
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("获取项目列表失败: {}", e)
        })),
    }
}

pub async fn get_project(
    State(state): State<ProjectsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    match state.project_service.get(&id).await {
        Ok(Some(project)) => Json(json!({
            "code": 200,
            "message": "success",
            "data": project
        })),
        Ok(None) => Json(json!({
            "code": 404,
            "message": "项目不存在"
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("获取项目失败: {}", e)
        })),
    }
}

pub async fn create_project(
    State(state): State<ProjectsState>,
    Json(payload): Json<CreateProjectRequest>,
) -> Json<Value> {
    if let Err(e) = validate_git_url(&payload.git_url) {
        return Json(json!({"code": 400, "message": e.to_string()}));
    }

    // TODO: 从 JWT 获取 user_id
    let owner_id = uuid::Uuid::new_v4();

    match state.project_service.create(
        &payload.name,
        &payload.git_url,
        owner_id,
        payload.description.as_deref(),
    ).await {
        Ok(project) => Json(json!({
            "code": 200,
            "message": "项目创建成功",
            "data": project
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("创建项目失败: {}", e)
        })),
    }
}

pub async fn update_project(
    State(state): State<ProjectsState>,
    Path(id): Path<String>,
    Json(payload): Json<UpdateProjectRequest>,
) -> Json<Value> {
    match state.project_service.update(
        &id,
        payload.name.as_deref(),
        payload.description.as_deref(),
    ).await {
        Ok(project) => Json(json!({
            "code": 200,
            "message": "项目更新成功",
            "data": project
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("更新项目失败: {}", e)
        })),
    }
}

pub async fn delete_project(
    State(state): State<ProjectsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    match state.project_service.delete(&id).await {
        Ok(_) => Json(json!({
            "code": 200,
            "message": "项目删除成功"
        })),
        Err(e) => Json(json!({
            "code": 500,
            "message": format!("删除项目失败: {}", e)
        })),
    }
}

pub async fn get_project_branches(
    State(state): State<ProjectsState>,
    Path(id): Path<String>,
) -> Json<Value> {
    match state.project_service.get(&id).await {
        Ok(Some(project)) => {
            match list_remote_branches(&project.git_url).await {
                Ok(branches) => Json(json!({"code": 200, "data": branches})),
                Err(e) => Json(json!({"code": 500, "message": e.to_string()})),
            }
        }
        Ok(None) => Json(json!({"code": 404, "message": "项目不存在"})),
        Err(e) => Json(json!({"code": 500, "message": e.to_string()})),
    }
}

pub fn routes(state: ProjectsState) -> Router {
    Router::new()
        .route("/projects", get(list_projects).post(create_project))
        .route("/projects/:id", get(get_project).put(update_project).delete(delete_project))
        .route("/projects/:id/branches", get(get_project_branches))
        .with_state(state)
}
