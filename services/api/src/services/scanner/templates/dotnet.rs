pub fn generate_dotnet_dockerfile(framework: &str, version: &str, port: u16) -> String {
    format!(r#"FROM mcr.microsoft.com/dotnet/sdk:{} AS builder
WORKDIR /app
COPY *.csproj ./
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o out

FROM mcr.microsoft.com/dotnet/aspnet:{}
WORKDIR /app
COPY --from=builder /app/out .
EXPOSE {}
CMD ["dotnet", "app.dll"]
"#, version, version, port)
}
