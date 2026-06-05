pub fn generate_java_dockerfile(framework: &str, version: &str, port: u16) -> String {
    format!(r#"FROM maven:3.9-eclipse-temurin-{} AS builder
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn package -DskipTests

FROM eclipse-temurin:{}-jre
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
EXPOSE {}
CMD ["java", "-jar", "app.jar"]
"#, version, version, port)
}
