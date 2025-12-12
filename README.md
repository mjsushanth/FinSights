# FinSights

#### Course Project (MLOps IE7374) - FinSights.
<!-- - Building an AI-powered financial analysis pipeline for structured KPI extraction and explainable reporting from 10-K filings SEC(Securities and Exchange Commission). -->

- FinSights is a production-grade financial document intelligence system. The system processes SEC 10-K filings to enable sophisticated question-answering capabilities for financial analysts and portfolio managers through a hybrid retrieval architecture.
- **The Problem**: Financial analysts spend countless hours manually parsing dense SEC 10-K filings to extract key performance indicators and answer strategic questions. With thousands of companies filing annually, this manual process is time-consuming, error-prone, and doesn't scale.
- **Our Solution**: FinSights combines structured KPI extraction with semantic retrieval-augmented generation (RAG) to provide, assembles multi-sourced data to deliver accurate, context-aware answers to complex financial queries. It promises cost-effectiveness, scalability, and true grounding for insights by citing actual filing IDs.
- FinSights' goal is to make dense financial documents easily explainable and interpretable. 

### Quick Redirect (Setup):
- Setup Instructions: **[Setup Instructions](ModelPipeline/README.md#L38)** 
- There are 2 setup options, preferred one being dockerized setup for local installation. **[Quick Start with Docker! (RECOMMENDED)](ModelPipeline/finrag_docker_loc_tg1/LOC_DOCKER_README.md)** and [Quick Start with Command/Ps1 Scripts](ModelPipeline/SETUP_README.md)
- Cloud deployment / CICD instructions are also here: **[AWS Cloud Deployment Guide](ModelPipeline/finrag_docker_loc_tg1_aws/ECS_DEPLOYMENT_GUIDE.md)** → Step-by-step ECS deployment instructions.

### Full Model Readme at:
- Please check the file [ModelPipeline README](ModelPipeline/README.md). Our core resources can be read in the Key Resource section, or the [Documentation Index](ModelPipeline/finrag_ml_tg1/DOCUMENTATION_INDEX.md).

## Architecture Diagram:
<p align="center">
  <img src="FinSights Architecture Diagram.png" width="800" alt="FinSights Architecture Diagram">
</p>
<p align="center"><em>FinSights Architecture Diagram</em></p>



## High level Conceptual Flow:
```
┌─────────────────────────────────────────────────────────────────┐
│ DATA ENGINEERING LAYER                                          │
│ SEC Edgar API → Sentence Extraction → S3 Storage (1M samples)  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ EMBEDDING & INDEXING LAYER                                      │
│ Cohere Embed v4 → S3 Vectors (200K+ 1024-d) → Metadata Filters │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ RAG ORCHESTRATION LAYER                                         │
│ Entity Extraction → Query Variants → Triple Retrieval Paths    │
│ (Filtered + Global + Variants) → Context Assembly              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ SYNTHESIS & SERVING LAYER                                       │
│ Dual Supply Lines (KPI + Semantic) → LLM (Claude Bedrock)      │
│ → Citation Headers → Structured Response                        │
└─────────────────────────────────────────────────────────────────┘
```

### Service Architecture:
- Three-Tier SOA / Client-Server / MVC / Microservices Lite.
```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION TIER                        │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Streamlit Frontend (Port 8501) /                  │     │
│  │  Entry-HTTP contract, session management, UI comps,│     │  
│  │  Talk to FastAPI client, display logic, etc.       │     │ 
└─────────────────────────────────────────────────────────────┘
                           ↓ HTTP POST /query
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION TIER                         │
│  │  FastAPI Backend (Port 8000)                       │     │
└─────────────────────────────────────────────────────────────┘
                           ↓ Python function call
┌─────────────────────────────────────────────────────────────┐
│                    BUSINESS LOGIC TIER                      │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Model Pipeline, ML Orchestrator                   │     │
└─────────────────────────────────────────────────────────────┘
                           ↓ API calls
┌─────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                        │
│  ├─ AWS S3, Cohere, Bedrock (Claude models)                 │
└─────────────────────────────────────────────────────────────┘
```
- Data Pipeline Setup: https://github.com/Finsights-MLOps/FinSights/blob/main/DataPipeline/SETUP_README.md
- Data Pipeline Documentation: https://github.com/Finsights-MLOps/FinSights/blob/main/DataPipeline/README.md


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

7. The `ModelPipeline/` contains the complete ML serving infrastructure with production-grade RAG implementation. The core orchestrator (`finrag_ml_tg1/rag_modules_src/synthesis_pipeline/orchestrator.py`) coordinates entity extraction, KPI lookup, semantic retrieval, and LLM synthesis through a clean `answer_query()` interface.
    - Key modules include EntityAdapter for company/year extraction, MetricPipeline for structured KPI queries, RAGPipeline for vector-based semantic search, and BedrockClient for Claude-powered synthesis. Full implementation details in [ModelPipeline README](ModelPipeline/README.md).

8. The `ModelPipeline/serving/` layer implements a three-tier service architecture separating concerns between presentation (Streamlit frontend), application (FastAPI backend), and business logic (ML orchestrator). Backend wraps the ML pipeline with RESTful HTTP endpoints while frontend provides a stateless chat interface.
    - Setup is automated via `setup_finrag` scripts with UV package manager for fast dependency resolution. One-click startup through `start_finrag` scripts launches both services with automatic browser opening. See [Setup Instructions](ModelPipeline/SETUP_README.md) for complete deployment guide.
    - Update! The above quick redirect and links, easily point to 2 better, stronger approaches.
    - We have complete automated CI-CD setup workflows that show how the applications required Dockerized images deploy on ECS serverless Fargate. And once that's done, you can quickly access the public serving frontend URL or IP, which makes it much easier to access the frontend application.
    - Secondly, we also have the proper edge deployment, which says the same dockerization approach can spin up on the local machine and you can access the front-end application through your machine. It will still connect the relative cloud services components, inference services, data services to the cloud, such as S3 and AWS Bedrock.

9. System achieves $0.017 - $0.025 per query cost efficiency through Parquet-based vector storage (99% savings vs managed databases), processes complex multi-company queries, and maintains comprehensive logging and audit trails across all tiers for production-grade observability.
    - Architecture supports independent scaling of frontend and backend services, demonstrates MLOps best practices including dependency injection, contract-driven development with Pydantic validation, and separation of ML inference from HTTP serving logic.


## Project Structure:
```
📦 FinSights/
 ┣ 📂 DataPipeline/                          # SEC data ingestion & ETL orchestration
 ┃ ┣ 📂 dag/                                 # Airflow DAGs for workflow automation
 ┃ ┣ 📂 src/                                 # SEC Edgar SDK ingestion + financial metrics extraction
 ┃ ┣ 📂 src_aws_etl/                         # S3 merge strategies (incremental + historical), archival, logging
 ┃ ┣ 📂 data_auto_stats/                     # Great Expectations validation, anomaly detection
 ┃ ┣ 📂 data_engineering_research/           # DuckDB analytics, Polars EDA, SQL exploration
 ┃ ┣ 📜 docker-compose.yaml                  # Container orchestration
 ┃ ┗ 📜 environment.yml                      # Conda environment spec
 ┃
 ┣ 📂 ModelPipeline/                         # LLM/RAG infrastructure & validation (finrag_ml_tg1/)
 ┃ ┣ 📂 platform_core/             # Embedding generation, S3 Vectors provisioning, Gold test curation
 ┃ ┃ ┣ 📜 01_Stage2_EmbeddingGen.ipynb       # Stage 2 meta table + embedding pipeline
 ┃ ┃ ┣ 📜 02_EmbeddingAnalytics.ipynb        # Vector-metadata parity, staleness audits
 ┃ ┃ ┣ 📜 03_S3Vector_TableProvisioning.ipynb
 ┃ ┃ ┣ 📜 04_S3Vector_BulkIngestion.ipynb
 ┃ ┃ ┣ 📜 05_GoldP1P2_TestSuite.ipynb        # Anchor-based validation tests
 ┃ ┃ ┣ 📜 06_GoldP3_HeuristicEng_Curation.ipynb
 ┃ ┃ ┗ 📜 07-09 (Cost, Architecture, Tests)
 ┃ ┃
 ┃ ┣ 📂 rag_modules_src/                     # Production RAG components (query-time execution)
 ┃ ┃ ┣ 📂 entity_adapter/                    # Entity extraction, fuzzy matching, metric mapping
 ┃ ┃ ┣ 📂 metric_pipeline/                   # Structured KPI extraction
 ┃ ┃ ┣ 📂 rag_pipeline/                      # Retrieval, context assembly, provenance tracking
 ┃ ┃ ┣ 📂 synthesis_pipeline/                # LLM response generation, citation validation
 ┃ ┃ ┣ 📂 prompts/                           # YAML prompt templates
 ┃ ┃ ┗ 📂 utilities/                         # Logging, error handling, shared helpers
 ┃ ┃
 ┃ ┣ 📂 loaders/                             # MLConfig service, data loading utilities
 ┃ ┣ 📂 data_cache/                          # Local Parquet mirrors, analysis exports
 ┃ ┣ 📂 .aws_config/                         # AWS service configurations
 ┃ ┣ 📂 .aws_secrets/                        # Credentials (gitignored)
 ┃ ┗ 📜 ml_config.yaml                       # 200+ model/retrieval parameters
 ┃
 ┣ 📂 design_docs/                           # Architecture diagrams, flow charts
 ┃
 ┣ 📜 README.md                              # Project overview & navigation
 ┣ 📜 ARCHITECTURE.md                        # Directory structure + pipeline flows
 ┣ 📜 IMPLEMENTATION_GUIDE.md                # Parts 1-10 technical deep-dive
 ┗ 📜 LLMOPS_TECHNICAL_COMPLIANCE.md         # MLOps requirement mapping

```

## DVC : 
Data version Control has been implemented in this Repo, and the data is stored on an s3 Bucket managed by our team. The metadata is stored in the .dvc folder.
The DVC is to control the versions of the data used in the ingestion pipeline ,so if any data is lost / manipulated with , we can retreive the version needed.

## MLFlow (for experiment tracking) : 
The FinRAG synthesis pipeline integrates MLflow for comprehensive experiment tracking, enabling systematic monitoring of query performance, cost analysis, and model comparison across different configurations.

#### Integration files
```
📦 FinSights/
 ┣ 📂 DataPipeline/                          
 ┣ 📂 ModelPipeline/                         
 ┃ ┣ 📂 rag_modules_src/
 ┃ ┃ ┣ 📂 synthesis_pipeline/                
 ┃ ┃ ┃ ┣ 📜 main.py              # CLI entry point
 ┃ ┃ ┃ ┣ 📜 mlflow_tracker.py    # Experiment management, run lifecycle, logging APIs
 ┃ ┃ ┃ ┣ 📜 mlflow_utils.py      # Metric extraction + integration helpers
 ┃ ┃ ┃ ┣ 📜 supply_lines.py      # Added 2 lines for metric_result
```
Details in [ModelPipeline MLFLOW_README](ModelPipeline/MLFLOW_README.md).

### Source Dataset Links:
1. Primary: https://huggingface.co/datasets/khaihernlow/financial-reports-sec
2. Live Ingestion metrics: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
3. SEC EDGAR API (company_tickers.json), State Street SPDR ETF holdings for S&P 500 constituents
2. Potentially used: EdgarTools https://github.com/dgunning/edgartools
4. Primary datasets' source citation: https://zenodo.org/records/5589195


