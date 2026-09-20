# infra — AWS CDK reference architecture (issue #23)

Provisions the AWS deployment target described in `docs/architecture.md`'s ["AWS deployment
topology"](../docs/architecture.md#aws-deployment-topology) section: VPC, ECS
Fargate (`api` + `worker`), RDS Postgres with `pgvector`, ElastiCache Redis, S3 (uploaded
documents + frontend static hosting), CloudFront, and Secrets Manager.

**This is not deployed.** Per the project's own decision (see the root `README.md`'s "Production
deployment (deferred)" section and issue #28), this app runs locally only. This directory exists
so the deployment story is real, runnable code — reviewable and diffable like anything else in
this repo — rather than a description of something nobody has actually built. `cdk deploy` would
work if pointed at a real AWS account; nobody has run it against one here.

## Prerequisites

- An AWS account and credentials configured locally (`aws configure`, or an SSO profile) — the CDK
  CLI resolves the target account/region from your normal AWS CLI credentials.
- Node.js (for the CDK CLI itself — `npx aws-cdk`, no global install needed) and Python 3.11+.
- The frontend built (`cd frontend && npm run build`) **before** `cdk deploy` — this stack deploys
  the static `frontend/dist` output to S3/CloudFront, it doesn't build the frontend itself (CDK
  asset bundling would need to reproduce the exact same Node/npm toolchain `frontend/Dockerfile`
  uses for local dev, for no real benefit over just running the build once yourself first). If
  `frontend/dist` doesn't exist yet, `cdk synth`/`deploy` still succeed — they just provision an
  empty frontend bucket.

## Deploy

```bash
cd frontend && npm run build && cd ..

cd infra
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

npx aws-cdk bootstrap    # once per account/region
npx aws-cdk deploy       # everything else
```

`cdk deploy` prints outputs when it finishes, including `AppUrl` (the CloudFront domain — the
whole app, frontend + API, lives at this one URL).

### After deploying: populate the real secrets

The stack provisions four Secrets Manager secrets (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GOOGLE_API_KEY`, `COHERE_API_KEY`) as empty placeholders — CDK-generated random strings, not real
keys, since a real key obviously never belongs in this stack's source. Set the real values after
deploying:

```bash
aws secretsmanager put-secret-value --secret-id ANTHROPIC_API_KEY --secret-string "sk-ant-..."
```

`SECRET_MANAGER=aws` is set on both ECS tasks, so `AWSSecretManager`
(`backend/app/adapters/secrets.py`, issue #22) resolves these at runtime — restart the `api`/
`worker` services (or just wait for the next deploy) to pick up a newly-set value. See
[`docs/secrets.md`](../docs/secrets.md).

## Tear down

```bash
npx aws-cdk destroy
```

Both S3 buckets and the RDS instance are provisioned with `RemovalPolicy.DESTROY` (and
`autoDeleteObjects` on the buckets) specifically so this leaves nothing behind — a deliberate
choice for a reference stack nobody is meant to run long-term, not something a real production
deployment would want (see below).

## What this is a reference shape for, not a production-hardened deployment

Kept deliberately basic — "the smallest deploy that actually works end-to-end", matching this
project's own stated engineering philosophy (`ASSIGNMENT.md`'s "we value a solid, well-engineered
basic solution far more than an over-engineered complex one"), not a ceiling. A real production
pass would change:

- **High availability**: single NAT gateway (not one per AZ), single-AZ RDS (`multi_az=False`),
  and a single-node ElastiCache cluster (no replication group/automatic failover) — each is a
  single point of failure today.
- **Data retention**: `RemovalPolicy.DESTROY` on the S3 buckets and RDS instance, 1-day RDS backup
  retention, `deletion_protection=False` — all chosen so tearing this stack down leaves nothing
  behind, the opposite of what you'd want once real data exists.
- **TLS to the origin**: the ALB listener is plain HTTP with no ACM certificate/custom domain
  (CloudFront-to-viewer is still HTTPS; only the CloudFront→ALB hop inside AWS is not). A real
  deployment would put a certificate on the ALB (or drop it in favor of CloudFront-only with a
  private VPC origin) and use a real domain via Route 53, rather than the default
  `*.cloudfront.net` name.
- **Scaling**: `desired_count=1` on both ECS services, no auto-scaling policy — see issue #26
  (rate limiting) and the auth ticket (#25) for the other prerequisites a real public deployment
  needs before scaling matters.
- **CI/CD**: `cdk deploy` is run by hand here; a real pipeline would run it from CI (CodePipeline,
  or the existing GitHub Actions setup) on merge to `main`, with `cdk diff` gating the change.
- **Auth, rate limiting, live cutover**: out of scope for this ticket specifically — see issues
  #25, #26, #28.

## Tests

`tests/test_stack.py` — CDK assertion tests (`aws_cdk.assertions.Template`) against the real
synthesized CloudFormation template: the database is Postgres 16 with storage encryption, Redis is
provisioned, all four provider secrets exist, both S3 buckets block public access, the ECS task
role trusts `ecs-tasks.amazonaws.com`, both Fargate services exist, the ALB health check targets
`/health`, and CloudFront forwards every API path pattern to the ALB. Run with:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
```
