use chrono::{Duration, Utc};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::AppError;

#[derive(Debug, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String,
    pub exp: usize,
    pub iat: usize,
    pub token_type: String,
}

impl Claims {
    pub fn new_access(user_id: Uuid, minutes: i64) -> Self {
        let now = Utc::now();
        let exp = (now + Duration::minutes(minutes)).timestamp() as usize;
        let iat = now.timestamp() as usize;
        Self {
            sub: user_id.to_string(),
            exp,
            iat,
            token_type: "access".to_string(),
        }
    }

    pub fn new_refresh(user_id: Uuid, days: i64) -> Self {
        let now = Utc::now();
        let exp = (now + Duration::days(days)).timestamp() as usize;
        let iat = now.timestamp() as usize;
        Self {
            sub: user_id.to_string(),
            exp,
            iat,
            token_type: "refresh".to_string(),
        }
    }
}

pub fn create_access_token(
    user_id: Uuid,
    secret: &str,
    minutes: i64,
) -> Result<String, AppError> {
    let claims = Claims::new_access(user_id, minutes);
    encode(
        &Header::default(),
        &claims,
        &EncodingKey::from_secret(secret.as_bytes()),
    )
    .map_err(|e| AppError::AuthError(e.to_string()))
}

pub fn create_refresh_token(
    user_id: Uuid,
    secret: &str,
    days: i64,
) -> Result<String, AppError> {
    let claims = Claims::new_refresh(user_id, days);
    encode(
        &Header::default(),
        &claims,
        &EncodingKey::from_secret(secret.as_bytes()),
    )
    .map_err(|e| AppError::AuthError(e.to_string()))
}

pub fn verify_token(token: &str, secret: &str) -> Result<Claims, AppError> {
    decode::<Claims>(
        token,
        &DecodingKey::from_secret(secret.as_bytes()),
        &Validation::default(),
    )
    .map(|data| data.claims)
    .map_err(|e| AppError::AuthError(e.to_string()))
}
