from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import Any, List
from ..tools.dalleTool import DallETool
from pydantic import BaseModel, Field
from ..utils.llmUtils import getLlm, getVerbose

class BannerImage(BaseModel):
   url:str = Field(description="URL of the generated image")

@CrewBase
class ReportBannerCrew():
    agents_config = '../config/reportBannerAgents.yaml'
    tasks_config = '../config/reportBannerTasks.yaml'
    agents: List[BaseAgent]
    tasks: List[Task]
    stepCallback:Any=None

    def __init__(self, stepCallback=None):
        self.stepCallback = stepCallback
    
    def getTools(self):
        dalleTool = DallETool(model="dall-e-2",
            size="256x256",
            n=1)
        return [dalleTool]

    @agent
    def banner_creator(self) -> Agent:
        return Agent(
            config=self.agents_config['banner_creator'],
            verbose=getVerbose(),
            tools=self.getTools(),
            llm=getLlm()
        )

    @task
    def banner_creation_task(self) -> Task:
        return Task(
            config=self.tasks_config['banner_creation_task'],
            output_pydantic=BannerImage
        )

    @crew
    def crew(self) -> Crew:
        """Creates the ReportBannerCrew crew"""

        return Crew(
            name="ReportBannerCrew",
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=getVerbose(),
            step_callback=self.stepCallback,
            task_callback=self.stepCallback
        )