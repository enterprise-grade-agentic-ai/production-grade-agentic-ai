import os
import logging
import boto3
from crewai.hooks import after_llm_call

logger = logging.getLogger(__name__)

bedrock_runtime = boto3.client("bedrock-runtime")

GUARDRAIL_ID = os.getenv("GUARDRAIL_ID")
GUARDRAIL_VERSION = os.getenv("GUARDRAIL_VERSION", "DRAFT")

def guardrail_input_check(last_message):
    response = bedrock_runtime.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source="INPUT",
        content=[{"text": {"text": last_message}}]
    )

    if response["action"] == "GUARDRAIL_INTERVENED":
        logger.warning(f"Guardrail blocked INPUT: {response.get('outputs', [])}")
        raise ValueError("Guardrail blocked input: content policy violation")
    
def register_guardrail_hooks():
    """Register Bedrock Guardrail hooks for LLM input/output validation.
    Call this once from the flow before any LLM calls are made."""

    @after_llm_call
    def guardrail_output_check(context):
        if not context.response:
            return None

        response = bedrock_runtime.apply_guardrail(
            guardrailIdentifier=GUARDRAIL_ID,
            guardrailVersion=GUARDRAIL_VERSION,
            source="OUTPUT",
            content=[{"text": {"text": context.response}}]
        )

        if response["action"] == "GUARDRAIL_INTERVENED":
            logger.warning(f"Guardrail blocked OUTPUT: {response.get('outputs', [])}")
            outputs = response.get("outputs", [])
            if outputs:
                return outputs[0].get("text", "I cannot provide that response.")
            return "I cannot provide that response."

        return None
