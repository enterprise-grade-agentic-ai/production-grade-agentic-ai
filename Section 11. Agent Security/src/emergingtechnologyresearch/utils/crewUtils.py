from . env import populateEnvWithSecrets
from .. flow import EmergingTechnologyFlow
from . memoryUtils import MemoryUtils

async def executeApp(inputs, step_callback = None)->str:
    response = ""

    populateEnvWithSecrets()

    # Trigger the emerging technology flow
    response = await EmergingTechnologyFlow(step_callback).kickoff_async(inputs=inputs)
    
    # Save response in memory
    MemoryUtils(sessionId=inputs['sessionId'], actorId=inputs['actorId']).saveMemory(
        userPrompt=inputs['prompt'], assistantResponse=response)
            
    return response