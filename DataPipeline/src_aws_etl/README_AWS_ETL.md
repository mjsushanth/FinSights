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
1. Single environment for all of DataPipeline (src_aws_etl, src_edgar_incremental,
   src_metrics): `conda env create -f ../environment.yml && conda activate finsight-venv`.
   (2026-07-27: the old per-module `requirements.txt` and `local_env_config/`
   conda file were retired to `../legacy/` - use the shared environment.yml instead.)
2. The credentials for AWS S3 access should be configured in `.aws_secrets/aws_credentials.env`, the example file given is `.aws_secrets/aws_credentials.env.example`.
3. To run, just execute `python etl/merge_pipeline.py` (or, going forward, hand off from
   `src_edgar_incremental/run_pipeline.py`'s Stage 6 push - no DAG/scheduler needed).

## Merge Strategy:
1. If exists: merge final + incremental
2. If doesn't exist: merge historical + incremental (bootstrap)

