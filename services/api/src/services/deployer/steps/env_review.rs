use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{watch, Notify};
use tracing::info;
use uuid::Uuid;
use sea_orm::{EntityTrait, ActiveModelTrait, Set};
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity, ActiveModel as DeploymentActiveModel, DeploymentStatus};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
    cancel_rx: &watch::Receiver<bool>,
    review_notify: Arc<Notify>,
) -> Result<(), AppError> {
    info!("步骤 4: 部署文件审核 - 部署 {}", deployment_id);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let config = dep.config.as_ref()
        .and_then(|c| c.as_object())
        .cloned()
        .unwrap_or_default();

    let repo_dir_str = config.get("_repo_dir")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let repo_dir = std::path::PathBuf::from(repo_dir_str);

    if !repo_dir.exists() {
        info!("仓库目录不存在，跳过审核");
        return Ok(());
    }

    // ── 1. 读取 docker-compose.yml 内容 ──
    let compose_path = repo_dir.join("docker-compose.yml");
    let compose_content = if compose_path.exists() {
        tokio::fs::read_to_string(&compose_path).await
            .map_err(|e| AppError::InternalError(format!("读取 docker-compose.yml 失败: {}", e)))?
    } else {
        info!("无 docker-compose.yml，跳过审核");
        return Ok(());
    };

    // ── 2. 检查是否已确认（进程重启恢复） ──
    let already_confirmed = config.get("env_vars_confirmed")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    if already_confirmed {
        info!("部署文件已确认（持久化标志），跳过等待");
        return Ok(());
    }

    // ── 3. 将 compose 内容写入 config（前端通过 GET /compose-file 读取展示） ──
    let mut new_config = config;
    new_config.insert("compose_content".to_string(), serde_json::Value::String(compose_content.clone()));

    // 同时提取环境变量供前端参考
    let env_vars = extract_env_from_compose(&compose_content);
    if !env_vars.is_empty() {
        let env_json: serde_json::Value = serde_json::to_value(&env_vars).unwrap_or_default();
        new_config.insert("pending_env_vars".to_string(), env_json);
        info!("从 compose 中提取到 {} 个环境变量", env_vars.len());
    }

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let mut am: DeploymentActiveModel = dep.into();
    am.config = Set(Some(serde_json::Value::Object(new_config)));
    am.update(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?;

    // ── 4. 设置 WAITING_REVIEW 状态，阻塞等待用户确认 ──
    info!("等待用户审核部署文件...");
    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let mut am: DeploymentActiveModel = dep.into();
    am.status = Set(DeploymentStatus::WaitingReview);
    am.update(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?;

    let timeout = std::time::Duration::from_secs(
        std::env::var("ENV_REVIEW_TIMEOUT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(1800)
    );

    tokio::select! {
        _ = review_notify.notified() => {
            info!("用户已确认部署文件");
        }
        _ = tokio::time::sleep(timeout) => {
            let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
                .map_err(|e| AppError::DatabaseError(e.to_string()))?
                .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;
            let mut am: DeploymentActiveModel = dep.into();
            am.status = Set(DeploymentStatus::Failed);
            am.error_message = Set(Some("部署文件审核超时，部署自动取消".to_string()));
            am.completed_at = Set(Some(chrono::Utc::now().naive_utc()));
            am.update(&db).await.ok();
            return Err(AppError::InternalError("部署文件审核超时".to_string()));
        }
        _ = async {
            loop {
                if *cancel_rx.borrow() { break; }
                let mut rx = cancel_rx.clone();
                let _ = rx.changed().await;
            }
        } => {
            return Err(AppError::DeploymentCancelled);
        }
    }

    // ── 5. 用户确认后，恢复 RUNNING 状态 ──
    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    let mut config = dep.config.as_ref()
        .and_then(|c| c.as_object())
        .cloned()
        .unwrap_or_default();
    config.insert("env_vars_confirmed".to_string(), serde_json::Value::Bool(true));

    let mut am: DeploymentActiveModel = dep.into();
    am.status = Set(DeploymentStatus::Running);
    am.config = Set(Some(serde_json::Value::Object(config)));
    am.update(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?;

    info!("步骤 4 完成: 部署文件审核");
    Ok(())
}

/// 从 docker-compose.yml 内容中提取所有 service 的 environment 变量
fn extract_env_from_compose(content: &str) -> HashMap<String, String> {
    let mut env_vars = HashMap::new();

    let yaml: serde_yaml::Value = match serde_yaml::from_str(content) {
        Ok(v) => v,
        Err(e) => {
            info!("解析 docker-compose.yml 失败: {}", e);
            return env_vars;
        }
    };

    if let Some(services) = yaml.get("services").and_then(|v| v.as_mapping()) {
        for (_svc_name, svc_def) in services {
            if let Some(env) = svc_def.get("environment") {
                match env {
                    serde_yaml::Value::Mapping(map) => {
                        for (k, v) in map {
                            if let (serde_yaml::Value::String(key), serde_yaml::Value::String(val)) = (k, v) {
                                env_vars.insert(key.clone(), val.clone());
                            } else if let serde_yaml::Value::String(key) = k {
                                env_vars.insert(key.clone(), format!("{:?}", v));
                            }
                        }
                    }
                    serde_yaml::Value::Sequence(seq) => {
                        for item in seq {
                            if let serde_yaml::Value::String(s) = item {
                                if let Some((key, value)) = s.split_once('=') {
                                    env_vars.insert(
                                        key.trim().to_string(),
                                        value.trim().trim_matches('"').trim_matches('\'').to_string(),
                                    );
                                }
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    env_vars
}
