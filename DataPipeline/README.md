### Pipeline Orchestration (Airflow DAGs)

We designed an Airflow DAG that automates the full ETL workflow for SEC filings - from fetching company data to generating structured outputs in a parquet file.

#### How it works

- We first pull the list of companies and verify all required configurations.

- Next, filings are automatically downloaded from official SEC sources.

- The raw, unstructured data is parsed to extract key sections (like Item 1A, Item 2, Item 7 etc) and transformed into standardized Parquet files which are then combined into a single parquet file.

- The processed outputs are then uploaded to cloud storage (AWS S3).

- Next, the temporary files are cleaned up and task status is logged.

- The next step is a core ETL pipeline based on polars on AWS S3 buckets, for a clean data merge concept between historical and live fact datasets. The fact datasets are also versioned and archived properly. (Ref: `src_aws_etl` folder.)

- Post-processing includes generating metadata and statistics for the ingested data (Great Expectations), and anomaly alerts. (Ref: `data_auto_stats` folder.)

The DAG ensures all stages — download → extract → transform → upload → clean — run sequentially in the right order.

### Unit Tests

We wrote comprehensive unit tests to validate the core functionality of the download_filings and extract_and_convert module.
All tests are written with pytest, use temporary directories for isolation, and run independently without needing any external data or network access.

