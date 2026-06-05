use axum::extract::ConnectInfo;
use axum::response::Response;
use std::net::SocketAddr;
use std::time::Instant;
use tracing::info;

pub async fn logging_middleware(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> Response {
    let method = request.method().clone();
    let uri = request.uri().clone();
    let start = Instant::now();

    let response = next.run(request).await;

    let elapsed = start.elapsed();
    let status = response.status();

    info!(
        "{} {} {} {}ms {}",
        method,
        uri,
        status.as_u16(),
        elapsed.as_millis(),
        addr.ip()
    );

    response
}
