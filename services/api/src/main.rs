mod config;
mod error;
mod db;
mod models;
mod utils;
mod middleware;
mod api;
mod services;

use axum::Router;
use axum::middleware::from_fn;
use std::net::SocketAddr;
use tracing::info;
use tracing_subscriber::EnvFilter;
use tracing_subscriber::fmt::writer::MakeWriterExt;
use tracing_appender::rolling;
use std::sync::Arc;

use config::AppConfig;
use services::deployer::manager::DeploymentStateManager;
use services::agent::AgentClient;
use services::auth::AuthService;
use services::project::ProjectService;
use services::project::MemberService;
use services::monitoring::MonitoringService;
use services::config::ConfigService;
use services::user::UserService;
use api::v1::deployments::DeploymentsState;
use api::v1::auth::AuthState;
use api::v1::projects::ProjectsState;
use api::v1::monitoring::MonitoringState;
use api::v1::configs::ConfigState;
use api::v1::users::UsersState;
use api::v1::members::MembersState;

#[tokio::main]
async fn main() {
    // 加载配置
    let config = AppConfig::from_env();

    // 初始化日志：按天切分文件 + 控制台输出
    let log_level = &config.log_level;
    let log_dir = &config.log_dir;
    let file_appender = rolling::daily(log_dir, "api.log");
    let (non_blocking, _guard) = tracing_appender::non_blocking(file_appender);

    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new(format!("stackpilot_backend={log_level},tower_http={log_level}")))
        )
        .with_target(true)
        .with_line_number(true)
        .with_writer(std::io::stderr.and(non_blocking))
        .init();

    // 保持 _guard 存活直到进程退出（否则日志丢失）
    let _guard = _guard;

    info!("配置加载完成，日志目录: {}", log_dir);

    // 创建数据库连接
    let db = db::get_db(&config).await.expect("数据库连接失败");
    info!("数据库连接成功");

    // 创建服务实例
    let agent_client = Arc::new(AgentClient::new(&config.agent_service_url));
    let deployment_manager = Arc::new(DeploymentStateManager::new(db.clone(), agent_client.clone()));
    let user_service = Arc::new(UserService::new(db.clone()));
    let auth_service = Arc::new(AuthService::new(&config.jwt_secret, config.jwt_expire_minutes, config.refresh_token_days, UserService::new(db.clone())));
    let project_service = Arc::new(ProjectService::new(db.clone()));
    let monitoring_service = Arc::new(MonitoringService::new(db.clone()));
    let member_service = Arc::new(MemberService::new(db.clone()));
    let config_service = Arc::new(ConfigService::new(db.clone()));

    // 创建状态
    let deployments_state = DeploymentsState {
        manager: deployment_manager,
        db: db.clone(),
        jwt_secret: config.jwt_secret.clone(),
        agent_client,
    };
    let auth_state = AuthState {
        auth_service,
    };
    let projects_state = ProjectsState {
        jwt_secret: config.jwt_secret.clone(),
        project_service,
    };
    let monitoring_state = MonitoringState {
        monitoring_service,
    };
    let config_state = ConfigState {
        config_service,
    };
    let users_state = UsersState {
        user_service,
        jwt_secret: config.jwt_secret.clone(),
    };
    let members_state = MembersState {
        member_service,
    };

    // 构建路由，组装中间件栈
    // 顺序（从内到外）：SecurityHeaders → CORS → RequestLogging
    // TODO: RateLimit 需要 State<IpRateLimiter>，暂时跳过，待后续 with_state 集成
    let app = Router::new()
        .nest("/api/v1", api::v1::routes(deployments_state, auth_state, projects_state, monitoring_state, config_state, users_state, members_state))
        .layer(from_fn(middleware::security_headers::security_headers_middleware))
        .layer(middleware::cors::cors_layer(&config.cors_origins))
        .layer(from_fn(middleware::logging::logging_middleware));

    // 启动服务器（使用 into_make_service_with_connect_info 以支持 ConnectInfo）
    let addr = format!("0.0.0.0:{}", config.server_port);
    info!("服务器启动在: {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .unwrap();

    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await
    .unwrap();
}
