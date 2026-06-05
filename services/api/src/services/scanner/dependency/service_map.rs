use std::collections::HashMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExternalService {
    pub name: String,
    pub category: String,
    pub image: String,
    pub default_port: u16,
    /// 用于在不同依赖文件中匹配的关键词列表
    pub detection_keys: Vec<String>,
}

/// 获取所有外部服务映射（40+ 服务）
pub fn get_external_services() -> HashMap<String, ExternalService> {
    let mut services = HashMap::new();

    // ========== 数据库 ==========

    services.insert("mysql".to_string(), ExternalService {
        name: "mysql".to_string(),
        category: "database".to_string(),
        image: "mysql:8.0".to_string(),
        default_port: 3306,
        detection_keys: vec![
            "mysql".to_string(), "mysql2".to_string(), "pymysql".to_string(),
            "mysqlclient".to_string(), "go-sql-driver/mysql".to_string(),
        ],
    });

    services.insert("postgres".to_string(), ExternalService {
        name: "postgres".to_string(),
        category: "database".to_string(),
        image: "postgres:15".to_string(),
        default_port: 5432,
        detection_keys: vec![
            "pg".to_string(), "postgres".to_string(), "postgresql".to_string(),
            "psycopg2".to_string(), "asyncpg".to_string(),
            "lib/pq".to_string(), "pgx".to_string(),
        ],
    });

    services.insert("postgresql".to_string(), ExternalService {
        name: "postgresql".to_string(),
        category: "database".to_string(),
        image: "postgres:15".to_string(),
        default_port: 5432,
        detection_keys: vec![
            "pg".to_string(), "postgres".to_string(), "postgresql".to_string(),
            "psycopg2".to_string(), "asyncpg".to_string(),
            "lib/pq".to_string(), "pgx".to_string(),
        ],
    });

    services.insert("mongodb".to_string(), ExternalService {
        name: "mongodb".to_string(),
        category: "database".to_string(),
        image: "mongo:7".to_string(),
        default_port: 27017,
        detection_keys: vec![
            "mongodb".to_string(), "mongoose".to_string(), "pymongo".to_string(),
            "mongo-driver".to_string(),
        ],
    });

    services.insert("sqlite".to_string(), ExternalService {
        name: "sqlite".to_string(),
        category: "database".to_string(),
        image: "nouchka/sqlite3:latest".to_string(),
        default_port: 0,
        detection_keys: vec![
            "sqlite".to_string(), "sqlite3".to_string(), "better-sqlite3".to_string(),
        ],
    });

    services.insert("cassandra".to_string(), ExternalService {
        name: "cassandra".to_string(),
        category: "database".to_string(),
        image: "cassandra:4.1".to_string(),
        default_port: 9042,
        detection_keys: vec![
            "cassandra".to_string(), "cassandra-driver".to_string(),
            "datastax".to_string(),
        ],
    });

    services.insert("couchdb".to_string(), ExternalService {
        name: "couchdb".to_string(),
        category: "database".to_string(),
        image: "couchdb:3".to_string(),
        default_port: 5984,
        detection_keys: vec![
            "couchdb".to_string(), "nano".to_string(), "couchdb-nano".to_string(),
        ],
    });

    // ========== 消息队列 ==========

    services.insert("kafka".to_string(), ExternalService {
        name: "kafka".to_string(),
        category: "messagequeue".to_string(),
        image: "confluentinc/cp-kafka:7.4.0".to_string(),
        default_port: 9092,
        detection_keys: vec![
            "kafka".to_string(), "kafkajs".to_string(), "kafka-node".to_string(),
            "spring-kafka".to_string(), "sarama".to_string(),
            "confluent-kafka".to_string(), "rdkafka".to_string(),
        ],
    });

    services.insert("rabbitmq".to_string(), ExternalService {
        name: "rabbitmq".to_string(),
        category: "messagequeue".to_string(),
        image: "rabbitmq:3-management".to_string(),
        default_port: 5672,
        detection_keys: vec![
            "amqplib".to_string(), "rabbitmq".to_string(),
            "spring-amqp".to_string(), "amqp".to_string(),
        ],
    });

    services.insert("rocketmq".to_string(), ExternalService {
        name: "rocketmq".to_string(),
        category: "messagequeue".to_string(),
        image: "apache/rocketmq:5.1.4".to_string(),
        default_port: 9876,
        detection_keys: vec![
            "rocketmq".to_string(), "rocketmq-client".to_string(),
        ],
    });

    services.insert("nats".to_string(), ExternalService {
        name: "nats".to_string(),
        category: "messagequeue".to_string(),
        image: "nats:2-alpine".to_string(),
        default_port: 4222,
        detection_keys: vec![
            "nats".to_string(), "nats.go".to_string(), "nats.js".to_string(),
            "nats-server".to_string(), "stan".to_string(),
        ],
    });

    services.insert("pulsar".to_string(), ExternalService {
        name: "pulsar".to_string(),
        category: "messagequeue".to_string(),
        image: "apachepulsar/pulsar:3.1.1".to_string(),
        default_port: 6650,
        detection_keys: vec![
            "pulsar".to_string(), "pulsar-client".to_string(),
        ],
    });

    // ========== 搜索引擎 ==========

    services.insert("elasticsearch".to_string(), ExternalService {
        name: "elasticsearch".to_string(),
        category: "search".to_string(),
        image: "elasticsearch:8.11.0".to_string(),
        default_port: 9200,
        detection_keys: vec![
            "elasticsearch".to_string(), "@elastic/elasticsearch".to_string(),
            "elastic".to_string(), "elasticsearch-py".to_string(),
        ],
    });

    services.insert("opensearch".to_string(), ExternalService {
        name: "opensearch".to_string(),
        category: "search".to_string(),
        image: "opensearchproject/opensearch:2.11.0".to_string(),
        default_port: 9200,
        detection_keys: vec![
            "opensearch".to_string(), "opensearch-py".to_string(),
            "@opensearch-project".to_string(),
        ],
    });

    services.insert("meilisearch".to_string(), ExternalService {
        name: "meilisearch".to_string(),
        category: "search".to_string(),
        image: "getmeili/meilisearch:v1.5".to_string(),
        default_port: 7700,
        detection_keys: vec![
            "meilisearch".to_string(), "meilisearch-go".to_string(),
        ],
    });

    services.insert("solr".to_string(), ExternalService {
        name: "solr".to_string(),
        category: "search".to_string(),
        image: "solr:9".to_string(),
        default_port: 8983,
        detection_keys: vec![
            "solr".to_string(), "solrj".to_string(), "solr-client".to_string(),
        ],
    });

    // ========== 对象存储 ==========

    services.insert("minio".to_string(), ExternalService {
        name: "minio".to_string(),
        category: "storage".to_string(),
        image: "minio/minio:latest".to_string(),
        default_port: 9000,
        detection_keys: vec![
            "minio".to_string(), "minio-go".to_string(),
            "minio-java".to_string(), "minio-py".to_string(),
        ],
    });

    services.insert("aws-sdk-s3".to_string(), ExternalService {
        name: "aws-sdk-s3".to_string(),
        category: "storage".to_string(),
        image: "amazon/aws-cli:latest".to_string(),
        default_port: 443,
        detection_keys: vec![
            "aws-sdk".to_string(), "@aws-sdk/client-s3".to_string(),
            "boto3".to_string(), "aws-sdk-go".to_string(),
        ],
    });

    services.insert("azure-storage-blob".to_string(), ExternalService {
        name: "azure-storage-blob".to_string(),
        category: "storage".to_string(),
        image: "mcr.microsoft.com/azure-storage/azurite:latest".to_string(),
        default_port: 10000,
        detection_keys: vec![
            "azure-storage".to_string(), "azure-storage-blob".to_string(),
            "Azure.Storage.Blobs".to_string(),
        ],
    });

    services.insert("cloud-storage".to_string(), ExternalService {
        name: "cloud-storage".to_string(),
        category: "storage".to_string(),
        image: "google/cloud-sdk:latest".to_string(),
        default_port: 443,
        detection_keys: vec![
            "@google-cloud/storage".to_string(), "cloud-storage".to_string(),
            "google-cloud-storage".to_string(),
        ],
    });

    // ========== 缓存 ==========

    services.insert("redis".to_string(), ExternalService {
        name: "redis".to_string(),
        category: "cache".to_string(),
        image: "redis:7-alpine".to_string(),
        default_port: 6379,
        detection_keys: vec![
            "redis".to_string(), "ioredis".to_string(),
            "jedis".to_string(), "lettuce".to_string(),
            "go-redis".to_string(), "redis-py".to_string(),
        ],
    });

    services.insert("memcached".to_string(), ExternalService {
        name: "memcached".to_string(),
        category: "cache".to_string(),
        image: "memcached:1.6-alpine".to_string(),
        default_port: 11211,
        detection_keys: vec![
            "memcached".to_string(), "memjs".to_string(),
            "pymemcache".to_string(), "gomemcache".to_string(),
        ],
    });

    // ========== 监控 ==========

    services.insert("prometheus".to_string(), ExternalService {
        name: "prometheus".to_string(),
        category: "monitoring".to_string(),
        image: "prom/prometheus:v2.47.0".to_string(),
        default_port: 9090,
        detection_keys: vec![
            "prometheus".to_string(), "prom-client".to_string(),
            "prometheus_client".to_string(), "promhttp".to_string(),
        ],
    });

    services.insert("grafana".to_string(), ExternalService {
        name: "grafana".to_string(),
        category: "monitoring".to_string(),
        image: "grafana/grafana:10.2.0".to_string(),
        default_port: 3001,
        detection_keys: vec![
            "grafana".to_string(), "grafana-client".to_string(),
        ],
    });

    services.insert("jaeger".to_string(), ExternalService {
        name: "jaeger".to_string(),
        category: "monitoring".to_string(),
        image: "jaegertracing/all-in-one:1.50".to_string(),
        default_port: 16686,
        detection_keys: vec![
            "jaeger".to_string(), "jaeger-client".to_string(),
            "jaegertracing".to_string(),
        ],
    });

    services.insert("zipkin".to_string(), ExternalService {
        name: "zipkin".to_string(),
        category: "monitoring".to_string(),
        image: "openzipkin/zipkin:latest".to_string(),
        default_port: 9411,
        detection_keys: vec![
            "zipkin".to_string(), "zipkin-reporter".to_string(),
            "spring-cloud-sleuth".to_string(),
        ],
    });

    services.insert("datadog".to_string(), ExternalService {
        name: "datadog".to_string(),
        category: "monitoring".to_string(),
        image: "datadog/agent:latest".to_string(),
        default_port: 8126,
        detection_keys: vec![
            "datadog".to_string(), "dd-trace".to_string(),
            "datadog-api-client".to_string(),
        ],
    });

    // ========== 注册中心 ==========

    services.insert("consul".to_string(), ExternalService {
        name: "consul".to_string(),
        category: "registry".to_string(),
        image: "consul:1.17".to_string(),
        default_port: 8500,
        detection_keys: vec![
            "consul".to_string(), "consul-api".to_string(),
            "hashicorp/consul".to_string(),
        ],
    });

    services.insert("etcd".to_string(), ExternalService {
        name: "etcd".to_string(),
        category: "registry".to_string(),
        image: "quay.io/coreos/etcd:v3.5.10".to_string(),
        default_port: 2379,
        detection_keys: vec![
            "etcd".to_string(), "etcd-client".to_string(),
            "go.etcd.io".to_string(),
        ],
    });

    services.insert("zookeeper".to_string(), ExternalService {
        name: "zookeeper".to_string(),
        category: "registry".to_string(),
        image: "zookeeper:3.9".to_string(),
        default_port: 2181,
        detection_keys: vec![
            "zookeeper".to_string(), "zkclient".to_string(),
            "curator".to_string(), "apache-zookeeper".to_string(),
        ],
    });

    services.insert("nacos".to_string(), ExternalService {
        name: "nacos".to_string(),
        category: "registry".to_string(),
        image: "nacos/nacos-server:v2.2.3".to_string(),
        default_port: 8848,
        detection_keys: vec![
            "nacos".to_string(), "nacos-client".to_string(),
            "spring-cloud-starter-alibaba-nacos".to_string(),
        ],
    });

    services.insert("eureka".to_string(), ExternalService {
        name: "eureka".to_string(),
        category: "registry".to_string(),
        image: "springcloud/eureka:latest".to_string(),
        default_port: 8761,
        detection_keys: vec![
            "eureka".to_string(), "spring-cloud-starter-netflix-eureka".to_string(),
            "eureka-client".to_string(),
        ],
    });

    // ========== API 网关 ==========

    services.insert("kong".to_string(), ExternalService {
        name: "kong".to_string(),
        category: "gateway".to_string(),
        image: "kong:3.4-alpine".to_string(),
        default_port: 8000,
        detection_keys: vec![
            "kong".to_string(), "kong-admin".to_string(),
        ],
    });

    services.insert("apisix".to_string(), ExternalService {
        name: "apisix".to_string(),
        category: "gateway".to_string(),
        image: "apache/apisix:3.6.0-alpine".to_string(),
        default_port: 9080,
        detection_keys: vec![
            "apisix".to_string(), "apisix-java".to_string(),
        ],
    });

    services.insert("traefik".to_string(), ExternalService {
        name: "traefik".to_string(),
        category: "gateway".to_string(),
        image: "traefik:v2.10".to_string(),
        default_port: 8080,
        detection_keys: vec![
            "traefik".to_string(), "traefik-go".to_string(),
        ],
    });

    // ========== 其他基础设施 ==========

    services.insert("keycloak".to_string(), ExternalService {
        name: "keycloak".to_string(),
        category: "auth".to_string(),
        image: "quay.io/keycloak/keycloak:22.0".to_string(),
        default_port: 8080,
        detection_keys: vec![
            "keycloak".to_string(), "keycloak-admin-client".to_string(),
            "spring-boot-starter-oauth2".to_string(),
        ],
    });

    services.insert("vault".to_string(), ExternalService {
        name: "vault".to_string(),
        category: "secrets".to_string(),
        image: "hashicorp/vault:1.15".to_string(),
        default_port: 8200,
        detection_keys: vec![
            "vault".to_string(), "vault-client".to_string(),
            "hashicorp/vault".to_string(),
        ],
    });

    services.insert("xxl-job".to_string(), ExternalService {
        name: "xxl-job".to_string(),
        category: "scheduler".to_string(),
        image: "xuxueli/xxl-job-admin:2.4.0".to_string(),
        default_port: 8070,
        detection_keys: vec![
            "xxl-job".to_string(), "xxl-job-core".to_string(),
        ],
    });

    services.insert("selenium".to_string(), ExternalService {
        name: "selenium".to_string(),
        category: "testing".to_string(),
        image: "selenium/standalone-chrome:latest".to_string(),
        default_port: 4444,
        detection_keys: vec![
            "selenium".to_string(), "selenium-webdriver".to_string(),
            "webdriver".to_string(),
        ],
    });

    services.insert("grpc".to_string(), ExternalService {
        name: "grpc".to_string(),
        category: "rpc".to_string(),
        image: "".to_string(),
        default_port: 50051,
        detection_keys: vec![
            "grpc".to_string(), "grpc-go".to_string(),
            "grpc-java".to_string(), "@grpc/grpc-js".to_string(),
            "grpcio".to_string(),
        ],
    });

    services.insert("protobuf".to_string(), ExternalService {
        name: "protobuf".to_string(),
        category: "rpc".to_string(),
        image: "".to_string(),
        default_port: 0,
        detection_keys: vec![
            "protobuf".to_string(), "protobufjs".to_string(),
            "prost".to_string(), "google-protobuf".to_string(),
        ],
    });

    services
}
