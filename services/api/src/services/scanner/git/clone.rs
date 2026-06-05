#![allow(dead_code)]
use std::path::PathBuf;
use tracing::info;
use crate::error::AppError;

pub struct GitService {
    temp_dir: PathBuf,
}

impl GitService {
    pub fn new(temp_dir: &str) -> Self {
        Self {
            temp_dir: PathBuf::from(temp_dir),
        }
    }

    pub async fn clone(&self, git_url: &str, branch: Option<&str>) -> Result<PathBuf, AppError> {
        let repo_name = git_url
            .rsplit('/')
            .next()
            .unwrap_or("repo")
            .replace(".git", "")
            .to_lowercase();

        let target_dir = self.temp_dir.join(&repo_name);

        info!("克隆仓库: {} -> {:?}", git_url, target_dir);

        let mut cmd = tokio::process::Command::new("git");
        cmd.arg("clone")
            .arg("--depth")
            .arg("1");

        if let Some(b) = branch {
            cmd.arg("--branch").arg(b);
        }

        cmd.arg(git_url).arg(&target_dir);

        let output = cmd.output().await
            .map_err(|e| AppError::InternalError(format!("Git 命令执行失败: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(AppError::InternalError(format!("Git 克隆失败: {}", stderr)));
        }

        info!("克隆完成: {:?}", target_dir);
        Ok(target_dir)
    }

    pub async fn get_latest_commit(&self, repo_dir: &PathBuf) -> Result<CommitInfo, AppError> {
        let output = tokio::process::Command::new("git")
            .arg("log")
            .arg("-1")
            .arg("--format=%H%n%an%n%s")
            .current_dir(repo_dir)
            .output()
            .await
            .map_err(|e| AppError::InternalError(format!("Git 命令执行失败: {}", e)))?;

        if !output.status.success() {
            return Err(AppError::InternalError("获取提交信息失败".to_string()));
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        let lines: Vec<&str> = stdout.trim().split('\n').collect();

        Ok(CommitInfo {
            hash: lines.first().unwrap_or(&"").to_string(),
            author: lines.get(1).unwrap_or(&"").to_string(),
            message: lines.get(2).unwrap_or(&"").to_string(),
        })
    }
}

pub struct CommitInfo {
    pub hash: String,
    pub author: String,
    pub message: String,
}
