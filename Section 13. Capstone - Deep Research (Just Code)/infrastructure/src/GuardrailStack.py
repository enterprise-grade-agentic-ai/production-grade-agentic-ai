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
            "DeepResearchGuardrail",
            name="DeepResearchGuardrail",
            description="Guardrail for Deep Research agent — blocks harmful content in research articles",
            blocked_input_messaging="Your request was blocked by our content policy.",
            blocked_outputs_messaging="The generated content was blocked by our content policy.",
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
            # No topic_policy_config — research articles may cover any legitimate topic
            # No sensitive_information_policy_config — research articles may cite public figures/institutions
        )

        CfnOutput(
            self,
            "DeepGuardrailId",
            value=guardrail.attr_guardrail_id,
            description="Deep Research Guardrail ID",
            export_name="DeepGuardrailId",
        )
