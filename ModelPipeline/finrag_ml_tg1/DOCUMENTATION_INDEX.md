# FinRAG Documentation Index

## Complete Resource Directory

| Category | Resource | Path | Description |
|----------|----------|------|-------------|
| **Getting Started** | | | |
| | Quick Start with Docker | [finrag_docker_loc_tg1/LOC_DOCKER_README.md](finrag_docker_loc_tg1/LOC_DOCKER_README.md) | Recommended local setup using Docker Compose |
| | Quick Start with Scripts | [SETUP_README.md](SETUP_README.md) | Command/PowerShell script-based installation |
| | AWS Cloud Deployment Guide | [finrag_docker_loc_tg1_aws/ECS_DEPLOYMENT_GUIDE.md](finrag_docker_loc_tg1_aws/ECS_DEPLOYMENT_GUIDE.md) | Step-by-step ECS deployment with GitHub Actions |
| **Core Documentation** | | | |
| | System Architecture | [finrag_ml_tg1/ARCHITECTURE.md](finrag_ml_tg1/ARCHITECTURE.md) | Directory structure, pipeline flow diagrams |
| | Implementation Guide | [finrag_ml_tg1/IMPLEMENTATION_GUIDE.md](finrag_ml_tg1/IMPLEMENTATION_GUIDE.md) | Detailed technical implementation (Parts 1-10) |
| | LLMOps Technical Compliance | [finrag_ml_tg1/LLMOPS_TECHNICAL_COMPLIANCE.md](finrag_ml_tg1/LLMOPS_TECHNICAL_COMPLIANCE.md) | LLM engineering standards, test suites, best practices |
| **Performance & Optimization** | | | |
| | Pipeline Latency Analysis | [finrag_ml_tg1/PIPELINE_LATENCY_ANALYSIS.md](finrag_ml_tg1/PIPELINE_LATENCY_ANALYSIS.md) | Stage-by-stage latency breakdown, optimization strategies |
| | S3 Vectors Query Cost Analysis | [finrag_ml_tg1/S3Vect_QueryCost.md](finrag_ml_tg1/S3Vect_QueryCost.md) | Cost analysis, optimization strategies, pricing models |
| | Performance vs Cost Analysis | [finrag_ml_tg1/Performance_Cost_Analysis.md](finrag_ml_tg1/Performance_Cost_Analysis.md) | Strategic design decisions, trade-off analysis |
| | Memory Optimization Guide | [finrag_ml_tg1/TechNotes_MemoryExp_Handling.md](finrag_ml_tg1/TechNotes_MemoryExp_Handling.md) | RAM/IO handling strategies, memory management |
| **Testing & Validation** | | | |
| | Evaluation Framework | [finrag_ml_tg1/validation_notebooks/06_Gold_Test_Framework.md](finrag_ml_tg1/validation_notebooks/06_Gold_Test_Framework.md) | Gold P3 suite, multi-phase evaluation, testing protocols |
| | Validation Notebooks | [finrag_ml_tg1/validation_notebooks/](finrag_ml_tg1/validation_notebooks/) | Integration tests, S3 Vector tests, RAG pipeline tests |
| **Operations & Monitoring** | | | |
| | AWS Log Monitoring & Analytics | [finrag_docker_loc_tg1_aws/AWS_LogMonitoring_Analytics.md](finrag_docker_loc_tg1_aws/AWS_LogMonitoring_Analytics.md) | Log monitoring, drift detection, model retraining concerns |
| **Module Contracts** | | | |
| | Platform Core Contract | [finrag_ml_tg1/platform_core/platform_core_contract.py](finrag_ml_tg1/platform_core/platform_core_contract.py) | ML feature lifecycle management API |
| | RAG Pipeline Contract | [finrag_ml_tg1/rag_modules_src/rag_pipeline/01_pipeline_contract.py](finrag_ml_tg1/rag_modules_src/rag_pipeline/01_pipeline_contract.py) | Core RAG pipeline interface definitions |
| | S3 Retriever Contract | [finrag_ml_tg1/rag_modules_src/rag_pipeline/s3_retriever_contract.py](finrag_ml_tg1/rag_modules_src/rag_pipeline/s3_retriever_contract.py) | S3 Vectors retrieval API specification |
| | Sentence Expander Contract | [finrag_ml_tg1/rag_modules_src/rag_pipeline/sentence_expander_contract.py](finrag_ml_tg1/rag_modules_src/rag_pipeline/sentence_expander_contract.py) | Context expansion interface |
| | Synthesis Pipeline Contract | [finrag_ml_tg1/rag_modules_src/synthesis_pipeline/models_contract.py](finrag_ml_tg1/rag_modules_src/synthesis_pipeline/models_contract.py) | Response generation and packaging API |
| **Code Organization** | | | |
| | Platform Core Module | [platform_core/](platform_core/) | ML feature lifecycle, smart caching, embedding generation |
| | RAG Modules Source | [rag_modules_src/](rag_modules_src/) | Production RAG components (entity extraction, retrieval, synthesis) |
| | Validation Notebooks | [validation_notebooks/](validation_notebooks/) | Gold tests, integration tests, isolation tests, S3 Vector tests |
| **Configuration & Artifacts** | | | |
| | ML Configuration | [ml_config.yaml](ml_config.yaml) | Primary system configuration file |
| | AWS Secrets | [.aws_secrets/](.aws_secrets/) | Credentials and authentication |
| | Environment Specs | [environments/](environments/) | Environment-specific configurations |
| | RAG Exports | [rag_modules_src/exports/](rag_modules_src/exports/) | Final production exports |
| | Data Cache | [data_cache/](data_cache/) | Intermediate processing results |
| | Test Outputs | [test_outputs/](test_outputs/) | Validation artifacts and test results |