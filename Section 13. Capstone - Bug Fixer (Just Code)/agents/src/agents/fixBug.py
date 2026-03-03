import argparse
import asyncio
import logging

from .utils.env import populateEnvWithSecrets
from .utils import llmUtils  # registers the LLM call hooks as a side effect
from openinference.instrumentation.crewai import CrewAIInstrumentor
from .crews.bugFixerFlow import BugFixerFlow
from langfuse import get_client

# Populate environment variables from AWS Secrets Manager
populateEnvWithSecrets()

# Setup langfuse for tracing
langfuse = get_client()
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")
CrewAIInstrumentor().instrument(skip_dep_check=True)

logger = logging.getLogger(__name__)


async def run(repo: str, bug_description: str, working_dir: str) -> str:
    inputs = {
        "codeRepo": repo,
        "codeWorkingDirectory": working_dir,
        "bugDescription": bug_description,
    }

    with langfuse.start_as_current_span(name="bug-fixer"):
        flow = BugFixerFlow()
        try:
            response = await flow.kickoff_async(inputs=inputs)
        except Exception as e:
            response = f"An error occurred while running the crew: {e}"
        finally:
            langfuse.update_current_trace(input=inputs, output=response)
            # Safety-net: if an exception aborted the flow before finalize()
            # could run, clean up the local clone here.
            flow._cleanup()
    langfuse.flush()
    return response


def main():
    parser = argparse.ArgumentParser(
        description="Automated bug fixer — clones a GitHub repo, fixes the bug, and opens a PR."
    )
    parser.add_argument(
        "--repo", "-r",
        required=True,
        help="GitHub repo URL (e.g. https://github.com/owner/repo)",
    )
    parser.add_argument(
        "--bug", "-b",
        required=True,
        help="Description of the bug to fix",
    )
    parser.add_argument(
        "--working-dir", "-d",
        default="../codeWorkingDirectory",
        help="Local directory where the repo will be cloned (default: ../codeWorkingDirectory)",
    )
    args = parser.parse_args()

    response = asyncio.run(run(args.repo, args.bug, args.working_dir))
    print(response)


if __name__ == "__main__":
    main()
