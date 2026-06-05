use sea_orm_migration::prelude::*;

#[derive(DeriveMigrationName)]
pub struct Migration;

#[async_trait::async_trait]
impl MigrationTrait for Migration {
    async fn up(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        // 创建枚举类型
        manager
            .get_connection()
            .execute_unprepared(
                "DO $$ BEGIN
                    CREATE TYPE deploymentstatus AS ENUM (
                        'pending','running','paused','cancelled','success',
                        'failed','rolling_back','rolled_back','waiting_review'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;",
            )
            .await?;

        manager
            .get_connection()
            .execute_unprepared(
                "DO $$ BEGIN
                    CREATE TYPE deploymentstep AS ENUM (
                        'clone','generate_review','build','env_review',
                        'push','deploy','configure','verify'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;",
            )
            .await?;

        // 1. users
        manager
            .create_table(
                Table::create()
                    .table(Users::Table)
                    .if_not_exists()
                    .col(ColumnDef::new(Users::Id).uuid().not_null().primary_key())
                    .col(ColumnDef::new(Users::Username).string_len(50).not_null())
                    .col(ColumnDef::new(Users::Email).string_len(100).not_null())
                    .col(ColumnDef::new(Users::PasswordHash).string_len(255).not_null())
                    .col(ColumnDef::new(Users::Role).string_len(20).not_null())
                    .col(ColumnDef::new(Users::Phone).string_len(20).null())
                    .col(ColumnDef::new(Users::Avatar).string_len(500).null())
                    .col(ColumnDef::new(Users::IsActive).boolean().default(true))
                    .col(ColumnDef::new(Users::LastLoginAt).timestamp().null())
                    .col(
                        ColumnDef::new(Users::CreatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .col(
                        ColumnDef::new(Users::UpdatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .to_owned(),
            )
            .await?;

        // users 唯一索引
        manager
            .create_index(
                Index::create()
                    .if_not_exists()
                    .name("ix_users_username")
                    .table(Users::Table)
                    .col(Users::Username)
                    .unique()
                    .to_owned(),
            )
            .await?;
        manager
            .create_index(
                Index::create()
                    .if_not_exists()
                    .name("ix_users_email")
                    .table(Users::Table)
                    .col(Users::Email)
                    .unique()
                    .to_owned(),
            )
            .await?;

        // 2. projects
        manager
            .create_table(
                Table::create()
                    .table(Projects::Table)
                    .if_not_exists()
                    .col(ColumnDef::new(Projects::Id).uuid().not_null().primary_key())
                    .col(ColumnDef::new(Projects::Name).string_len(100).not_null())
                    .col(ColumnDef::new(Projects::GitUrl).string_len(500).not_null())
                    .col(ColumnDef::new(Projects::OwnerId).uuid().not_null())
                    .col(ColumnDef::new(Projects::Description).text().null())
                    .col(ColumnDef::new(Projects::DefaultBranch).string_len(100).default("main"))
                    .col(ColumnDef::new(Projects::IsArchived).boolean().default(false))
                    .col(
                        ColumnDef::new(Projects::CreatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .col(
                        ColumnDef::new(Projects::UpdatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .foreign_key(
                        ForeignKey::create()
                            .name("fk_projects_owner_id")
                            .from(Projects::Table, Projects::OwnerId)
                            .to(Users::Table, Users::Id),
                    )
                    .to_owned(),
            )
            .await?;

        // 3. project_members
        manager
            .create_table(
                Table::create()
                    .table(ProjectMembers::Table)
                    .if_not_exists()
                    .col(
                        ColumnDef::new(ProjectMembers::Id)
                            .uuid()
                            .not_null()
                            .primary_key(),
                    )
                    .col(ColumnDef::new(ProjectMembers::ProjectId).uuid().not_null())
                    .col(ColumnDef::new(ProjectMembers::UserId).uuid().not_null())
                    .col(ColumnDef::new(ProjectMembers::Role).string_len(20).not_null())
                    .col(ColumnDef::new(ProjectMembers::InvitedBy).uuid().null())
                    .col(
                        ColumnDef::new(ProjectMembers::CreatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .col(
                        ColumnDef::new(ProjectMembers::UpdatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .foreign_key(
                        ForeignKey::create()
                            .name("fk_project_members_project_id")
                            .from(ProjectMembers::Table, ProjectMembers::ProjectId)
                            .to(Projects::Table, Projects::Id),
                    )
                    .foreign_key(
                        ForeignKey::create()
                            .name("fk_project_members_user_id")
                            .from(ProjectMembers::Table, ProjectMembers::UserId)
                            .to(Users::Table, Users::Id),
                    )
                    .foreign_key(
                        ForeignKey::create()
                            .name("fk_project_members_invited_by")
                            .from(ProjectMembers::Table, ProjectMembers::InvitedBy)
                            .to(Users::Table, Users::Id),
                    )
                    .to_owned(),
            )
            .await?;

        // project_members 索引
        manager
            .create_index(
                Index::create()
                    .if_not_exists()
                    .name("ix_project_members_project_id")
                    .table(ProjectMembers::Table)
                    .col(ProjectMembers::ProjectId)
                    .to_owned(),
            )
            .await?;
        manager
            .create_index(
                Index::create()
                    .if_not_exists()
                    .name("ix_project_members_user_id")
                    .table(ProjectMembers::Table)
                    .col(ProjectMembers::UserId)
                    .to_owned(),
            )
            .await?;

        // 4. deployments
        manager
            .create_table(
                Table::create()
                    .table(Deployments::Table)
                    .if_not_exists()
                    .col(
                        ColumnDef::new(Deployments::Id)
                            .uuid()
                            .not_null()
                            .primary_key(),
                    )
                    .col(ColumnDef::new(Deployments::ProjectId).uuid().not_null())
                    .col(ColumnDef::new(Deployments::UserId).uuid().null())
                    .col(
                        ColumnDef::new(Deployments::Status)
                            .custom(DeploymentStatus::Enum)
                            .not_null()
                            .default(Expr::cust("'pending'::deploymentstatus")),
                    )
                    .col(
                        ColumnDef::new(Deployments::CurrentStep)
                            .custom(DeploymentStep::Enum)
                            .null(),
                    )
                    .col(
                        ColumnDef::new(Deployments::Progress)
                            .integer()
                            .not_null()
                            .default(0),
                    )
                    .col(ColumnDef::new(Deployments::Platform).string_len(20).not_null())
                    .col(ColumnDef::new(Deployments::Config).json_binary().null())
                    .col(ColumnDef::new(Deployments::GitUrl).string_len(500).null())
                    .col(ColumnDef::new(Deployments::Branch).string_len(200).default("main"))
                    .col(ColumnDef::new(Deployments::ImageTag).string_len(500).null())
                    .col(ColumnDef::new(Deployments::DeployUrl).string_len(500).null())
                    .col(ColumnDef::new(Deployments::CommitHash).string_len(40).null())
                    .col(ColumnDef::new(Deployments::CommitMessage).text().null())
                    .col(ColumnDef::new(Deployments::ErrorMessage).text().null())
                    .col(ColumnDef::new(Deployments::ErrorDetails).json_binary().null())
                    .col(ColumnDef::new(Deployments::CanResume).integer().default(0))
                    .col(ColumnDef::new(Deployments::ResumeData).json_binary().null())
                    .col(ColumnDef::new(Deployments::Duration).integer().null())
                    .col(ColumnDef::new(Deployments::StartedAt).timestamp().null())
                    .col(ColumnDef::new(Deployments::CompletedAt).timestamp().null())
                    .col(
                        ColumnDef::new(Deployments::UpdatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .col(
                        ColumnDef::new(Deployments::CreatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .foreign_key(
                        ForeignKey::create()
                            .name("fk_deployments_project_id")
                            .from(Deployments::Table, Deployments::ProjectId)
                            .to(Projects::Table, Projects::Id),
                    )
                    .foreign_key(
                        ForeignKey::create()
                            .name("fk_deployments_user_id")
                            .from(Deployments::Table, Deployments::UserId)
                            .to(Users::Table, Users::Id),
                    )
                    .to_owned(),
            )
            .await?;

        // 5. deployment_logs
        manager
            .create_table(
                Table::create()
                    .table(DeploymentLogs::Table)
                    .if_not_exists()
                    .col(
                        ColumnDef::new(DeploymentLogs::Id)
                            .uuid()
                            .not_null()
                            .primary_key(),
                    )
                    .col(
                        ColumnDef::new(DeploymentLogs::DeploymentId)
                            .uuid()
                            .not_null(),
                    )
                    .col(ColumnDef::new(DeploymentLogs::Level).string_len(20).not_null())
                    .col(ColumnDef::new(DeploymentLogs::Message).text().not_null())
                    .col(ColumnDef::new(DeploymentLogs::Details).json_binary().null())
                    .col(ColumnDef::new(DeploymentLogs::Step).string_len(50).null())
                    .col(
                        ColumnDef::new(DeploymentLogs::CreatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .foreign_key(
                        ForeignKey::create()
                            .name("fk_deployment_logs_deployment_id")
                            .from(DeploymentLogs::Table, DeploymentLogs::DeploymentId)
                            .to(Deployments::Table, Deployments::Id),
                    )
                    .to_owned(),
            )
            .await?;

        // 6. deployment_checkpoints
        manager
            .create_table(
                Table::create()
                    .table(DeploymentCheckpoints::Table)
                    .if_not_exists()
                    .col(
                        ColumnDef::new(DeploymentCheckpoints::Id)
                            .uuid()
                            .not_null()
                            .primary_key(),
                    )
                    .col(
                        ColumnDef::new(DeploymentCheckpoints::DeploymentId)
                            .uuid()
                            .not_null(),
                    )
                    .col(
                        ColumnDef::new(DeploymentCheckpoints::Step)
                            .string_len(50)
                            .not_null(),
                    )
                    .col(
                        ColumnDef::new(DeploymentCheckpoints::StepIndex)
                            .integer()
                            .not_null(),
                    )
                    .col(
                        ColumnDef::new(DeploymentCheckpoints::StateData)
                            .json_binary()
                            .null(),
                    )
                    .col(
                        ColumnDef::new(DeploymentCheckpoints::ResourcesCreated)
                            .json_binary()
                            .null(),
                    )
                    .col(
                        ColumnDef::new(DeploymentCheckpoints::CreatedAt)
                            .timestamp()
                            .null(),
                    )
                    .foreign_key(
                        ForeignKey::create()
                            .name("fk_deployment_checkpoints_deployment_id")
                            .from(
                                DeploymentCheckpoints::Table,
                                DeploymentCheckpoints::DeploymentId,
                            )
                            .to(Deployments::Table, Deployments::Id),
                    )
                    .to_owned(),
            )
            .await?;

        // 7. system_configs
        manager
            .create_table(
                Table::create()
                    .table(SystemConfigs::Table)
                    .if_not_exists()
                    .col(
                        ColumnDef::new(SystemConfigs::Id)
                            .uuid()
                            .not_null()
                            .primary_key(),
                    )
                    .col(
                        ColumnDef::new(SystemConfigs::Key)
                            .string_len(100)
                            .not_null()
                            .unique_key(),
                    )
                    .col(ColumnDef::new(SystemConfigs::Value).json_binary().not_null())
                    .col(
                        ColumnDef::new(SystemConfigs::ValueType)
                            .string_len(20)
                            .not_null(),
                    )
                    .col(ColumnDef::new(SystemConfigs::Description).text().null())
                    .col(
                        ColumnDef::new(SystemConfigs::DefaultValue)
                            .json_binary()
                            .null(),
                    )
                    .col(
                        ColumnDef::new(SystemConfigs::ValidationRule)
                            .json_binary()
                            .null(),
                    )
                    .col(
                        ColumnDef::new(SystemConfigs::IsSensitive)
                            .boolean()
                            .default(false),
                    )
                    .col(
                        ColumnDef::new(SystemConfigs::CreatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .col(
                        ColumnDef::new(SystemConfigs::UpdatedAt)
                            .timestamp()
                            .default(Expr::cust("now()")),
                    )
                    .to_owned(),
            )
            .await?;

        Ok(())
    }

    async fn down(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        manager
            .drop_table(Table::drop().table(SystemConfigs::Table).to_owned())
            .await?;
        manager
            .drop_table(Table::drop().table(DeploymentCheckpoints::Table).to_owned())
            .await?;
        manager
            .drop_table(Table::drop().table(DeploymentLogs::Table).to_owned())
            .await?;
        manager
            .drop_table(Table::drop().table(Deployments::Table).to_owned())
            .await?;
        manager
            .drop_table(Table::drop().table(ProjectMembers::Table).to_owned())
            .await?;
        manager
            .drop_table(Table::drop().table(Projects::Table).to_owned())
            .await?;
        manager
            .drop_table(Table::drop().table(Users::Table).to_owned())
            .await?;

        manager
            .get_connection()
            .execute_unprepared("DROP TYPE IF EXISTS deploymentstep;")
            .await?;
        manager
            .get_connection()
            .execute_unprepared("DROP TYPE IF EXISTS deploymentstatus;")
            .await?;

        Ok(())
    }
}

// ── PG 枚举类型标识 ──────────────────────────────────

#[derive(Iden)]
#[allow(dead_code)]
enum DeploymentStatus {
    #[iden = "deploymentstatus"]
    Enum,
    Pending,
    Running,
    Paused,
    Cancelled,
    Success,
    Failed,
    RollingBack,
    RolledBack,
    WaitingReview,
}

#[derive(Iden)]
#[allow(dead_code)]
enum DeploymentStep {
    #[iden = "deploymentstep"]
    Enum,
    Clone,
    GenerateReview,
    Build,
    EnvReview,
    Push,
    Deploy,
    Configure,
    Verify,
}

// ── 表列标识 ──────────────────────────────────────────

#[derive(Iden)]
enum Users {
    Table,
    Id,
    Username,
    Email,
    PasswordHash,
    Role,
    Phone,
    Avatar,
    IsActive,
    LastLoginAt,
    CreatedAt,
    UpdatedAt,
}

#[derive(Iden)]
enum Projects {
    Table,
    Id,
    Name,
    GitUrl,
    OwnerId,
    Description,
    DefaultBranch,
    IsArchived,
    CreatedAt,
    UpdatedAt,
}

#[derive(Iden)]
enum ProjectMembers {
    Table,
    Id,
    ProjectId,
    UserId,
    Role,
    InvitedBy,
    CreatedAt,
    UpdatedAt,
}

#[derive(Iden)]
enum Deployments {
    Table,
    Id,
    ProjectId,
    UserId,
    Status,
    CurrentStep,
    Progress,
    Platform,
    Config,
    GitUrl,
    Branch,
    ImageTag,
    DeployUrl,
    CommitHash,
    CommitMessage,
    ErrorMessage,
    ErrorDetails,
    CanResume,
    ResumeData,
    Duration,
    StartedAt,
    CompletedAt,
    UpdatedAt,
    CreatedAt,
}

#[derive(Iden)]
enum DeploymentLogs {
    Table,
    Id,
    DeploymentId,
    Level,
    Message,
    Details,
    Step,
    CreatedAt,
}

#[derive(Iden)]
enum DeploymentCheckpoints {
    Table,
    Id,
    DeploymentId,
    Step,
    StepIndex,
    StateData,
    ResourcesCreated,
    CreatedAt,
}

#[derive(Iden)]
enum SystemConfigs {
    Table,
    Id,
    Key,
    Value,
    ValueType,
    Description,
    DefaultValue,
    ValidationRule,
    IsSensitive,
    CreatedAt,
    UpdatedAt,
}
