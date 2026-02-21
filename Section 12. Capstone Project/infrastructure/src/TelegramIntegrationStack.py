from aws_cdk import (
    Stack,
    Fn,
    Duration,
    CfnOutput,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct
import os

class TelegramIntegrationStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        region = Stack.of(self).region

        # REST API with prod stage
        api = apigateway.RestApi(
            self,
            "OrangeTelegramApi",
            rest_api_name="OrangeTelegramApi",
            deploy_options=apigateway.StageOptions(
                stage_name="prod"
            ),
        )

        # API Key (not required on the endpoint, but available to Lambda for webhook validation)
        api_key = apigateway.ApiKey(
            self,
            "OrangeTelegramApiKey",
            enabled=True,
        )

        # Usage plan (required to associate the API key with the API)
        usage_plan = api.add_usage_plan(
            "OrangeTelegramUsagePlan",
            name="OrangeTelegramUsagePlan",
        )
        usage_plan.add_api_key(api_key)

        # Lambda function
        lambda_code_path = os.path.join(os.path.dirname(__file__), "..", "lambda", "handle_telegram_message")

        agentcore_runtime_arn = Fn.import_value("AgentCoreRuntimeArn")
        
        telegram_handler = lambda_.Function(
            self,
            "Orange-HandleTelegramMessage",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_asset(lambda_code_path),
            environment={
                "API_KEY_ID": api_key.key_id,
                "AGENTCORE_RUNTIME_ARN": agentcore_runtime_arn,
                "AGENTCORE_RUNTIME_ENDPOINT": "DEFAULT"
            },
        )

        # Permission to fetch the API key value
        telegram_handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["apigateway:GET"],
                resources=[
                    f"arn:aws:apigateway:{region}::/apikeys/{api_key.key_id}"
                ],
            )
        )

        # Permission to invoke the AgentCore runtime
        telegram_handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=[
                    agentcore_runtime_arn,
                    f"{agentcore_runtime_arn}/*"
                ],
            )
        )

        # POST /chat -> Lambda proxy integration (no API key required)
        chat_resource = api.root.add_resource("chat")
        chat_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(telegram_handler),
            api_key_required=False,
        )

        # Outputs
        CfnOutput(
            self,
            "TelegramApiUrl",
            value=f"{api.url}chat",
            description="Telegram webhook URL (POST /chat)",
        )

        CfnOutput(
            self,
            "TelegramApiKeyId",
            value=api_key.key_id,
            description="API Key ID for Telegram webhook secret_token",
        )

        CfnOutput(
            self,
            "TelegramLambdaName",
            value=telegram_handler.function_name,
            description="Lambda function name for Telegram webhook handler",
        )

        # CloudWatch Tier 1 Alarms
        telegram_handler.metric_errors(
            period=Duration.minutes(1)
        ).create_alarm(
            self,
            "OrangeTelegramLambdaErrors",
            alarm_name="OrangeTelegramLambdaErrors",
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        telegram_handler.metric_throttles(
            period=Duration.minutes(1)
        ).create_alarm(
            self,
            "OrangeTelegramLambdaThrottles",
            alarm_name="OrangeTelegramLambdaThrottles",
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        api.metric_server_error(
            period=Duration.minutes(1)
        ).create_alarm(
            self,
            "OrangeTelegramApi5xx",
            alarm_name="OrangeTelegramApi5xx",
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

