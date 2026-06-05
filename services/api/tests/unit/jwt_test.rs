use uuid::Uuid;
use stackpilot_backend::utils::jwt::{create_access_token, create_refresh_token, verify_token};

#[test]
fn test_create_and_verify_access_token() {
    let user_id = Uuid::new_v4();
    let secret = "test-secret-key";

    let token = create_access_token(user_id, secret, 120).unwrap();
    assert!(!token.is_empty());

    let claims = verify_token(&token, secret).unwrap();
    assert_eq!(claims.sub, user_id.to_string());
    assert_eq!(claims.token_type, "access");
}

#[test]
fn test_create_and_verify_refresh_token() {
    let user_id = Uuid::new_v4();
    let secret = "test-secret-key";

    let token = create_refresh_token(user_id, secret, 7).unwrap();
    assert!(!token.is_empty());

    let claims = verify_token(&token, secret).unwrap();
    assert_eq!(claims.sub, user_id.to_string());
    assert_eq!(claims.token_type, "refresh");
}

#[test]
fn test_verify_invalid_token() {
    let result = verify_token("invalid-token", "secret");
    assert!(result.is_err());
}

#[test]
fn test_verify_wrong_secret() {
    let user_id = Uuid::new_v4();
    let token = create_access_token(user_id, "secret1", 120).unwrap();

    let result = verify_token(&token, "secret2");
    assert!(result.is_err());
}

#[test]
fn test_create_access_token_different_users() {
    let user1 = Uuid::new_v4();
    let user2 = Uuid::new_v4();
    let secret = "test-secret";

    let token1 = create_access_token(user1, secret, 120).unwrap();
    let token2 = create_access_token(user2, secret, 120).unwrap();

    let claims1 = verify_token(&token1, secret).unwrap();
    let claims2 = verify_token(&token2, secret).unwrap();

    assert_ne!(claims1.sub, claims2.sub);
    assert_eq!(claims1.sub, user1.to_string());
    assert_eq!(claims2.sub, user2.to_string());
}
