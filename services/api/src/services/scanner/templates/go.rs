pub fn generate_go_dockerfile(framework: &str, version: &str, port: u16) -> String {
    format!(r#"FROM golang:{}-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o main .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/main .
EXPOSE {}
CMD ["./main"]
"#, version, port)
}
