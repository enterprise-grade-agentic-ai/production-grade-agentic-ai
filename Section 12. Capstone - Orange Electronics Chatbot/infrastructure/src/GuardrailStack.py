from aws_cdk import (
    Stack,
    CfnOutput,
    aws_bedrock as bedrock,
)
from constructs import Construct


class GuardrailStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        guardrail = bedrock.CfnGuardrail(
            self,
            "OrangeGuardrail",
            name="OrangeElectronicsGuardrail",
            description="Guardrail for Orange Electronics agent - blocks PII, harmful content, and competitor mentions",
            blocked_input_messaging="Your message was blocked by our content policy. Please rephrase and try again.",
            blocked_outputs_messaging="The response was blocked by our content policy.",
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="HATE",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="INSULTS",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="SEXUAL",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="VIOLENCE",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="MISCONDUCT",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                ]
            ),
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
                topics_config=[
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name="Apple",
                        definition="Questions about Apple products and its comparison with products offered by Orange.",
                        type="DENY",
                    ),
                ]
            ),

            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=[
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="ADDRESS", action="BLOCK"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="AGE", action="BLOCK"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="CREDIT_DEBIT_CARD_NUMBER", action="BLOCK"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="EMAIL", action="BLOCK"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="INTERNATIONAL_BANK_ACCOUNT_NUMBER", action="BLOCK"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="PHONE", action="BLOCK")
                ]
            ),
        )

        CfnOutput(
            self,
            "OrangeGuardrailId",
            value=guardrail.attr_guardrail_id,
            description="Guardrail ID",
            export_name="OrangeGuardrailId",
        )

