import asyncio
import base64
import boto3
import json
import markdown as md_lib
import os
import logging
import uuid
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from crewai import Agent, Crew, Process, Task
from crewai.flow.flow import Flow, listen, router, start
from crewai.flow import or_

from ..utils.llmUtils import getLlm, getVerbose
from crewai_tools import RagTool
from ..utils.guardrailUtils import register_guardrail_hooks, guardrail_input_check
from crewai_tools.tools.rag import RagToolConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
register_guardrail_hooks()


# ── Enums & State ───────────────────────────────────────────────────────────────

class SubQuestions(BaseModel):
    sub_questions: Optional[list[str]] = Field(default=None, description="Generated list of research sub questions")

class SubQuestionFinding(BaseModel):
    finding: str = Field(default=None, description="Generated research content per page extracted")
    url: str = Field(default=None, description="URL of the page from which content has been extracted")

class SubQuestionFindings(BaseModel):
    findings: Optional[list[SubQuestionFinding]] = Field(default=None, description="Generated research findings for all sub-questions")

class GapsIdentified(BaseModel):
    gaps: Optional[list[str]] = Field(default=None, description="Gaps identified")

class DeepResearchState(BaseModel):
    # Caller-supplied inputs
    question: Optional[str] = Field(default=None, description="Research topic")

    # Internal pipeline state
    mcpUrl: Optional[str] = Field(default=None, description="MCP Url of Tavily")
    sub_questions: Optional[SubQuestions] = Field(default=None, description="Generated research sub questions")
    article_draft: Optional[str] = Field(default=None, description="First draft article")
    critic_feedback: Optional[str] = Field(default=None, description="Critic's feedback on draft")
    final_article: Optional[str] = Field(default=None, description="Revised final article")
    published_url: Optional[str] = Field(default=None, description="Published article URL")
    gap_check_iterations: int = Field(default=0, description="Gap check iterations performed")
    rag_tool: Optional[RagTool] = Field(default=None, description="RAG tool for Agentic RAG")
    article_id: Optional[str] = Field(default=None, description="Unique ID for this article's S3 assets")
    banner_image_url: Optional[str] = Field(default=None, description="S3 URL of the generated banner image")

# ── Flow ────────────────────────────────────────────────────────────────────────

class DeepResearchFlow(Flow[DeepResearchState]):
    agentsConfig: dict = {}
    tasksConfig: dict = {}

    # Loads agent and task YAML configs from the config directory.
    def __init__(self):
        super().__init__()
        current_dir = Path(__file__).resolve().parent
        with open(f"{current_dir}/../config/deepResearchAgents.yaml", 'r') as f:
            self.agentsConfig = yaml.safe_load(f)
        with open(f"{current_dir}/../config/deepResearchTasks.yaml", 'r') as f:
            self.tasksConfig = yaml.safe_load(f)

    # Entry point: sets up the RAG tool, runs the guardrail check, and generates sub-questions via the planner crew.
    @start()
    async def initialize(self):
        config: RagToolConfig = {
            "embedding_model": {
                "provider": "amazon-bedrock",
                "config": {
                    "model_name": "amazon.titan-embed-text-v2:0"
                }
            }
        }
        self.state.rag_tool = RagTool(config=config, similarity_threshold=0.5, limit=5)
        self.state.mcpUrl = f"https://mcp.tavily.com/mcp/?tavilyApiKey={os.getenv('TAVILY_API_KEY')}"

        guardrail_input_check(self.state.question)
        result = await self._run_crew(
            crew_name="planner",
            inputs={"question": self.state.question},
            output_model=SubQuestions, 
            mcps = [self.state.mcpUrl]
        )
        self.state.sub_questions = result.pydantic
        logger.info(f"initialize complete — generated {len(self.state.sub_questions.sub_questions)} sub-questions")

    # Triggers parallel web research for each planner-generated sub-question.
    @listen(initialize)
    async def runResearch(self):
        await self._run_parallel_research(self.state.sub_questions.sub_questions)
        logger.info("runResearch complete — all sub-questions researched and ingested into RAG")

    # Spawns concurrent researcher crews for each sub-question and ingests findings into the RAG tool.
    async def _run_parallel_research(self, sub_questions: list[str]):
        # Researches a single sub-question and adds its findings to the RAG store.
        async def research_one(sub_question: str, idx: int):
            inputs = {
                "sub_question": sub_question,
                "question": self.state.question
            }
            
            result = await self._run_crew(crew_name = "researcher", inputs = inputs, output_model = SubQuestionFindings, mcps = [self.state.mcpUrl])
            findings: SubQuestionFindings = result.pydantic
            for f in findings.findings:
                self.state.rag_tool.add(f"Content: {f.finding}\nSource URL: {f.url}", data_type="text")

        coroutines = [research_one(sq, i) for i, sq in enumerate(sub_questions)]
        await asyncio.gather(*coroutines)
        logger.info(f"_run_parallel_research complete — researched {len(sub_questions)} question(s)")


    # Iterates up to 2 gap-check cycles, filling knowledge gaps with additional parallel research.
    @listen("runResearch")
    async def checkGaps(self):
        while self.state.gap_check_iterations < 2:
            self.state.gap_check_iterations += 1
            result = await self._run_crew(
                crew_name="gap_checker",
                inputs={
                    "sub-questions": "\n".join(f"Sub-Question {i+1}: {q}" for i, q in enumerate(self.state.sub_questions.sub_questions))
                },
                tools=[self.state.rag_tool],
                output_model=GapsIdentified
            )
            gaps_identified: GapsIdentified = result.pydantic

            if not gaps_identified or not gaps_identified.gaps:
                break

            await self._run_parallel_research(gaps_identified.gaps)
        logger.info(f"checkGaps complete — performed {self.state.gap_check_iterations} gap-check iteration(s)")


    # Generates the first article draft using accumulated RAG knowledge and any prior critic feedback.
    @listen("checkGaps")
    async def writeArticle(self):
        result = await self._run_crew(
            crew_name="writer",
            inputs={
                "question": self.state.question,
                "sub-questions": "\n".join(f"Sub-Question {i+1}: {q}" for i, q in enumerate(self.state.sub_questions.sub_questions)),
                "critic_feedback": self.state.critic_feedback or ""
            },
            tools=[self.state.rag_tool]
        )
        self.state.article_draft = result.raw
        logger.info("writeArticle complete — article draft written")

    # Sends the draft to the critic crew and stores structured improvement feedback.
    @listen("writeArticle")
    async def critiqueArticle(self):
        result = await self._run_crew(
            crew_name="critic",
            inputs={"article_draft": self.state.article_draft}
        )
        self.state.critic_feedback = result.raw.strip()
        logger.info(f"critiqueArticle complete — feedback received (length={len(self.state.critic_feedback)})")

    # Routes to revision if feedback is present, otherwise marks the draft as approved.
    @router(critiqueArticle)
    def routeAfterCritique(self):
        if not self.state.critic_feedback:
            self.state.final_article = self.state.article_draft
            logger.info("routeAfterCritique — article approved, no revision needed")
            return "Approved"
        logger.info("routeAfterCritique — article needs revision")
        return "NeedsRevision"

    # Rewrites the article incorporating critic feedback to produce the final version.
    @listen("NeedsRevision")
    async def reviseArticle(self):
        result = await self._run_crew(
            crew_name="writer",
            inputs={
                "question": self.state.question,
                "sub-questions": "\n".join(f"Sub-Question {i+1}: {q}" for i, q in enumerate(self.state.sub_questions.sub_questions)),
                "critic_feedback": self.state.critic_feedback
            },
            tools=[self.state.rag_tool]
        )
        self.state.final_article = result.raw
        logger.info("reviseArticle complete — final article revised")

    # Generates a banner image prompt via agent, renders it with Nova Canvas, and uploads the PNG to S3.
    @listen(or_("Approved", "reviseArticle"))
    async def generateBanner(self):
        """Generate a clipart banner image for the article using Titan Image Generator G1."""
        # Step 1: Agent generates a focused image prompt from the article
        result = await self._run_crew(
            crew_name="banner",
            inputs={"final_article": self.state.final_article}
        )
        image_prompt = result.raw.strip()
        logger.info(f"Banner prompt: {image_prompt}")

        # Step 2: Call Titan Image Generator G1
        bedrock = boto3.client("bedrock-runtime")
        body = json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": image_prompt,
                "negativeText": "photorealistic, photograph, text, words, letters, complex background, human faces"
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 720,
                "width": 1280,
                "seed": 12,
                "cfgScale": 6.5
            }
        })
        response = bedrock.invoke_model(
            modelId="amazon.nova-canvas-v1:0",
            body=body,
            contentType="application/json",
            accept="application/json"
        )
        response_body = json.loads(response["body"].read())
        image_data = base64.b64decode(response_body["images"][0])

        # Step 3: Upload PNG to S3 with public-read ACL
        self.state.article_id = str(uuid.uuid4())
        bucket = os.environ["ARTICLE_BUCKET"]
        key = f"banners/{self.state.article_id}.png"
        s3 = boto3.client("s3")
        s3.put_object(Bucket=bucket, Key=key, Body=image_data, ContentType="image/png", ACL="public-read")
        region = boto3.session.Session().region_name or os.environ.get("SECRET_REGION", "us-east-1")
        self.state.banner_image_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
        logger.info(f"generateBanner complete — banner uploaded: {self.state.banner_image_url}")

    # Converts the final markdown article to HTML with the banner embedded and publishes it to S3.
    @listen("generateBanner")
    async def publishArticle(self):
        """Convert final article markdown to HTML, embed banner, and publish to S3."""
        html_body = md_lib.markdown(self.state.final_article, extensions=["tables", "fenced_code"])
        banner_tag = f'<img src="{self.state.banner_image_url}" alt="Article Banner" class="banner" />'
        template_path = Path(__file__).resolve().parent.parent / "templates" / "article_template.html"
        html = template_path.read_text().replace("<!-- ARTICLE_BANNER -->", banner_tag).replace("<!-- ARTICLE_BODY -->", html_body)
        bucket = os.environ["ARTICLE_BUCKET"]
        key = f"articles/{self.state.article_id}.html"
        s3 = boto3.client("s3")
        s3.put_object(Bucket=bucket, Key=key, Body=html.encode("utf-8"), ContentType="text/html", ACL="public-read")
        region = boto3.session.Session().region_name or os.environ.get("SECRET_REGION", "us-east-1")
        self.state.published_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
        logger.info(f"publishArticle complete — article published: {self.state.published_url}")

    # Returns the final published S3 URL as the flow output.
    @listen("publishArticle")
    def finish(self):
        logger.info(f"finish — flow complete, published URL: {self.state.published_url}")
        return self.state.published_url

    # ── Helpers ─────────────────────────────────────────────────────────────────

    # Builds and runs a named single-agent CrewAI crew, returning the kickoff result.
    async def _run_crew(self, crew_name: str, inputs: dict, tools: list = [], output_model=None, mcps: list[str] = []):
        """
        Reuses the exact runCrew() pattern from orangeElectronicsFlow.py:
        builds Agent + Task + Crew, calls kickoff(), tracks token usage.
        """
        agent = Agent(
            config=self.agentsConfig[f"{crew_name}_agent"],
            verbose=getVerbose(),
            tools=tools,
            llm=getLlm(),
            mcps=mcps
        )

        if output_model:
            task = Task(
                config=self.tasksConfig[f"{crew_name}_task"],
                output_pydantic=output_model,
                agent=agent
            )
        else:
            task = Task(
                config=self.tasksConfig[f"{crew_name}_task"],
                agent=agent
            )

        crew = Crew(
            name=f"{crew_name}_crew",
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=getVerbose()
        )

        result = await crew.kickoff_async(inputs=inputs)
        return result
