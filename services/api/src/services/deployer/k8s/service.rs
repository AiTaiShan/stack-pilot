use tracing::info;
use crate::error::AppError;
use super::deployment::K8sService;

impl K8sService {
    pub async fn create_service(
        &self,
        namespace: &str,
        name: &str,
        port: u16,
        target_port: u16,
        service_type: &str,
    ) -> Result<(), AppError> {
        info!("创建 K8s Service: {}/{}", namespace, name);

        let mut cmd = tokio::process::Command::new("kubectl");
        cmd.arg("expose").arg("deployment").arg(name)
            .arg("--port").arg(port.to_string())
            .arg("--target-port").arg(target_port.to_string())
            .arg("--type").arg(service_type)
            .arg("-n").arg(namespace);

        if let Some(ref kc) = self.kubeconfig {
            cmd.arg("--kubeconfig").arg(kc);
        }

        let output = cmd.output().await
            .map_err(|e| AppError::InternalError(format!("kubectl 命令执行失败: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(AppError::InternalError(format!("创建 Service 失败: {}", stderr)));
        }

        info!("Service 创建成功: {}/{}", namespace, name);
        Ok(())
    }

    pub async fn create_namespace(
        &self,
        namespace: &str,
    ) -> Result<(), AppError> {
        info!("创建 K8s Namespace: {}", namespace);

        let mut cmd = tokio::process::Command::new("kubectl");
        cmd.arg("create").arg("namespace").arg(namespace);

        if let Some(ref kc) = self.kubeconfig {
            cmd.arg("--kubeconfig").arg(kc);
        }

        let output = cmd.output().await
            .map_err(|e| AppError::InternalError(format!("kubectl 命令执行失败: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            // 忽略已存在的错误
            if !stderr.contains("AlreadyExists") {
                return Err(AppError::InternalError(format!("创建 Namespace 失败: {}", stderr)));
            }
        }

        info!("Namespace 创建成功: {}", namespace);
        Ok(())
    }

    pub async fn create_ingress(
        &self,
        name: &str,
        host: &str,
        service_name: &str,
        port: u16,
    ) -> Result<(), AppError> {
        info!("创建 K8s Ingress: {} -> {}:{}", name, service_name, port);

        let yaml = format!(
            r#"apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: {}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {}
            port:
              number: {}
"#,
            name, host, service_name, port
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

        info!("Ingress 创建成功: {}", name);
        Ok(())
    }

    pub async fn delete_ingress(&self, name: &str) -> Result<(), AppError> {
        info!("删除 K8s Ingress: {}", name);

        tokio::process::Command::new("kubectl")
            .args(["delete", "ingress", name, "--ignore-not-found"])
            .output()
            .await
            .ok();

        info!("Ingress 删除完成: {}", name);
        Ok(())
    }
}
