# FinSights - Data Pipeline

### Data Acquisition
- The data ingestion stage implements a robust pipeline, ensuring reliable and automated retrieval of SEC filings for selected companies. Data is fetched directly from the SEC EDGAR database using a modular crawler (download_filings.py), which downloads 10-K filings.
- It supports configurable year ranges, multiple companies, and filing types defined in config/config.json. 
- The list of companies are stored in a CSV file (companies.csv) in AWS S3 bucket at the beginning of pipeline and stored locally for downstream tasks. 
- The entire ingestion process is environment-driven through .env variables, reproducible with environment.yml.

### Data Preprocessing:
Raw SEC filings are cleaned, parsed, and converted into structured formats using extract_and_convert.py.This module:
- Extracts key SEC Items (e.g., Item 1A – Risk Factors, Item 7 – MD&A).
- Cleans HTML tags, normalizes texts (replace special Unicode characters, remove page numbers and headers, fix broken section headers) and tokenizes sentences.
- Generates consistent metadata: CIK, company name, report year, section ID, timestamps, and version tags
- Exports to Parquet files for downstream analytics

### Test Modules
- We wrote comprehensive unit tests to validate the core functionality of the download_filings and extract_and_convert module as well as AWS connection modules(download_from_s3 and upload_to_s3).
- All tests are written with pytest, use temporary directories for isolation, and run independently without needing any external data or network access.
  
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


#### Setup
Refer to SETUP_README.md file for details about setting up the environment for running the AirFlow pipeline locally.

### Data Versioning with DVC
All intermediate datasets (raw, extracted, parquet) are tracked using DVC to ensure reproducibility and lineage. 
- Datasets stored under /datasets with .dvc metadata files.
- Remote storage configured to point to AWS S3.
- DVC tracks data versions.

### Tracking and Logging
Integrated logging has been implemented across all modules using Python’s logging module. Timestamps, severity levels, and filenames are logged for every stage. Airflow logs are also stored locally for now for each run.



