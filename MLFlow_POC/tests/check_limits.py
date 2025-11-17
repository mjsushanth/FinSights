import boto3
from datetime import datetime

client = boto3.client('bedrock', region_name='us-east-1')

# List available models
response = client.list_foundation_models()

print("Available Claude Models:")
for model in response['modelSummaries']:
    if 'claude' in model['modelId'].lower():
        print(f"  - {model['modelId']}")
        print(f"    Input: {model.get('inputModalities', [])}")
        print(f"    Output: {model.get('outputModalities', [])}")

# Your current usage
print(f"\nCurrent time: {datetime.now()}")
print("Rate limits apply per minute window")