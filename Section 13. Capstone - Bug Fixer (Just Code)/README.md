# Bug Fixer Agent

An agentic bug-fixing system built with CrewAI, Langfuse, and a Docker sandbox. Given a GitHub repository URL and a bug description, the agent clones the repo, plans a fix, implements it, validates it by running the test suite, and — on success — commits the changes and opens a pull request.

## Architecture

```
  CLI (fixBug.py)
    |
    | --repo <github-url> --bug "<description>"
    v
  BugFixerFlow (CrewAI Flow)
    |
    |-- initialize      → logs startup info
    |
    |-- setup           → git clone repo
    |                     git checkout -b bug-fix-<uuid>
    |                     mount clone into Docker sandbox
    |
    |-- plan            → Planner Agent
    |       |-- grep_search, glob_search, read_file
    |       |-- list_directory, bash
    |       └── produces a step-by-step fix plan
    |
    |-- implement       → Implementer Agent
    |       |-- read_file, edit_file, write_file
    |       |-- grep_search, glob_search, bash
    |       └── applies every step of the plan
    |
    |-- validate        → Validator Agent
    |       |-- bash, run_command
    |       └── runs the test suite, reports results
    |
    |-- check_results   → router
    |       |-- tests passed  → "success"
    |       |-- tests failed  → "retry" (back to plan, max 3x)
    |       └── retries exhausted → "exhausted"
    |
    └── finalize
            |-- success  → git add -A → git commit → git push → gh pr create
            └── cleanup  → delete local clone
```

All agent file operations run inside a hardened Docker container that mounts the cloned repo as a read-write volume. The host filesystem is otherwise inaccessible.

## Prerequisites

- **Python 3.10+**
- **uv** — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Docker** — for the sandboxed code execution environment
- **git** — for cloning and branching
- **GitHub CLI (`gh`)** — for opening pull requests; install with `brew install gh` then `gh auth login`
- **Langfuse account** — for tracing ([cloud.langfuse.com](https://cloud.langfuse.com))
- An LLM API key — Anthropic, OpenAI, or AWS Bedrock (see [Configuration](#configuration))

## Local Setup

### 1. Install dependencies

```bash
cd agents
uv sync
```

### 2. Configure environment variables

```bash
cp agents/.env.template agents/.env
# Edit agents/.env with your values
```

| Variable | Description |
|----------|-------------|
| `LANGFUSE_SECRET_KEY` | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key |
| `LANGFUSE_BASE_URL` | Langfuse host (default: `https://cloud.langfuse.com`) |
| `ANTHROPIC_API_KEY` | Anthropic API key (if using Claude) |
| `OPENAI_API_KEY` | OpenAI API key (if using GPT) |
| `OPENAI_API_MODEL` | OpenAI model name (optional, defaults to `gpt-5.2`) |

If none of the above API keys are set, the agent falls back to AWS Bedrock (`bedrock/us.anthropic.claude-sonnet-4-6`).

## Usage

```bash
cd agents
uv run python -m src.agents.fixBug \
  --repo https://github.com/owner/repo \
  --bug "Description of the bug to fix"
```

### Options

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--repo` | `-r` | Yes | GitHub repo URL |
| `--bug` | `-b` | Yes | Bug description |
| `--working-dir` | `-d` | No | Local directory for cloning (default: `../codeWorkingDirectory`) |

### Example

```bash
uv run python -m src.agents.fixBug \
  --repo https://github.com/owner/my-app \
  --bug "The login endpoint returns 500 when the email field contains uppercase letters" \
  --working-dir /tmp/bug-fixer
```

On success the agent prints a summary including the PR URL. On failure it prints the last test output after exhausting all retries.

## How It Works

1. **Setup** — The repo is cloned into `{working-dir}/{repo-name}` and a new branch `bug-fix-<8-char-uuid>` is created. The clone directory is mounted into a Docker sandbox so agents can read and modify files safely.

2. **Plan** — The Planner Agent reads the codebase (grep, glob, file reads) and produces a numbered, step-by-step fix plan based on the bug description.

3. **Implement** — The Implementer Agent follows the plan and edits source files inside the sandbox.

4. **Validate** — The Validator Agent discovers and runs the test suite. Results are parsed to determine pass/fail.

5. **Retry loop** — If tests fail, the flow retries up to 3 times, feeding the failure output back into the planner so each attempt uses a different approach.

6. **Finalize** — On success: changes are committed (`fix: <bug description>`), the branch is pushed, and a PR is opened via `gh pr create`. On failure or error: the local clone is deleted and a summary of the last test output is returned.

## Agent Tools

Each agent has access to a subset of the following tools, all of which operate inside the Docker sandbox:

| Tool | Description | Used by |
|------|-------------|---------|
| `grep_search` | Search file contents using regex | Planner, Implementer, Validator |
| `glob_search` | Find files by pattern | Planner, Implementer, Validator |
| `list_directory` | List files in a directory | Planner, Implementer, Validator |
| `read_file` | Read the contents of a file | Planner, Implementer, Validator |
| `bash` | Run arbitrary shell commands | Planner, Implementer, Validator |
| `edit_file` | Apply targeted edits to a file | Implementer, Validator |
| `write_file` | Write or overwrite a file | Implementer, Validator |
| `run_command` | Run a command and capture output | Validator |
| `web_search` | Search the web | — |
| `web_fetch` | Fetch a URL | — |

## Tracing

All LLM calls and agent steps are traced in Langfuse under a `bug-fixer` span. Request/response hooks log the last two messages of each LLM call for debugging.

## Docker Sandbox Security

The Docker container used for code execution has been hardened with resource limits, capability restrictions, and filesystem constraints. This provides a reasonable security baseline, but it is not a complete isolation boundary.

For stronger isolation, consider alternatives such as Podman (rootless containers), gVisor (`--runtime=runsc`), or Kata Containers, depending on your platform and threat model.
