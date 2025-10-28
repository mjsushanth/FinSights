### Pipeline Orchestration (Airflow DAGs)

We designed an Airflow DAG that automates the full ETL workflow for SEC filings - from fetching company data to generating structured, ready-to-analyze outputs.

#### How it works

- We first pull the list of companies and verify all required configurations.

- Next, filings are automatically downloaded from official SEC sources.

- The raw, unstructured data is parsed to extract key sections (like Item 1A, Item 2, Item 7 etc) and transformed into standardized Parquet files which are combined into a single parquet file.

- The processed outputs are then uploaded to cloud storage (AWS S3) for downstream analysis.

- Finally, temporary files are cleaned up and task status is logged.

The DAG ensures all stages — download → extract → transform → upload → clean — run seamlessly and in the right order.

### Unit Tests

We wrote comprehensive unit tests to validate the core functionality of the download_filings and extract_and_convert module.
All tests are written with pytest, use temporary directories for isolation, and run independently without needing any external data or network access.
