# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Course repository for "End-to-End Production Grade Agentic AI: Concepts to Hands-on". Each section is an independent project progressing from foundational concepts to production capstones.

**⚠️ AWS Cost Warning:** Many sections deploy real AWS infrastructure (Bedrock, AgentCore, CDK stacks). Always tear down resources after use.

## Package Management & Running Code

All Python projects use **UV** as the package manager with **Hatchling** as the build system.

```bash
# Install dependencies (run inside a section folder with pyproject.toml)
uv sync

# Run a project entry point
uv run python -m src.emergingtechnologyresearch.run

# Run a specific script
uv run python src/emergingtechnologyresearch/run.py

# Add a dependency
uv add <package>
```

No test suite exists — sections are course demos, not tested applications.

## Environment Setup

Every section with code has a `.env.template`. Copy it to `.env` and fill in values before running:

```bash
cp .env.template .env
```

Key credentials used across sections:
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — Bedrock LLM inference
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` — observability tracing
- `OPENAI_API_KEY` — fallback LLM and DALL-E image generation (Section 08+)
- `TAVILY_API_KEY` — web search tool (Section 06+)

## Architecture

### Section Structure (03–11)
Each section is a standalone Python project:
```
Section XX/
├── .env.template
├── pyproject.toml          # UV project config, entry points
├── src/{project_name}/
│   ├── crews/              # CrewAI crew definitions (agents + tasks)
│   ├── config/             # YAML agent/task configs (CrewAI convention)
│   ├── utils/
│   │   ├── env.py          # Loads .env, reads AWS Secrets Manager
│   │   └── llmUtils.py     # Bedrock LLM factory
│   └── run.py              # CLI entry point
└── miscellaneous/          # Setup scripts, utilities
```

### Capstone Projects (12–14)
Split into `agents/` and `infrastructure/` subdirectories:
- `agents/` — CrewAI application code, Dockerfile for AgentCore deployment
- `infrastructure/` — AWS CDK stacks (Python), one stack per AWS service

### Core Framework: CrewAI
All agents are built with CrewAI. Key concepts:
- **Crew** — orchestrates agents and tasks
- **Agent** — has a role, goal, backstory, and tools
- **Task** — assigned to an agent with expected output
- YAML configs in `config/agents.yaml` and `config/tasks.yaml` define agent/task properties

### LLM Integration: AWS Bedrock
`llmUtils.py` wraps `boto3` to create CrewAI-compatible LLM objects targeting Bedrock foundation models (Claude Sonnet by default). Some sections support OpenAI as a fallback via environment variable.

### Observability: Langfuse
`env.py` in each section initializes Langfuse tracing via `openinference-instrumentation-crewai`. Set `LANGFUSE_*` env vars to see traces at your Langfuse dashboard.

### Deployment: AWS Bedrock AgentCore
Sections 04+ deploy agents to AgentCore Runtime:
- Handler file (e.g., `agentCoreHandler.py`) wraps the crew with the AgentCore SDK
- `.bedrock_agentcore.yaml` configures the runtime
- Deploy with `bedrock-agentcore deploy` CLI

### Infrastructure as Code: AWS CDK
Capstone infrastructure stacks in `infrastructure/src/`:
```bash
cd "Section 12. Capstone - Orange Electronics Chatbot/infrastructure"
uv sync
cdk deploy --all       # deploy all stacks
cdk destroy --all      # tear down (do this to avoid charges)
```
Stacks follow a dependency order (e.g., Knowledge Base → AgentCore → Telegram Integration).

## Key Patterns

- **A2A (Agent-to-Agent):** Section 10 uses the `a2a-sdk` to expose agents as HTTP servers with an agent card protocol
- **MCP Tools:** Section 06+ use MCP Gateway for tool access (Tavily search, S3 publish via Lambda); configured via `mcp_config` in crew setup
- **Docker Sandbox:** Section 13 (Issue Fixer) executes bash commands in a Docker container for safe code execution
- **Dual Agent Security:** Section 11 runs a monitor agent in parallel to detect goal hijacking
- **Memory:** Section 07 uses AWS Bedrock AgentCore Memory for persistent user preference storage
