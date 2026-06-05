#![allow(dead_code)]
use sysinfo::System;
use sea_orm::{EntityTrait, QueryFilter, ColumnTrait};
use crate::error::AppError;
use crate::models::deployment::{self, Entity as DeploymentEntity, DeploymentStatus};

pub struct MonitoringService {
    db: sea_orm::DatabaseConnection,
}

impl MonitoringService {
    pub fn new(db: sea_orm::DatabaseConnection) -> Self {
        Self { db }
    }

    pub async fn get_system_status(&self) -> Result<SystemStatus, AppError> {
        let mut sys = System::new_all();
        sys.refresh_all();

        let cpu_usage = sys.global_cpu_info().cpu_usage() as f64;

        let memory_usage = if sys.total_memory() > 0 {
            (sys.used_memory() as f64 / sys.total_memory() as f64) * 100.0
        } else {
            0.0
        };

        let disks = sysinfo::Disks::new_with_refreshed_list();
        let disk_usage = if !disks.is_empty() {
            let total: u64 = disks.iter().map(|d| d.total_space()).sum();
            let available: u64 = disks.iter().map(|d| d.available_space()).sum();
            if total > 0 {
                ((total - available) as f64 / total as f64) * 100.0
            } else {
                0.0
            }
        } else {
            0.0
        };

        let active_deployments = DeploymentEntity::find()
            .filter(deployment::Column::Status.eq(DeploymentStatus::Running))
            .all(&self.db)
            .await
            .map(|d| d.len() as i32)
            .unwrap_or(0);

        let total_projects = crate::models::project::Entity::find()
            .all(&self.db)
            .await
            .map(|p| p.len() as i32)
            .unwrap_or(0);

        Ok(SystemStatus {
            cpu_usage,
            memory_usage,
            disk_usage,
            active_deployments,
            total_projects,
        })
    }

    pub async fn get_deployment_stats(&self) -> Result<DeploymentStats, AppError> {
        let deployments = DeploymentEntity::find()
            .all(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        let total = deployments.len() as i32;
        let success = deployments.iter().filter(|d| d.status == DeploymentStatus::Success).count() as i32;
        let failed = deployments.iter().filter(|d| d.status == DeploymentStatus::Failed).count() as i32;
        let running = deployments.iter().filter(|d| d.status == DeploymentStatus::Running).count() as i32;
        let pending = deployments.iter().filter(|d| d.status == DeploymentStatus::Pending).count() as i32;

        Ok(DeploymentStats {
            total,
            success,
            failed,
            running,
            pending,
        })
    }

    pub async fn get_metrics(&self, name: &str, _duration: i64) -> Result<serde_json::Value, AppError> {
        match name {
            "deployments" => {
                let stats = self.get_deployment_stats().await?;
                Ok(serde_json::json!({"name": "deployments", "data": stats}))
            }
            "system" => {
                let status = self.get_system_status().await?;
                Ok(serde_json::json!({"name": "system", "data": status}))
            }
            _ => Err(AppError::NotFound(format!("指标 '{}' 不存在", name))),
        }
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct SystemStatus {
    pub cpu_usage: f64,
    pub memory_usage: f64,
    pub disk_usage: f64,
    pub active_deployments: i32,
    pub total_projects: i32,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct DeploymentStats {
    pub total: i32,
    pub success: i32,
    pub failed: i32,
    pub running: i32,
    pub pending: i32,
}
