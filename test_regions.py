import os
import boto3
from botocore.client import Config

env_path = '../bhavyadoshi_managerapp/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k.strip(': ')] = v.strip()

regions_to_test = ['ap-southeast-1', 'us-east-1', 'us-west-1', 'eu-west-1', 'eu-central-1', 'auto', '', 'ap-northeast-1']

for region in regions_to_test:
    print(f"\n--- Testing region: '{region}' ---")
    s3 = boto3.client('s3',
        endpoint_url=os.environ.get('AWS_S3_ENDPOINT_URL'),
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        region_name=region if region else None,
        config=Config(signature_version='s3v4')
    )
    try:
        s3.put_object(Bucket=os.environ.get('AWS_STORAGE_BUCKET_NAME'), Key='test.txt', Body=b'hello')
        print("Success!! Region:", region)
        break
    except Exception as e:
        print("Error:", type(e).__name__, e)
