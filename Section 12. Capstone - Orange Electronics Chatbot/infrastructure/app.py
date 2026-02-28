#!/usr/bin/env python3
import aws_cdk as cdk

from src.KnowledgeBaseStack import KnowledgeBaseStack
from src.MCP_Stack import MCP_Stack
from src.AgentMemoryStack import AgentMemoryStack
from src.AgentCoreStack import AgentCoreStack
from src.TelegramIntegrationStack import TelegramIntegrationStack
from src.GuardrailStack import GuardrailStack

app = cdk.App()
guardrailStack = GuardrailStack(app, "OrangeGuardrail")
kbStack = KnowledgeBaseStack(app, "OrangeKB")
mcpStack = MCP_Stack(app, "OrangeMCP")
memoryStack = AgentMemoryStack(app, "OrangeAgentMemory")

agentCoreStack = AgentCoreStack(app, "OrangeAgentCore")
agentCoreStack.add_dependency(kbStack)
agentCoreStack.add_dependency(mcpStack)
agentCoreStack.add_dependency(memoryStack)
agentCoreStack.add_dependency(guardrailStack)

telegramStack = TelegramIntegrationStack(app, "OrangeTelegramIntegration")
telegramStack.add_dependency(agentCoreStack)

app.synth()
