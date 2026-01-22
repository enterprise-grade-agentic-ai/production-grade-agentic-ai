from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import Any, List
from enum import Enum
from ..utils.llmUtils import getLlm, getVerbose

# Define Pydantic models for output
from pydantic import BaseModel, Field

class Intent(Enum):
    EMERGING_TECHNOLOGY_RESEARCH = "EMERGING_TECHNOLOGY_RESEARCH"
    EMERGING_TECHNOLOGY_FOLLOW_UP_QUERY = "EMERGING_TECHNOLOGY_FOLLOW_UP_QUERY"
    USER_PROFILE_INFORMATION_IS_REQUIRED = "USER_PROFILE_INFORMATION_IS_REQUIRED"

class PromptIntent(BaseModel):
   intent: Intent = Field(description="Intent of the Prompt")
   topic: str = Field(description="Topic of the intent. Only used when intent is EMERGING_TECHNOLOGY_RESEARCH")
   style: str = Field(description="Style of the expected output.")

@CrewBase
class IntentAnalyzer():
    """IntentAnalyzer crew"""
    agents_config = '../config/intentAgents.yaml'
    tasks_config = '../config/intentTasks.yaml'
    agents: List[BaseAgent]
    tasks: List[Task]
    stepCallback:Any=None

    def __init__(self, stepCallback=None):
        self.stepCallback = stepCallback

    @agent
    def intent_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['intent_analyst'],
            verbose=getVerbose(),
            llm = getLlm()
        )

    @task
    def intent_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config['intent_analysis_task'],
            output_pydantic=PromptIntent
        )

    @crew
    def crew(self) -> Crew:
        """Creates the IntentAnalyzer crew"""
        return Crew(
            name="IntentAnalyzer",
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=getVerbose(),
            step_callback=self.stepCallback,
            task_callback=self.stepCallback
        )