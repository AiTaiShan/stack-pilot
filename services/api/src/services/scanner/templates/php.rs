pub fn generate_php_dockerfile(framework: &str, version: &str, port: u16) -> String {
    format!(r#"FROM php:{}-apache
WORKDIR /var/www/html
COPY . .
RUN docker-php-ext-install pdo pdo_mysql
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer
RUN composer install --no-dev
EXPOSE {}
CMD ["apache2-foreground"]
"#, version, port)
}
