from datetime import datetime
from langfuse import get_client
from openinference.instrumentation.crewai import CrewAIInstrumentor
from . crews.researchCrew import Emergingtechnologyresearch
from termcolor import colored
from . utils.env import populateEnvWithSecrets
import asyncio
from rich.console import Console

# Step1: Populate environment variables from AWS secrets manager
populateEnvWithSecrets()
    
# Step2: Setup langfuse for tracing
langfuse = get_client()
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")
CrewAIInstrumentor().instrument(skip_dep_check=True)

#Step3: Ask user for the research topic
async def main():    
    user_input = input("Enter the topic to be researched: ")
    inputs = {
        "topic": user_input,
        'current_year': str(datetime.now().year)
    }
    response = ""
    #Execute the crew
    with langfuse.start_as_current_span(name="emerging-technology-research-trace"):
        try: 
            response = Emergingtechnologyresearch().crew().kickoff(inputs=inputs).json_dict
        except Exception as e:
            response = f"An error occurred while running the crew: {e}"
        finally:
            langfuse.update_current_trace(input=inputs, output=response)
    langfuse.flush()
    print(colored(f"Assistant:",'blue'))
    console = Console()
    console.print(response)
if __name__ == "__main__":
    asyncio.run(main())