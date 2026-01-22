import json
import boto3
from datetime import datetime
import os

# Initialize S3 client
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    Lambda function to write a report to S3 bucket.
    
    Expected event structure:
    {
        "report": "Report content as string",
        "topic": "topic-name"
    }
    """
    
    try:
        # Extract report from event
        report = event.get('report')
        if not report:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No report provided in the event'})
            }

        # Extract topic from event
        topic = event.get('topic')
        if not topic:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No topic provided in the event'})
            }
        
        # Get bucket name from environment variable
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        if not bucket_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No bucket name set in the environment variable'})
            }
        
        # Generate file name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = f'AgentGeneratedReports/{topic}_{timestamp}.json'
        
        # Write report to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=report.encode('utf-8'),
            ContentType='text/plain'
        )
        
        # Generate S3 URL
        s3_url = f"s3://{bucket_name}/{file_name}"
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Report successfully written to S3',
                'bucket': bucket_name,
                'file_name': file_name,
                's3_url': s3_url
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to write report to S3',
                'details': str(e)
            })
        }