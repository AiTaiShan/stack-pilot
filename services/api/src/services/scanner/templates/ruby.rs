#![allow(dead_code)]
pub fn generate_ruby_dockerfile(_framework: &str, version: &str, port: u16) -> String {
    format!(r#"FROM ruby:{}-slim
WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN bundle install
COPY . .
EXPOSE {}
CMD ["bundle", "exec", "rails", "server", "-b", "0.0.0.0"]
"#, version, port)
}
