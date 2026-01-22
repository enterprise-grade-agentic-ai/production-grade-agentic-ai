import os
from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError


class PublishedReportUtils:
    def _get_mongodb_client(self) -> MongoClient:
        """Creates and returns a MongoDB client based on environment variables."""
        mongodb_url = os.getenv("MONGODB_URL")
        
        return MongoClient(mongodb_url)

    def publishReport(self, actor_id:str, report_topic:str, report_contents:str) -> str:
        if not actor_id or not report_topic or not report_contents:
            return "Error: actor_id, report_topic, and report_contents are all required."

        try:
            # Get MongoDB client
            client = self._get_mongodb_client()
            
            # Get database name from environment variable or use default
            database_name = os.getenv("MONGODB_DATABASE", "default")
            db = client[database_name]
            
            # Get collection
            collection = db["published_reports"]
            
            # Create document
            document = {
                "actor_id": actor_id,
                "report_topic": report_topic,
                "report_contents": report_contents,
                "created_at": datetime.utcnow(),
            }
            
            # Insert document
            result = collection.insert_one(document)
            
            # Close connection
            client.close()
            
            return f"Successfully stored report. Document ID: {result.inserted_id}"
            
        except ConnectionFailure as e:
            return f"Error: Failed to connect to MongoDB. {str(e)}"
        except PyMongoError as e:
            return f"Error: MongoDB operation failed. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected error occurred. {str(e)}"

    def getReportTopics(self, actor_id:str) -> list[str]:
        if not actor_id:
            return []

        try:
            # Get MongoDB client
            client = self._get_mongodb_client()
            
            # Get database name from environment variable or use default
            database_name = os.getenv("MONGODB_DATABASE", "default")
            db = client[database_name]
            
            # Get collection
            collection = db["published_reports"]
            
            # Query last 10 documents filtered by actor_id, sorted by created_at descending
            documents = collection.find(
                {"actor_id": actor_id}
            ).sort("created_at", -1).limit(10)
            
            print (documents)
            # Convert documents to list
            result_list = []
            for doc in documents:
                result_list.append(doc["report_topic"])
            
            # Close connection
            client.close()
            
            return result_list
            
        except ConnectionFailure as e:
            return []
        except PyMongoError as e:
            return []
        except Exception as e:
            return []
