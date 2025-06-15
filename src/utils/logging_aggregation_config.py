"""
Configuration templates for integrating with popular log aggregation services.
This module provides configuration examples for various logging backends.
"""

import os
from typing import Dict, Any


def get_elasticsearch_config() -> Dict[str, Any]:
    """
    Configuration for Elasticsearch/ELK Stack integration.

    Returns:
        Dictionary with Elasticsearch configuration
    """
    return {
        "hosts": os.getenv("ELASTICSEARCH_HOSTS", "localhost:9200").split(","),
        "index_pattern": "daily-profit-model-{date}",
        "doc_type": "_doc",
        "buffer_size": 1000,
        "flush_interval": 5,  # seconds
        "auth": {
            "username": os.getenv("ELASTICSEARCH_USER"),
            "password": os.getenv("ELASTICSEARCH_PASSWORD"),
        },
        "ssl": {
            "enabled": os.getenv("ELASTICSEARCH_SSL", "false").lower() == "true",
            "verify": os.getenv("ELASTICSEARCH_SSL_VERIFY", "true").lower() == "true",
        },
    }


def get_cloudwatch_config() -> Dict[str, Any]:
    """
    Configuration for AWS CloudWatch Logs integration.

    Returns:
        Dictionary with CloudWatch configuration
    """
    return {
        "region": os.getenv("AWS_REGION", "us-east-1"),
        "log_group": os.getenv("CLOUDWATCH_LOG_GROUP", "/aws/ecs/daily-profit-model"),
        "log_stream_prefix": os.getenv("CLOUDWATCH_STREAM_PREFIX", "app"),
        "batch_size": 10000,  # bytes
        "batch_time": 5000,  # milliseconds
        "create_log_group": True,
        "retention_days": 30,
    }


def get_datadog_config() -> Dict[str, Any]:
    """
    Configuration for Datadog logging integration.

    Returns:
        Dictionary with Datadog configuration
    """
    return {
        "api_key": os.getenv("DATADOG_API_KEY"),
        "app_key": os.getenv("DATADOG_APP_KEY"),
        "host": os.getenv("DATADOG_HOST", "http-intake.logs.datadoghq.com"),
        "port": int(os.getenv("DATADOG_PORT", "443")),
        "use_ssl": True,
        "service": "daily-profit-model",
        "source": "python",
        "tags": [
            f"env:{os.getenv('ENVIRONMENT', 'development')}",
            f"version:{os.getenv('APP_VERSION', '1.0.0')}",
            "team:data-engineering",
        ],
        "hostname": os.getenv("HOSTNAME", "localhost"),
    }


def get_splunk_config() -> Dict[str, Any]:
    """
    Configuration for Splunk HTTP Event Collector (HEC) integration.

    Returns:
        Dictionary with Splunk configuration
    """
    return {
        "host": os.getenv("SPLUNK_HOST", "localhost"),
        "port": int(os.getenv("SPLUNK_PORT", "8088")),
        "token": os.getenv("SPLUNK_HEC_TOKEN"),
        "index": os.getenv("SPLUNK_INDEX", "main"),
        "source": "daily-profit-model",
        "sourcetype": "_json",
        "verify_ssl": os.getenv("SPLUNK_VERIFY_SSL", "true").lower() == "true",
        "timeout": 30,
        "retry_count": 3,
        "batch_size": 10,  # events
    }


def get_fluentd_config() -> Dict[str, Any]:
    """
    Configuration for Fluentd/Fluent Bit integration.

    Returns:
        Dictionary with Fluentd configuration
    """
    return {
        "host": os.getenv("FLUENTD_HOST", "localhost"),
        "port": int(os.getenv("FLUENTD_PORT", "24224")),
        "tag": "daily-profit-model",
        "buffer_size": 8192,
        "timeout": 3.0,
        "nanosecond_precision": True,
        "msgpack_kwargs": {"use_bin_type": True},
    }


def get_prometheus_config() -> Dict[str, Any]:
    """
    Configuration for Prometheus metrics (complementary to logging).

    Returns:
        Dictionary with Prometheus configuration
    """
    return {
        "port": int(os.getenv("PROMETHEUS_PORT", "8000")),
        "path": "/metrics",
        "namespace": "daily_profit_model",
        "buckets": [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        "labels": {
            "environment": os.getenv("ENVIRONMENT", "development"),
            "service": "daily-profit-model",
            "version": os.getenv("APP_VERSION", "1.0.0"),
        },
    }


def get_loki_config() -> Dict[str, Any]:
    """
    Configuration for Grafana Loki integration.

    Returns:
        Dictionary with Loki configuration
    """
    return {
        "url": os.getenv("LOKI_URL", "http://localhost:3100"),
        "push_path": "/loki/api/v1/push",
        "labels": {
            "app": "daily-profit-model",
            "environment": os.getenv("ENVIRONMENT", "development"),
            "namespace": os.getenv("K8S_NAMESPACE", "default"),
            "pod": os.getenv("K8S_POD_NAME", "local"),
        },
        "auth": {
            "username": os.getenv("LOKI_USERNAME"),
            "password": os.getenv("LOKI_PASSWORD"),
        },
        "verify_ssl": os.getenv("LOKI_VERIFY_SSL", "true").lower() == "true",
        "timeout": 10,
        "compression": "snappy",
    }


def get_kafka_config() -> Dict[str, Any]:
    """
    Configuration for Kafka logging integration.

    Returns:
        Dictionary with Kafka configuration
    """
    return {
        "bootstrap_servers": os.getenv("KAFKA_BROKERS", "localhost:9092").split(","),
        "topic": os.getenv("KAFKA_LOG_TOPIC", "application-logs"),
        "key": "daily-profit-model",
        "compression_type": "gzip",
        "batch_size": 16384,
        "linger_ms": 10,
        "buffer_memory": 33554432,  # 32MB
        "security_protocol": os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
        "sasl_mechanism": os.getenv("KAFKA_SASL_MECHANISM"),
        "sasl_username": os.getenv("KAFKA_USERNAME"),
        "sasl_password": os.getenv("KAFKA_PASSWORD"),
    }


# Example environment variable configuration
EXAMPLE_ENV_CONFIG = """
# Elasticsearch Configuration
ELASTICSEARCH_HOSTS=es-node1:9200,es-node2:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=your-password
ELASTICSEARCH_SSL=true

# AWS CloudWatch Configuration
AWS_REGION=us-east-1
CLOUDWATCH_LOG_GROUP=/aws/ecs/daily-profit-model
CLOUDWATCH_STREAM_PREFIX=app

# Datadog Configuration
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-app-key
ENVIRONMENT=production
APP_VERSION=1.0.0

# Splunk Configuration
SPLUNK_HOST=splunk.example.com
SPLUNK_PORT=8088
SPLUNK_HEC_TOKEN=your-hec-token
SPLUNK_INDEX=main

# Fluentd Configuration
FLUENTD_HOST=fluentd.example.com
FLUENTD_PORT=24224

# Prometheus Configuration
PROMETHEUS_PORT=8000

# Loki Configuration
LOKI_URL=http://loki.example.com:3100
LOKI_USERNAME=loki
LOKI_PASSWORD=your-password

# Kafka Configuration
KAFKA_BROKERS=kafka1:9092,kafka2:9092
KAFKA_LOG_TOPIC=application-logs
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=PLAIN
KAFKA_USERNAME=your-username
KAFKA_PASSWORD=your-password
"""


def print_example_config():
    """Print example environment configuration."""
    print("Example environment configuration for log aggregation:")
    print(EXAMPLE_ENV_CONFIG)
