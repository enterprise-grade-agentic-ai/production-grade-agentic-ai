from crewai import Agent, Crew, Process, Task
from ..utils.mcpUtils import McpUtils
from ..utils.llmUtils import getLlm, getVerbose
from crewai_tools.aws.bedrock.knowledge_base.retriever_tool import BedrockKBRetrieverTool
import os
import logging
from pydantic import BaseModel, Field
from crewai.flow import or_
from crewai.flow.flow import Flow, listen, router, start
from typing import Optional
from enum import Enum
from ..utils.memoryUtils import MemoryUtils
from ..utils.guardrailUtils import register_guardrail_hooks, guardrail_input_check
from ..utils.toolCallValidationUtils import register_tool_call_hooks
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)
register_guardrail_hooks()
register_tool_call_hooks()

class Intent(Enum):
    DEVICE_REGISTRATION = "DEVICE_REGISTRATION"
    PRODUCT_INFORMATION = "PRODUCT_INFORMATION"
    GREETINGS = "GREETINGS"
    NOT_VALID = "NOT_VALID"

class PromptIntent(BaseModel):
   intent: Intent = Field(description="Intent of the Prompt")

class OrangeElectronicsFlowState(BaseModel):
    prompt:Optional[str] = Field(default=None, description="User prompt")
    sessionId:Optional[str] = Field(default=None, description="ID of the session")
    customerId:Optional[str] = Field(default=None, description="ID of the customer")
    customerFirstName:Optional[str] = Field(default=None, description="Name of the customer")
    conversationHistory:Optional[str] = Field(default=None, description="Conversation History")
    intent:Optional[PromptIntent] = Field(default=None, description="Intent identified for the prompt")
    response:Optional[str] = Field(default="", description="Response generated")
    totalTokenUsage:int = Field(default=0, description="Total tokens used across all crews")

class OrangeElectronicsFlow(Flow[OrangeElectronicsFlowState]):
    """OrangeElectronicFlow flow"""
    agentsConfig: {}
    tasksConfig: {}

    def __init__(self):
        super().__init__()
        currentDir = Path(__file__).resolve().parent
        with open(f"{currentDir}/../config/orangeElectronicsAgents.yaml", 'r') as agentConfig:
            self.agentsConfig = yaml.safe_load(agentConfig)
        with open(f"{currentDir}/../config/orangeElectronicsTasks.yaml", 'r') as taskConfig:
            self.tasksConfig = yaml.safe_load(taskConfig)

    @start()
    def initialize(self):
        self.state.conversationHistory = MemoryUtils(
            sessionId=self.state.sessionId, 
            customerId=self.state.customerId).loadShortTermMemory()

    @listen("initialize")
    def checkIntent(self):
        guardrail_input_check(self.state.prompt)
        if self.state.prompt == "/start":
            self.state.prompt = "hi"
            self.state.intent = PromptIntent(intent=Intent.GREETINGS)
        else:    
            self.state.intent = self.runCrew(crewName="intent_detection", outputModel=PromptIntent).pydantic

    @router(checkIntent)
    def routeRequest(self):
        match self.state.intent.intent:
            case Intent.DEVICE_REGISTRATION:
                return "DeviceRegistration"
            case Intent.PRODUCT_INFORMATION:
                return "ProductInformation"
            case Intent.GREETINGS:
                return "Greetings"
        return "NotValid"

    @listen("DeviceRegistration")
    def deviceRegistration(self):
        self.state.response = self.runCrew(crewName="device_registration", tools=McpUtils().getTools()).raw

    @listen("ProductInformation")
    def productInformation(self):
        kb_tool = BedrockKBRetrieverTool(
            knowledge_base_id=os.getenv('AWS_KNOWLEDGE_BASE_ID'),
            number_of_results=5
        )
        self.state.response = self.runCrew(crewName="product_information", tools=[kb_tool]).raw

    @listen("Greetings")
    def greetings(self):
        self.state.response = self.runCrew(crewName="greetings", tools=[]).raw

    @listen("NotValid")
    def notValid(self):
        self.state.response = "Sorry! I currently can not handle this query."

    @listen(or_(deviceRegistration, productInformation, greetings, notValid))
    def finish(self):
        # Save response in memory
        MemoryUtils(sessionId=self.state.sessionId, customerId=self.state.customerId).saveMemory(
                userPrompt=self.state.prompt, assistantResponse=self.state.response)

        return self.state.response

    def runCrew(self, crewName, tools=[], outputModel= None):
        agent = Agent(
            config=self.agentsConfig[f"{crewName}_agent"],
            verbose=getVerbose(),
            tools=tools,
            llm=getLlm()
        )

        if outputModel:
            task = Task(
                config=self.tasksConfig[f"{crewName}_task"],
                output_pydantic=outputModel,
                agent=agent
            )
        else:
            task = Task(
                config=self.tasksConfig[f"{crewName}_task"],
                agent=agent
            )

        crew = Crew(
            name=f"{crewName}_Crew",
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=getVerbose()
        )
        result = crew.kickoff(inputs={
            "prompt": self.state.prompt,
            "conversationHistory": self.state.conversationHistory,
            "customerId": self.state.customerId,
            "customerFirstName": self.state.customerFirstName
        })
        self.state.totalTokenUsage += result.token_usage.total_tokens
        return result