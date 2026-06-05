use stackpilot_backend::error::AppError;
use stackpilot_backend::utils::retry::{with_retry, GIT_RETRY, DOCKER_RETRY, HTTP_RETRY};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;

#[tokio::test]
async fn test_retry_success_first_attempt() {
    let result = with_retry(&GIT_RETRY, || async { Ok::<_, AppError>(42) }).await;
    assert_eq!(result.unwrap(), 42);
}

#[tokio::test]
async fn test_retry_success_after_failure() {
    let attempts = Arc::new(AtomicU32::new(0));
    let attempts_clone = attempts.clone();
    let result = with_retry(&HTTP_RETRY, move || {
        let a = attempts_clone.clone();
        async move {
            if a.fetch_add(1, Ordering::SeqCst) < 2 {
                Err(AppError::NetworkError("fail".to_string()))
            } else {
                Ok(42)
            }
        }
    }).await;
    assert_eq!(result.unwrap(), 42);
    assert!(attempts.load(Ordering::SeqCst) >= 3);
}

#[tokio::test]
async fn test_retry_non_retryable_error() {
    let attempts = Arc::new(AtomicU32::new(0));
    let attempts_clone = attempts.clone();
    let result: Result<i32, _> = with_retry(&DOCKER_RETRY, move || {
        let a = attempts_clone.clone();
        async move {
            a.fetch_add(1, Ordering::SeqCst);
            Err(AppError::ValidationError("not retryable".to_string()))
        }
    }).await;
    assert!(result.is_err());
    assert_eq!(attempts.load(Ordering::SeqCst), 1); // 不重试
}

#[tokio::test]
async fn test_retry_exhaustion() {
    let attempts = Arc::new(AtomicU32::new(0));
    let attempts_clone = attempts.clone();
    let result: Result<i32, _> = with_retry(&HTTP_RETRY, move || {
        let a = attempts_clone.clone();
        async move {
            a.fetch_add(1, Ordering::SeqCst);
            Err(AppError::NetworkError("always fail".to_string()))
        }
    }).await;
    assert!(result.is_err());
    assert_eq!(attempts.load(Ordering::SeqCst), 4); // 1 initial + 3 retries
}
