import argparse
import asyncio
import logging

from .utils.env import populateEnvWithSecrets
from .utils.llmUtils import registerLlmHooks
from openinference.instrumentation.crewai import CrewAIInstrumentor
from .crews.issueFixerFlow import IssueFixerFlow
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

# Register LLM hooks (fixes Anthropic role-alternation requirement)
registerLlmHooks()

async def run(repo: str, issue_description: str, working_dir: str) -> str:
    inputs = {
        "codeRepo": repo,
        "codeWorkingDirectory": working_dir,
        "issueDescription": issue_description,
    }

    with langfuse.start_as_current_span(name="issue-fixer"):
        flow = IssueFixerFlow()
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
        description="Automated issue fixer — clones a GitHub repo, fixes the issue, and opens a PR."
    )
    parser.add_argument(
        "--plot", action="store_true",
        help="Render the flow diagram and exit (opens an HTML file in the browser).",
    )
    parser.add_argument(
        "--repo", "-r",
        help="GitHub repo URL (e.g. https://github.com/owner/repo)",
    )
    parser.add_argument(
        "--issue", "-b",
        help="Description of the issue to fix",
    )
    parser.add_argument(
        "--working-dir", "-d",
        default="../codeWorkingDirectory",
        help="Local directory where the repo will be cloned (default: ../codeWorkingDirectory)",
    )
    args = parser.parse_args()

    if args.plot:
        IssueFixerFlow().plot()
        return

    if not args.repo or not args.issue:
        parser.error("--repo and --issue are required when not using --plot")

    response = asyncio.run(run(args.repo, args.issue, args.working_dir))
    print(response)


if __name__ == "__main__":
    main()
