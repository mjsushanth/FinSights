import boto3
import json
import datetime
from src_metrics import config
from utils.helpers import setup_logger
logger = setup_logger()

def save_to_s3(json_data):
    """Upload JSON metrics to S3."""
    session = boto3.session.Session(profile_name=config.AWS_PROFILE)
    s3_client = session.client("s3")

    timestamp = datetime.datetime.now().strftime("%Y%m%d")
    file_name = f"{config.S3_FOLDER}/metrics_{timestamp}.json"
    json_bytes = json.dumps(json_data, indent=4).encode("utf-8")

    s3_client.put_object(
        Bucket=config.S3_BUCKET,
        Key=file_name,
        Body=json_bytes,
        ContentType="application/json"
    )
    print(f"✅ Uploaded to s3://{config.S3_BUCKET}/{file_name}")
    return file_name
