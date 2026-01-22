#!/bin/bash

# Configure AgentCore
uv sync
source .venv/bin/activate
uv pip freeze --exclude-editable > requirements.txt
agentcore configure