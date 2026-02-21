import os
import logging
from crewai.hooks import before_tool_call

logger = logging.getLogger(__name__)


def register_tool_call_hooks():
    """Register tool call validation hooks.
    Call this once from the flow before any tool calls are made."""

    @before_tool_call
    def validate_customer_id(context):
        """Intercept tool calls to validate customer_id matches the current session."""
        tool_input = context.tool_input
        if "customer_id" in tool_input:
            expected_customer_id = os.getenv("CUSTOMER_ID")
            if tool_input["customer_id"] != expected_customer_id:
                logger.warning(
                    f"Blocked tool '{context.tool_name}': "
                    f"customer_id '{tool_input['customer_id']}' does not match expected '{expected_customer_id}'"
                )
                return False
        return True
