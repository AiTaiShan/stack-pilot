#![allow(dead_code)]
pub fn generate_rust_dockerfile(_framework: &str, version: &str, port: u16) -> String {
    format!(r#"FROM rust:{} AS builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/target/release/app .
EXPOSE {}
CMD ["./app"]
"#, version, port)
}
