use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 8: 验证部署 - 部署 {}", deployment_id);

    let dep = DeploymentEntity::find_by_id(deployment_id).one(&db).await
        .map_err(|e| AppError::DatabaseError(e.to_string()))?
        .ok_or_else(|| AppError::NotFound("部署不存在".to_string()))?;

    // 从 config 读取 repo_dir
    let config = dep.config.as_ref()
        .and_then(|c| c.as_object())
        .cloned()
        .unwrap_or_default();

    let repo_dir_str = config.get("_repo_dir")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let repo_dir = std::path::PathBuf::from(repo_dir_str);

    // 从 git_url 提取 compose 项目名（docker compose 用目录名作项目名）
    let repo_name = dep.git_url
        .as_ref()
        .and_then(|u| u.rsplit('/').next())
        .unwrap_or("app")
        .replace(".git", "")
        .to_lowercase();

    match dep.platform.as_str() {
        "docker" => {
            // 用 docker compose ps 检查容器状态
            let output = tokio::process::Command::new("docker")
                .args(["compose", "ps", "--format", "json"])
                .current_dir(&repo_dir)
                .output()
                .await;

            match output {
                Ok(out) if out.status.success() => {
                    let stdout = String::from_utf8_lossy(&out.stdout);
                    if stdout.trim().is_empty() {
                        // 回退到旧版 docker-compose
                        let output2 = tokio::process::Command::new("docker-compose")
                            .args(["ps"])
                            .current_dir(&repo_dir)
                            .output()
                            .await;
                        match output2 {
                            Ok(out2) if out2.status.success() => {
                                let stdout2 = String::from_utf8_lossy(&out2.stdout);
                                if stdout2.contains("Up") {
                                    info!("容器运行正常（docker-compose）");
                                } else {
                                    info!("警告: 未找到运行中的容器");
                                }
                            }
                            _ => {
                                info!("警告: 无法检查容器状态");
                            }
                        }
                    } else {
                        // 解析 compose ps JSON 输出
                        if stdout.contains("\"running\"") || stdout.contains("\"Up\"") {
                            info!("容器运行正常");
                        } else {
                            info!("警告: 容器状态异常: {}", stdout.trim());
                        }
                    }
                }
                _ => {
                    // 回退：用 docker ps 按 compose 项目名过滤
                    let output2 = tokio::process::Command::new("docker")
                        .args(["ps", "--filter", &format!("name={}", repo_name), "--format", "{{.Names}} {{.Status}}"])
                        .output()
                        .await;
                    match output2 {
                        Ok(out2) if out2.status.success() => {
                            let stdout2 = String::from_utf8_lossy(&out2.stdout);
                            if stdout2.trim().is_empty() {
                                info!("警告: 未找到运行中的容器");
                            } else {
                                info!("容器状态:\n{}", stdout2.trim());
                            }
                        }
                        _ => {
                            info!("警告: 无法检查容器状态");
                        }
                    }
                }
            }
        }
        "k8s" => {
            // 检查 K8s Deployment 是否 ready
            let name = dep.git_url
                .as_ref()
                .and_then(|u| u.rsplit('/').next())
                .unwrap_or("app")
                .replace(".git", "")
                .to_lowercase();
            let namespace = format!("stackpilot-{}", deployment_id);

            let output = tokio::process::Command::new("kubectl")
                .args(["get", "deployment", &name, "-n", &namespace, "-o", "jsonpath={.status.readyReplicas}"])
                .output()
                .await;

            match output {
                Ok(out) if out.status.success() => {
                    let stdout = String::from_utf8_lossy(&out.stdout);
                    let ready: u32 = stdout.trim().parse().unwrap_or(0);
                    if ready > 0 {
                        info!("Kubernetes 部署验证通过: {} 个 Pod 就绪", ready);
                    } else {
                        info!("警告: Kubernetes 部署无就绪 Pod");
                    }
                }
                Ok(out) => {
                    let stderr = String::from_utf8_lossy(&out.stderr);
                    info!("Kubernetes 验证失败: {}", stderr.trim());
                }
                Err(e) => {
                    info!("kubectl 命令执行失败: {}", e);
                }
            }
        }
        _ => {
            info!("未知平台，跳过验证");
        }
    }

    info!("步骤 8 完成: 部署验证");
    Ok(())
}
