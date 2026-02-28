import json
import os
import boto3

def populateEnvWithSecrets():
    secret_name = os.getenv("SECRET_NAME")
    region_name = os.getenv("SECRET_REGION")

    if secret_name and region_name:
        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )
        
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
        secret = get_secret_value_response['SecretString']
        secret = json.loads(secret)
        for key, value in secret.items():
            os.environ[key] = value