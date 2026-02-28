from aws_cdk import (
    Stack,
    Fn,
    Duration,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    aws_bedrockagentcore as bedrockagentcore,
    aws_cloudwatch as cloudwatch,
    aws_xray as xray,
    CfnOutput,
)
from constructs import Construct
import os
import subprocess

class AgentCoreStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get account and region info
        account = Stack.of(self).account
        region = Stack.of(self).region

        # Run local command before building to update requirements.txt
        subprocess.run(["sh", "agentCoreDeployFromCDK.sh"], check=True, cwd="../agents")
        
        # Build and push Docker image from agents directory
        docker_image = ecr_assets.DockerImageAsset(
            self,
            "OrangeAgentDockerImage",
            directory=os.path.join(os.path.dirname(__file__), "..", "..", "agents"),
            asset_name="orange-images"
        )

        # IAM execution role for AgentCore runtime
        execution_role = iam.Role(
            self,
            "OrangeAgentCoreExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "aws:SourceAccount": account
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account}:*"
                    }
                }
            ),
            description="Execution role for Amazon Bedrock AgentCore runtime",
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:DescribeLogStreams",
                    "logs:CreateLogGroup"
                ],
                resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*"],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:DescribeLogGroups"
                ],
                resources=[f"arn:aws:logs:{region}:{account}:log-group:*"],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"],
            )
        )
        
        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:GetAuthorizationToken"
                ],
                resources=["*"],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer"
                ],
                resources=[docker_image.repository.repository_arn],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets"
                ],
                resources=["*"],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:PutMetricData"
                ],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "cloudwatch:namespace": "bedrock-agentcore"
                    }
                }
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:GetEvent",
                    "bedrock-agentcore:GetMemory",
                    "bedrock-agentcore:GetMemoryRecord",
                    "bedrock-agentcore:ListActors",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:ListMemoryRecords",
                    "bedrock-agentcore:ListSessions",
                    "bedrock-agentcore:DeleteEvent",
                    "bedrock-agentcore:DeleteMemoryRecord",
                    "bedrock-agentcore:RetrieveMemoryRecords"
                ],
                resources=[Fn.import_value("OrangeAgentMemoryArn")],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:GetResourceApiKey"
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{region}:{account}:token-vault/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account}:token-vault/default/apikeycredentialprovider/*",
                    f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default/workload-identity/orange-electronics-agent*"
                ],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:GetResourceOauth2Token"
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{region}:{account}:token-vault/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account}:token-vault/default/oauth2credentialprovider/*",
                    f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default/workload-identity/orange-electronics-agent*"
                ],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default/workload-identity/orange-electronics-agent*"
                ],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
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
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue"
                ],
                resources=[Fn.import_value("OrangeSecretsArn")],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:Retrieve"
                ],
                resources=[Fn.import_value("OrangeKnowledgeBaseArn")],
            )
        )

        # Create the AgentCore Runtime with IAM authentication
        agentcore_runtime = bedrockagentcore.CfnRuntime(
            self,
            "OrangeAgentCoreRuntime",
            agent_runtime_name="orange_electronics_agent",
            description="Orange Electronics telegram bot agent with IAM authentication",
            role_arn=execution_role.role_arn,
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration = bedrockagentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=docker_image.image_uri,
                )
            ),
            environment_variables={
                "SECRET_NAME": Fn.import_value("OrangeSecretsName"),
                "SECRET_REGION": region,
                "AWS_REGION": region,
                "AWS_DEFAULT_REGION": region,
                "MEMORY_ID": Fn.import_value("OrangeAgentMemoryId"),
                "MCP_CLIENT_ID": Fn.import_value("OrangeMcpClientID"),
                "MCP_TOKEN_URL": f"https://{Fn.import_value('OrangeCognitoDomainName')}.auth.{region}.amazoncognito.com/oauth2/token",
                "MCP_GATEWAY_URL": Fn.import_value("OrangeMcpGatewayUrl"),
                "AWS_KNOWLEDGE_BASE_ID": Fn.import_value("OrangeKnowledgeBaseId"),
                "GUARDRAIL_ID": Fn.import_value("OrangeGuardrailId"),
                "CREWAI_DISABLE_TELEMETRY": "true",
                "LITELLM_LOCAL_MODEL_COST_MAP": "true",
                # "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
                # "OTEL_TRACES_EXPORTER": "otlp",
                # "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://localhost:4318/v1/traces",
                "OTEL_TRACES_SAMPLER": "always_on",
                "OTEL_LOG_LEVEL": "debug"
            },
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC"
            )
        )

        # Ensure the runtime is created only after the role and its policies are fully attached
        agentcore_runtime.node.add_dependency(execution_role)

        # Using the DEFAULT endpoint. AgentCore automatically routes to the latest version.
        
        # Outputs
        CfnOutput(
            self,
            "AgentCoreRuntimeArn",
            value=agentcore_runtime.attr_agent_runtime_arn,
            description="ARN of the AgentCore Runtime",
            export_name="AgentCoreRuntimeArn"
        )
        
        CfnOutput(
            self,
            "AgentCoreRuntimeId",
            value=agentcore_runtime.attr_agent_runtime_id,
            description="ID of the AgentCore Runtime",
        )

        CfnOutput(
            self,
            "ECRRepositoryUri",
            value=docker_image.repository.repository_arn,
            description="ECR Repository ARN for the agent container",
        )

        CfnOutput(
            self,
            "ExecutionRoleArn",
            value=execution_role.role_arn,
            description="ARN of the AgentCore Execution Role",
        )

        # CloudWatch Tier 1 Alarms
        runtime_dimensions = {
            "AgentRuntimeName": "orange_electronics_agent"
        }

        cloudwatch.Alarm(
            self,
            "OrangeAgentCoreSyncErrors",
            alarm_name="OrangeAgentCoreSyncErrors",
            metric=cloudwatch.Metric(
                namespace="AWS/BedrockAgentCore",
                metric_name="SyncInvocationErrors",
                dimensions_map=runtime_dimensions,
                period=Duration.minutes(1),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        cloudwatch.Alarm(
            self,
            "OrangeAgentCoreFlowErrors",
            alarm_name="OrangeChatErrors",
            metric=cloudwatch.Metric(
                namespace="bedrock-agentcore",
                metric_name="OrangeElectronicsFlowErrors",
                period=Duration.minutes(1),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Token usage anomaly detection per intent
        intents = ["DEVICE_REGISTRATION", "PRODUCT_INFORMATION", "GREETINGS", "NOT_VALID"]

        for intent in intents:
            intent_dimensions = {
                "AgentRuntimeName": "orange_electronics_agent",
                "Intent": intent
            }

            cloudwatch.CfnAnomalyDetector(
                self,
                f"TokenUsageAnomalyDetector{intent}",
                namespace="bedrock-agentcore",
                metric_name="OrangeElectronicsFlowTokens",
                stat="Maximum",
                dimensions=[
                    cloudwatch.CfnAnomalyDetector.DimensionProperty(
                        name="AgentRuntimeName",
                        value="orange_electronics_agent"
                    ),
                    cloudwatch.CfnAnomalyDetector.DimensionProperty(
                        name="Intent",
                        value=intent
                    )
                ]
            )

            intent_metric = cloudwatch.Metric(
                namespace="bedrock-agentcore",
                metric_name="OrangeElectronicsFlowTokens",
                dimensions_map=intent_dimensions,
                period=Duration.minutes(5),
                statistic="Maximum",
            )

            anomaly_band = cloudwatch.MathExpression(
                expression="ANOMALY_DETECTION_BAND(m1, 2)",
                using_metrics={"m1": intent_metric},
                period=Duration.minutes(5),
            )

            cloudwatch.Alarm(
                self,
                f"OrangeTokenUsageAnomaly{intent}",
                alarm_name=f"OrangeTokenUsage-{intent}",
                metric=anomaly_band,
                threshold=0,
                evaluation_periods=3,
                comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_LOWER_OR_GREATER_THAN_UPPER_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )

        # X-Ray Insights: auto-detects response time and error rate anomalies from traces
        xray.CfnGroup(
            self,
            "OrangeAgentCoreTraceGroup",
            group_name="OrangeAgentCoreTraces",
            filter_expression='service("orange_electronics_agent.DEFAULT")',
            insights_configuration=xray.CfnGroup.InsightsConfigurationProperty(
                insights_enabled=True,
                notifications_enabled=False,
            ),
        )


