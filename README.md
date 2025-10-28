# finrag-insights-mlops

#### Course Project (MLOps IE7374) - FINRAG Insights! 
- Building an AI-powered financial analysis pipeline for structured KPI extraction and explainable reporting from 10-K filings.

## Project Overview:

1. For background, and Business HLD (High-Level Design) refer to the `design_docs/Finance RAG - HLD Draft v1.1.xlsx and Project Scoping_IE 7374_FinSights.pdf`. They explain the business problem, solution approach, and high-level architecture.
    - The Excel file contains cloud cost estimates, tool research, and algorithm analysis—essential reference for developers.

2. The DataPipeline module hosts the live SEC data ingestion process. It's a step in **Data Preprocessing**, to handle crawl-download-parse and upload final structured filings to AWS S3 buckets. Main contents are the `DataPipeline/src` and it's related `DataPipeline/dag` which orchestrates it.

3. For initial data engineering, please refer to `DataPipeline/data_engineering_research` 
    - Here, `data_engineering_research/duckdb_data_engineering` has `README` and strategy documentation files related to key technical achievements, data quality approach, sampling strategies, etc. `duckdb_data_engineering/sql` has DuckDB SQL scripts for number of operations.
    - Files like `data_engineering_research/exploratory_research` has `Research_README.md` and massive sets of EDA, experiment scripts with polars, EDA-charts, `Master_EDA_Notes.pdf` etc.

4. `src_aws_etl/` has the code, tests, configs, and requirements for the AWS S3 based ETL pipeline (Merge, Archive, Logs). Main code files are in `src_aws_etl/etl/`. 
    - Here is where bulk historical data and live data merge meaningfully and cleanly. Archival of older data and log management is also handled here.

5. Following that, `DataSchemaValidation/` has a really good collection of modules for schema validation, data quality checks, automated testing and stat-generation using `great_expectations` and `anamoly detection and alerts`.


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
        ├── DataSchemaValidation/           # Data quality & validation framework ( Great Expectations, Anamoly )
        │
        ├── src_aws_etl/                    # AWS S3 ETL operations ( Merge Incr + Historical, Archive, Log Management )
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


### Source Dataset Links:
1. Primary: https://huggingface.co/datasets/khaihernlow/financial-reports-sec
2. SEC EDGAR API (company_tickers.json), State Street SPDR ETF holdings for S&P 500 constituents
2. Potentially used: EdgarTools https://github.com/dgunning/edgartools
4. Primary datasets' source citation: https://zenodo.org/records/5589195


