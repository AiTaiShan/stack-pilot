use std::path::Path;
use tracing::info;
use crate::error::AppError;

/// 为前端项目生成 nginx.conf
pub fn generate_nginx_conf(
    frontend_port: u16,
    api_prefix: &str,
    gateway_service: &str,
    gateway_port: u16,
) -> String {
    format!(
        r#"server {{
    listen {frontend_port};
    server_name localhost;

    # 前端静态文件
    location / {{
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }}

    # API 反向代理
    location {api_prefix} {{
        proxy_pass http://{gateway_service}:{gateway_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }}

    # 健康检查
    location /health {{
        access_log off;
        return 200 'OK';
        add_header Content-Type text/plain;
    }}
}}
"#,
        frontend_port = frontend_port,
        api_prefix = api_prefix,
        gateway_service = gateway_service,
        gateway_port = gateway_port,
    )
}

/// 为前端项目生成 Dockerfile（带 nginx 反向代理）
pub fn generate_frontend_dockerfile(
    build_cmd: &str,
    output_dir: &str,
    frontend_port: u16,
    api_prefix: &str,
    gateway_service: &str,
    gateway_port: u16,
) -> String {
    let nginx_conf = generate_nginx_conf(frontend_port, api_prefix, gateway_service, gateway_port);

    format!(
        r#"FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN {build_cmd}

FROM nginx:alpine
COPY --from=builder /app/{output_dir} /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE {frontend_port}
CMD ["nginx", "-g", "daemon off;"]
"#,
        build_cmd = build_cmd,
        output_dir = output_dir,
        frontend_port = frontend_port,
    )
}

/// 写入 nginx.conf 文件
pub async fn write_nginx_conf(
    repo_dir: &Path,
    frontend_port: u16,
    api_prefix: &str,
    gateway_service: &str,
    gateway_port: u16,
) -> Result<(), AppError> {
    let nginx_conf = generate_nginx_conf(frontend_port, api_prefix, gateway_service, gateway_port);
    let conf_path = repo_dir.join("nginx.conf");

    tokio::fs::write(&conf_path, &nginx_conf).await
        .map_err(|e| AppError::InternalError(format!("写入 nginx.conf 失败: {}", e)))?;

    info!("已生成 nginx.conf: {:?}", conf_path);
    Ok(())
}
