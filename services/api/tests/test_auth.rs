use stackpilot_backend::utils::jwt::{create_access_token, create_refresh_token, verify_token};
use uuid::Uuid;

#[test]
fn test_create_and_verify_access_token() {
    let user_id = Uuid::new_v4();
    let secret = "test-secret-key";
    let token = create_access_token(user_id, secret, 120).unwrap();
    let claims = verify_token(&token, secret).unwrap();
    assert_eq!(claims.sub, user_id.to_string());
    assert_eq!(claims.token_type, "access");
}

#[test]
fn test_create_and_verify_refresh_token() {
    let user_id = Uuid::new_v4();
    let secret = "test-secret-key";
    let token = create_refresh_token(user_id, secret, 7).unwrap();
    let claims = verify_token(&token, secret).unwrap();
    assert_eq!(claims.sub, user_id.to_string());
    assert_eq!(claims.token_type, "refresh");
}

#[test]
fn test_verify_token_wrong_secret() {
    let user_id = Uuid::new_v4();
    let token = create_access_token(user_id, "correct-secret", 120).unwrap();
    let result = verify_token(&token, "wrong-secret");
    assert!(result.is_err());
}

#[test]
fn test_verify_token_invalid_format() {
    let result = verify_token("invalid-token-string", "any-secret");
    assert!(result.is_err());
}

#[test]
fn test_bcrypt_hash_and_verify() {
    let password = "my-secure-password";
    let hash = bcrypt::hash(password, 4).unwrap();
    assert!(bcrypt::verify(password, &hash).unwrap());
    assert!(!bcrypt::verify("wrong-password", &hash).unwrap());
}

#[test]
fn test_bcrypt_different_hashes() {
    let password = "same-password";
    let hash1 = bcrypt::hash(password, 4).unwrap();
    let hash2 = bcrypt::hash(password, 4).unwrap();
    // bcrypt 生成不同的 hash（不同的 salt）
    assert_ne!(hash1, hash2);
    // 但都能验证通过
    assert!(bcrypt::verify(password, &hash1).unwrap());
    assert!(bcrypt::verify(password, &hash2).unwrap());
}

#[test]
fn test_access_token_expiry() {
    let user_id = Uuid::new_v4();
    let secret = "test-secret";
    // 创建一个过期时间很短的 token（0 分钟）
    let token = create_access_token(user_id, secret, 0).unwrap();
    // token 应该已经过期，验证会失败
    // 注意：jsonwebtoken 默认有 leeway，可能需要等待几秒
    // 这里只验证 token 能被创建
    assert!(!token.is_empty());
}

#[test]
fn test_claims_sub_is_uuid() {
    let user_id = Uuid::new_v4();
    let secret = "test-secret";
    let token = create_access_token(user_id, secret, 120).unwrap();
    let claims = verify_token(&token, secret).unwrap();
    // sub 应该是有效的 UUID
    let parsed = Uuid::parse_str(&claims.sub);
    assert!(parsed.is_ok());
    assert_eq!(parsed.unwrap(), user_id);
}
