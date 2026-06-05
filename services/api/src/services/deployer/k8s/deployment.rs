use tracing::info;
use crate::error::AppError;

pub struct K8sService {
    pub(crate) kubeconfig: Option<String>,
}

impl K8sService {
    pub fn new(kubeconfig: Option<&str>) -> Self {
        Self {
            kubeconfig: kubeconfig.map(|s| s.to_string()),
        }
    }

    pub async fn create_deployment(
        &self,
        namespace: &str,
        name: &str,
        image: &str,
        replicas: i32,
        _port: u16,
        _env_vars: Option<Vec<(String, String)>>,
    ) -> Result<(), AppError> {
        info!("创建 K8s Deployment: {}/{}", namespace, name);

        let mut cmd = tokio::process::Command::new("kubectl");
        cmd.arg("create").arg("deployment").arg(name)
            .arg("--image").arg(image)
            .arg("--replicas").arg(replicas.to_string())
            .arg("-n").arg(namespace);

        if let Some(ref kc) = self.kubeconfig {
            cmd.arg("--kubeconfig").arg(kc);
        }

        let output = cmd.output().await
            .map_err(|e| AppError::InternalError(format!("kubectl 命令执行失败: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(AppError::InternalError(format!("创建 Deployment 失败: {}", stderr)));
        }

        info!("Deployment 创建成功: {}/{}", namespace, name);
        Ok(())
    }

    pub async fn create_deployment_with_env(
        &self,
        name: &str,
        image: &str,
        env_vars: Vec<(String, String)>,
    ) -> Result<(), AppError> {
        info!("创建 K8s Deployment (带环境变量): {}", name);

        let env_section: String = if env_vars.is_empty() {
            String::new()
        } else {
            let mut lines = String::from("        env:\n");
            for (k, v) in &env_vars {
                lines.push_str(&format!("        - name: {}\n          value: \"{}\"\n", k, v));
            }
            lines
        };

        let yaml = format!(
            r#"apiVersion: apps/v1
kind: Deployment
metadata:
  name: {}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {}
  template:
    metadata:
      labels:
        app: {}
    spec:
      containers:
      - name: {}
        image: {}
        ports:
        - containerPort: 8080
{}"#,
            name, name, name, name, image, env_section
        );

        let mut child = tokio::process::Command::new("kubectl")
            .args(["apply", "-f", "-"])
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| AppError::K8sError {
                code: "KUBECTL_FAILED".to_string(),
                message: format!("kubectl 启动失败: {}", e),
            })?;

        if let Some(mut stdin) = child.stdin.take() {
            use tokio::io::AsyncWriteExt;
            stdin.write_all(yaml.as_bytes()).await.ok();
        }

        let output = child.wait_with_output().await.map_err(|e| AppError::K8sError {
            code: "KUBECTL_FAILED".to_string(),
            message: format!("kubectl 执行失败: {}", e),
        })?;

        if !output.status.success() {
            return Err(AppError::K8sError {
                code: "APPLY_FAILED".to_string(),
                message: String::from_utf8_lossy(&output.stderr).to_string(),
            });
        }

        self.wait_for_deployment(name, 300).await
    }

    pub async fn wait_for_deployment(
        &self,
        name: &str,
        timeout_secs: u64,
    ) -> Result<(), AppError> {
        info!("等待 Deployment 就绪: {} (超时 {}s)", name, timeout_secs);

        let start = std::time::Instant::now();
        loop {
            let output = tokio::process::Command::new("kubectl")
                .args(["rollout", "status", "deployment", name, "--timeout=10s"])
                .output()
                .await;

            if let Ok(o) = output {
                if o.status.success() {
                    info!("Deployment 已就绪: {}", name);
                    return Ok(());
                }
            }

            if start.elapsed().as_secs() > timeout_secs {
                return Err(AppError::K8sError {
                    code: "WAIT_TIMEOUT".to_string(),
                    message: format!("Deployment {} 未在 {}s 内就绪", name, timeout_secs),
                });
            }

            tokio::time::sleep(std::time::Duration::from_secs(5)).await;
        }
    }

    pub async fn delete_deployment(
        &self,
        namespace: &str,
        name: &str,
    ) -> Result<(), AppError> {
        info!("删除 K8s Deployment: {}/{}", namespace, name);

        let mut cmd = tokio::process::Command::new("kubectl");
        cmd.arg("delete").arg("deployment").arg(name)
            .arg("-n").arg(namespace);

        if let Some(ref kc) = self.kubeconfig {
            cmd.arg("--kubeconfig").arg(kc);
        }

        let output = cmd.output().await
            .map_err(|e| AppError::InternalError(format!("kubectl 命令执行失败: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(AppError::InternalError(format!("删除 Deployment 失败: {}", stderr)));
        }

        info!("Deployment 删除成功: {}/{}", namespace, name);
        Ok(())
    }

    pub async fn scale_deployment(
        &self,
        namespace: &str,
        name: &str,
        replicas: i32,
    ) -> Result<(), AppError> {
        info!("扩缩容 K8s Deployment: {}/{} -> {} replicas", namespace, name, replicas);

        let mut cmd = tokio::process::Command::new("kubectl");
        cmd.arg("scale").arg("deployment").arg(name)
            .arg("--replicas").arg(replicas.to_string())
            .arg("-n").arg(namespace);

        if let Some(ref kc) = self.kubeconfig {
            cmd.arg("--kubeconfig").arg(kc);
        }

        let output = cmd.output().await
            .map_err(|e| AppError::InternalError(format!("kubectl 命令执行失败: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(AppError::InternalError(format!("扩缩容失败: {}", stderr)));
        }

        info!("扩缩容成功: {}/{}", namespace, name);
        Ok(())
    }
}
