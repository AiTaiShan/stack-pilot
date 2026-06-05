use uuid::Uuid;
use sea_orm::{EntityTrait, QueryFilter, ColumnTrait, ActiveModelTrait, Set};
use tracing::info;
use serde::Serialize;
use crate::error::AppError;
use crate::models::project::{self, Entity as ProjectEntity, ActiveModel as ProjectActiveModel};

pub struct ProjectService {
    db: sea_orm::DatabaseConnection,
}

impl ProjectService {
    pub fn new(db: sea_orm::DatabaseConnection) -> Self {
        Self { db }
    }

    pub async fn create(
        &self,
        name: &str,
        git_url: &str,
        owner_id: Uuid,
        description: Option<&str>,
    ) -> Result<ProjectInfo, AppError> {
        let project = ProjectActiveModel {
            id: Set(Uuid::new_v4()),
            name: Set(name.to_string()),
            git_url: Set(git_url.to_string()),
            owner_id: Set(owner_id),
            description: Set(description.map(|s| s.to_string())),
            default_branch: Set(Some("main".to_string())),
            is_archived: Set(Some(false)),
            ..Default::default()
        };

        let result = project.insert(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("项目创建成功: {}", result.name);

        Ok(ProjectInfo {
            id: result.id.to_string(),
            name: result.name,
            git_url: result.git_url,
            owner_id: result.owner_id.to_string(),
            description: result.description,
            default_branch: result.default_branch.unwrap_or_else(|| "main".to_string()),
        })
    }

    pub async fn get(&self, id: &str) -> Result<Option<ProjectInfo>, AppError> {
        let uuid = Uuid::parse_str(id)
            .map_err(|e| AppError::ValidationError(format!("无效的项目 ID: {}", e)))?;

        let project = ProjectEntity::find_by_id(uuid)
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        Ok(project.map(|p| ProjectInfo {
            id: p.id.to_string(),
            name: p.name,
            git_url: p.git_url,
            owner_id: p.owner_id.to_string(),
            description: p.description,
            default_branch: p.default_branch.unwrap_or_else(|| "main".to_string()),
        }))
    }

    pub async fn list(&self, owner_id: Option<&str>) -> Result<Vec<ProjectInfo>, AppError> {
        let mut query = ProjectEntity::find();

        if let Some(oid) = owner_id {
            let uuid = Uuid::parse_str(oid)
                .map_err(|e| AppError::ValidationError(format!("无效的用户 ID: {}", e)))?;
            query = query.filter(project::Column::OwnerId.eq(uuid));
        }

        let projects = query
            .all(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        Ok(projects.into_iter().map(|p| ProjectInfo {
            id: p.id.to_string(),
            name: p.name,
            git_url: p.git_url,
            owner_id: p.owner_id.to_string(),
            description: p.description,
            default_branch: p.default_branch.unwrap_or_else(|| "main".to_string()),
        }).collect())
    }

    pub async fn update(
        &self,
        id: &str,
        name: Option<&str>,
        description: Option<&str>,
    ) -> Result<ProjectInfo, AppError> {
        let uuid = Uuid::parse_str(id)
            .map_err(|e| AppError::ValidationError(format!("无效的项目 ID: {}", e)))?;

        let project = ProjectEntity::find_by_id(uuid)
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("项目不存在".to_string()))?;

        let mut active_model: ProjectActiveModel = project.into();

        if let Some(n) = name {
            active_model.name = Set(n.to_string());
        }
        if let Some(d) = description {
            active_model.description = Set(Some(d.to_string()));
        }

        let result = active_model.update(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("项目更新成功: {}", result.id);

        Ok(ProjectInfo {
            id: result.id.to_string(),
            name: result.name,
            git_url: result.git_url,
            owner_id: result.owner_id.to_string(),
            description: result.description,
            default_branch: result.default_branch.unwrap_or_else(|| "main".to_string()),
        })
    }

    pub async fn delete(&self, id: &str) -> Result<(), AppError> {
        let uuid = Uuid::parse_str(id)
            .map_err(|e| AppError::ValidationError(format!("无效的项目 ID: {}", e)))?;

        let project = ProjectEntity::find_by_id(uuid)
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("项目不存在".to_string()))?;

        let active_model: ProjectActiveModel = project.into();
        active_model.delete(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("项目已删除: {}", id);
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct ProjectInfo {
    pub id: String,
    pub name: String,
    pub git_url: String,
    pub owner_id: String,
    pub description: Option<String>,
    pub default_branch: String,
}
