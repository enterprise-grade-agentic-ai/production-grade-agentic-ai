from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import Any, List
from ..utils.mcpUtils import McpUtils
from ..utils.llmUtils import getLlm, getVerbose

# Define Pydantic models for output
from pydantic import BaseModel, Field

class CriticFeedback(BaseModel):
   qualityFeedback: str = Field(description="Feedback on report quality")
   approved: bool = Field(description="True if approved, false if has feedback")

@CrewBase
class CriticCrew():
    """CriticCrew"""

    agents_config = '../config/criticAgents.yaml'
    tasks_config = '../config/criticTasks.yaml'
    agents: List[BaseAgent]
    tasks: List[Task]
    stepCallback:Any=None

    def __init__(self, stepCallback=None):
        self.stepCallback = stepCallback
    
    def getTools(self):
        return McpUtils().getTools()

    @agent
    def critic_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['critic_agent'],
            verbose=getVerbose(),
            tools=self.getTools(),
            llm = getLlm()
        )

    @task
    def critic_task(self) -> Task:
        return Task(
            config=self.tasks_config['critic_task'],
            output_pydantic=CriticFeedback
        )

    @crew
    def crew(self) -> Crew:
        """Creates the CriticCrew crew"""

        return Crew(
            name="CriticCrew",
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=getVerbose(),
            step_callback=self.stepCallback,
            task_callback=self.stepCallback
        )