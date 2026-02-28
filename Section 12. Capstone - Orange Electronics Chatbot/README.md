# Orange Electronics Telegram Bot

An AI-powered Telegram chatbot for Orange Electronics, built with CrewAI and AWS Bedrock AgentCore. The bot handles product inquiries, device registration, and general greetings using agentic AI with intent routing, RAG-based knowledge retrieval, and conversational memory.

## Architecture

```
  Telegram User
       |
       v
  API Gateway (POST /chat)
       |
       v
  Lambda (handle_telegram_message)
       |
       v
  +--- AgentCore Runtime (CrewAI) ---+
  |                                  |
  |  Memory --> Guardrail --> Intent |
  |                              |   |
  |                +-------------+   |
  |                |                 |
  |       +--------+--------+        |
  |       |                 |        |
  |  Device Regist.   Product Info   |
  +------|-----------------|---------+
         |                 |
         v                 v
    MCP Gateway      Knowledge Base
         |            |          |
         v            v          v
      Lambda      S3 Vectors   S3 Bucket
         |        (Titan v2)   (PDFs)
         v
      DynamoDB
```

### AWS Services Used

- **Amazon Bedrock AgentCore** - Runtime for hosting the CrewAI agent
- **Amazon Bedrock Foundation Models** - LLM inference (Amazon Nova)
- **Amazon Bedrock Knowledge Base** - RAG with S3 Vectors for product catalog and repair policy
- **Amazon Bedrock Guardrails** - Content filtering, PII blocking, and competitor mention detection
- **AgentCore MCP Gateway** - Tool execution via Model Context Protocol
- **AgentCore Memory** - Short-term conversational memory (semantic + user preference)
- **AgentCore Observability** - Tracing and monitoring
- **AWS Lambda** - Telegram webhook handler and device management functions
- **Amazon API Gateway** - REST endpoint for Telegram webhook
- **Amazon DynamoDB** - Customer-device mappings
- **Amazon Cognito** - OAuth2 M2M authentication for MCP
- **Amazon S3** - Document storage and vector embeddings
- **AWS CDK** - Infrastructure as Code

### CDK Stacks

| Stack | Description |
|-------|-------------|
| `OrangeGuardrail` | Bedrock Guardrail with content filters, topic policies, and PII blocking |
| `OrangeKB` | S3 bucket, S3 Vectors index, Bedrock Knowledge Base, and data source ingestion |
| `OrangeMCP` | Cognito user pool, DynamoDB table, device management Lambda, MCP Gateway |
| `OrangeAgentMemory` | Bedrock AgentCore memory with semantic and user preference strategies |
| `OrangeAgentCore` | ECR image, IAM role, and Bedrock AgentCore Runtime |
| `OrangeTelegramIntegration` | API Gateway, webhook handler Lambda, API key |

## Prerequisites

- **AWS CLI** configured with credentials for your account
- **Node.js** (for AWS CDK CLI)
- **Python 3.11+**
- **uv** (Python package manager) - install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Docker** (for building the AgentCore container image)
- **AWS CDK CLI** - install with `npm install -g aws-cdk`
- A **Telegram Bot Token** (see [Create a Telegram Bot](#2-create-a-telegram-bot))

## 1. Bootstrap and Deploy the CDK Stacks

### Bootstrap CDK

If this is the first time deploying CDK in your AWS account/region, bootstrap it:

```bash
cd infrastructure
uv sync
uv run cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
```

Replace `<ACCOUNT_ID>` and `<REGION>` with your values (e.g., `aws://311141546982/us-east-1`).

### Deploy All Stacks

```bash
cd infrastructure
uv run cdk deploy --all --require-approval broadening
```

This deploys the stacks in dependency order:
1. `OrangeGuardrail`, `OrangeKB`, `OrangeMCP`, `OrangeAgentMemory` (no interdependencies)
2. `OrangeAgentCore` (depends on all of the above)
3. `OrangeTelegramIntegration` (depends on `OrangeAgentCore`)

After deployment, note the outputs:
- **TelegramApiUrl** - The webhook URL (e.g., `https://<api-id>.execute-api.<region>.amazonaws.com/prod/chat`)

### Preview Changes Before Deploying

```bash
uv run cdk diff --all
```

## 2. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts to choose a name and username
3. BotFather will respond with a **Bot Token** (e.g., `81....13:AAGk...nvE`). Save this token securely.

## 3. Store the Telegram Bot Token in AWS Secrets Manager

The CDK stack creates an AWS Secrets Manager secret. The AgentCore runtime reads this secret at startup to load the Telegram bot token. Add your bot token to it:

```bash
TELEGRAM_TOKEN=<BOT_TOKEN>
SECRET_ID=$(aws cloudformation describe-stacks \
  --stack-name OrangeMCP \
  --query "Stacks[0].Outputs[?OutputKey=='OrangeSecretsName'].OutputValue" \
  --output text)

aws secretsmanager put-secret-value \
  --secret-id "$SECRET_ID" \
  --secret-string "$(
    aws secretsmanager get-secret-value \
      --secret-id "$SECRET_ID" \
      --query SecretString \
      --output text \
    | python3 -c "import sys,json; d=json.load(sys.stdin); d['TELEGRAM_TOKEN']='$TELEGRAM_TOKEN'; print(json.dumps(d))"
  )"
```

Replace `<BOT_TOKEN>` with the token from BotFather.

## 4. Set the Telegram Webhook

After deploying the CDK stacks, connect your Telegram bot to the API Gateway endpoint.

### Retrieve the API Key

The API key created by CDK is used as the `secret_token` to validate incoming webhook requests. Retrieve it with:

```bash
API_KEY_ID=$(aws cloudformation describe-stacks \
  --stack-name OrangeTelegramIntegration \
  --query "Stacks[0].Outputs[?OutputKey=='TelegramApiKeyId'].OutputValue" \
  --output text 2>/dev/null)

SECRET_TOKEN=$(aws apigateway get-api-key \
  --api-key "$API_KEY_ID" \
  --include-value \
  --query "value" \
  --output text)

echo "Secret Token: $SECRET_TOKEN"
```

### Retrieve the API Gateway URL

```bash
WEBHOOK_URL=$(aws cloudformation describe-stacks \
  --stack-name OrangeTelegramIntegration \
  --query "Stacks[0].Outputs[?OutputKey=='TelegramApiUrl'].OutputValue" \
  --output text)

echo "Webhook URL: $WEBHOOK_URL"
```

### Set the Webhook

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"$WEBHOOK_URL\",
    \"secret_token\": \"$SECRET_TOKEN\"
  }"
```

You should see a response like:

```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

### Verify the Webhook

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_TOKEN/getWebhookInfo" | python3 -m json.tool
```

## 5. Test the Bot on Telegram

1. Open Telegram and search for your bot by its username
2. Start a conversation by sending `/start` or a greeting like "Hello"
3. Try these sample interactions:

| Intent | Example Message |
|--------|----------------|
| Greeting | "Hi there!" |
| Product Information | "What products does Orange Electronics sell?" |
| Product Information | "Tell me about the repair policy" |
| Device Registration | "Register my new TV with serial number ABC123" |
| Device Registration | "What devices do I have registered?" |

4. The bot should respond within a few seconds. If there is no response, check the logs as mentioned in the next section.

## Logs

### Lambda Logs

```bash
LAMBDA_NAME=$(aws cloudformation describe-stacks \
  --stack-name OrangeTelegramIntegration \
  --query "Stacks[0].Outputs[?OutputKey=='TelegramLambdaName'].OutputValue" \
  --output text)

aws logs tail /aws/lambda/$LAMBDA_NAME --since 1h
```

### AgentCore Runtime Logs

```bash
RUNTIME_ID=$(aws cloudformation describe-stacks \
  --stack-name OrangeAgentCore \
  --query "Stacks[0].Outputs[?OutputKey=='AgentCoreRuntimeId'].OutputValue" \
  --output text)
TODAY=$(date -u +%Y/%m/%d)
aws logs tail /aws/bedrock-agentcore/runtimes/$RUNTIME_ID-DEFAULT  --log-stream-name-prefix "$TODAY/[runtime-logs]" --since 1h
```

## Tear Down

To destroy all stacks and associated resources:

```bash
cd infrastructure
uv run cdk destroy --all
```
