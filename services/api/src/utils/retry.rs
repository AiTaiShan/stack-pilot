use std::time::Duration;
use tokio::time::sleep;
use tracing::warn;
use crate::error::AppError;

pub struct RetryPolicy {
    pub max_retries: u32,
    pub base_delay: Duration,
    pub max_delay: Duration,
}

pub const GIT_RETRY: RetryPolicy = RetryPolicy {
    max_retries: 3,
    base_delay: Duration::from_secs(2),
    max_delay: Duration::from_secs(30),
};

pub const DOCKER_RETRY: RetryPolicy = RetryPolicy {
    max_retries: 3,
    base_delay: Duration::from_secs(5),
    max_delay: Duration::from_secs(60),
};

pub const K8S_RETRY: RetryPolicy = RetryPolicy {
    max_retries: 3,
    base_delay: Duration::from_secs(3),
    max_delay: Duration::from_secs(30),
};

pub const HTTP_RETRY: RetryPolicy = RetryPolicy {
    max_retries: 3,
    base_delay: Duration::from_secs(1),
    max_delay: Duration::from_secs(15),
};

pub async fn with_retry<T, F, Fut>(
    policy: &RetryPolicy,
    mut operation: F,
) -> Result<T, AppError>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = Result<T, AppError>>,
{
    let mut last_error = None;

    for attempt in 0..=policy.max_retries {
        match operation().await {
            Ok(result) => return Ok(result),
            Err(e) => {
                if !e.retryable() || attempt >= policy.max_retries {
                    return Err(e);
                }
                let delay = std::cmp::min(
                    policy.base_delay * 2u32.pow(attempt),
                    policy.max_delay,
                );
                warn!("操作失败 (attempt {}/{}): {}, {}ms 后重试",
                    attempt + 1, policy.max_retries + 1, e, delay.as_millis());
                sleep(delay).await;
                last_error = Some(e);
            }
        }
    }

    Err(last_error.unwrap_or_else(|| AppError::InternalError("重试耗尽".to_string())))
}
