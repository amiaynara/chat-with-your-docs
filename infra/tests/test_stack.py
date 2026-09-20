"""Assertion tests for the CDK stack (issue #23) — synthesize the stack and check the
resulting CloudFormation template has the resources/properties the architecture
promises, the same "assert on the real synthesized output" spirit as this repo's
backend tests asserting on real HTTP responses rather than internals.
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from stacks.chat_with_your_docs_stack import (
    API_PATH_PATTERNS,
    PROVIDER_SECRET_NAMES,
    ChatWithYourDocsStack,
)


@pytest.fixture(scope="module")
def template() -> Template:
    app = App()
    stack = ChatWithYourDocsStack(
        app, "TestStack", env=Environment(account="123456789012", region="us-east-1")
    )
    return Template.from_stack(stack)


def test_synthesizes_without_error(template: Template) -> None:
    # If the fixture above didn't raise, synthesis already succeeded; this just
    # makes that assertion explicit and gives pytest something to report on.
    assert template.to_json()


def test_database_is_postgres_16_with_storage_encryption(template: Template) -> None:
    template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {
            "Engine": "postgres",
            # PostgresEngineVersion.VER_16 (unversioned) synthesizes to the bare
            # major version "16", letting AWS resolve the current default 16.x minor
            # at deploy time rather than pinning one here.
            "EngineVersion": "16",
            "StorageEncrypted": True,
            "PubliclyAccessible": False,
        },
    )


def test_redis_cluster_is_provisioned(template: Template) -> None:
    template.has_resource_properties(
        "AWS::ElastiCache::CacheCluster",
        {"Engine": "redis", "NumCacheNodes": 1},
    )


def test_all_four_provider_secrets_are_created(template: Template) -> None:
    for name in PROVIDER_SECRET_NAMES:
        template.has_resource_properties("AWS::SecretsManager::Secret", {"Name": name})


def test_documents_and_frontend_buckets_block_all_public_access(template: Template) -> None:
    template.resource_count_is("AWS::S3::Bucket", 2)
    template.all_resources_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_ecs_task_role_trusts_ecs_tasks(template: Template) -> None:
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                            }
                        )
                    ]
                )
            }
        },
    )


def test_two_fargate_services_are_provisioned(template: Template) -> None:
    template.resource_count_is("AWS::ECS::Service", 2)
    template.all_resources_properties("AWS::ECS::Service", {"LaunchType": "FARGATE"})


def test_api_target_group_health_check_targets_health_endpoint(template: Template) -> None:
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::TargetGroup",
        {"HealthCheckPath": "/health", "Protocol": "HTTP"},
    )


def test_cloudfront_distribution_forwards_every_api_path_to_the_alb(template: Template) -> None:
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like(
                {
                    "CacheBehaviors": Match.array_with(
                        [
                            Match.object_like({"PathPattern": pattern})
                            for pattern in API_PATH_PATTERNS
                        ]
                    )
                }
            )
        },
    )
