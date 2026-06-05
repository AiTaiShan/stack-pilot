pub fn generate_node_dockerfile(framework: &str, version: &str, port: u16) -> String {
    let base_image = format!("node:{}", version);

    match framework {
        "express" | "fastify" | "koa" => format!(
            r#"FROM {base_image} AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

FROM {base_image}-slim

WORKDIR /app

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app .

EXPOSE {port}

CMD ["node", "index.js"]
"#,
            base_image = base_image,
            port = port
        ),
        _ => format!(
            r#"FROM {base_image}

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE {port}

CMD ["npm", "start"]
"#,
            base_image = base_image,
            port = port
        ),
    }
}
