import os
from .utils.env import populateEnvWithSecrets
from bedrock_agentcore import BedrockAgentCoreApp
from openinference.instrumentation.crewai import CrewAIInstrumentor
from .crews.deepResearchFlow import DeepResearchFlow

# Create AgentCore App
app = BedrockAgentCoreApp()

# Setup CrewAI instrumentation
CrewAIInstrumentor().instrument(skip_dep_check=True)

@app.entrypoint
async def invoke(payload):
    topic = payload.get("topic")

    if not topic:
        raise ValueError("Missing required payload parameter: topic")

    # Populate environment variables from AWS Secrets Manager
    populateEnvWithSecrets()

    if not os.getenv("TAVILY_API_KEY"):
        raise RuntimeError("Internal server error: TAVILY_API_KEY is not configured")

    inputs = {
        "question": topic
    }

    response = await DeepResearchFlow().kickoff_async(inputs=inputs)
    return response

if __name__ == "__main__":
    app.run()
