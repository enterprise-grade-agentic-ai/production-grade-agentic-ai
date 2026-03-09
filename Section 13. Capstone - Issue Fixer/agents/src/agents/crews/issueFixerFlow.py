"""
IssueFixerFlow — CrewAI Flow that implements the core agentic loop:

    Plan  →  Implement  →  Test  →  Retry (up to MAX_RETRIES times)

Three single-agent crews are spun up in sequence:

    planner_crew     — reads the codebase, creates a step-by-step fix plan
    implementer_crew — applies every step of the plan to the source files
    validator_crew   — discovers and runs the test suite, reports results

If the tests fail the flow increments a retry counter and routes back to a
fresh planning step, this time feeding in the full failure output so the
planner understands what went wrong.  This loop repeats until either the
tests pass or MAX_RETRIES is reached.
"""

import logging
import shutil
import subprocess
import uuid
from pathlib import Path
import yaml
from pydantic import BaseModel, Field

from crewai import Agent, Crew, Process, Task
from crewai.flow.flow import Flow, listen, or_, router, start

from ..utils.llmUtils import getLlm, getVerbose
from .tools import (
    bash,
    edit_file,
    glob_search,
    grep_search,
    list_directory,
    read_file,
    run_command,
    set_sandbox_root,
    web_fetch,
    web_search,
    write_file,
)
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

MAX_RETRIES = 3


# ── State ────────────────────────────────────────────────────────────────────

class IssueFixerState(BaseModel):
    # ---- caller-supplied inputs ----
    codeRepo: str = Field(default="", description="GitHub repo URL (https://github.com/owner/repo)")
    codeWorkingDirectory: str = Field(default="", description="Local base directory for clones")
    issueDescription: str = Field(default="", description="Issue description / GitHub issue text")

    # ---- derived at setup time ----
    repoName: str = Field(default="", description="Repo name extracted from URL (used as sandbox sub-path)")
    branchName: str = Field(default="", description="UUID-based fix branch created during setup")

    # ---- runtime state ----
    plan: Optional[str] = Field(default="", description="Current fix plan from the planner")
    test_results: Optional[str] = Field(default="", description="Output from the last test run")
    tests_passed: Optional[bool] = Field(default=False)
    retry_count: Optional[int] = Field(default=0)


# ── Flow ─────────────────────────────────────────────────────────────────────

class IssueFixerFlow(Flow[IssueFixerState]):
    """Orchestrates Plan → Implement → Test → Retry using CrewAI Flow."""

    agentsConfig: dict = {}
    tasksConfig: dict = {}

    def __init__(self):
        super().__init__()
        config_dir = Path(__file__).resolve().parent.parent / "config"
        with open(config_dir / "issueFixerAgents.yaml", "r") as f:
            self.agentsConfig = yaml.safe_load(f)
        with open(config_dir / "issueFixerTasks.yaml", "r") as f:
            self.tasksConfig = yaml.safe_load(f)

    # ── Step 1: Clone repo and create fix branch ──────────────────────────────
    @start()
    def setup(self):
        logger.info("=" * 60)
        logger.info("IssueFixer starting")
        logger.info("  Repo : %s", self.state.codeRepo)
        logger.info("  Issue: %s", self.state.issueDescription[:120])
        logger.info("=" * 60)

        """Clone the GitHub repo locally and create a UUID fix branch."""
        repo_url = self.state.codeRepo.strip()
        if not repo_url.startswith("http") and not repo_url.startswith("git@"):
            repo_url = f"https://github.com/{repo_url}"

        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        self.state.repoName = repo_name

        clone_path = Path(self.state.codeWorkingDirectory).resolve() / repo_name

        if not (clone_path / ".git").exists():
            logger.info("Cloning %s → %s", repo_url, clone_path)
            result = subprocess.run(
                ["git", "clone", repo_url, str(clone_path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed:\n{result.stderr.strip()}")
            logger.info("Clone complete.")
        else:
            logger.info("Repo already cloned at %s — skipping clone.", clone_path)

        branch_name = f"issue-fix-{uuid.uuid4().hex[:8]}"
        self.state.branchName = branch_name
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True, text=True, cwd=str(clone_path),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git checkout -b {branch_name} failed:\n{result.stderr.strip()}"
            )
        logger.info("Created branch: %s", branch_name)

        set_sandbox_root(str(Path(self.state.codeWorkingDirectory).resolve()))
        logger.info("Sandbox root set to: %s", clone_path)

    # ── Step 2: Plan ─────────────────────────────────────────────────────────
    # Triggered by setup on the first pass, and by the "retry" event on
    # every subsequent pass — so a single method serves both cases.

    @listen(or_(setup, "retry"))
    async def plan(self):
        attempt = self.state.retry_count + 1
        logger.info("[attempt %d] Planning the fix…", attempt)

        retry_context = (
            ""
            if self.state.retry_count == 0
            else (
                f"RETRY {self.state.retry_count}/{MAX_RETRIES}\n\n"
                f"The previous fix failed. Test output:\n{self.state.test_results}\n\n"
                "Study the failures carefully and produce a different approach."
            )
        )
        try:
            result = await self._run_crew(
                crew_name="planner",
                task_config_key="planner_task",
                inputs={
                    "issue_description": self.state.issueDescription,
                    "code_repo": self.state.repoName,
                    "retry_context": retry_context,
                },
                tools=[grep_search, glob_search, read_file, list_directory, bash, web_search, web_fetch]
            )
            self.state.plan = result.raw
            logger.info("[attempt %d] Plan ready (%d chars)", attempt, len(self.state.plan))
        except Exception as exc:
            logger.exception("[attempt %d] Planner crew failed: %s", attempt, exc)
            raise

    # ── Step 3: Implement ─────────────────────────────────────────────────────

    @listen(plan)
    async def implement(self):
        logger.info("[attempt %d] Implementing…", self.state.retry_count + 1)
        await self._run_crew(
            crew_name="implementer",
            task_config_key="implementer_task",
            inputs={
                "code_repo": self.state.repoName,
                "plan": self.state.plan,
            },
            tools=[grep_search, glob_search, read_file, list_directory, bash, 
                   read_file, edit_file, write_file],
        )

    # ── Step 4: Validate ──────────────────────────────────────────────────────

    @listen(implement)
    async def validate(self):
        logger.info("[attempt %d] Running tests…", self.state.retry_count + 1)
        result = await self._run_crew(
            crew_name="validator",
            task_config_key="validator_task",
            inputs={"code_repo": self.state.repoName},
            tools=[grep_search, glob_search, read_file, list_directory, bash, 
                   read_file, edit_file, write_file, run_command],
        )
        self.state.test_results = result.raw
        self.state.tests_passed = _parse_passed(result.raw)
        logger.info(
            "[attempt %d] Tests passed: %s",
            self.state.retry_count + 1,
            self.state.tests_passed,
        )

    # ── Router: loop back to plan on failure, or finish ───────────────────────

    @router(validate)
    async def check_results(self):
        if self.state.tests_passed:
            logger.info("All tests passed — done!")
            return "success"
        if self.state.retry_count < MAX_RETRIES:
            self.state.retry_count += 1
            logger.info(
                "Tests failed — retry %d / %d",
                self.state.retry_count,
                MAX_RETRIES,
            )
            return "retry"          # re-triggers plan()
        logger.info("Tests failed after %d attempts — giving up.", MAX_RETRIES + 1)
        return "exhausted"

    # ── Terminal step ─────────────────────────────────────────────────────────
    @listen(or_("success", "exhausted"))
    async def finalize(self) -> str:
        separator = "=" * 60
        if self.state.tests_passed:
            pr_note = ""
            try:
                pr_url = self._commit_and_pr()
                pr_note = f"\n\nPR created: {pr_url}"
            except Exception as exc:
                logger.exception("Failed to commit / create PR: %s", exc)
                pr_note = f"\n\nWarning: failed to commit/create PR — {exc}"
            summary = (
                f"{separator}\n"
                f"BUG FIX SUCCESSFUL (retries used: {self.state.retry_count})\n"
                f"{separator}\n\n"
                f"Plan applied:\n{self.state.plan}"
                f"{pr_note}"
            )
        else:
            summary = (
                f"{separator}\n"
                f"BUG FIX FAILED after {MAX_RETRIES} retries.\n"
                f"{separator}\n\n"
                f"Last test output:\n{self.state.test_results}"
            )
        logger.info(summary)
        self._cleanup()
        return summary

    # ── Helper ───────────────────────────────────────────────────────────────

    async def _run_crew(
        self,
        crew_name: str,
        task_config_key: str,
        inputs: dict,
        tools: list,
        output_model=None,
        mcps: list[str] = [],
    ):
        """Spin up a single-agent crew, run it asynchronously, return the result."""
        agent = Agent(
            config=self.agentsConfig[f"{crew_name}_agent"],
            verbose=getVerbose(),
            tools=tools,
            llm=getLlm(),
            mcps=mcps
        )

        task_kwargs = dict(
            config=self.tasksConfig[task_config_key],
            agent=agent,
        )
        if output_model:
            task_kwargs["output_pydantic"] = output_model
        task = Task(**task_kwargs)

        crew = Crew(
            name=f"{crew_name}_crew",
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=getVerbose(),
        )

        return await crew.kickoff_async(inputs=inputs)

    def _cleanup(self) -> None:
        """Delete the local clone if it still exists."""
        if not self.state.repoName or not self.state.codeWorkingDirectory:
            return
        clone_path = Path(self.state.codeWorkingDirectory).resolve() / self.state.repoName
        if clone_path.exists():
            shutil.rmtree(clone_path)
            logger.info("Deleted local clone: %s", clone_path)

    def _commit_and_pr(self) -> str:
        """Stage all changes, commit, push, and open a GitHub PR. Returns the PR URL."""
        clone_path = Path(self.state.codeWorkingDirectory).resolve() / self.state.repoName

        # Stage everything
        result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True, text=True, cwd=str(clone_path),
        )
        if result.returncode != 0:
            raise RuntimeError(f"git add failed:\n{result.stderr.strip()}")

        # Bail early if there's nothing to commit
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(clone_path),
        )
        if not status.stdout.strip():
            logger.warning("No changes detected — skipping commit and PR.")
            return "(no changes committed)"

        # Commit
        short_desc = self.state.issueDescription[:72].replace('"', "'")
        commit_msg = f"fix: {short_desc}"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True, text=True, cwd=str(clone_path),
        )
        if result.returncode != 0:
            raise RuntimeError(f"git commit failed:\n{result.stderr.strip()}")
        logger.info("Committed: %s", commit_msg)

        # Push branch
        result = subprocess.run(
            ["git", "push", "origin", self.state.branchName],
            capture_output=True, text=True, cwd=str(clone_path),
        )
        if result.returncode != 0:
            raise RuntimeError(f"git push failed:\n{result.stderr.strip()}")
        logger.info("Pushed branch: %s", self.state.branchName)

        # Create PR via GitHub CLI
        pr_title = f"fix: {self.state.issueDescription[:60]}"
        pr_body = (
            f"## Summary\n\n"
            f"Automated fix for the following issue:\n\n"
            f"> {self.state.issueDescription}\n\n"
            f"## Fix Plan\n\n"
            f"{self.state.plan}\n\n"
            f"## Test Results\n\n"
            f"{self.state.test_results}"
        )
        result = subprocess.run(
            ["gh", "pr", "create",
             "--title", pr_title,
             "--body", pr_body,
             "--head", self.state.branchName],
            capture_output=True, text=True, cwd=str(clone_path),
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr create failed:\n{result.stderr.strip()}")
        pr_url = result.stdout.strip()
        logger.info("PR created: %s", pr_url)
        return pr_url


# ── Utility ───────────────────────────────────────────────────────────────────

def _parse_passed(output: str) -> bool:
    """Return False if the validator's report contains failure/error indicators, True otherwise."""
    if "FAILED" in output:
        return False
    return True
