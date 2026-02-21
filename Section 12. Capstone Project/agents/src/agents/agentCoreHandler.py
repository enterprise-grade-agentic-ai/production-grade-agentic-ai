from . utils.env import populateEnvWithSecrets
from bedrock_agentcore import BedrockAgentCoreApp
from openinference.instrumentation.crewai import CrewAIInstrumentor
import requests
import os
import logging
import threading
import boto3
from opentelemetry import context as otel_context, trace
from . crews.orangeElectronicsFlow import OrangeElectronicsFlow, Intent

logger = logging.getLogger(__name__)

# Create AgentCore App
app = BedrockAgentCoreApp()

# Setup CrewAI instrumentation
CrewAIInstrumentor().instrument(skip_dep_check=True)

def publish_error_metric():
    try:
        boto3.client("cloudwatch").put_metric_data(
            Namespace="bedrock-agentcore",
            MetricData=[{
                "MetricName": "OrangeElectronicsFlowErrors",
                "Value": 1,
                "Unit": "Count",
            }]
        )
    except Exception as e:
        logger.error(f"Failed to publish error metric: {e}")

def publish_token_usage_metric(flow):
    if flow.state.totalTokenUsage <= 0:
        return
    intent = flow.state.intent.intent.value if flow.state.intent else Intent.NOT_VALID.value
    try:
        boto3.client("cloudwatch").put_metric_data(
            Namespace="bedrock-agentcore",
            MetricData=[{
                "MetricName": "OrangeElectronicsFlowTokens",
                "Value": flow.state.totalTokenUsage,
                "Unit": "Count",
                "Dimensions": [
                    {"Name": "AgentRuntimeName", "Value": "orange_electronics_agent"},
                    {"Name": "Intent", "Value": intent}
                ]
            }]
        )
    except Exception as e:
        logger.error(f"Failed to publish token usage metric: {e}")

@app.entrypoint
def invoke(payload):
    prompt = payload.get("prompt")
    customerId = payload.get("customerId")
    sessionId = payload.get("sessionId")
    customerFirstName = payload.get("customerFirstName")
    chatId = payload.get("chatId")
    synchronous = payload.get("runSync")

    if not all([prompt, customerId, sessionId, customerFirstName, chatId]):
        raise ValueError("Missing required payload parameters")

    os.environ["CUSTOMER_ID"] = customerId

    inputs = {
        "prompt": prompt,
        'sessionId': sessionId,
        'customerId': customerId,
        'customerFirstName': customerFirstName
    }

    def background_work():
        unhandledException = None
        flow = OrangeElectronicsFlow()
        try:
            # Populate environment variables from AWS secrets manager
            populateEnvWithSecrets()

            # Trigger the CrewAI Flow
            response = flow.kickoff(inputs=inputs)
        except ValueError as e:
            response = "Our safety filters blocked the request or the response."
        except Exception as e:
            response = "An unknown error occurred while processing your request."
            unhandledException = e
            publish_error_metric()

        telegram_token = os.getenv("TELEGRAM_TOKEN")
        if telegram_token:
            telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            payload = {
                "chat_id": chatId,
                "text": response
            }
            requests.post(telegram_url, json=payload, timeout=10)

        publish_token_usage_metric(flow)

        if unhandledException:
            raise unhandledException

        return response

    if synchronous:
        return background_work()
    else:
        # Capture AgentCore's context (trace ID + session ID) to use as parent
        invoke_ctx = otel_context.get_current()
        task_id = app.add_async_task("background_processing")
        tracer = trace.get_tracer("AgentCore.Runtime.Invoke")
        def background_work_wrapper():
            with tracer.start_as_current_span("agent_invocation", context=invoke_ctx) as span:
                try:
                    background_work()
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    span.record_exception(e)
                finally:
                    app.complete_async_task(task_id)
            trace.get_tracer_provider().force_flush()

        threading.Thread(target=background_work_wrapper).start()
        return f"Started background task (ID: {task_id}). Agent status is now BUSY."
if __name__ == "__main__":
  app.run()
