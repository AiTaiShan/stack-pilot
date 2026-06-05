use sea_orm::{EntityTrait, QueryFilter, ColumnTrait, ActiveModelTrait, Set};
use uuid::Uuid;
use tracing::info;
use crate::error::AppError;
use crate::models::project_member::{self, Entity as MemberEntity, ActiveModel as MemberActiveModel};

pub struct MemberService {
    db: sea_orm::DatabaseConnection,
}

impl MemberService {
    pub fn new(db: sea_orm::DatabaseConnection) -> Self {
        Self { db }
    }

    pub async fn add_member(
        &self,
        project_id: &str,
        user_id: &str,
        role: &str,
    ) -> Result<ProjectMemberInfo, AppError> {
        let pid = Uuid::parse_str(project_id)
            .map_err(|e| AppError::ValidationError(e.to_string()))?;
        let uid = Uuid::parse_str(user_id)
            .map_err(|e| AppError::ValidationError(e.to_string()))?;

        // 检查是否已存在
        let existing = MemberEntity::find()
            .filter(project_member::Column::ProjectId.eq(pid))
            .filter(project_member::Column::UserId.eq(uid))
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        if existing.is_some() {
            return Err(AppError::ValidationError("该用户已是项目成员".to_string()));
        }

        let member = MemberActiveModel {
            id: Set(Uuid::new_v4()),
            project_id: Set(pid),
            user_id: Set(uid),
            role: Set(role.to_string()),
            invited_by: Set(None),
            created_at: Set(Some(chrono::Utc::now().naive_utc())),
            updated_at: Set(Some(chrono::Utc::now().naive_utc())),
        };

        let result = member
            .insert(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("成员添加成功: project={}, user={}", project_id, user_id);

        Ok(ProjectMemberInfo {
            id: result.id.to_string(),
            project_id: result.project_id.to_string(),
            user_id: result.user_id.to_string(),
            role: result.role,
        })
    }

    pub async fn remove_member(
        &self,
        project_id: &str,
        user_id: &str,
    ) -> Result<(), AppError> {
        let pid = Uuid::parse_str(project_id)
            .map_err(|e| AppError::ValidationError(e.to_string()))?;
        let uid = Uuid::parse_str(user_id)
            .map_err(|e| AppError::ValidationError(e.to_string()))?;

        let member = MemberEntity::find()
            .filter(project_member::Column::ProjectId.eq(pid))
            .filter(project_member::Column::UserId.eq(uid))
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("成员不存在".to_string()))?;

        let active: MemberActiveModel = member.into();
        active
            .delete(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        info!("成员移除成功: project={}, user={}", project_id, user_id);
        Ok(())
    }

    pub async fn list_members(
        &self,
        project_id: &str,
    ) -> Result<Vec<ProjectMemberInfo>, AppError> {
        let pid = Uuid::parse_str(project_id)
            .map_err(|e| AppError::ValidationError(e.to_string()))?;

        let members = MemberEntity::find()
            .filter(project_member::Column::ProjectId.eq(pid))
            .all(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        Ok(members
            .into_iter()
            .map(|m| ProjectMemberInfo {
                id: m.id.to_string(),
                project_id: m.project_id.to_string(),
                user_id: m.user_id.to_string(),
                role: m.role,
            })
            .collect())
    }

    pub async fn update_role(
        &self,
        project_id: &str,
        user_id: &str,
        role: &str,
    ) -> Result<ProjectMemberInfo, AppError> {
        let pid = Uuid::parse_str(project_id)
            .map_err(|e| AppError::ValidationError(e.to_string()))?;
        let uid = Uuid::parse_str(user_id)
            .map_err(|e| AppError::ValidationError(e.to_string()))?;

        let member = MemberEntity::find()
            .filter(project_member::Column::ProjectId.eq(pid))
            .filter(project_member::Column::UserId.eq(uid))
            .one(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?
            .ok_or_else(|| AppError::NotFound("成员不存在".to_string()))?;

        let mut active: MemberActiveModel = member.into();
        active.role = Set(role.to_string());

        let result = active
            .update(&self.db)
            .await
            .map_err(|e| AppError::DatabaseError(e.to_string()))?;

        Ok(ProjectMemberInfo {
            id: result.id.to_string(),
            project_id: result.project_id.to_string(),
            user_id: result.user_id.to_string(),
            role: result.role,
        })
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ProjectMemberInfo {
    pub id: String,
    pub project_id: String,
    pub user_id: String,
    pub role: String,
}
