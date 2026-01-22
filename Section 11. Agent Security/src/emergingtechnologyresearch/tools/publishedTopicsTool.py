from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..utils.publishedReportUtils import PublishedReportUtils

class PublishedTopicsSchema(BaseModel):
    """Input for Published Topics Tool."""

    actor_id: str = Field(description="The actor ID to get published topics for.")

class PublishedTopicsTool(BaseTool):
    name: str = "Published Topics Tool"
    description: str = "Returns a comma-separated list of topics already published for the given actor ID."
    args_schema: Type[BaseModel] = PublishedTopicsSchema

    def _run(self, **kwargs) -> str:
        actor_id = kwargs.get("actor_id")

        if not actor_id:
            return "Error: actor_id is required."

        ## TODO LEARNER to uncomment below code to fix the Identity and Privilege abuse
        # if actor_id != os.getenv("ACTOR_ID"):
        #     return "Error: HACK INTERCEPTED! You are trying to fetch published topics for other user."

        try:
            utils = PublishedReportUtils()
            topics = utils.getReportTopics(actor_id)
            
            if not topics:
                return "No published topics found for the given actor ID."
            
            # Return comma-separated list of topics
            return ", ".join(topics)
        except Exception as e:
            return f"Error: An unexpected error occurred while retrieving published topics. {str(e)}"
