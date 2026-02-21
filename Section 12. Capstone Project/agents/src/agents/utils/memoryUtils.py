import itertools
import os
from bedrock_agentcore.memory import MemoryClient

class MemoryUtils:
    sessionId:str = None
    customerId:str = None

    def __init__(self, sessionId:str, customerId:str):
        self.sessionId = sessionId
        self.customerId = customerId

    def saveMemory(self, userPrompt:str, assistantResponse:str):
        userPrompt = userPrompt[:9000]
        assistantResponse = assistantResponse[:9000]
        
        payload = [
            [userPrompt, "USER"],
            [assistantResponse, "ASSISTANT"]
        ]

        params = {
            "memory_id": os.getenv("MEMORY_ID"),
            "actor_id": self.customerId,
            "session_id": self.sessionId,
            "messages": payload
        }
        MemoryClient().create_event(**params)

    def loadShortTermMemory(self, count:int=10) -> str:
        params = {
            "memory_id": os.getenv("MEMORY_ID"),
            "actor_id": self.customerId,
            "session_id": self.sessionId,
            "k": count
        }
        turns = MemoryClient().get_last_k_turns(**params)
        flattened_list = list(itertools.chain.from_iterable(turns))
        response = ""
        for item in flattened_list:
            response += item['role'] + ": " + item['content']['text'] + "\n"
        return response