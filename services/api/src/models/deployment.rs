use sea_orm::entity::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, EnumIter, DeriveActiveEnum, Serialize, Deserialize)]
#[sea_orm(rs_type = "String", db_type = "Enum", enum_name = "deploymentstatus")]
#[serde(rename_all = "snake_case")]
pub enum DeploymentStatus {
    #[sea_orm(string_value = "pending")]
    Pending,
    #[sea_orm(string_value = "running")]
    Running,
    #[sea_orm(string_value = "paused")]
    Paused,
    #[sea_orm(string_value = "cancelled")]
    Cancelled,
    #[sea_orm(string_value = "success")]
    Success,
    #[sea_orm(string_value = "failed")]
    Failed,
    #[sea_orm(string_value = "rolling_back")]
    RollingBack,
    #[sea_orm(string_value = "rolled_back")]
    RolledBack,
    #[sea_orm(string_value = "waiting_review")]
    WaitingReview,
}

#[derive(Debug, Clone, PartialEq, Eq, EnumIter, DeriveActiveEnum, Serialize, Deserialize)]
#[sea_orm(rs_type = "String", db_type = "Enum", enum_name = "deploymentstep")]
#[serde(rename_all = "snake_case")]
pub enum DeploymentStep {
    #[sea_orm(string_value = "clone")]
    Clone,
    #[sea_orm(string_value = "generate_review")]
    GenerateReview,
    #[sea_orm(string_value = "build")]
    Build,
    #[sea_orm(string_value = "env_review")]
    EnvReview,
    #[sea_orm(string_value = "push")]
    Push,
    #[sea_orm(string_value = "deploy")]
    Deploy,
    #[sea_orm(string_value = "configure")]
    Configure,
    #[sea_orm(string_value = "verify")]
    Verify,
}

#[derive(Clone, Debug, PartialEq, DeriveEntityModel, Serialize, Deserialize)]
#[sea_orm(table_name = "deployments")]
pub struct Model {
    #[sea_orm(primary_key, auto_increment = false)]
    pub id: Uuid,
    pub project_id: Uuid,
    pub user_id: Option<Uuid>,
    pub status: DeploymentStatus,
    pub current_step: Option<DeploymentStep>,
    pub progress: i32,
    pub platform: String,
    pub config: Option<Json>,
    pub git_url: Option<String>,
    pub branch: Option<String>,
    pub image_tag: Option<String>,
    pub deploy_url: Option<String>,
    pub commit_hash: Option<String>,
    pub commit_message: Option<String>,
    pub error_message: Option<String>,
    pub error_details: Option<Json>,
    pub can_resume: Option<i32>,
    pub resume_data: Option<Json>,
    pub duration: Option<i32>,
    pub started_at: Option<chrono::NaiveDateTime>,
    pub completed_at: Option<chrono::NaiveDateTime>,
    pub updated_at: Option<chrono::NaiveDateTime>,
    pub created_at: Option<chrono::NaiveDateTime>,
}

#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {
    #[sea_orm(
        belongs_to = "super::project::Entity",
        from = "Column::ProjectId",
        to = "super::project::Column::Id"
    )]
    Project,
    #[sea_orm(
        belongs_to = "super::user::Entity",
        from = "Column::UserId",
        to = "super::user::Column::Id"
    )]
    User,
}

impl Related<super::project::Entity> for Entity {
    fn to() -> RelationDef {
        Relation::Project.def()
    }
}

impl Related<super::user::Entity> for Entity {
    fn to() -> RelationDef {
        Relation::User.def()
    }
}

impl ActiveModelBehavior for ActiveModel {}
