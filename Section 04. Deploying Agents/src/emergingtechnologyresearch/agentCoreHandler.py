from bedrock_agentcore import BedrockAgentCoreApp
from datetime import datetime
from . crews.researchCrew import Emergingtechnologyresearch
from . utils.env import populateEnvWithSecrets

# Create AgentCore App
app = BedrockAgentCoreApp()

# Populate environment variables from AWS secrets manager
populateEnvWithSecrets()

@app.entrypoint
def invoke(payload, context):
  topic = payload.get("topic")
  inputs = {
      'topic': topic,
      'current_year': str(datetime.now().year)
  }

  # Execute the crew
  response = Emergingtechnologyresearch().crew().kickoff(inputs=inputs).raw
  
  return response

if __name__ == "__main__":
  app.run()
