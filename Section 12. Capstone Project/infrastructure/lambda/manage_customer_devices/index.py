"""Lambda handler to save customer ID and device ID to DynamoDB."""

import json
import os
from datetime import datetime
from enum import Enum

import boto3


class ActionType(str, Enum):
    """Enum for supported action types."""
    CREATE = "create"
    READ = "read"
    DELETE = "delete"


def handler(event, context):
    
    """
    Supports both direct invocation and API Gateway (body as JSON string).
    """
    # Extract bedrockAgentCoreToolName from client context if available
    bedrock_tool_name = None
    if context.client_context and hasattr(context.client_context, 'custom'):
        bedrock_tool_name = context.client_context.custom.get('bedrockAgentCoreToolName')

    table_name = os.environ["TABLE_NAME"]
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    # Support direct invocation or API Gateway with body
    if "body" in event:
        body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
    else:
        body = event

    # Deduce action type from tool name
    action_type = None
    if bedrock_tool_name:
        tool_name_lower = bedrock_tool_name.lower()
        if "save" in tool_name_lower or "create" in tool_name_lower or "register" in tool_name_lower:
            action_type = ActionType.CREATE.value
        elif "get" in tool_name_lower or "read" in tool_name_lower or "list" in tool_name_lower or "fetch" in tool_name_lower:
            action_type = ActionType.READ.value
        elif "delete" in tool_name_lower or "remove" in tool_name_lower or "unregister" in tool_name_lower:
            action_type = ActionType.DELETE.value

    # Fallback to body type if tool name doesn't provide action type
    if not action_type:
        action_type = body.get("type")

    valid_actions = [action.value for action in ActionType]
    if not action_type or action_type not in valid_actions:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"action_type must be one of: {', '.join(valid_actions)}"}),
        }

    customer_id = body.get("customer_id")
    if not customer_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "customer_id is required"}),
        }

    if action_type in [ActionType.CREATE.value, ActionType.DELETE.value]:
        device_id = body.get("device_id")

        if not device_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "device_id is required"}),
            }

        if action_type == ActionType.CREATE.value: # CREATE
            item = {
                "customer_id": customer_id,
                "device_id": device_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
            }

            table.put_item(Item=item)

            return {
                "statusCode": 200,
                "body": json.dumps({"message": "Saved successfully", "customer_id": customer_id, "device_id": device_id}),
            }
        else:  # DELETE
            table.delete_item(
                Key={
                    "customer_id": customer_id,
                    "device_id": device_id
                }
            )

            return {
                "statusCode": 200,
                "body": json.dumps({"message": "Deleted successfully", "customer_id": customer_id, "device_id": device_id}),
            }
    else:  # READ
        response = table.query(
            KeyConditionExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )

        devices = response.get("Items", [])

        return {
            "statusCode": 200,
            "body": json.dumps({
                "customer_id": customer_id,
                "devices": devices,
                "count": len(devices)
            }),
        }