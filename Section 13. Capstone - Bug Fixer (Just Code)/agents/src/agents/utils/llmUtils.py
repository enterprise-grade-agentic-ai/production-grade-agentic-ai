import json
import logging
import os
from crewai.hooks.decorators import after_llm_call, before_llm_call
from crewai.hooks.llm_hooks import LLMCallHookContext
from crewai.llm import BaseLLM, LLM
from typing import (
    Any,
    Union,
)
from pydantic import InstanceOf

logger = logging.getLogger(__name__)

# ── LLM call debug hooks (auto-registered by the decorators) ──────────────────
@before_llm_call
def log_llm_request(context: LLMCallHookContext) -> None:
    # Anthropic requires messages to alternate roles (user/assistant).
    # When the last message is from the assistant, we either split it into a
    # Thought/Action part (assistant) and an Observation part (user), or flip
    # the role to "user" if no Observation is present yet.
    if context.messages and context.messages[-1]["role"] == "assistant":
        content = context.messages[-1].get("content", "")
        if isinstance(content, str) and "\nObservation:" in content:
            # Split ReAct message: keep Thought/Action/Input as assistant,
            # promote Observation (the tool result) to a user message.
            # This correctly models the environment feeding back to the agent.
            thought_action, observation = content.split("\nObservation:", 1)
            context.messages[-1]["content"] = thought_action
            context.messages.append({"role": "user", "content": "Observation:" + observation})
        else:
            # No Observation yet (first call or final answer path) — flip role.
            context.messages[-1]["role"] = "user"

def getVerbose() -> bool:
    return True if os.getenv("VERBOSE_OUTPUT") == "TRUE" else False

def getLlm()->Union[str, InstanceOf[BaseLLM], Any]:
    if os.getenv('OPENAI_API_KEY'):
        if os.getenv('OPENAI_API_MODEL'):
            return LLM(
                model=f"openai/{os.getenv('OPENAI_API_MODEL')}",
                api_key=os.getenv('OPENAI_API_KEY')
            )
        else:
            return LLM(
                model='openai/gpt-5.2',
                api_key=os.getenv('OPENAI_API_KEY')
            )
    elif os.getenv('ANTHROPIC_API_KEY'):
        return LLM(
            model='anthropic/claude-sonnet-4-6',
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
    else:
        return LLM(
            model='bedrock/us.anthropic.claude-sonnet-4-6',
            stream=False
        )
