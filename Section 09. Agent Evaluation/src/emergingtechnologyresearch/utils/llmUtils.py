import os
from crewai.llm import BaseLLM, LLM
from typing import (
    Any,
    Union,
)
from pydantic import InstanceOf

def getVerbose() -> bool:
    return True if os.getenv("VERBOSE_OUTPUT") == "TRUE" else False

def getLlm()->Union[str, InstanceOf[BaseLLM], Any]:
    if os.getenv('OPENAI_API_KEY'):
        return LLM(
            model='openai/gpt-4.1',
            api_key=os.getenv('OPENAI_API_KEY')
        )
    else:
        return LLM('bedrock/us.amazon.nova-pro-v1:0')