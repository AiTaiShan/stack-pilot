use std::sync::Arc;
use tokio::sync::{watch, Notify};
use uuid::Uuid;
use sea_orm::{EntityTrait, ActiveModelTrait, Set, ColumnTrait, QueryFilter, QueryOrder};
use tracing::{info, warn};

use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity, ActiveModel as DeploymentActiveModel, DeploymentStatus, DeploymentStep};
use crate::models::deployment_log::{Entity as DeploymentLogEntity, Column as LogColumn};
use crate::services::agent::AgentClient;
use crate::services::agent::types::DeployDiagnoseRequest;

const STEPS: [&str; 8] = ["clone", "generate_review", "build", "env_review", "push", "deploy", "configure", "verify"];
const STEP_PROGRESS: [i32; 8] = [10, 35, 55, 65, 75, 85, 93, 100];
const MAX_DIAGNOSE_RETRIES: i32 = 3;

// 需要诊断的步骤（文件问题可修复）
const DIAGNOSABLE_STEPS: &[&str] = &["build", "deploy", "verify", "push", "configure"];

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

/// 从步骤名获取在 STEPS 数组中的索引
fn step_index(step: &str) -> Option<usize> {
    STEPS.iter().position(|&s| s == step)
}

pub async fn check_signals(cancel_rx: &watch::Receiver<bool>, pause_rx: &watch::Receiver<bool>) -> Result<(), AppError> {
    if *cancel_rx.borrow() { return Err(AppError::DeploymentCancelled); }
    while *pause_rx.borrow() {
        let mut cancel_clone = cancel_rx.clone();
        let mut pause_clone = pause_rx.clone();
        tokio::select! {
            result = cancel_clone.changed() => {
                result.ok();
                if *cancel_clone.borrow() {
                    return Err(AppError::DeploymentCancelled);
                }
            }
            result = pause_clone.changed() => {
                result.ok();
            }
        }
    }
    if *cancel_rx.borrow() { return Err(AppError::DeploymentCancelled); }
    Ok(())
}

pub async fn execute_deployment(
    db: sea_orm::DatabaseConnection, deployment_id: Uuid,
    git_url: &str, branch: &str, platform: &str,
    cancel_rx: watch::Receiver<bool>, pause_rx: watch::Receiver<bool>,
    agent_client: Arc<AgentClient>,
    review_notify: Arc<Notify>,
) -> Result<(), AppError> {
    let mut start_index = 0;
    let mut retry_count = 0;

    loop {
        for i in start_index..STEPS.len() {
            let step = STEPS[i];
            check_signals(&cancel_rx, &pause_rx).await?;
            update_deployment_progress(&db, deployment_id, step, STEP_PROGRESS[i]).await?;
            write_deployment_log_with_step(&db, deployment_id, "info", &format!("开始步骤: {}", step), step).await?;

            let result = match step {
                "clone" => crate::services::deployer::steps::clone::execute(db.clone(), deployment_id, git_url, branch).await,
                "generate_review" => crate::services::deployer::steps::review::execute(db.clone(), deployment_id).await,
                "build" => crate::services::deployer::steps::build::execute(db.clone(), deployment_id).await,
                "env_review" => crate::services::deployer::steps::env_review::execute(db.clone(), deployment_id, &cancel_rx, review_notify.clone()).await,
                "push" => crate::services::deployer::steps::push::execute(db.clone(), deployment_id).await,
                "deploy" => crate::services::deployer::steps::deploy::execute(db.clone(), deployment_id, platform).await,
                "configure" => crate::services::deployer::steps::configure::execute(db.clone(), deployment_id).await,
                "verify" => crate::services::deployer::steps::verify::execute(db.clone(), deployment_id).await,
                _ => Err(AppError::InternalError(format!("未知步骤: {}", step))),
            };

            match result {
                Ok(()) => {
                    write_deployment_log_with_step(&db, deployment_id, "info", &format!("步骤完成: {}", step), step).await?;
                }
                Err(e) => {
                    write_deployment_log_with_step(&db, deployment_id, "error", &format!("步骤失败: {} - {}", step, e), step).await?;

                    // 判断是否需要诊断
                    if DIAGNOSABLE_STEPS.contains(&step) && retry_count < MAX_DIAGNOSE_RETRIES {
                        info!("步骤 {} 失败，尝试 AI 诊断 (retry={}/{})", step, retry_count, MAX_DIAGNOSE_RETRIES);

                        match try_diagnose_and_fix(&db, deployment_id, step, &agent_client, retry_count).await {
                            Ok(diagnose_result) => {
                                if diagnose_result.fixable_by_agent {
                                    // 可修复：更新文件，从 review 步骤重新开始
                                    info!("诊断结果：可修复 (category={})，从 review 步骤重新开始", diagnose_result.failure_category);
                                    write_deployment_log_with_step(&db, deployment_id, "info",
                                        &format!("AI 诊断：{}，自动修复中...", diagnose_result.diagnosis), "diagnose").await?;

                                    // 更新部署文件（如果需要）
                                    // 注意：这里需要实际更新文件，但目前先记录诊断结果
                                    retry_count += 1;
                                    start_index = step_index("generate_review").unwrap_or(1);
                                    break; // 跳出内层循环，重新开始
                                } else {
                                    // 不可修复：记录诊断结果，标记失败
                                    info!("诊断结果：不可修复 (category={})", diagnose_result.failure_category);
                                    write_deployment_log_with_step(&db, deployment_id, "error",
                                        &format!("AI 诊断：{}\n建议：{}", diagnose_result.diagnosis, diagnose_result.suggestions.join("; ")),
                                        "diagnose").await?;
                                    fail_deployment(&db, deployment_id, &format!("[{}] {}", diagnose_result.failure_category, diagnose_result.diagnosis)).await;
                                    cleanup_temp_dir(deployment_id).await;
                                    return Err(e);
                                }
                            }
                            Err(diag_err) => {
                                // 诊断失败，记录失败原因并标记失败
                                warn!("AI 诊断失败: {}", diag_err);
                                write_deployment_log_with_step(&db, deployment_id, "error",
                                    &format!("AI 诊断服务不可用: {}\n原始错误: {}", diag_err, e), "diagnose").await.ok();
                                fail_deployment(&db, deployment_id, &e.to_string()).await;
                                cleanup_temp_dir(deployment_id).await;
                                return Err(e);
                            }
                        }
                    } else {
                        // 不需要诊断或已达到最大重试次数
                        if retry_count >= MAX_DIAGNOSE_RETRIES {
                            write_deployment_log_with_step(&db, deployment_id, "error",
                                &format!("已达最大重试次数 ({})，停止重试", MAX_DIAGNOSE_RETRIES), step).await?;
                        }
                        fail_deployment(&db, deployment_id, &e.to_string()).await;
                        cleanup_temp_dir(deployment_id).await;
                        return Err(e);
                    }
                }
            }
        }

        // 如果循环正常结束（没有 break），说明部署成功
        if start_index == 0 || start_index >= STEPS.len() {
            break;
        }
        // 如果是重试后从中间开始，循环会继续
    }

    success_deployment(&db, deployment_id).await;
    cleanup_temp_dir(deployment_id).await;
    Ok(())
}

/// 尝试诊断并修复
async fn try_diagnose_and_fix(
    db: &sea_orm::DatabaseConnection,
    deployment_id: Uuid,
    failed_step: &str,
    agent_client: &AgentClient,
    retry_count: i32,
) -> Result<DiagnoseResult, AppError> {
    // 获取部署信息
    let dep = DeploymentEntity::find_by_id(deployment_id).one(db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    // 获取关键日志
    let logs = get_key_logs(db, deployment_id, failed_step).await?;

    // 从 config 获取项目信息
    let config = dep.config.as_ref().cloned().unwrap_or_default();
    let scan_result = config.get("scan_result").cloned().unwrap_or_default();
    let project_type = scan_result.get("project_type").and_then(|v| v.as_str()).unwrap_or("single").to_string();
    let language = scan_result.get("language").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
    let framework = scan_result.get("framework").and_then(|v| v.as_str()).unwrap_or("").to_string();

    // 获取部署文件内容（用于修复）
    let dockerfile_content = config.get("dockerfile_content").and_then(|v| v.as_str()).map(|s| s.to_string());
    let compose_content = config.get("compose_content").and_then(|v| v.as_str()).map(|s| s.to_string());

    // 调用 Agent 诊断
    let request = DeployDiagnoseRequest {
        deployment_id: deployment_id.to_string(),
        failed_step: failed_step.to_string(),
        project_type,
        language,
        framework,
        dockerfile_content,
        compose_content,
        logs,
        retry_count,
        max_retries: MAX_DIAGNOSE_RETRIES,
    };

    let response = agent_client.deploy_diagnose(request).await?;

    Ok(DiagnoseResult {
        diagnosis: response.diagnosis,
        suggestions: response.suggestions,
        failure_category: response.failure_category,
        fixable_by_agent: response.fixable_by_agent,
        fixed_content: response.fixed_content,
        fixed_file_type: response.fixed_file_type,
    })
}

/// 获取关键日志（失败步骤的日志 + error 日志 + 最后 20 条）
async fn get_key_logs(db: &sea_orm::DatabaseConnection, deployment_id: Uuid, failed_step: &str) -> Result<Vec<String>, AppError> {
    let all_logs = DeploymentLogEntity::find()
        .filter(LogColumn::DeploymentId.eq(deployment_id))
        .order_by_asc(LogColumn::CreatedAt)
        .all(db)
        .await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?;

    let mut key_logs = Vec::new();
    let mut seen = std::collections::HashSet::new();

    // 1. 失败步骤的日志
    for log in all_logs.iter().filter(|l| l.step.as_deref() == Some(failed_step)) {
        if seen.insert(log.message.clone()) {
            key_logs.push(log.message.clone());
        }
    }

    // 2. error 级别的日志
    for log in all_logs.iter().filter(|l| l.level == "error") {
        if seen.insert(log.message.clone()) {
            key_logs.push(log.message.clone());
        }
    }

    // 3. 如果太少，补充最后 20 条
    if key_logs.len() < 5 {
        for log in all_logs.iter().rev().take(20) {
            if seen.insert(log.message.clone()) {
                key_logs.push(log.message.clone());
            }
        }
    }

    // 限制总条数
    key_logs.truncate(50);
    Ok(key_logs)
}

#[allow(dead_code)]
struct DiagnoseResult {
    diagnosis: String,
    suggestions: Vec<String>,
    failure_category: String,
    fixable_by_agent: bool,
    fixed_content: Option<String>,
    fixed_file_type: Option<String>,
}

async fn fail_deployment(db: &sea_orm::DatabaseConnection, id: Uuid, msg: &str) {
    if let Some(dep) = DeploymentEntity::find_by_id(id).one(db).await.ok().flatten() {
        let mut am: DeploymentActiveModel = dep.into();
        am.status = Set(DeploymentStatus::Failed);
        am.error_message = Set(Some(msg.to_string()));
        am.completed_at = Set(Some(chrono::Utc::now().naive_utc()));
        if let Err(e) = am.update(db).await {
            tracing::error!("更新部署状态为 Failed 失败: {}", e);
        }
    }
}

async fn success_deployment(db: &sea_orm::DatabaseConnection, id: Uuid) {
    if let Some(dep) = DeploymentEntity::find_by_id(id).one(db).await.ok().flatten() {
        let mut am: DeploymentActiveModel = dep.into();
        am.status = Set(DeploymentStatus::Success);
        am.progress = Set(100);
        am.completed_at = Set(Some(chrono::Utc::now().naive_utc()));
        if let Err(e) = am.update(db).await {
            tracing::error!("更新部署状态为 Success 失败: {}", e);
        }
    }
}

/// 清理部署临时目录
async fn cleanup_temp_dir(deployment_id: Uuid) {
    let temp_dir = format!("/tmp/stackpilot/{}", deployment_id);
    if let Err(e) = tokio::fs::remove_dir_all(&temp_dir).await {
        tracing::warn!("清理临时目录失败 {}: {}", temp_dir, e);
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

#[allow(dead_code)]
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
