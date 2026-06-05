use crate::error::AppError;

pub async fn list_remote_branches(git_url: &str) -> Result<Vec<String>, AppError> {
    let output = tokio::process::Command::new("git")
        .arg("ls-remote")
        .arg("--heads")
        .arg(git_url)
        .output()
        .await
        .map_err(|e| AppError::InternalError(format!("Git 命令执行失败: {}", e)))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(AppError::InternalError(format!("获取分支列表失败: {}", stderr)));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let branches: Vec<String> = stdout
        .lines()
        .filter_map(|line| {
            line.split('\t').nth(1).map(|ref_name| {
                ref_name.replace("refs/heads/", "")
            })
        })
        .collect();

    Ok(branches)
}
