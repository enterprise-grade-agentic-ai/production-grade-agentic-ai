# Challenge: Hello Agentic

This challenge is about building what the instructor demonstrated in the section videos. Your goal is to create a basic CrewAI agentic application with Langfuse tracing and structured output. The current folder contains the reference implementation from the instructor. You can refer to that code as well as the README.md in this folder for guidance.

> **Cost note:** This challenge makes LLM API calls, which are pay-per-use — keep an eye on your usage if you run it many times. Langfuse has a generous free tier and shouldn't add to your bill.

---

## Task 1: Create a CrewAI-Based Agentic Application

Create your first CrewAI agentic application. The [CrewAI QuickStart guide](https://docs.crewai.com/en/quickstart) is a good starting point.

---

## Task 2: Explore Internals Using Langfuse

Tracing is essential for understanding what's happening inside an agentic application. Integrate Langfuse to capture traces as demonstrated in this section. Refer to the [Langfuse + CrewAI integration docs](https://langfuse.com/integrations/frameworks/crewai) for setup steps.

---

## Task 3: Generate Structured Output

Agentic applications often need to produce output that other systems can consume. Modify your application to return structured output using Pydantic. Refer to the [CrewAI tasks documentation](https://docs.crewai.com/en/concepts/tasks#using-output-pydantic) for guidance.

---
