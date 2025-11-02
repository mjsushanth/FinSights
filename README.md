# FinSights

#### Course Project (MLOps IE7374) - FINRAG Insights.
- Building an AI-powered financial analysis pipeline for structured KPI extraction and explainable reporting from 10-K filings SEC(Securities and Exchange Commission).

## Project Overview:

1. For background, and Business HLD (High-Level Design) please feel free to skim through [Scoping](design_docs/Project_Scoping_IE7374_FinSights.pdf) and [Design](design_docs/Finance_RAG_HLD_v1.xlsx)(excel). They explain the business problem, solution approach, and high-level architecture.  
    - The Excel file contains dataset initial understanding, cloud cost estimates, tool research, and algorithm analysis—essential reference for developers.

2. The DataPipeline module hosts the live SEC(Securities and Exchange Commission) data ingestion process. It's a step in **Data Preprocessing**, to handle crawl-download-parse and upload final structured filings to AWS S3 buckets. Main contents are the `DataPipeline/src` and it's related `DataPipeline/dag` which orchestrates it.

3. For initial data engineering, please refer to `DataPipeline/data_engineering_research` 
    - Here, [Data Engineering](DataPipeline/data_engineering_research/duckdb_data_engineering/Data_Engineering_README.md) and other README files document strategy, key technical achievements, data quality approach, sampling strategies, etc. `duckdb_data_engineering/sql` has DuckDB SQL scripts for number of operations. 
    - Files in `data_engineering_research/exploratory_research` has [Research](DataPipeline/data_engineering_research/exploratory_research/Research_README.md#L5) and massive sets of EDA, experiment scripts with polars, EDA-charts - [EDA Notes](DataPipeline/data_engineering_research/exploratory_research/polars_eda_research/Master_EDA_Notes.pdf) etc. 

4. `src_aws_etl/` has the code, tests, configs, and requirements for the AWS S3 based ETL pipeline (Merge, Archive, Logs). Main code files are in `src_aws_etl/etl/`. 
    - Here is where bulk historical data and live data merge meaningfully and cleanly. Archival of older data and log management is also handled here.


5. `src_metrics/` has the code, tests, configs, and requirements for the Data Ingestion pipeline, here we collect and process all the financial metrics(RAW numbers) from the 10-K SEC(Securities and Exchange Commission).

6. Following that, `data_auto_stats/` has a really good collection of modules for schema validation, data quality checks, automated testing and stat-generation using `great_expectations` and `anamoly detection and alerts`.


## Project Structure:
```
    ROOT FOLDER OF PROJECT/
    │
    ├── design_docs/                    # Architecture & planning documents

    ├── DataPipeline/                   # SEC data ingestion & orchestration
        │
        ├── dag/                         # Airflow DAGs for orchestration
        ├── src/                         # SEC data ingestion source code
        │
        ├── data_auto_stats/           # Data quality & validation framework ( Great Expectations, Anamoly )
        │
        ├── src_aws_etl/                    # AWS S3 ETL operations ( Merge Incr + Historical, Archive, Log Management )
        │
        ├── src_metrics/                    # SEC data ingestion using Edgar SDK for Financial Metrics
        │                           
        │
        ├── data_engineering_research/            # DuckDB data engineering workspace
        │  ├── duckdb_data_engineering/     
        │  │   ├── sql/                           # SQL scripts
        │  │
        │  ├── exploratory_research/              # Core Data Study, Polars EDA, OpenAI, LLM/LLama-cpp/ML experiments
        │  
        │
        ├── docker-compose.yaml             # Container orchestration
        ├── Dockerfile                      # Application container
        ├── environment.yml                 # Conda environment specification
```
## DVC : 
Data version Control has been implemented in this Repo, and the data is stored on an s3 Bucket managed by our team. The metadata is stored in the .dvc folder.
The DVC is to control the versions of the data used in the ingestion pipeline ,so if any data is lost / manipulated with , we can retreive the version needed.

## High level Conceptual Flow:
```
    ┌─────────────────────────────────────────────────────────────┐
    │ DATA ENGINEERING LAYER                                      │
    │ Extract → Transform → Load                                  │
    └─────────────────────────────────────────────────────────────┘
                                ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ ML FEATURE ENGINEERING LAYER                                │
    └─────────────────────────────────────────────────────────────┘
                                ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ SERVING LAYER                                               │
    │ Vector Store → Retrieval → Generation                       │
    └─────────────────────────────────────────────────────────────┘
```


- Data Pipeline Setup: https://github.com/Finsights-MLOps/FinSights/blob/main/DataPipeline/SETUP_README.md
- Data Pipeline Documentation: https://github.com/Finsights-MLOps/FinSights/blob/main/DataPipeline/README.md

### Source Dataset Links:
1. Primary: https://huggingface.co/datasets/khaihernlow/financial-reports-sec
2. Live Ingestion metrics: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
3. SEC EDGAR API (company_tickers.json), State Street SPDR ETF holdings for S&P 500 constituents
2. Potentially used: EdgarTools https://github.com/dgunning/edgartools
4. Primary datasets' source citation: https://zenodo.org/records/5589195


