use tower_http::cors::{CorsLayer, AllowOrigin};
use axum::http::{Method, header};

pub fn cors_layer(origins: &[String]) -> CorsLayer {
    let allowed_origins: Vec<_> = origins.iter()
        .filter_map(|o| o.trim().parse().ok())
        .collect();

    CorsLayer::new()
        .allow_origin(AllowOrigin::list(allowed_origins))
        .allow_methods([Method::GET, Method::POST, Method::PUT, Method::DELETE, Method::OPTIONS])
        .allow_headers([header::AUTHORIZATION, header::CONTENT_TYPE])
        .max_age(std::time::Duration::from_secs(3600))
}
