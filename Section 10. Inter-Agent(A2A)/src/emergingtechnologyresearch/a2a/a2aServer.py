"""This file serves as the main entry point for the application.

It initializes the A2A server, defines the agent's capabilities,
and starts the server to handle incoming requests.
"""

import logging
import os

import click

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from .a2aResearchExecutor import EmergingTechnologyResearchExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option('--host', 'host', default='127.0.0.1')
@click.option('--port', 'port', default=9000)
def a2aServer(host, port):
    """Entry point for the A2A + CrewAI Emerging Technology Research."""
    try:
        capabilities = AgentCapabilities(streaming=False)
        skill = AgentSkill(
            id='emerging_technology_research',
            name='Emerging Technology Research',
            description=(
                'Generate engaging and brief report about an emerging technology. '
                ' The report will have multiple sections and with each section having '
                ' overview, list of key developments and impact on the world. I can '
                ' even answer followup questions on already conducted research in same session'
            ),
            tags=['emerging technology research', 'technology research'],
            examples=['Research on use of high range batteries in electric cars',
                'Research on impact of quantum computing on cryptography',
                'I have a followup question on its impact on defense'],
        )

        agent_host_url = (
            os.getenv('HOST_OVERRIDE')
            if os.getenv('HOST_OVERRIDE')
            else f'http://{host}:{port}/'
        )
        agent_card = AgentCard(
            name='Emerging Technology Research',
            description=(
                'Generate engaging and brief report about an emerging technology. '
                ' The report will have multiple sections and with each section having '
                ' overview, list of key developments and impact on the world.'
            ),
            url=agent_host_url,
            version='1.0.0',
            default_input_modes=['text', 'text/plain'],
            default_output_modes=['text', 'text/plain'],
            capabilities=capabilities,
            skills=[skill],
        )
        
        request_handler = DefaultRequestHandler(
            agent_executor=EmergingTechnologyResearchExecutor(),
            task_store=InMemoryTaskStore(),
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )
        import uvicorn

        uvicorn.run(server.build(), host=host, port=port)

    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        exit(1)


if __name__ == '__main__':
    a2aServer()
