# FinSights - Data Pipeline

### Data Acquisition:
1. We first acquired bulk of our data (10-K filings) from an initial chosen dataset source - HuggingFace dataset.
    -  These are all our data engineering feature achievements [Data Engineering Feats](data_engineering_research/duckdb_data_engineering/Data_Engineering_README.md#L71) 
    -  Overall, we achieved merging 3 heterogeneous sources, custom dimension curation, stratified sampling pipeline, manual data injection support, data quality checks and validation suite, and more.
    -  More extensive research is done, documented at [Polars Research:](#polars-research) with multiple EDA notebooks.
 
2. Apart from that, there's a live data ingestion stage which implements a pipeline, ensuring reliable and automated retrieval of SEC filings for selected companies. 
   - Data is fetched directly from the SEC EDGAR database using a modular crawler (download_filings.py), which downloads 10-K filings.
   - It supports configurable year ranges, multiple companies, and filing types defined in config/config.json. 
   - The list of companies are stored in a CSV file (companies.csv) in AWS S3 bucket at the beginning of pipeline and stored locally for downstream tasks. 
   - The entire ingestion process is environment-driven through .env variables, reproducible with environment.yml.

3. We also have a working code that uses the EDGAR SDK and EDGAR API to fetch live numeric/metric data.


### Data Preprocessing:
- For huggingface dataset - the earlier documentation [Data Engineering Feats](data_engineering_research/duckdb_data_engineering/Data_Engineering_README.md#L71) has detailed information about preprocessing.
- For live data - Raw SEC filings are cleaned, parsed, and converted into structured formats using extract_and_convert.py. This module extracts key SEC Items (e.g., Item 1A – Risk Factors, Item 7 – MD&A).
- Cleans HTML tags, normalizes texts (replace special Unicode characters, remove page numbers and headers, fix broken section headers) and tokenizes sentences.
- Generates consistent metadata: CIK, company name, report year, section ID, timestamps, and version tags
- Exports to Parquet files for downstream analytics

### Test Modules
- For huggingface dataset - Files such as `31_run_stratified_post_analysis.sql` and several other validation scripts, ad-hoc analysis scripts act as our data quality checks.
- We wrote comprehensive unit tests to validate the core functionality of the download_filings and extract_and_convert module as well as AWS connection modules(download_from_s3 and upload_to_s3).
- All tests are written with pytest, use temporary directories for isolation, and run independently without needing any external data or network access.
  

### Pipeline Orchestration (Airflow DAGs)
We designed an Airflow DAG that automates the full ETL workflow for SEC filings - from fetching company data to generating structured outputs in a parquet file. 

#### How it works:
- We first pull the list of companies and verify all required configurations. 
- Next, filings are automatically downloaded from official SEC sources.
- The raw, unstructured data is parsed to extract key sections (like Item 1A, Item 2, Item 7 etc) and transformed into standardized Parquet files which are then combined into a single parquet file.
- The processed outputs are then uploaded to cloud storage (AWS S3).
- Next, the temporary files are cleaned up and task status is logged.
- The next step is a core ETL pipeline based on polars on AWS S3 buckets, for a clean data merge concept between historical and live fact datasets. The fact datasets are also versioned and archived properly. (Ref: `src_aws_etl` folder.)
- Post-processing includes generating metadata and statistics for the ingested data (Great Expectations), and anomaly alerts. (Ref: `data_auto_stats` folder.) [To be integrated into Docker-Airflow.]
- The DAG ensures all stages — download → extract → transform → upload → clean — run sequentially in the right order.


#### SETUP:
Refer to **SETUP_README.md** file for details about setting up the environment for running the AirFlow pipeline locally.

### Data Versioning with DVC
All intermediate datasets (raw, extracted, parquet) are tracked using DVC to ensure reproducibility and lineage. 
- Datasets stored under /datasets with .dvc metadata files.
- Remote storage configured to point to AWS S3.
- DVC tracks data versions.

### Tracking and Logging
Integrated logging has been implemented across all modules using Python’s logging module. Timestamps, severity levels, and filenames are logged for every stage. Airflow logs are also stored locally for now for each run.

### Data Schema & Statistics Generation

We implemented a two-phase automated data validation system using Great Expectations.

### How it works:

**Phase 1: Early Validation (20-Column Schema)**
- Runs immediately after the initial data extraction and merge step, before feature engineering
- Validates schema conformance, structural integrity (CIK format, filing dates), temporal coherence, and null constraints
- Halts pipeline on failure with email alerts to stakeholders

**Phase 2: Comprehensive Statistics (24-Column Schema)**
- Runs after feature engineering on final dataset with derived columns (`cik_int`, `tickers`, `likely_kpi`, `has_numbers`, `has_comparison`, `row_hash`)
- Generates detailed statistical profiles, validates uniqueness constraints, monitors KPI extraction rates

### Technical Stack:
- Great Expectations for schema generation and validation rules
- Boto3 for S3 data access (bucket: `sentence-data-ingestion`)
- PyArrow for Parquet handling
- Configurable validation rules per phase in `config.py`
- Ephemeral GE context for Docker/Airflow compatibility

### Output & Monitoring:
- Validation results logged to `logs/` and saved as JSON artifacts in `output/`
- Email alerts on quality threshold breaches
- Quality metrics tracked: schema completeness, null distribution, temporal consistency, duplicate counts

**Integration:** The GE code (validation and statistics) can be tested manually with 1 command. Cant be automated into docker run or DAG run. RCA being: dockercompose and GE library have some conflicts, issues about context discovery and writable root access.

### Anomaly Detection & Alerts
The pipeline flags anomalies during preprocessing and ingestion:
- Missing sections or malformed filings
- Year mismatch or out-of-range reports
- Conversion errors logged and surfaced as Airflow task alerts
Future extension: Slack/email alerts for failed or incomplete extractions.



## Bias Mitigation Documentation:

1. Bias in the data:
   - After firm data study and EDA (on 71.8M rows of historical data), we believe any processes like - treating dimensions (like sector, data size, years) and their distribution as a bias to be "corrected" via sampling is wrong. We do not recommend artificially creating uniformity on meaningful data. 
   - Our philosophy is: **preserve informational variance**, understand that analysis burdens, accounting complexity, and disclosure quality, disclosure volume are real world patterns. We dont want to **distort** that.
   - We understand the real bias in our system being: Temporal gaps, Selection Bias, Recency Bias, Generation-time bias, or Model bias, etc.
   - What guides our understanding of bias for this dataset is the `polars_eda_research/Master_EDA_Notes.pdf` file which has a detailed study of data distributions, patterns.

2. Data Slicing & Mitigation Strategies: 
    - Our duckdb engineering handles data selection with stratified sampling, with a temporal sampling strat with adaptive allocation & prioritization of recent data. It also supports manual injection of external data.
    - Alongside temporal stratification, we use a weighted multi-objective sampling score to prioritize high-quality disclosures from diverse sectors **and** the S&P 500 companies list from State Street SPDR ETF holdings. 
    -  More at -[Sampling Readup](data_engineering_research/duckdb_data_engineering/DuckDB_Sampling_Strategy.md#temporal-sampling-strategy) and [Multi-Objective Sampling Score Explanation](data_engineering_research/duckdb_data_engineering/DuckDB_Sampling_Strategy.md#weighted-multi-objective-sampling-score-explanation).
   
3. Documented Impact Analysis:
   - We will be able to update this section, informing of our impact as soon as our RAG pipeline is built fully.


