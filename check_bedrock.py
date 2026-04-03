from dotenv import load_dotenv
load_dotenv('.env')
import boto3, os

client = boto3.client(
    'bedrock',
    region_name=os.environ.get('AWS_REGION', 'eu-west-2'),
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
)

models = client.list_foundation_models()['modelSummaries']
for m in models:
    print(m['modelId'])
