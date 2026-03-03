from aws_cdk import (
    Stack,
    Fn,
    RemovalPolicy,
    aws_iam as iam,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    aws_ecr_assets as ecr_assets,
    aws_bedrockagentcore as bedrockagentcore,
    CfnOutput,
)
from constructs import Construct
import os
import subprocess


class AgentCoreStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account = Stack.of(self).account
        region = Stack.of(self).region

        # Secrets Manager
        agent_secret = secretsmanager.Secret(
            self,
            "DeepResearchApiSecrets",
            secret_name="deep-research/secrets",
            description="Deep Research API secrets",
            removal_policy=RemovalPolicy.DESTROY,
            secret_object_value={}
        )

        # S3 bucket for published articles — ACLs enabled, no blanket bucket policy.
        # Public access is granted per-object via ACL="public-read" at upload time.
        article_bucket = s3.Bucket(
            self,
            "DeepResearchArticlesBucket",
            bucket_name=f"deep-research-articles-{account}",
            removal_policy=RemovalPolicy.DESTROY,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                ignore_public_acls=False,
                block_public_policy=True,
                restrict_public_buckets=True,
            ),
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
        )

        # Run local script to update requirements.txt before building the image
        subprocess.run(["sh", "agentCoreDeployFromCDK.sh"], check=True, cwd="../agents")

        # Build and push Docker image from agents directory
        docker_image = ecr_assets.DockerImageAsset(
            self,
            "DeepResearchDockerImage",
            directory=os.path.join(os.path.dirname(__file__), "..", "..", "agents"),
            asset_name="deep-research-images"
        )

        # IAM execution role for AgentCore runtime
        execution_role = iam.Role(
            self,
            "DeepResearchAgentCoreExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account}:*"}
                }
            ),
            description="Execution role for Deep Research Bedrock AgentCore runtime",
        )

        # CloudWatch logging
        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:DescribeLogStreams", "logs:CreateLogGroup"],
            resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*"],
        ))

        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:DescribeLogGroups"],
            resources=[f"arn:aws:logs:{region}:{account}:log-group:*"],
        ))

        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"],
        ))

        # ECR image pull
        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ecr:GetAuthorizationToken"],
            resources=["*"],
        ))

        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
            resources=[docker_image.repository.repository_arn],
        ))

        # X-Ray tracing
        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "xray:PutTraceSegments",
                "xray:PutTelemetryRecords",
                "xray:GetSamplingRules",
                "xray:GetSamplingTargets"
            ],
            resources=["*"],
        ))

        # CloudWatch custom metrics
        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
            conditions={"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}}
        ))

        # MCP Gateway access (workload identity + OAuth token)
        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock-agentcore:GetResourceOauth2Token",
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
            ],
            resources=[
                f"arn:aws:bedrock-agentcore:{region}:{account}:token-vault/default",
                f"arn:aws:bedrock-agentcore:{region}:{account}:token-vault/default/oauth2credentialprovider/*",
                f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default",
                f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default/workload-identity/deep_research_agent*"
            ],
        ))

        # Bedrock model invocation + guardrails
        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ApplyGuardrail"
            ],
            resources=[
                "arn:aws:bedrock:*::foundation-model/*",
                "arn:aws:bedrock:*:*:inference-profile/*",
                f"arn:aws:bedrock:{region}:{account}:*"
            ],
        ))

        # Secrets Manager
        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["secretsmanager:GetSecretValue"],
            resources=[agent_secret.secret_arn],
        ))

        # Article bucket write access
        execution_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["s3:PutObject", "s3:PutObjectAcl"],
            resources=[article_bucket.bucket_arn + "/*"],
        ))

        # Create the AgentCore Runtime
        agentcore_runtime = bedrockagentcore.CfnRuntime(
            self,
            "DeepResearchAgentCoreRuntime",
            agent_runtime_name="deep_research_agent",
            description="Deep Research agent — mimics Gemini Deep Research using CrewAI",
            role_arn=execution_role.role_arn,
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=bedrockagentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=docker_image.image_uri,
                )
            ),
            environment_variables={
                "SECRET_NAME": agent_secret.secret_name,
                "SECRET_REGION": region,
                "AWS_REGION": region,
                "AWS_DEFAULT_REGION": region,
                "ARTICLE_BUCKET": article_bucket.bucket_name,
                "GUARDRAIL_ID": Fn.import_value("DeepGuardrailId"),
                "CREWAI_DISABLE_TELEMETRY": "true",
                "LITELLM_LOCAL_MODEL_COST_MAP": "true",
                "OTEL_TRACES_SAMPLER": "always_on",
                "OTEL_LOG_LEVEL": "debug"
            },
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC"
            )
        )

        agentcore_runtime.node.add_dependency(execution_role)

        # Outputs
        CfnOutput(self, "DeepAgentCoreRuntimeArn",
            value=agentcore_runtime.attr_agent_runtime_arn,
            description="ARN of the Deep Research AgentCore Runtime",
            export_name="DeepAgentCoreRuntimeArn"
        )

        CfnOutput(self, "DeepAgentCoreRuntimeId",
            value=agentcore_runtime.attr_agent_runtime_id,
            description="ID of the Deep Research AgentCore Runtime",
        )

        CfnOutput(self, "DeepECRRepositoryUri",
            value=docker_image.repository.repository_arn,
            description="ECR Repository ARN for the Deep Research agent container",
        )

        CfnOutput(self, "DeepExecutionRoleArn",
            value=execution_role.role_arn,
            description="ARN of the Deep Research AgentCore Execution Role",
        )

        CfnOutput(self, "DeepSecretsName",
            value=agent_secret.secret_name,
            description="Name of the Deep Research API secrets",
            export_name="DeepSecretsName",
        )