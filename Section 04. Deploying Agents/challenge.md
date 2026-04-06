# Challenge: Deploying Agents

This challenge is about building what the instructor demonstrated in the section videos. Your goal is to deploy the emerging technology research application to AWS AgentCore and explore its observability and version management features. The current folder contains the reference implementation from the instructor. You can refer to that code as well as the README.md in this folder for guidance.

> **Cost note:** Deploying to AWS AgentCore incurs cloud compute costs while the agent is running. Tear down the deployment when you're done testing to avoid idle charges.

---

## Task 1: Deploy in AWS AgentCore

In this task you are expected to:

- Modify your agentic application to be deployable in AgentCore.
- Configure and deploy your agent using the Starter Toolkit.
- Invoke the deployed application, including across multiple AgentCore sessions.

Refer to the [Starter Toolkit documentation](https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/quickstart.html). In the "Create Your Agent" step, invoke your CrewAI crew instead of the Strands agent shown in the docs (Strands is just another agentic framework). You can generate a `requirements.txt` with:

```
uv pip freeze --exclude-editable > requirements.txt
```

---

## Task 2: Explore the AgentCore Console

After deployment, explore the AWS AgentCore console to review the deployed application. Pay attention to how AgentCore manages endpoints and versions.

---

## Task 3: Explore AWS CloudWatch Observability

After invoking the application, explore metrics and traces in [AWS CloudWatch GenAI observability](https://console.aws.amazon.com/cloudwatch/home#gen-ai-observability).

---

## Bonus: Change the Authentication Mechanism

If you'd like to go further, switch the agent's authentication mechanism from IAM to OAuth using AWS Cognito as the identity provider. Refer to the [AgentCore OAuth documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html) for steps.

---