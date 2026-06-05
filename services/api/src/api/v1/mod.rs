pub mod health;
pub mod auth;
pub mod projects;
pub mod deployments;
pub mod monitoring;
pub mod configs;
pub mod users;
pub mod members;

use axum::Router;
use deployments::DeploymentsState;
use auth::AuthState;
use projects::ProjectsState;
use monitoring::MonitoringState;
use configs::ConfigState;
use users::UsersState;
use members::MembersState;

pub fn routes(
    deployments_state: DeploymentsState,
    auth_state: AuthState,
    projects_state: ProjectsState,
    monitoring_state: MonitoringState,
    config_state: ConfigState,
    users_state: UsersState,
    members_state: MembersState,
) -> Router {
    Router::new()
        .merge(health::routes())
        .merge(auth::routes(auth_state))
        .merge(projects::routes(projects_state))
        .merge(deployments::routes().with_state(deployments_state))
        .merge(monitoring::routes(monitoring_state))
        .merge(configs::routes(config_state))
        .merge(users::routes(users_state))
        .merge(members::routes(members_state))
}
