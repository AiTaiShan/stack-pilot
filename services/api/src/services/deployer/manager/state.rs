#![allow(dead_code)]
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{RwLock, watch, Notify};
use uuid::Uuid;
use sea_orm::{EntityTrait, ActiveModelTrait, Set, ColumnTrait, QueryFilter};
use tracing::{info, warn, error};

use crate::error::AppError;
use crate::models::deployment::{self, Entity as DeploymentEntity, ActiveModel as DeploymentActiveModel, DeploymentStatus};
use crate::services::agent::AgentClient;

pub struct DeploymentRuntime {
    pub cancel_tx: watch::Sender<bool>,
    pub pause_tx: watch::Sender<bool>,
    pub review_notify: Arc<Notify>,
    pub handle: Option<tokio::task::JoinHandle<()>>,
}

pub struct DeploymentStateManager {
    db: sea_orm::DatabaseConnection,
    agent_client: Arc<AgentClient>,
    active: Arc<RwLock<HashMap<Uuid, DeploymentRuntime>>>,
}

impl DeploymentStateManager {
    pub fn new(db: sea_orm::DatabaseConnection, agent_client: Arc<AgentClient>) -> Self {
        Self {
            db,
            agent_client,
            active: Arc::new(RwLock::new(HashMap::new()))
        }
    }

    pub async fn recover_on_startup(&self) -> Result<(), AppError> {
        let running = DeploymentEntity::find()
            .filter(deployment::Column::Status.eq(DeploymentStatus::Running))
            .all(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;
        for dep in running {
            let mut active: DeploymentActiveModel = dep.clone().into();
            active.status = Set(deployment::DeploymentStatus::Failed);
            active.error_message = Set(Some("服务重启中断".to_string()));
            active.completed_at = Set(Some(chrono::Utc::now().naive_utc()));
            active.update(&self.db).await.ok();
            warn!("恢复部署状态: {} -> FAILED", dep.id);
        }
        Ok(())
    }

    pub async fn create_deployment(&self, deployment_id: Uuid, git_url: String, branch: String, platform: String) -> Result<(), AppError> {
        let (cancel_tx, cancel_rx) = watch::channel(false);
        let (pause_tx, pause_rx) = watch::channel(false);
        let review_notify = Arc::new(Notify::new());
        let dep = DeploymentEntity::find_by_id(deployment_id).one(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;
        let mut am: DeploymentActiveModel = dep.into();
        am.status = Set(deployment::DeploymentStatus::Running);
        am.started_at = Set(Some(chrono::Utc::now().naive_utc()));
        am.update(&self.db).await.ok();

        let db = self.db.clone();
        let agent_client = self.agent_client.clone();
        let active_map = self.active.clone();
        let review_notify_clone = review_notify.clone();
        let handle = tokio::spawn(async move {
            let result = super::executor::execute_deployment(
                db.clone(), deployment_id, &git_url, &branch, &platform,
                cancel_rx, pause_rx, agent_client, review_notify_clone
            ).await;
            active_map.write().await.remove(&deployment_id);
            match result {
                Ok(()) => info!("部署完成: {}", deployment_id),
                Err(e) => error!("部署失败: {} - {}", deployment_id, e),
            }
        });
        self.active.write().await.insert(deployment_id, DeploymentRuntime { cancel_tx, pause_tx, review_notify, handle: Some(handle) });
        info!("部署已启动: {}", deployment_id);
        Ok(())
    }

    pub async fn cancel_deployment(&self, id: &Uuid) -> Result<(), AppError> {
        let active = self.active.read().await;
        let runtime = active.get(id).ok_or_else(|| AppError::NotFound("部署不在运行中".to_string()))?;
        runtime.cancel_tx.send(true).unwrap();
        info!("部署取消信号已发送: {}", id);

        // 尝试回滚：停止 docker-compose 服务
        if let Some(dep) = DeploymentEntity::find_by_id(*id).one(&self.db).await.ok().flatten() {
            if let Some(git_url) = &dep.git_url {
                let repo_name = git_url.rsplit('/').next()
                    .unwrap_or("app")
                    .replace(".git", "")
                    .to_lowercase();
                let project_name = format!("stackpilot-{}", repo_name);

                // 尝试停止 docker-compose 服务
                let _ = tokio::process::Command::new("docker")
                    .args(["compose", "-p", &project_name, "down", "--remove-orphans"])
                    .output()
                    .await;

                info!("已回滚部署资源: {}", project_name);
            }
        }

        Ok(())
    }

    pub async fn pause_deployment(&self, id: &Uuid) -> Result<(), AppError> {
        let active = self.active.read().await;
        let runtime = active.get(id).ok_or_else(|| AppError::NotFound("部署不在运行中".to_string()))?;
        runtime.pause_tx.send(true).unwrap();
        let dep = DeploymentEntity::find_by_id(*id).one(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;
        let mut am: DeploymentActiveModel = dep.into();
        am.status = Set(deployment::DeploymentStatus::Paused);
        am.update(&self.db).await.ok();
        info!("部署已暂停: {}", id);
        Ok(())
    }

    pub async fn resume_deployment(&self, id: &Uuid) -> Result<(), AppError> {
        let active = self.active.read().await;
        let runtime = active.get(id).ok_or_else(|| AppError::NotFound("部署不在运行中".to_string()))?;
        runtime.pause_tx.send(false).unwrap();
        let dep = DeploymentEntity::find_by_id(*id).one(&self.db).await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;
        let mut am: DeploymentActiveModel = dep.into();
        am.status = Set(deployment::DeploymentStatus::Running);
        am.update(&self.db).await.ok();
        info!("部署已恢复: {}", id);
        Ok(())
    }

    pub async fn confirm_env_review(&self, id: &Uuid) -> Result<(), AppError> {
        let active = self.active.read().await;
        let runtime = active.get(id).ok_or_else(|| AppError::NotFound("部署不在运行中".to_string()))?;
        runtime.review_notify.notify_one();
        info!("环境变量审核已确认: {}", id);
        Ok(())
    }

    pub async fn is_active(&self, id: &Uuid) -> bool {
        self.active.read().await.contains_key(id)
    }

    pub async fn active_read(&self) -> tokio::sync::RwLockReadGuard<'_, HashMap<Uuid, DeploymentRuntime>> {
        self.active.read().await
    }
}
