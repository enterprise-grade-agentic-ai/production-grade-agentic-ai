#!/usr/bin/env python3
import aws_cdk as cdk

from src.AgentCoreStack import AgentCoreStack
from src.GuardrailStack import GuardrailStack

app = cdk.App()

guardrailStack = GuardrailStack(app, "DeepResearchGuardrail")
agentCoreStack = AgentCoreStack(app, "DeepResearchAgentCore")
agentCoreStack.add_dependency(guardrailStack)

app.synth()
