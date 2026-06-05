#![allow(dead_code)]
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use governor::{Quota, RateLimiter};
use std::num::NonZeroU32;
use std::sync::Arc;

pub type IpRateLimiter = Arc<
    RateLimiter<
        governor::state::NotKeyed,
        governor::state::InMemoryState,
        governor::clock::DefaultClock,
        governor::middleware::NoOpMiddleware,
    >,
>;

pub fn create_rate_limiter() -> IpRateLimiter {
    let quota = Quota::per_minute(NonZeroU32::new(300).unwrap());
    Arc::new(RateLimiter::direct(quota))
}

pub async fn rate_limit_middleware(
    axum::extract::State(limiter): axum::extract::State<IpRateLimiter>,
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> Response {
    match limiter.check() {
        Ok(_) => next.run(request).await,
        Err(_) => {
            let body = axum::Json(serde_json::json!({
                "code": 42901,
                "message": "请求过于频繁，请稍后重试",
                "severity": "LOW",
                "retryable": false,
                "timestamp": chrono::Utc::now().naive_utc().format("%Y-%m-%dT%H:%M:%S%.fZ").to_string(),
            }));
            (StatusCode::TOO_MANY_REQUESTS, body).into_response()
        }
    }
}
