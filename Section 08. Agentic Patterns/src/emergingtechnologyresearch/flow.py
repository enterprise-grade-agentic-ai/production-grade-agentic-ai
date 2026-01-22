# Create a flow class
from datetime import datetime
from crewai.flow import or_
from crewai.flow.flow import Flow, listen, router, start
from typing import Any,Optional
import os

from pydantic import BaseModel, Field

from . utils.memoryUtils import MemoryUtils

from . crews.followupCrew import FollowupQuestionCrew
from . crews.intentCrew import Intent, PromptIntent, IntentAnalyzer
from . crews.researchCrew import Emergingtechnologyresearch, ResearchReport
from . crews.reportBannerCrew import ReportBannerCrew

import asyncio

# Pydantic model for the flow state
class EmergingTechnologyFlowState(BaseModel):
    prompt:Optional[str] = Field(default=None, description="User prompt")
    sessionId:Optional[str] = Field(default=None, description="ID of the session")
    actorId:Optional[str] = Field(default=None, description="ID of the actor")
    intent:Optional[PromptIntent] = Field(default=None, description="Intent identified for the prompt")
    response:Optional[str] = Field(default="", description="Response generated")
    report:Optional[ResearchReport] = Field(default=None, description="Report generated")
    conversationHistory:Optional[str] = Field(default=None, description="Conversation History")
    preferences:Optional[str] = Field(default=None, description="User Preferences")
    banners:Optional[list[str]] = Field(default=None, description="Array of banner images for each section")

# Flow taking care of user prompt
class EmergingTechnologyFlow(Flow[EmergingTechnologyFlowState]):
    stepCallback:Any=None

    def __init__(self, stepCallback=None):
        super().__init__()
        self.stepCallback = stepCallback
    
    @start()
    def initialize(self):
        self.state.conversationHistory = MemoryUtils(
            sessionId=self.state.sessionId, 
            actorId=self.state.actorId).loadShortTermMemory()

        self.state.preferences = MemoryUtils(
            sessionId=self.state.sessionId, 
            actorId=self.state.actorId).extractUserPreferences()

    @listen("initialize")
    def checkIntent(self):
        inputs = {
            'prompt': self.state.prompt,
            'preferences': self.state.preferences
        }

        response = IntentAnalyzer(self.stepCallback).crew().kickoff(inputs=inputs)
        self.state.intent = response.pydantic

    @router(checkIntent)
    def routeRequest(self):
        match self.state.intent.intent:
            case Intent.EMERGING_TECHNOLOGY_RESEARCH:
                return "EmergingTechnologyResearch"
            case Intent.EMERGING_TECHNOLOGY_FOLLOW_UP_QUERY:
                return "EmergingTechnologyFollowup"

    @listen("EmergingTechnologyResearch")
    def research(self):
        inputs = {
            'topic': self.state.intent.topic,
            'current_year': str(datetime.now().year),
            'style': self.state.intent.style,
            'prompt': self.state.prompt,
        }
        self.state.report = Emergingtechnologyresearch(self.stepCallback).crew().kickoff(inputs=inputs).pydantic

    @listen(research)
    async def generateBannerImages(self):
        if (os.getenv('GENERATE_BANNERS') == "TRUE" and os.getenv("OPENAI_API_KEY") != None 
                and self.state.report != None and self.state.report.sections != None):
            results = []
            for section in self.state.report.sections:
                inputs = {
                    'topic': section.title,
                    'overview': section.overview,
                    'style': self.state.intent.style
                }
                result = ReportBannerCrew(self.stepCallback).crew().kickoff_async(inputs=inputs)
                results.append(result)
            
            results = await asyncio.gather(*results)
        
            banners = []
            for result in results:
                banners.append(result.pydantic.url)
            self.state.banners = banners

    @listen(generateBannerImages)
    def generateReport(self):
        if self.state.report:
            response = f"# Research Report on: {self.state.intent.topic}\n"
            for i, section in enumerate(self.state.report.sections,0):
                response += f"## {section.title} \n\n"
                if (self.state.banners != None and self.state.banners[i] != None):
                    response += f"![Banner]({self.state.banners[i]}) \n\n"
                response += f"### Overview \n"
                response += f"{section.overview} \n"
                response += f"### Key Developments \n"
                for keyDevelopment in section.keyDevelopments:
                    response += f"+ {keyDevelopment} \n"
                response += f"### Impact \n"
                response += f"{section.impact} \n\n"
            response += f"## Conclusion:\n"
            response += f"{self.state.report.conclusion} \n"
            self.state.response = response

    @listen("EmergingTechnologyFollowup")
    def followup(self):
        inputs = {
            'prompt': self.state.prompt,
            'style': self.state.intent.style,
            'history': self.state.conversationHistory,
            'actorId': self.state.actorId
        }
        self.state.response = FollowupQuestionCrew(self.stepCallback).crew().kickoff(inputs=inputs).raw

    @listen(or_(generateReport, followup))
    def finish(self):
        return self.state.response