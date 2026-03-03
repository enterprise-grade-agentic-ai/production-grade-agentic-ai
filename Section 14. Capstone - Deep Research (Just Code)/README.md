# Deep Research Agent

A Udemy Capstone project that mimics Gemini Deep Research using CrewAI, AWS Bedrock, and AWS AgentCore. Given a research topic, the agent conducts parallel web research, synthesizes findings into a long-form article, applies an editorial critique loop, and publishes the final article to a public URL on S3.

## Architecture

```
  Caller
    |
    | { "topic": "..." }
    v
  AgentCore Runtime (CrewAI)
    |
    |-- Planner Agent --> 5-7 sub-questions
    |
    |-- Researcher Agents (parallel, one per sub-question)
    |       |-- tavily_search  (Tavily MCP)
    |       |-- tavily_extract (Tavily MCP)
    |       |-- Populates research output in CrewAI native RAG Tool
    |
    |-- Gap Checker Agent (loop, max 2x)
    |       |-- RAG Tool
    |
    |-- Writer Agent  --> draft article (queries RAG Tool)
    |-- Critic Agent  --> review article
    |-- Writer Agent  --> revised article (queries RAG Tool)
    |-- Generate Banner --> banner image of the article
    |-- Publish to S3
            |
            v
        Public Article URL (S3)
```

### AWS Services Used

- **Amazon Bedrock AgentCore** - Runtime for hosting the CrewAI agent container
- **Amazon Bedrock Foundation Models** - LLM inference as well as image generation
- **Amazon Bedrock Guardrails** - Content filtering before article publication
- **AgentCore Observability** - CloudWatch tracing
- **Amazon S3** - Final article
- **AWS CDK** - Infrastructure as Code

### CDK Stacks

| Stack | Description |
|-------|-------------|
| `DeepGuardrail` | Bedrock Guardrail with content filters (hate, violence, sexual, misconduct) |
| `DeepResearchAgentCore` | ECR image, IAM role, Secrets Manager secret, S3 article bucket, and Bedrock AgentCore Runtime |

## Prerequisites

- **AWS CLI** configured with credentials for your account
- **Node.js** (for AWS CDK CLI)
- **Python 3.11+**
- **uv** (Python package manager) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Docker** (for building the AgentCore container image)
- **AWS CDK CLI** — install with `npm install -g aws-cdk`
- **Tavily API key** — sign up at [tavily.com](https://tavily.com)

## 1. Bootstrap and Deploy the CDK Stacks

### Bootstrap CDK

If this is the first time deploying CDK in your AWS account/region:

```bash
cd infrastructure
uv sync
uv run cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
```

Replace `<ACCOUNT_ID>` and `<REGION>` with your values (e.g., `aws://123456789012/us-east-1`).

### Deploy All Stacks

```bash
cd infrastructure
uv run cdk deploy --all --require-approval broadening
```
### Preview Changes Before Deploying

```bash
uv run cdk diff --all
```

## 2. Set API Keys

### 2a. Set the Tavily API Key in Secrets Manager

The Tavily API key is stored in the `deep-research/secrets` Secrets Manager secret created by the `DeepResearchAgentCore` stack. Set it after deployment:

```bash
TAVILY_API_KEY=<YOUR_TAVILY_API_KEY>

SECRET_ID=$(aws cloudformation describe-stacks \
  --stack-name DeepResearchAgentCore \
  --query "Stacks[0].Outputs[?OutputKey=='DeepSecretsName'].OutputValue" \
  --output text)

aws secretsmanager put-secret-value \
  --secret-id "$SECRET_ID" \
  --secret-string "$(
    aws secretsmanager get-secret-value \
      --secret-id "$SECRET_ID" \
      --query SecretString \
      --output text \
    | python3 -c "import sys,json; d=json.load(sys.stdin); d['TAVILY_API_KEY']='$TAVILY_API_KEY'; print(json.dumps(d))"
  )"
```

## 3. Run the Deep Research Pipeline

The agent exposes a two-phase API via the AgentCore Runtime.

### Retrieve the Runtime ARN

```bash
RUNTIME_ARN=$(aws cloudformation describe-stacks \
  --stack-name DeepResearchAgentCore \
  --query "Stacks[0].Outputs[?OutputKey=='DeepAgentCoreRuntimeArn'].OutputValue" \
  --output text)

echo "Runtime ARN: $RUNTIME_ARN"
```

### Invoke the Pipeline

Send the topic and the agent runs the full pipeline — researching, writing, critiquing, and publishing the article to S3.

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --payload '{"topic": "The impact of large language models on software development"}' \
  --cli-binary-format raw-in-base64-out \
  --cli-read-timeout 900 \
  /dev/stdout
```

The response is the public S3 URL of the published article.

### Expected Pipeline Duration

| Step | Approximate Time |
|------|-----------------|
| Planner (sub-topics generation) | ~30 sec |
| Parallel research (5-7 agents) | 2-4 min |
| Gap check (up to 2x) | 1-3 min |
| Writing + critique + revision | 2-4 min |
| Generate article banner imager | <30 sec |
| Publish to S3 | <10 sec |
| **Total** | **~5-12 min** |

## 4. View Logs

### AgentCore Runtime Logs

```bash
RUNTIME_ID=$(aws cloudformation describe-stacks \
  --stack-name DeepResearchAgentCore \
  --query "Stacks[0].Outputs[?OutputKey=='DeepAgentCoreRuntimeId'].OutputValue" \
  --output text)

TODAY=$(date -u +%Y/%m/%d)
aws logs tail /aws/bedrock-agentcore/runtimes/$RUNTIME_ID-DEFAULT \
  --log-stream-name-prefix "$TODAY/[runtime-logs]" \
  --since 1h
```

## 5. Local Development

Copy the environment template and fill in your values:

```bash
cp agents/.env.template agents/.env
# Edit agents/.env with your values
```

Install dependencies:

```bash
cd agents
uv sync
```

Run the agent handler locally:

```bash
cd agents
uv run python -m src.agents.agentCoreHandler
```

## Tear Down

To destroy all stacks and associated resources:

```bash
cd infrastructure
uv run cdk destroy --all
```