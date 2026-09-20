#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.chat_with_your_docs_stack import ChatWithYourDocsStack

app = cdk.App()
ChatWithYourDocsStack(
    app,
    "ChatWithYourDocs",
    description="Chat With Your Docs — AWS reference architecture (issue #23)",
    # No explicit `env` (account/region): CDK resolves both from the deployer's
    # configured AWS CLI credentials/region at synth time (CDK_DEFAULT_ACCOUNT/
    # CDK_DEFAULT_REGION) — the standard "deploy wherever I'm authenticated"
    # default. Pin an explicit Environment(account=..., region=...) instead if this
    # stack is ever deployed for real (issue #28) from a fixed CI/CD account.
)

app.synth()
