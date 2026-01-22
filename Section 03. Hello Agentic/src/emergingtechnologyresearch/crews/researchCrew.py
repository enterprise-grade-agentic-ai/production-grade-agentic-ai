from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from ..utils.llmUtils import getLlm, getVerbose
from typing import (
    Any,
    List
)
from pydantic import BaseModel, Field

class Section(BaseModel):
   title: str = Field(description="Title of the section")
   overview: str = Field(description="Overview of the title")
   keyDevelopments: list[str] = Field(description="Key developments in the title")
   impact: str = Field(description="Impact in the world because of the title")

class ResearchReport(BaseModel):
    title:str = Field(description="Title of the report")
    sections:list[Section] = Field(description="List of sections together forming a report")
    conclusion:str = Field(description="Conclusion of the report")

class ResearchPoints(BaseModel):
   sections: list[str] = Field(description="List of bullet points together forming a report")

@CrewBase
class Emergingtechnologyresearch():
    """Emergingtechnologyresearch crew"""

    agents_config = '../config/researchAgents.yaml'
    tasks_config = '../config/researchTasks.yaml'
    agents: List[BaseAgent]
    tasks: List[Task]
    stepCallback:Any=None

    def __init__(self, stepCallback=None):
        self.stepCallback = stepCallback
    
    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['researcher'],
            verbose=getVerbose(),
            llm=getLlm()
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['reporting_analyst'],
            verbose=getVerbose(),
            llm=getLlm()
        )

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config['research_task'],
            output_pydantic=ResearchPoints
        )

    @task
    def reporting_task(self) -> Task:
        return Task(
            config=self.tasks_config['reporting_task'],
            output_json=ResearchReport
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Emergingtechnologyresearch crew"""
        return Crew(
            name="Emergingtechnologyresearch",
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=getVerbose(),
            step_callback=self.stepCallback,
            task_callback=self.stepCallback
        )