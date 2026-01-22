import os
from . env import populateEnvWithSecrets
from .. flow import EmergingTechnologyFlow
from . memoryUtils import MemoryUtils
from .. flow import UserProfileIsRequired

async def executeApp(inputs, step_callback = None)->str:
    response = ""

    populateEnvWithSecrets()
    # Trigger the emerging technology flow
    response = await EmergingTechnologyFlow(step_callback).kickoff_async(inputs=inputs)
    if response == "UserProfileIsRequired":
        raise UserProfileIsRequired()

    # Save response in memory
    MemoryUtils(sessionId=inputs['sessionId'], actorId=inputs['actorId']).saveMemory(
        userPrompt=inputs['prompt'], assistantResponse=response)
            
    return response