import json
import logging
import os
import boto3

# Set up the logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
bedrock_agent_runtime = boto3.client('bedrock-agentcore')

def handler(event, context):
    client = boto3.client('apigateway')
    
    if not event['headers'] or not event['headers']['X-Telegram-Bot-Api-Secret-Token']:
        return {
            "statusCode": 403
        }

    api_key_sent = event['headers']['X-Telegram-Bot-Api-Secret-Token']
    response = client.get_api_key(apiKey=os.environ.get("API_KEY_ID"), includeValue=True)
    if (not response) or (response['enabled'] is False) or (not response['value']) or (response['value'] != api_key_sent):
        return {
            "statusCode": 403
        }

    body = json.loads(event.get('body', '{}'))
    if not body['message'] or not body['message']['chat'] or not body['message']['chat']['id']:
        return {
            "statusCode": 400
        }

    # Invoke Bedrock Agent asynchronously
    chat = body['message']['chat']
    response = invoke_agent(
            prompt=body['message']['text'],
            sessionId=chat['id'],
            customerId=chat['username'], 
            customerFirstName=chat['first_name'])

    if response:
        return {
            "statusCode": 200
        }
    else:
        return {
            "statusCode": 500
        } 

def invoke_agent(prompt, sessionId, customerId, customerFirstName):
    try:
        longSessionId = f"CustomerId-{customerId}_SessionID-{str(sessionId)}"
        payload_dict = {   
            "prompt": prompt,
            "customerId": customerId,
            "sessionId": longSessionId,
            "customerFirstName": customerFirstName,
            "chatId": str(sessionId)
        }
        payload_bytes = json.dumps(payload_dict).encode('utf-8')

        agent_arn = os.environ.get('AGENTCORE_RUNTIME_ARN') 
        
        response = bedrock_agent_runtime.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=longSessionId,
            payload=payload_bytes,
            contentType='application/json',
            accept='application/json',
            qualifier=os.environ.get('AGENTCORE_RUNTIME_ENDPOINT', 'DEFAULT')
        )

        return response

    except Exception as e:
        logger.error(f"Error invoking Bedrock Agent: {str(e)}")
        return None

