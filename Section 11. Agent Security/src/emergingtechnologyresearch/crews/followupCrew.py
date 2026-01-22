from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import Any, List
from ..utils.llmUtils import getLlm, getVerbose
from ..tools.publishedTopicsTool import PublishedTopicsTool

@CrewBase
class FollowupQuestionCrew():
    """FollowupQuestionCrew crew"""
    agents_config = '../config/followupAgents.yaml'
    tasks_config = '../config/followupTasks.yaml'
    agents: List[BaseAgent]
    tasks: List[Task]
    stepCallback:Any=None

    def __init__(self, stepCallback=None):
        self.stepCallback = stepCallback

    @agent
    def followup_question_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['followup_question_agent'],
            verbose=getVerbose(),
            llm = getLlm(),
            tools = [PublishedTopicsTool()]
        )

    @task
    def followup_question_task(self) -> Task:
        return Task(
            config=self.tasks_config['followup_question_task']
        )

    @crew
    def crew(self) -> Crew:
        """Creates the FollowupQuestionCrew crew"""
        return Crew(
            name="FollowupQuestionCrew",
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=getVerbose(),
            step_callback=self.stepCallback,
            task_callback=self.stepCallback
        )