import os
import boto3
import sys

# Load env manually from bhavyadoshi_managerapp since dotenv might not be installed
env_path = '../bhavyadoshi_managerapp/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k.strip(': ')] = v.strip()

region_raw = os.environ.get('AWS_S3_REGION_NAME', 'ap-southeast-1')
region = region_raw.replace('=', '').strip()

print("Using region:", region)

s3 = boto3.client('s3',
    endpoint_url=os.environ.get('AWS_S3_ENDPOINT_URL'),
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=region
)
print("Uploading with default boto3...")
try:
    s3.put_object(Bucket=os.environ.get('AWS_STORAGE_BUCKET_NAME'), Key='test_upload.txt', Body=b'Testing upload')
    print("Success")
except Exception as e:
    print("Error:", e)

from botocore.client import Config
print("\nUploading with s3v4 and path addressing...")
s3_path = boto3.client('s3',
    endpoint_url=os.environ.get('AWS_S3_ENDPOINT_URL'),
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=region,
    config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
)
try:
    s3_path.put_object(Bucket=os.environ.get('AWS_STORAGE_BUCKET_NAME'), Key='test_upload_path.txt', Body=b'Testing upload path')
    print("Success")
except Exception as e:
    print("Error:", e)

print("\nUploading with virtual addressing...")
s3_virtual = boto3.client('s3',
    endpoint_url=os.environ.get('AWS_S3_ENDPOINT_URL'),
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=region,
    config=Config(signature_version='s3v4', s3={'addressing_style': 'virtual'})
)
try:
    s3_virtual.put_object(Bucket=os.environ.get('AWS_STORAGE_BUCKET_NAME'), Key='test_upload_virtual.txt', Body=b'Testing upload virtual')
    print("Success")
except Exception as e:
    print("Error:", e)
