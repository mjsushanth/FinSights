import boto3
import datetime

AWS_PROFILE = "default"
S3_BUCKET = "sentence-data-ingestion"
S3_FOLDER = "Edgar_Sentence_API"

def save_to_s3():
    """Upload Parquet data to S3."""
    session = boto3.session.Session(profile_name=AWS_PROFILE)
    s3_client = session.client("s3")

    # Define paths
    s3_key = f"{S3_FOLDER}/sentence_incremental_data.parquet"
    local_path = "/Users/karthikmac/Documents/MLOps-Edgar-SDK/scripts/sentence/sec_rag_data/10k_sentences_validated.parquet"
    
    # 🚨 CRITICAL FIX: Use upload_file
    s3_client.upload_file(
        Filename=local_path,  # The path to the local file
        Bucket=S3_BUCKET,
        Key=s3_key,           # The destination S3 key
        # Parquet files are binary data, so the ContentType should be appropriate
        ExtraArgs={'ContentType': 'application/octet-stream'}
    )
    
    print(f"✅ Uploaded contents of {local_path} to s3://{S3_BUCKET}/{s3_key}")
    return s3_key

if __name__ == '__main__':
    save_to_s3()