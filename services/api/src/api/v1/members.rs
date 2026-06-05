use axum::Router;
use axum::routing::{get, post, put, delete};
use axum::extract::{State, Path};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;

use crate::services::project::member::MemberService;

#[derive(Clone)]
pub struct MembersState {
    pub member_service: Arc<MemberService>,
}

#[derive(Deserialize)]
pub struct AddMemberRequest {
    pub user_id: String,
    pub role: Option<String>,
}

#[derive(Deserialize)]
pub struct UpdateMemberRequest {
    pub role: String,
}

pub async fn list_members(
    State(state): State<MembersState>,
    Path(project_id): Path<String>,
) -> Json<Value> {
    match state.member_service.list_members(&project_id).await {
        Ok(members) => {
            let total = members.len();
            Json(json!({
                "code": 200,
                "data": {
                    "items": members,
                    "total": total
                }
            }))
        }
        Err(e) => Json(json!({
            "code": 500,
            "message": e.to_string()
        })),
    }
}

pub async fn add_member(
    State(state): State<MembersState>,
    Path(project_id): Path<String>,
    Json(req): Json<AddMemberRequest>,
) -> Json<Value> {
    let role = req.role.as_deref().unwrap_or("member");
    match state.member_service.add_member(&project_id, &req.user_id, role).await {
        Ok(member) => Json(json!({
            "code": 200,
            "data": member
        })),
        Err(e) => Json(json!({
            "code": 400,
            "message": e.to_string()
        })),
    }
}

pub async fn update_member(
    State(state): State<MembersState>,
    Path((project_id, user_id)): Path<(String, String)>,
    Json(req): Json<UpdateMemberRequest>,
) -> Json<Value> {
    match state.member_service.update_role(&project_id, &user_id, &req.role).await {
        Ok(member) => Json(json!({
            "code": 200,
            "data": member
        })),
        Err(e) => Json(json!({
            "code": 400,
            "message": e.to_string()
        })),
    }
}

pub async fn remove_member(
    State(state): State<MembersState>,
    Path((project_id, user_id)): Path<(String, String)>,
) -> Json<Value> {
    match state.member_service.remove_member(&project_id, &user_id).await {
        Ok(()) => Json(json!({
            "code": 200,
            "message": "成员已移除"
        })),
        Err(e) => Json(json!({
            "code": 400,
            "message": e.to_string()
        })),
    }
}

pub fn routes(state: MembersState) -> Router {
    Router::new()
        .route("/projects/:project_id/members", get(list_members).post(add_member))
        .route("/projects/:project_id/members/:user_id", put(update_member).delete(remove_member))
        .with_state(state)
}
