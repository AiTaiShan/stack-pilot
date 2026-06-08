use tracing::info;
use uuid::Uuid;
use sea_orm::EntityTrait;
use tokio::io::AsyncWriteExt;
use crate::error::AppError;
use crate::models::deployment::{Entity as DeploymentEntity};

pub async fn execute(
    db: sea_orm::DatabaseConnection,
    deployment_id: Uuid,
) -> Result<(), AppError> {
    info!("步骤 7: 配置服务 - 部署 {}", deployment_id);

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

    match dep.platform.as_str() {
        "docker" | "local" => {
            let env_path = repo_dir.join(".env");
            if env_path.exists() {
                info!(".env 文件已就绪: {:?}", env_path);
            }

            let compose_path = repo_dir.join("docker-compose.yml");
            if compose_path.exists() {
                info!("docker-compose.yml 已就绪: {:?}", compose_path);
            }

            info!("Docker 平台配置完成");
        }
        "k8s" => {
            let env_path = repo_dir.join(".env");
            if env_path.exists() {
                let name = dep.git_url
                    .as_ref()
                    .and_then(|u| u.rsplit('/').next())
                    .unwrap_or("app")
                    .replace(".git", "")
                    .to_lowercase();
                let namespace = format!("stackpilot-{}", deployment_id);
                let configmap_name = format!("{}-env", name);

                // 创建 ConfigMap：直接用 --from-env-file 指向 .env 文件路径
                let env_path_str = env_path.to_string_lossy().to_string();
                let output = tokio::process::Command::new("kubectl")
                    .args(["create", "configmap", &configmap_name,
                           &format!("--from-env-file={}", env_path_str),
                           "-n", &namespace,
                           "--dry-run=client", "-o", "yaml"])
                    .output()
                    .await;

                match output {
                    Ok(out) if out.status.success() => {
                        let yaml = String::from_utf8_lossy(&out.stdout);

                        // apply ConfigMap：将 yaml 写入 stdin
                        let mut child = tokio::process::Command::new("kubectl")
                            .args(["apply", "-f", "-"])
                            .stdin(std::process::Stdio::piped())
                            .stdout(std::process::Stdio::piped())
                            .stderr(std::process::Stdio::piped())
                            .spawn()
                            .map_err(|e| AppError::InternalError(format!("kubectl apply 启动失败: {}", e)))?;

                        if let Some(mut stdin) = child.stdin.take() {
                            stdin.write_all(yaml.as_bytes()).await
                                .map_err(|e| AppError::InternalError(format!("写入 stdin 失败: {}", e)))?;
                            drop(stdin);
                        }

                        let result = child.wait_with_output().await;
                        match result {
                            Ok(a) if a.status.success() => {
                                info!("ConfigMap {} 创建成功", configmap_name);
                            }
                            Ok(a) => {
                                let stderr = String::from_utf8_lossy(&a.stderr);
                                info!("ConfigMap 创建失败（非致命）: {}", stderr.trim());
                            }
                            Err(e) => {
                                info!("ConfigMap 创建失败（非致命）: {}", e);
                            }
                        }
                    }
                    Ok(out) => {
                        let stderr = String::from_utf8_lossy(&out.stderr);
                        info!("ConfigMap 生成失败（非致命）: {}", stderr.trim());
                    }
                    Err(e) => {
                        info!("kubectl 命令执行失败（非致命）: {}", e);
                    }
                }
            } else {
                info!("无 .env 文件，跳过 ConfigMap 创建");
            }

            info!("Kubernetes 平台配置完成");
        }
        _ => {
            info!("未知平台，跳过配置");
        }
    }

    info!("步骤 7 完成: 服务配置");
    Ok(())
}
