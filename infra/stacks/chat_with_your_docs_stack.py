"""CDK stack for the AWS reference architecture (docs/architecture.md's dashed PROD
panel; issue #23). Provisions the whole stack — VPC, ECS Fargate (api + worker), RDS
Postgres with pgvector, ElastiCache Redis, S3 (uploaded-document storage + frontend
static hosting), CloudFront, and Secrets Manager — so `cdk deploy` stands up a working
environment in one command.

Not deployed for this submission (see README's "Production deployment (deferred)"
section and issue #28's live-cutover ticket) — this is the code that *would* run it,
reviewable and diffable like any other part of this repo, not a promise left
undemonstrated. See infra/README.md for deploy steps and infra/docs/architecture.md
(or docs/architecture.md's AWS section) for the topology diagram.
"""

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_elasticache as elasticache
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIST_DIR = REPO_ROOT / "frontend" / "dist"

# Names of the four provider API keys this app resolves via SecretManager
# (backend/app/adapters/secrets.py, issue #22) when SECRET_MANAGER=aws — the same
# names LocalSecretManager expects in backend/.secrets locally (docs/secrets.md).
# Provisioned here as empty placeholder secrets (CDK's default random-string
# generator); real values are set manually post-deploy — see infra/README.md. Never
# committed to this stack's code, same as backend/.secrets is gitignored locally.
PROVIDER_SECRET_NAMES = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "COHERE_API_KEY"]

# FastAPI's own route prefixes (backend/app/main.py, api/documents.py, api/chat.py) —
# CloudFront forwards exactly these path patterns to the API's ALB origin; everything
# else falls through to the S3-hosted frontend static assets (the default behavior).
API_PATH_PATTERNS = [
    "/documents",
    "/documents/*",
    "/chat/*",
    "/health",
    "/docs",
    "/docs/*",
    "/redoc",
    "/openapi.json",
]


@dataclass
class _Redis:
    url: str
    security_group: ec2.SecurityGroup


class ChatWithYourDocsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = self._build_vpc()
        cluster = ecs.Cluster(
            self, "Cluster", vpc=vpc, container_insights_v2=ecs.ContainerInsights.ENABLED
        )

        documents_bucket = self._build_documents_bucket()
        provider_secrets = self._build_provider_secrets()
        database = self._build_database(vpc)
        redis = self._build_redis(vpc)

        app_security_group = ec2.SecurityGroup(
            self,
            "AppSecurityGroup",
            vpc=vpc,
            description="Shared security group for the api and worker ECS tasks",
            allow_all_outbound=True,
        )
        database.connections.allow_default_port_from(
            app_security_group, "ECS tasks (api/worker) -> RDS Postgres"
        )
        redis.security_group.add_ingress_rule(
            app_security_group, ec2.Port.tcp(6379), "ECS tasks (api/worker) -> ElastiCache Redis"
        )

        task_role = self._build_task_role(documents_bucket, provider_secrets, database)
        environment, secrets = self._build_container_env(database, redis, documents_bucket)

        api_service = self._build_api_service(
            cluster, task_role, app_security_group, environment, secrets
        )
        self._build_worker_service(cluster, task_role, app_security_group, environment, secrets)

        distribution = self._build_frontend_hosting(api_service.load_balancer)

        self._build_outputs(api_service, database, documents_bucket, distribution)

    # ---- network -------------------------------------------------------

    def _build_vpc(self) -> ec2.Vpc:
        # Single NAT gateway (not one per AZ) — a cost-conscious default for a
        # reference/demo deployment, not a production-HA choice; see infra/README.md's
        # "what a hardening pass would change" section.
        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="private-app",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private-data",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )
        # Free, no extra setup: routes the api/worker tasks' S3 traffic (documents
        # bucket reads/writes) straight to S3 over the VPC instead of through the NAT
        # gateway, which otherwise bills for every byte processed.
        vpc.add_gateway_endpoint("S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3)
        return vpc

    # ---- data stores -----------------------------------------------------

    def _build_documents_bucket(self) -> s3.Bucket:
        return s3.Bucket(
            self,
            "DocumentsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            # This reference stack is never actually deployed (issue #28) — DESTROY +
            # auto_delete_objects means `cdk destroy` leaves nothing behind if someone
            # does try it. A real production bucket would use RemovalPolicy.RETAIN.
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

    def _build_provider_secrets(self) -> dict[str, secretsmanager.Secret]:
        return {
            name: secretsmanager.Secret(
                self,
                f"Secret{name.title().replace('_', '')}",
                secret_name=name,
                description=(
                    f"{name} — placeholder (CDK-generated random value) provisioned by "
                    "this stack; the real key is set manually post-deploy, never "
                    "committed to this repo. Read by AWSSecretManager "
                    "(backend/app/adapters/secrets.py) when SECRET_MANAGER=aws."
                ),
            )
            for name in PROVIDER_SECRET_NAMES
        }

    def _build_database(self, vpc: ec2.Vpc) -> rds.DatabaseInstance:
        # pgvector is an RDS-allowlisted extension on Postgres 15.2+/16.1+ (no custom
        # parameter group needed) — the api container's existing startup command
        # (`alembic upgrade head`, unchanged from docker-compose.yml) runs `CREATE
        # EXTENSION IF NOT EXISTS vector` via the baseline migration
        # (alembic/versions/0001_baseline.py) the same way it does locally.
        return rds.DatabaseInstance(
            self,
            "Database",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MICRO),
            credentials=rds.Credentials.from_generated_secret("app_user"),
            database_name="app",
            allocated_storage=20,
            storage_encrypted=True,
            # Reference/demo defaults, not production-hardened — see
            # infra/README.md's "what a hardening pass would change" section
            # (Multi-AZ, longer backup retention, deletion protection, RETAIN).
            multi_az=False,
            backup_retention=Duration.days(1),
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
        )

    def _build_redis(self, vpc: ec2.Vpc) -> _Redis:
        security_group = ec2.SecurityGroup(
            self,
            "RedisSecurityGroup",
            vpc=vpc,
            description="ElastiCache Redis (Celery broker/result backend)",
            allow_all_outbound=False,
        )
        subnet_group = elasticache.CfnSubnetGroup(
            self,
            "RedisSubnetGroup",
            description="Private isolated subnets for ElastiCache Redis",
            subnet_ids=vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED).subnet_ids,
        )
        cluster = elasticache.CfnCacheCluster(
            self,
            "Redis",
            engine="redis",
            # Reference/demo default: a single node, no replication/automatic
            # failover — see infra/README.md's hardening notes.
            cache_node_type="cache.t3.micro",
            num_cache_nodes=1,
            vpc_security_group_ids=[security_group.security_group_id],
            cache_subnet_group_name=subnet_group.ref,
        )
        cluster.add_resource_dependency(subnet_group)
        url = f"redis://{cluster.attr_redis_endpoint_address}:{cluster.attr_redis_endpoint_port}/0"
        return _Redis(url=url, security_group=security_group)

    # ---- IAM -------------------------------------------------------------

    def _build_task_role(
        self,
        documents_bucket: s3.Bucket,
        provider_secrets: dict[str, secretsmanager.Secret],
        database: rds.DatabaseInstance,
    ) -> iam.Role:
        # Least-privilege: read on exactly the 4 named provider secrets (not a broad
        # secretsmanager:GetSecretValue on *), read on the RDS-generated credentials
        # secret, and read/write on the documents bucket only — no static AWS keys
        # anywhere (issue #27's "secrets management production cutover" ticket).
        role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Least-privilege role for the api/worker ECS tasks",
        )
        documents_bucket.grant_read_write(role)
        for secret in provider_secrets.values():
            secret.grant_read(role)
        assert database.secret is not None  # set by Credentials.from_generated_secret
        database.secret.grant_read(role)
        return role

    # ---- container environment -------------------------------------------

    def _build_container_env(
        self, database: rds.DatabaseInstance, redis: _Redis, documents_bucket: s3.Bucket
    ) -> tuple[dict[str, str], dict[str, ecs.Secret]]:
        assert database.secret is not None
        environment = {
            # Mirrors backend/.env.docker's non-secret defaults — see docs/embeddings.md,
            # docs/llm-providers.md and docs/secrets.md for what each toggle does.
            "DB_HOST": database.db_instance_endpoint_address,
            "DB_PORT": database.db_instance_endpoint_port,
            "DB_NAME": "app",
            "REDIS_URL": redis.url,
            "OBJECT_STORAGE_BUCKET": documents_bucket.bucket_name,
            # Deliberately empty (not omitted): S3ObjectStorage treats an empty
            # endpoint/credentials as "use the real AWS S3 endpoint and the task
            # role's default boto3 credential chain" (app/adapters/storage.py) —
            # leaving these unset entirely would instead fall back to Settings'
            # local-dev MinIO defaults.
            "OBJECT_STORAGE_ENDPOINT_URL": "",
            "OBJECT_STORAGE_ACCESS_KEY": "",
            "OBJECT_STORAGE_SECRET_KEY": "",
            "SECRET_MANAGER": "aws",
            "AWS_SECRETS_REGION": self.region,
            "LLM_PROVIDER": "anthropic",
            "LLM_MODEL": "claude-haiku-4-5-20251001",
            "EMBEDDING_PROVIDER": "local",
            "LOCAL_EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
            "RERANKER_ENABLED": "false",
            "SESSION_COOKIE_SECURE": "true",
        }
        secrets = {
            "DB_USER": ecs.Secret.from_secrets_manager(database.secret, field="username"),
            "DB_PASSWORD": ecs.Secret.from_secrets_manager(database.secret, field="password"),
        }
        return environment, secrets

    # ---- compute -----------------------------------------------------------

    def _backend_image(self) -> ecs.ContainerImage:
        # Same backend/Dockerfile docker-compose.yml's api/worker services build from
        # — no separate production image; api and worker only differ by command.
        return ecs.ContainerImage.from_asset(str(BACKEND_DIR))

    def _build_api_service(
        self,
        cluster: ecs.Cluster,
        task_role: iam.Role,
        security_group: ec2.SecurityGroup,
        environment: dict[str, str],
        secrets: dict[str, ecs.Secret],
    ) -> ecs_patterns.ApplicationLoadBalancedFargateService:
        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "ApiService",
            cluster=cluster,
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            # desired_count=1 (a reference/demo default, not HA): allow the single
            # task to be fully replaced during a deployment rather than blocking on
            # an unreachable "50% of 1 task" minimum, and roll back automatically if
            # the new task fails to start instead of hanging for up to 3 hours.
            min_healthy_percent=0,
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            public_load_balancer=True,
            security_groups=[security_group],
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=self._backend_image(),
                container_port=8000,
                task_role=task_role,
                environment=environment,
                secrets=secrets,
                # Matches docker-compose.yml's api command minus --reload (dev-only).
                command=[
                    "sh",
                    "-c",
                    "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000",
                ],
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="api", log_retention=logs.RetentionDays.ONE_WEEK
                ),
            ),
        )
        # docs/architecture.md/issue #24: real health checks wired into the ALB target
        # group, targeting the same GET /health the app already exposes.
        service.target_group.configure_health_check(path="/health", healthy_http_codes="200")
        return service

    def _build_worker_service(
        self,
        cluster: ecs.Cluster,
        task_role: iam.Role,
        security_group: ec2.SecurityGroup,
        environment: dict[str, str],
        secrets: dict[str, ecs.Secret],
    ) -> ecs.FargateService:
        # No load balancer — the worker has no HTTP interface, it only consumes tasks
        # from Redis (matches docker-compose.yml's worker service having no `ports`).
        task_definition = ecs.FargateTaskDefinition(
            self, "WorkerTaskDefinition", cpu=512, memory_limit_mib=1024, task_role=task_role
        )
        task_definition.add_container(
            "worker",
            image=self._backend_image(),
            environment=environment,
            secrets=secrets,
            command=["celery", "-A", "app.celery_app", "worker", "--loglevel=info"],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="worker", log_retention=logs.RetentionDays.ONE_WEEK
            ),
        )
        return ecs.FargateService(
            self,
            "WorkerService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=1,
            min_healthy_percent=0,
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            security_groups=[security_group],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

    # ---- frontend hosting --------------------------------------------------

    def _build_frontend_hosting(self, load_balancer) -> cloudfront.Distribution:
        # A Vite/React SPA is static output (frontend/dist) — served from S3 behind
        # CloudFront, not the dev-server container frontend/Dockerfile builds (that
        # image is dev-only: `npm run dev`, never intended for production; see
        # infra/README.md). CloudFront also fronts the API (below) so the whole app
        # is one origin as far as the browser's concerned — VITE_API_BASE_URL can
        # stay empty/relative (frontend/src/api/*.ts's `?? 'http://localhost:8000'`
        # fallback is what local dev without it set uses instead), which sidesteps
        # needing the ALB's DNS name to be known before the frontend is built.
        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        api_origin = origins.LoadBalancerV2Origin(
            load_balancer,
            # The ALB listener here is plain HTTP (no ACM certificate on this
            # reference stack — see infra/README.md); CloudFront-to-viewer is still
            # HTTPS via viewer_protocol_policy below.
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        )
        frontend_origin = origins.S3BucketOrigin.with_origin_access_control(frontend_bucket)

        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=frontend_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            additional_behaviors={
                pattern: cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                )
                for pattern in API_PATH_PATTERNS
            },
            # SPA client-side routing: CloudFront's own 403 (OAC-fronted S3 denies a
            # key that doesn't exist) is rewritten to 200 + index.html, matching how
            # a single-page app is meant to handle unknown paths.
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403, response_http_status=200, response_page_path="/index.html"
                ),
                cloudfront.ErrorResponse(
                    http_status=404, response_http_status=200, response_page_path="/index.html"
                ),
            ],
        )

        if FRONTEND_DIST_DIR.exists():
            s3deploy.BucketDeployment(
                self,
                "FrontendDeployment",
                sources=[s3deploy.Source.asset(str(FRONTEND_DIST_DIR))],
                destination_bucket=frontend_bucket,
                distribution=distribution,
                distribution_paths=["/*"],
            )
        # else: frontend/dist doesn't exist yet (`npm run build` hasn't been run) —
        # synth/deploy still succeeds, provisioning an empty frontend bucket; see
        # infra/README.md's deploy steps for building the frontend first.

        return distribution

    # ---- outputs -------------------------------------------------------------

    def _build_outputs(
        self,
        api_service: ecs_patterns.ApplicationLoadBalancedFargateService,
        database: rds.DatabaseInstance,
        documents_bucket: s3.Bucket,
        distribution: cloudfront.Distribution,
    ) -> None:
        CfnOutput(
            self,
            "AppUrl",
            value=f"https://{distribution.distribution_domain_name}",
            description="The whole app (frontend + API, via CloudFront)",
        )
        CfnOutput(
            self,
            "ApiLoadBalancerDnsName",
            value=api_service.load_balancer.load_balancer_dns_name,
            description="Direct ALB DNS name for the api service (bypasses CloudFront)",
        )
        CfnOutput(
            self,
            "DatabaseSecretArn",
            value=database.secret.secret_arn if database.secret else "",
            description="Secrets Manager secret holding the RDS master credentials",
        )
        CfnOutput(
            self,
            "DocumentsBucketName",
            value=documents_bucket.bucket_name,
            description="S3 bucket backing ObjectStorage (uploaded documents)",
        )
