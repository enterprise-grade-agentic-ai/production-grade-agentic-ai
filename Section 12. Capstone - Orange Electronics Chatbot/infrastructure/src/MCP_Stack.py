from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnOutput,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_bedrockagentcore as bedrockagentcore,
    aws_secretsmanager as secretsmanager,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct
import os
from typing import Tuple

class MCP_Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        device_management_lambda = self.setupDeviceManagementLambda()
        mcp_user_pool, mcp_m2m_client, user_pool_domain = self.setupCognito()
        self.setupMCPGateway(mcp_user_pool, mcp_m2m_client, user_pool_domain, device_management_lambda)
        self.setupSecret(mcp_m2m_client)

        # CloudWatch Tier 1 Alarm
        device_management_lambda.metric_errors(
            period=Duration.minutes(1)
        ).create_alarm(
            self,
            "OrangeDeviceLambdaErrors",
            alarm_name="OrangeDeviceLambdaErrors",
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

    def setupCognito(self) -> Tuple[cognito.UserPool, cognito.UserPoolClient, cognito.UserPoolDomain] :
        # Cognito User Pool for MCP Gateway authentication
        mcp_user_pool = cognito.UserPool(
            self,
            "orange-mcp-user-pool",
            removal_policy=RemovalPolicy.DESTROY
        )

        read_scope = cognito.ResourceServerScope(
            scope_name="read", 
            scope_description="Read access"
        )

        resource_server = mcp_user_pool.add_resource_server("MyApiResourceServer",
            identifier="MyApiResourceServer",
            scopes=[read_scope] # Pass the variables here
        )
        resource_server.apply_removal_policy(RemovalPolicy.DESTROY)

        # M2M app client for authenticating requests to the MCP Gateway
        # Uses client_id + client_secret (client credentials grant); no OAuth flows.
        mcp_m2m_client = mcp_user_pool.add_client(
            "Orance-MCPM2MClient",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    client_credentials=True # The specific flow for M2M
                ),
                scopes=[
                    cognito.OAuthScope.resource_server(resource_server, read_scope)
                ]
            )
        )

        CfnOutput(self, "OrangeMcpClientID",
            value=mcp_m2m_client.user_pool_client_id,
            export_name="OrangeMcpClientID",
        )

        account = Stack.of(self).account

        user_pool_domain = cognito.UserPoolDomain(self,
            "Orange-Domain",
            user_pool=mcp_user_pool,
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"orange-{account}"
            )
        )

        CfnOutput(self, "OrangeCognitoDomainName",
            value=user_pool_domain.domain_name,
            export_name="OrangeCognitoDomainName",
        )

        return mcp_user_pool, mcp_m2m_client, user_pool_domain

    def setupDeviceManagementLambda(self) -> lambda_.Function:
        # DynamoDB table for customer–device mappings
        customer_devices_table = dynamodb.Table(
            self,
            "Orange-CustomerDevicesTable",
            table_name="customer-devices",
            partition_key=dynamodb.Attribute(
                name="customer_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="device_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Lambda function that manages customer devices
        lambda_code_path = os.path.join(
            os.path.dirname(__file__), "../lambda/manage_customer_devices"
        )
        manage_customer_devices_lambda = lambda_.Function(
            self,
            "Orange-ManageCustomerDevices",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_asset(lambda_code_path),
            environment={
                "TABLE_NAME": customer_devices_table.table_name,
            },
        )

        customer_devices_table.grant_read_write_data(manage_customer_devices_lambda)

        return manage_customer_devices_lambda

    def setupMCPGateway(self, mcp_user_pool, mcp_m2m_client, user_pool_domain, manage_customer_devices_lambda) -> None:
        # IAM role for the Bedrock AgentCore MCP Gateway (invokes Lambda targets)
        region = Stack.of(self).region
        # TODO Add condition for MCP Gateway ID
        # TODO Add bedrock-agentcore:GetPolicyEngine to allow policy engine calls
        gateway_role = iam.Role(
            self,
            "Orange-MCPGatewayRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Role for Bedrock AgentCore MCP Gateway to invoke Lambda targets",
        )
        manage_customer_devices_lambda.grant_invoke(gateway_role)

        # Cognito discovery URL for JWT validation (issuer + JWKS)
        cognito_discovery_url = (
            f"https://cognito-idp.{region}.amazonaws.com/"
            f"{mcp_user_pool.user_pool_id}/.well-known/openid-configuration"
        )

        # Bedrock AgentCore MCP Gateway, authenticated via Cognito JWT
        mcp_gateway = bedrockagentcore.CfnGateway(
            self,
            "Orange-MCPGateway",
            name="Orange-MCP-gateway",
            role_arn=gateway_role.role_arn,
            authorizer_type="CUSTOM_JWT",
            protocol_type="MCP",
            authorizer_configuration={
                "customJwtAuthorizer": {
                    "discoveryUrl": cognito_discovery_url,
                    "allowedClients": [mcp_m2m_client.user_pool_client_id],
                }
            },
            description="MCP Gateway authenticated with Cognito M2M client",
        )
        mcp_gateway.node.add_dependency(gateway_role)
        mcp_gateway.node.add_dependency(mcp_m2m_client)
        mcp_gateway.node.add_dependency(user_pool_domain)

        CfnOutput(self, "OrangeMcpGatewayUrl",
            value=mcp_gateway.attr_gateway_url,
            export_name="OrangeMcpGatewayUrl",
        )

        # Gateway target: Lambda function for Manage Customer Devices (typed CDK props)
        # CredentialProviderConfigurations is required for Lambda targets: use WORKLOAD_IDENTITY
        # so the gateway uses its workload identity (IAM role) to invoke the Lambda.
        bedrockagentcore.CfnGatewayTarget(
            self,
            "CustomerDeviceManagementTarget",
            gateway_identifier=mcp_gateway.ref,
            name="device-management",
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=bedrockagentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=manage_customer_devices_lambda.function_arn,
                        tool_schema=bedrockagentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="save_customer_device",
                                    description="Saves a customer ID and device ID mapping",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "customer_id": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Customer identifier",
                                            ),
                                            "device_id": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Device identifier",
                                            )
                                        },
                                        required=["customer_id", "device_id"],
                                    ),
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="remove_customer_device",
                                    description="Removes a customer ID and device ID mapping",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "customer_id": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Customer identifier",
                                            ),
                                            "device_id": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Device identifier",
                                            )
                                        },
                                        required=["customer_id", "device_id"]
                                    ),
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_customer_devices",
                                    description="Reads customer ID and device ID mappings",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "customer_id": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Customer identifier",
                                            )
                                        },
                                        required=["customer_id"]
                                    ),
                                )
                            ],
                        ),
                    ),
                ),
            ),
            credential_provider_configurations=[
                bedrockagentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE",
                    # Gateway uses IAM (its service role) to authenticate and invoke the Lambda target.
                ),
            ],
            description="Lambda target to manage customer devices",
        )

    def setupSecret(self, mcp_client) -> None:
        # Create the Secret in AWS Secrets Manager
        my_secret = secretsmanager.Secret(self, "ApiSecrets",
            secret_name="orange/secrets",
            description="Contains Cognito Client Secret and OpenAI Key",
            secret_object_value={
                "MCP_CLIENT_SECRET": mcp_client.user_pool_client_secret
            }
        )

        # Export the secret ARN
        CfnOutput(
            self,
            "OrangeSecretsArn",
            value=my_secret.secret_arn,
            description="ARN of the API secrets in Secrets Manager",
            export_name="OrangeSecretsArn",
        )

        CfnOutput(
            self,
            "OrangeSecretsName",
            value=my_secret.secret_name,
            description="Name of the API secrets in Secrets Manager",
            export_name="OrangeSecretsName",
        )