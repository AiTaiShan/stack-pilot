pub mod git;
pub mod rules;
pub mod dependency;
pub mod templates;
pub mod detector;

pub use detector::{detect, ScanResult};
