from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InvalidParamsError,
    Part,
    Task,
    TextPart,
    UnsupportedOperationError,
    TaskState,
    TaskStatus,
    Role
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
    new_artifact
)
from a2a.utils.errors import ServerError
from .. utils.crewUtils import executeApp
from .. flow import UserProfileIsRequired
from .. utils.env import populateEnvWithSecrets
from langfuse import get_client
from openinference.instrumentation.crewai import CrewAIInstrumentor

# Step1: Populate environment variables from AWS secrets manager
populateEnvWithSecrets()
    
# Step2: Setup langfuse for tracing
langfuse = get_client()
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")
CrewAIInstrumentor().instrument(skip_dep_check=True)

class EmergingTechnologyResearchExecutor(AgentExecutor):
    """Emerging technology research AgentExecutor Example."""

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        # Initiate current task
        currentTask = context.current_task
        if not currentTask:
            currentTask = new_task(context.message)
        history = currentTask.history.copy()

        # Build query String based on conversation history
        query = ""
        userInput = context.get_user_input()
        for message in currentTask.history:
            for part in message.parts:
                if (isinstance(part.root, TextPart)):
                    query += message.role + ": " + part.root.text + "\\n"
        query += Role.user +  ": " + userInput + "\\n"

        result = ""
        with langfuse.start_as_current_span(name="A2A: emerging-technology-research-trace"):
            # Trigger CrewAI Flow
            try:
                inputs = {
                    'prompt': query,
                    'sessionId': context.context_id,
                    'actorId': context.context_id # TODO fetch from the bearer token
                }
                
                result = await executeApp(inputs)
                parts = [Part(root=TextPart(text=result))]
                history.append(new_agent_text_message(result))
                await event_queue.enqueue_event(
                    Task(
                        status=TaskStatus(state=TaskState.completed),
                        id=context.task_id,
                        context_id=context.context_id,
                        artifacts=[new_artifact(parts, f'{context.task_id}')],
                        history=history
                    )
                )
            except UserProfileIsRequired as e:
                history.append(new_agent_text_message(e.message))
                await event_queue.enqueue_event(
                    Task(
                        status=TaskStatus(
                            state=TaskState.input_required,
                            message=new_agent_text_message(e.message)),
                        id=context.task_id,
                        context_id=context.context_id,
                        history=history
                    )
                )
            except Exception as e:
                updater = TaskUpdater(event_queue, currentTask.id, currentTask.context_id)
                result = "Failed to get the result"
                await updater.failed(
                    message=new_agent_text_message(result)
                )
            finally:
                langfuse.update_current_trace(input=inputs, output=result)
                langfuse.flush()

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        raise ServerError(error=UnsupportedOperationError())

    def _validate_request(self, context: RequestContext) -> bool:
        return False
