use tokio::sync::watch;
use uuid::Uuid;
use sea_orm::{EntityTrait, ActiveModelTrait, Set};

use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity, ActiveModel as DeploymentActiveModel, DeploymentStatus, DeploymentStep};

const STEPS: [&str; 8] = ["clone", "generate_review", "build", "env_review", "push", "deploy", "configure", "verify"];
const STEP_PROGRESS: [i32; 8] = [10, 35, 55, 65, 75, 85, 93, 100];

fn parse_step(s: &str) -> Option<DeploymentStep> {
    match s {
        "clone" => Some(DeploymentStep::Clone),
        "generate_review" => Some(DeploymentStep::GenerateReview),
        "build" => Some(DeploymentStep::Build),
        "env_review" => Some(DeploymentStep::EnvReview),
        "push" => Some(DeploymentStep::Push),
        "deploy" => Some(DeploymentStep::Deploy),
        "configure" => Some(DeploymentStep::Configure),
        "verify" => Some(DeploymentStep::Verify),
        _ => None,
    }
}

pub async fn check_signals(cancel_rx: &watch::Receiver<bool>, pause_rx: &watch::Receiver<bool>) -> Result<(), AppError> {
    if *cancel_rx.borrow() { return Err(AppError::DeploymentCancelled); }
    while *pause_rx.borrow() {
        let mut rx = pause_rx.clone();
        rx.changed().await.unwrap();
    }
    if *cancel_rx.borrow() { return Err(AppError::DeploymentCancelled); }
    Ok(())
}

pub async fn execute_deployment(
    db: sea_orm::DatabaseConnection, deployment_id: Uuid,
    git_url: &str, branch: &str, platform: &str,
    cancel_rx: watch::Receiver<bool>, pause_rx: watch::Receiver<bool>,
) -> Result<(), AppError> {
    for (i, step) in STEPS.iter().enumerate() {
        check_signals(&cancel_rx, &pause_rx).await?;
        update_deployment_progress(&db, deployment_id, step, STEP_PROGRESS[i]).await?;
        write_deployment_log(&db, deployment_id, "info", &format!("开始步骤: {}", step)).await?;

        let result = match *step {
            "clone" => crate::services::deployer::steps::clone::execute(db.clone(), deployment_id, git_url, branch).await,
            "generate_review" => crate::services::deployer::steps::review::execute(db.clone(), deployment_id).await,
            "build" => crate::services::deployer::steps::build::execute(db.clone(), deployment_id).await,
            "env_review" => crate::services::deployer::steps::env_review::execute(db.clone(), deployment_id).await,
            "push" => crate::services::deployer::steps::push::execute(db.clone(), deployment_id).await,
            "deploy" => crate::services::deployer::steps::deploy::execute(db.clone(), deployment_id, platform).await,
            "configure" => crate::services::deployer::steps::configure::execute(db.clone(), deployment_id).await,
            "verify" => crate::services::deployer::steps::verify::execute(db.clone(), deployment_id).await,
            _ => Err(AppError::InternalError(format!("未知步骤: {}", step))),
        };

        match result {
            Ok(()) => { write_deployment_log_with_step(&db, deployment_id, "info", &format!("步骤完成: {}", step), step).await?; }
            Err(e) => {
                write_deployment_log_with_step(&db, deployment_id, "error", &format!("步骤失败: {} - {}", step, e), step).await?;
                fail_deployment(&db, deployment_id, &e.to_string()).await;
                return Err(e);
            }
        }
    }
    success_deployment(&db, deployment_id).await;
    Ok(())
}

async fn fail_deployment(db: &sea_orm::DatabaseConnection, id: Uuid, msg: &str) {
    if let Some(dep) = DeploymentEntity::find_by_id(id).one(db).await.ok().flatten() {
        let mut am: DeploymentActiveModel = dep.into();
        am.status = Set(DeploymentStatus::Failed);
        am.error_message = Set(Some(msg.to_string()));
        am.completed_at = Set(Some(chrono::Utc::now().naive_utc()));
        am.update(db).await.ok();
    }
}

async fn success_deployment(db: &sea_orm::DatabaseConnection, id: Uuid) {
    if let Some(dep) = DeploymentEntity::find_by_id(id).one(db).await.ok().flatten() {
        let mut am: DeploymentActiveModel = dep.into();
        am.status = Set(DeploymentStatus::Success);
        am.progress = Set(100);
        am.completed_at = Set(Some(chrono::Utc::now().naive_utc()));
        am.update(db).await.ok();
    }
}

pub async fn update_deployment_progress(db: &sea_orm::DatabaseConnection, id: Uuid, step: &str, progress: i32) -> Result<(), AppError> {
    let dep = DeploymentEntity::find_by_id(id).one(db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;
    let mut am: DeploymentActiveModel = dep.into();
    am.current_step = Set(parse_step(step));
    am.progress = Set(progress);
    am.update(db).await.map_err(|e| AppError::DatabaseError(e.to_string()))?;
    Ok(())
}

pub async fn write_deployment_log(db: &sea_orm::DatabaseConnection, deployment_id: Uuid, level: &str, message: &str) -> Result<(), AppError> {
    write_deployment_log_with_step(db, deployment_id, level, message, "").await
}

pub async fn write_deployment_log_with_step(db: &sea_orm::DatabaseConnection, deployment_id: Uuid, level: &str, message: &str, step: &str) -> Result<(), AppError> {
    use crate::models::deployment_log::ActiveModel as LogActiveModel;
    let step_value = if step.is_empty() { None } else { Some(step.to_string()) };
    LogActiveModel {
        id: Set(Uuid::new_v4()),
        deployment_id: Set(deployment_id),
        level: Set(level.to_string()),
        message: Set(message.to_string()),
        details: Set(None),
        step: Set(step_value),
        created_at: Set(Some(chrono::Utc::now().naive_utc())),
    }.insert(db).await.map_err(|e| AppError::DatabaseError(e.to_string()))?;
    Ok(())
}
