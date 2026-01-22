# 📚 Section 02. Background to Agentic AI

## 🎯 Purpose
This section primarily focuses on introducing GenAI, Agentic AI and also setting up Cursor IDE and using its code generation features.

## 🚀 Prompt used in demo
In the demo, we used below prompt to generate code using `Cursor` IDE
```
Role: You are an expert python programmer specializing in writing readable, clean and documented code with most efficient data structures and algorithms.

Action: Create a python class to generate the last 3 numbers of a fibonacci series of a specified length.

Context:
 - Code would be run on a low-end device with very limited CPU and memory.
 - Code would be executed in realtime.

Expectations:
 - Code should be optimized to use minimal CPU.
 - Code should validate the input variable specifying length of fibonacci series.
 - Generate test cases for negative and positive cases. The test cases should take care of small as well as large fibonacci series.
 - There should be separate python files for logic and test cases.
 - As part of code generation, run the test cases.
 - If any test case is failing, you might need to change the logic or the test case to make the test case pass.
 - Do not use any third-party APIs or libraries.
 - Response time out should be less than 2 seconds. And if it takes more than 2 seconds, the class should throw an exception
```

**Happy Learning! 🎉🤖**