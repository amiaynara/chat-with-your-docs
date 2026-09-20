"""Tests for Settings' database_url assembly from discrete parts.

ECS (infra/, issue #23) injects RDS connection info as separate env vars — DB_HOST/
DB_PORT/DB_NAME as plain values, DB_USER/DB_PASSWORD from the RDS-managed Secrets
Manager secret via ecs.Secret.from_secrets_manager — rather than one templated
DATABASE_URL, since Secrets Manager/ECS has no way to interpolate a secret's fields
into a single string value. Settings assembles database_url from those parts when
DB_HOST is set; otherwise database_url is used as-is (the local-dev default).
"""

from app.config import Settings


def test_database_url_used_as_is_when_db_host_is_not_set():
    settings = Settings(database_url="postgresql+psycopg://a:b@c:1/d")

    assert settings.database_url == "postgresql+psycopg://a:b@c:1/d"


def test_database_url_assembled_from_discrete_parts_when_db_host_is_set():
    settings = Settings(
        db_host="my-rds-instance.abc123.us-east-1.rds.amazonaws.com",
        db_port=5432,
        db_name="app",
        db_user="app_user",
        db_password="s3cr3t",
    )

    assert settings.database_url == (
        "postgresql+psycopg://app_user:s3cr3t"
        "@my-rds-instance.abc123.us-east-1.rds.amazonaws.com:5432/app"
    )
