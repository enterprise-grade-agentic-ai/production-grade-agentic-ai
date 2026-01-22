import os
from . env import populateEnvWithSecrets
from .. crews.orchestratorWorkerCrew import OrchestratorWorkerCrew
from .. flow import EmergingTechnologyFlow
from . memoryUtils import MemoryUtils

async def executeApp(inputs, step_callback = None)->str:
    response = ""

    populateEnvWithSecrets()
    fullAutonomy = True if os.getenv("AUTONOMOUS_ORCHESTRATION") == "TRUE" else False
    
    if fullAutonomy:
        inputs["conversationHistory"] = MemoryUtils(sessionId=inputs['sessionId'], actorId=inputs['actorId']).loadShortTermMemory()
        inputs["preferences"] = MemoryUtils(sessionId=inputs['sessionId'], actorId=inputs['actorId']).extractUserPreferences()
        # Trigger the orchestrator worker crew
        response = OrchestratorWorkerCrew(step_callback).crew().kickoff(inputs=inputs).pydantic.answer
    else:
        # Trigger the emerging technology flow
        response = await EmergingTechnologyFlow(step_callback).kickoff_async(inputs=inputs)

    # Save response in memory
    MemoryUtils(sessionId=inputs['sessionId'], actorId=inputs['actorId']).saveMemory(
        userPrompt=inputs['prompt'], assistantResponse=response)
            
    return response