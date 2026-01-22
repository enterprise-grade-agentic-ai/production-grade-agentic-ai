import os
import requests
from crewai_tools import MCPServerAdapter

class McpUtils:
    def getTools(self):
        # Retrieves and configures MCP (Model Context Protocol) tools for the crew agents.
        # This method handles the complete authentication flow with the MCP gateway:
        # 1. Retrieves OAuth2 credentials from environment variables
        # 2. Obtains a bearer token using client credentials grant
        # 3. Configures the MCP server adapter with the token
        # 4. Returns the available tools for use by crew agents
        try:
            client_id = os.getenv("MCP_CLIENT_ID")
            client_secret = os.getenv("MCP_CLIENT_SECRET")
            response = requests.post(
                os.getenv("MCP_TOKEN_URL"),
                data="grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}".format(client_id=client_id, client_secret=client_secret),
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            bearer_token = response.json()["access_token"]
        
            server_params = {
                "url": os.getenv("MCP_GATEWAY_URL"),
                "transport": "streamable-http",
                "headers": {
                    "Authorization": f"Bearer {bearer_token}"
                }
            }
            mcp_server_adapter = MCPServerAdapter(server_params)
            return mcp_server_adapter.tools
        except Exception as e:
            raise Exception(f"An error occurred while getting tools from MCP: {e}")