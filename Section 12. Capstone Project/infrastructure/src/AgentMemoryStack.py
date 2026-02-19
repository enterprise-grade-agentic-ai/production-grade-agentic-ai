from aws_cdk import (
    Stack,
    CfnOutput,
    aws_bedrockagentcore as bedrockagentcore,
)
from constructs import Construct

class AgentMemoryStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create AgentCore Short Term Memory
        memory = bedrockagentcore.CfnMemory(self, 
            "Orange_AgentMemory",
            name="Orange_AgentMemory",
            description="Memory for Agents used by Orange Electronics",
            event_expiry_duration = 7,
            memory_strategies=[
                bedrockagentcore.CfnMemory.MemoryStrategyProperty(
                    semantic_memory_strategy=bedrockagentcore.CfnMemory.SemanticMemoryStrategyProperty(
                        name="Orange_AgentSemanticMemory",
                    )
                ),
                bedrockagentcore.CfnMemory.MemoryStrategyProperty(
                    user_preference_memory_strategy=bedrockagentcore.CfnMemory.UserPreferenceMemoryStrategyProperty(
                        name="Orange_AgentUserPrefsMemory",
                    )
                )
            ]
        )

        CfnOutput(self, "OrangeAgentMemoryArn",
            value=memory.attr_memory_arn,
            export_name="OrangeAgentMemoryArn",
        )

        CfnOutput(self, "OrangeAgentMemoryId",
            value=memory.attr_memory_id,
            export_name="OrangeAgentMemoryId",
        )