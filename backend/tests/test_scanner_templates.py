#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dockerfile 模板单元测试

测试各语言模板的 generate() 函数是否正确生成 Dockerfile 内容。
"""

import pytest
from app.services.scanner.templates.node_template import generate


def test_node_template_basic():
    """测试标准 Node.js 模板"""
    df = generate(port=3000, build_cmd="npm run build", start_cmd="npm start", framework="")
    assert "FROM node:18-alpine" in df
    assert "EXPOSE 3000" in df
    assert "npm run build" in df
    assert "npm start" in df


def test_node_template_nextjs():
    """测试 Next.js 多阶段构建模板"""
    df = generate(port=3000, build_cmd="npm run build", start_cmd="npm start", framework="next")
    assert "FROM node:18-alpine AS" in df
    assert "COPY --from=builder" in df


def test_node_template_pnpm():
    """测试 pnpm 包管理器模板"""
    df = generate(port=3000, build_cmd="pnpm run build", start_cmd="pnpm start", framework="")
    assert "npm install -g pnpm" in df
    assert "pnpm run build" in df


def test_node_template_yarn():
    """测试 yarn 包管理器模板"""
    df = generate(port=3000, build_cmd="yarn build", start_cmd="yarn start", framework="")
    assert "yarn build" in df
    assert "yarn start" in df


from app.services.scanner.templates.python_template import generate as py_gen


def test_python_template_django():
    """测试 Python Django 模板"""
    df = py_gen(port=8000, build_cmd="pip install -r requirements.txt", start_cmd="python manage.py runserver", framework="django")
    assert "FROM python:3.11-slim" in df
    assert "python manage.py runserver" in df
    assert "EXPOSE 8000" in df


def test_python_template_fastapi():
    """测试 Python FastAPI 模板"""
    df = py_gen(port=8000, build_cmd="pip install -r requirements.txt", start_cmd="uvicorn main:app --host 0.0.0.0", framework="fastapi")
    assert "FROM python:3.11-slim" in df
    assert "uvicorn main:app" in df


def test_python_template_generic():
    """测试 Python 通用模板"""
    df = py_gen(port=8000, build_cmd="pip install -r requirements.txt", start_cmd="python app.py", framework="")
    assert "FROM python:3.11-slim" in df
    assert "python app.py" in df


from app.services.scanner.templates.go_template import generate as go_gen


def test_go_template():
    """测试 Go 多阶段构建模板"""
    df = go_gen(port=8080, build_cmd="go build -o main .", start_cmd="./main", framework="")
    assert "FROM golang:1.21-alpine AS builder" in df
    assert "go build -o main" in df
    assert "EXPOSE 8080" in df
    # 多阶段构建到 alpine
    assert "FROM alpine:latest" in df
    assert "COPY --from=builder" in df


from app.services.scanner.templates.rust_template import generate as rs_gen


def test_rust_template():
    """测试 Rust 多阶段构建模板"""
    df = rs_gen(port=8080, build_cmd="cargo build --release", start_cmd="./target/release/app", framework="")
    assert "FROM rust:1.75-slim AS builder" in df
    assert "cargo build --release" in df
    assert "FROM debian:bookworm-slim" in df
    assert "EXPOSE 8080" in df


from app.services.scanner.templates.java_template import generate as java_gen


def test_java_template_spring_boot():
    """测试 Java Spring Boot 多阶段构建模板"""
    df = java_gen(port=8080, build_cmd="mvn package -DskipTests", start_cmd="java -jar app.jar", framework="spring-boot")
    assert "FROM eclipse-temurin:17-jdk-alpine AS builder" in df
    assert "mvn package -DskipTests" in df
    assert "FROM eclipse-temurin:17-jre-alpine" in df
    assert "COPY --from=builder" in df
    assert "EXPOSE 8080" in df


from app.services.scanner.templates.php_template import generate as php_gen


def test_php_template():
    """测试 PHP 通用模板"""
    df = php_gen(port=80, build_cmd="composer install --no-dev", start_cmd="", framework="")
    assert "FROM php:8.2-apache" in df
    assert "composer install --no-dev" in df
    assert "EXPOSE 80" in df
    assert 'CMD ["apache2-foreground"]' in df


def test_php_template_laravel():
    """测试 PHP Laravel 模板"""
    df = php_gen(port=80, build_cmd="composer install", start_cmd="php artisan serve", framework="laravel")
    assert "FROM php:8.2-apache" in df
    assert "composer install" in df


from app.services.scanner.templates.ruby_template import generate as rb_gen


def test_ruby_template_rails():
    """测试 Ruby Rails 模板"""
    df = rb_gen(port=3000, build_cmd="bundle install", start_cmd="bundle exec rails server", framework="rails")
    assert "FROM ruby:3.2-slim" in df
    assert "bundle install" in df
    assert "bundle exec rails server" in df
    assert "EXPOSE 3000" in df


def test_ruby_template_sinatra():
    """测试 Ruby Sinatra 模板"""
    df = rb_gen(port=4567, build_cmd="bundle install", start_cmd="ruby app.rb", framework="sinatra")
    assert "FROM ruby:3.2-slim" in df
    assert "EXPOSE 4567" in df


from app.services.scanner.templates.dotnet_template import generate as dn_gen


def test_dotnet_template():
    """测试 .NET 多阶段构建模板"""
    df = dn_gen(port=5000, build_cmd="dotnet publish -c Release -o out", start_cmd="", framework="")
    assert "FROM mcr.microsoft.com/dotnet/sdk:8.0 AS builder" in df
    assert "dotnet publish -c Release -o out" in df
    assert "FROM mcr.microsoft.com/dotnet/aspnet:8.0" in df
    assert "EXPOSE 5000" in df
