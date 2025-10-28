# AWS ETL Pipeline

## Overview:
This directory contains the AWS ETL pipeline code - It interacts with the files present in the S3 bucket, specifically the final (or history) and incremental data files.

## Directory Structure:
```
├── duckdb_finsight_data/           # data engineering. entire DuckDB work
├── notebooks/                      # intense research ( EDAs, Polars, Tests, llamacpp..)
└── model/                          # model experiments (potentially)

├── src_aws_etl/                    # data engineering - on AWS for live data ingestion
│   ├── config/
│   ├── etl/ .....
│   └── requirements.txt            # boto3, polars (no cuda ML libs.)
│
├── src_embeddings/                 # ML feature engineering, etc. (to be developed further)
│   ├── chunking/
```

## Requirements:
1. The subfolder src_aws_etl/ contains a requirements.txt file. Please install the dependencies. 
2. Instructions with step wise commands are present as comments in the requirements.txt file itself.
3. After recent considerations, we now provide `local_env_config/finrag_aws_etl_env.yml` - a conda environment file. NBoth pip and mamba/conda approach are compatible in this module.
4. The credentials for AWS S3 access should be configured in `.aws_secrets/aws_credentials.env`, the example file given is `.aws_secrets/aws_credentials.env.example`.
5. To run, just execute `python etl/merge_pipeline.py`. However, this integrates into an earlier DAG on the data ingestion pipeline so that automatically calls this execution,

## Merge Strategy:
1. If exists: merge final + incremental
2. If doesn't exist: merge historical + incremental (bootstrap)

