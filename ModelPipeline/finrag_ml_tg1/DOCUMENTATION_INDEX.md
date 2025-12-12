# FinRAG Documentation Index

## Complete Resource Directory

| Category | Resource | Path | Description |
|----------|----------|------|-------------|
| **Getting Started** | | | |
| | AWS Cloud Deployment Guide | [ECS_DEPLOYMENT_GUIDE.md](../finrag_docker_loc_tg1_aws/ECS_DEPLOYMENT_GUIDE.md) | Step-by-step ECS deployment with GitHub Actions |
| | Quick Start with Docker | [LOC_DOCKER_README.md](../finrag_docker_loc_tg1/LOC_DOCKER_README.md) | Recommended local setup using Docker Compose |
| | Quick Start with Scripts | [SETUP_README.md](../SETUP_README.md) | Command/PowerShell script-based installation |
| **Core Documentation** | | | |
| | System Architecture | [ARCHITECTURE.md](ARCHITECTURE.md) | Directory structure, pipeline flow diagrams |
| | Implementation Guide | [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) | Detailed technical implementation (Parts 1-10) |
| | LLMOps Technical Compliance | [LLMOPS_TECHNICAL_COMPLIANCE.md](LLMOPS_TECHNICAL_COMPLIANCE.md) | LLM engineering standards, test suites, best practices |
| **Performance & Optimization** | | | |
| | Pipeline Latency Analysis | [PIPELINE_LATENCY_ANALYSIS.md](PIPELINE_LATENCY_ANALYSIS.md) | Stage-by-stage latency breakdown, optimization strategies |
| | S3 Vectors Query Cost Analysis | [S3Vect_QueryCost.md](S3Vect_QueryCost.md) | Cost analysis, optimization strategies, pricing models |
| | Performance vs Cost Analysis | [Performance_Cost_Analysis.md](Performance_Cost_Analysis.md) | Strategic design decisions, trade-off analysis |
| | Memory Optimization Guide | [TechNotes_MemoryExp_Handling.md](TechNotes_MemoryExp_Handling.md) | RAM/IO handling strategies, memory management |
| **Testing & Validation** | | | |
| | Evaluation Framework | [06_Gold_Test_Framework.md](validation_notebooks/06_Gold_Test_Framework.md) | Gold P3 suite, multi-phase evaluation, testing protocols |
| | Validation Notebooks | [validation_notebooks/](validation_notebooks/) | Integration tests, S3 Vector tests, RAG pipeline tests |
| **Operations & Monitoring** | | | |
| | AWS Log Monitoring & Analytics | [AWS_LogMonitoring_Analytics.md](../finrag_docker_loc_tg1_aws/AWS_LogMonitoring_Analytics.md) | Log monitoring, drift detection, model retraining concerns |
| **Module Contracts** | | | |
| | Platform Core Contract | [platform_core_contract.py](platform_core/platform_core_contract.py) | ML feature lifecycle management API |
| | RAG Pipeline Contract | [01_pipeline_contract.py](rag_modules_src/rag_pipeline/01_pipeline_contract.py) | Core RAG pipeline interface definitions |
| | S3 Retriever Contract | [s3_retriever_contract.py](rag_modules_src/rag_pipeline/s3_retriever_contract.py) | S3 Vectors retrieval API specification |
| | Sentence Expander Contract | [sentence_expander_contract.py](rag_modules_src/rag_pipeline/sentence_expander_contract.py) | Context expansion interface |
| | Synthesis Pipeline Contract | [models_contract.py](rag_modules_src/synthesis_pipeline/models_contract.py) | Response generation and packaging API |
| **Code Organization** | | | |
| | Platform Core Module | [platform_core/](platform_core/) | ML feature lifecycle, smart caching, embedding generation |
| | RAG Modules Source | [rag_modules_src/](rag_modules_src/) | Production RAG components (entity extraction, retrieval, synthesis) |
| | Validation Notebooks | [validation_notebooks/](validation_notebooks/) | Gold tests, integration tests, isolation tests, S3 Vector tests |
| **Configuration & Artifacts** | | | |
| | ML Configuration | [ml_config.yaml](../finrag_ml_tg1/.aws_config/ml_config.yaml) | Primary system configuration file |
| | AWS Secrets | [.aws_secrets/](../finrag_ml_tg1/.aws_secrets/) | Credentials and authentication |
| | Environment Specs | [environments/](../finrag_ml_tg1/environments/) | Environment-specific configurations |
| | RAG Exports | [exports/](rag_modules_src/exports/) | Final production exports |
| | Data Cache | [data_cache/](../finrag_ml_tg1/data_cache/) | Intermediate processing results |
| | Isolation Test Notebooks | [01_Isolation_Test_NBS/](rag_modules_src/01_Isolation_Test_NBS/) | Component isolation tests, integration tests |
| | LLM Evaluation Notebooks | [02_LLMEval_Notebooks/](rag_modules_src/02_LLMEval_Notebooks/) | LLM evaluation metrics, quality assessments |To run code, enable code execution and file creation in Settings > Capabilities.

