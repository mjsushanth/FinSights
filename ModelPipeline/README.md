# FinRAG: Financial Retrieval-Augmented Generation System

---

## Overview
FinRAG is out attempt at a production-grade financial intelligence platform that processes SEC 10-K filings through a RAG architecture. The system combines traditional data engineering, communication with financial and sentence fact tables with modern semantic search to have an LLM-synthesized answer. We find it particularly suited for complex, narrative and factoid financial queries.

**Core Innovation**: Hybrid retrieval system fusing structured KPI extraction - communication, multi-context assembly, narrative semantic search with meaningful variant-diversity queries, window-expansion on hop context, and excellent sets of adapters or extractors - that grab complex multi-year, multi-company, multi-KPI, multi-section financial patterns through natural language.

Our [Documentation index](finrag_ml_tg1/DOCUMENTATION_INDEX.md) provides a complete resource directory. It's easy navigation, but the same can be done by reading through the key resources and depository navigation mentioned below. The documentation index file has it in a tabular format!

---

## Philosophy & Design Principles
- Choose best cloud production over Local-Prototypes: **AWS infrastructure (S3 storage, S3 Vectors, Bedrock, ECS Fargate)**. 
- Cost-conscious architecture: Cost-tracking analytical queries at multiple modules, and Cost-logging at every LLM call!
- Proper LLM validation: Sets of Automated Gold-Validation with Self@, Hit@, MMR@, Median distance and other concepts. Complete heuristic-NLP based approach for curation of a **Business-realistic Gold evaluation suite** (P3 Gold Standards)
- Validation at every layer: 5-stage S3 Vectors tests, staleness audits, parity checks, Chained-Integration test notebooks, Isolation tests.
- Real world data over toy datasets. And, tons of algorithmic strong features!

## (Some) Technical Highlights
- **Embedding Infrastructure**: 400K+ Cohere v4 1024-d vectors in S3 Vectors, $0.017-$0.06+ per query depending on complexity. Simple, single-entity queries with little retrieved context sit near the $0.017 floor; queries that fan out across ten-plus companies, six to eight sections, multiple domains, and many KPI-triggering keywords pull in far more retrieval calls and assembled context, pushing cost to $0.04-$0.06 and sometimes higher. Both ends have been observed in practice - cost scales with retrieved-context volume and entity fan-out, not a fixed per-query rate.
- **Hybrid Retrieval**: Semantic search (query variants + metadata filters) + structured KPI extraction
- **Context Engineering**: Edge-safe window expansion (±3 sentences), provenance tracking, chronological assembly
- **Evaluation Framework**: 31-question Gold P3 suite spanning factoid → multi-hop reasoning, Self, Hit@k, MRR, distance metrics; then, LLM-Eval (BERTScore, BLEURT, ROUGE-L, Cosine). 
- **NLP Front-End**: Fuzzy company resolution, multi-year parsing, risk topic classification, metric canonicalization

---

## Key Resources & Repository Navigation

### Start easily here: 
1. **[Quick Start with Docker! (RECOMMENDED)](finrag_docker_loc_tg1/LOC_DOCKER_README.md)** → Local Docker-based setup for easy launch of backend + frontend.
2. **[Quick Start with Command/Ps1 Scripts](SETUP_README.md)** → Get up and running quickly
  - Do setup with just click-install, and Run batch/sh files - launches streamlit.

### CI/CD Process (or) Cloud Deployment Starts here:
1. **[ECS Fargate Design and Runbook](./finrag_docker_loc_tg1_aws/ECS_FARGATE_RUNBOOK.md)** → **START HERE.** The live, working AWS deployment: architecture and why it is shaped that way, measured task sizing, the full cost model, the IAM least-privilege policy, and the `up` / `down` / `destroy` verbs. Deployed and verified end to end on account 908877262866 on 2026-07-31. One command: `python -m deploy_aws.cli up` from `ModelPipeline/`, or double-click `finsights_aws.command`.
2. **[Historical ECS Deployment Record](./finrag_docker_loc_tg1_aws/HISTORICAL_2025-12_ECS_DEPLOYMENT_GUIDE.md)** → HISTORICAL RECORD, not a runbook. Documents the `deploy-ecs.yml` GitHub Actions workflow and the ECS Fargate deployment that ran publicly in Dec 2025 on AWS account 729472661729, now decommissioned. The resource identifiers in it are dead and the workflow cannot be replayed as written. Kept as the record of what was built and what broke. Replacement documentation follows once the new AWS pipeline works end to end.

### **Documentation**
- **[ARCHITECTURE.md](finrag_ml_tg1/ARCHITECTURE.md)** → Directory structure + pipeline flow diagrams
- **[IMPLEMENTATION_GUIDE.md](finrag_ml_tg1/IMPLEMENTATION_GUIDE.md)** → Detailed technical implementation (Parts 1-10)
- **[S3Vect_QueryCost.md](finrag_ml_tg1/S3Vect_QueryCost.md)** → Cost analysis and optimization strategies
- **[LLMOPS_TECHNICAL_COMPLIANCE.md](finrag_ml_tg1/LLMOPS_TECHNICAL_COMPLIANCE.md)** → LLM engineering standards, Test suites, LLM usage compliance, and best practices

### **Code Organization**
**Feature-Cloud Data preparation (or) Retrieval Spine Module**:
  - **`platform_core/`** → ML Feature lifecycle management (smart caching, Stage 1-2-3 tables, Lean tables, embedding generation, embedding execution histories, S3 provisioning, PutVectors API for Vector Index at S3, etc.)
**Core App-Serving RAG Modules (Minimal Packaging)**:
  - **`rag_modules_src/`** → Production RAG components (entity extraction, retrieval, synthesis)
**Isolation/Integration Tests, RAG Tests, ML-NLP heavy modules**:
- **`validation_notebooks/`**: 3 Phase Gold tests, Manual grounding tests displayed side-by-side, RAG pipeline integration tests, S3 Vector tests. Complete isolation or 'conductor' tests which have chained 2-5 modules, etc.

### Evaluation Philosophy:
- **[Evaluation Framework & Gold Standards](finrag_ml_tg1/validation_notebooks/06_Gold_Test_Framework.md)** → We have significant, multi-phase evaluation strategies, gold standard creation, Automated and manual testing protocols. 

### Analytics, Logs & Drift Monitoring:
- Please refer to **[AWS Log Monitoring & Analytics Notebook](finrag_docker_loc_tg1_aws/AWS_LogMonitoring_Analytics.md)** for details.
- **[Model Retraining Concerns](finrag_docker_loc_tg1_aws/AWS_LogMonitoring_Analytics.md##23)** are mentioned here.

### Performance or Latency Analysis:
- Please refer to **[Pipeline Latency Analysis](finrag_ml_tg1/PIPELINE_LATENCY_ANALYSIS.md)** for detailed latency breakdowns and optimizations.

### Model Optimization:
- For model (RAG pipeline memory/IO) optimization, our complete document is here: **[TechNotes Memory Handling](finrag_ml_tg1/TechNotes_MemoryExp_Handling.md)**
- Read our strategic design and performance-cost decisions here: **[Performance & Cost Analysis](finrag_ml_tg1/Performance_Cost_Analysis.md)**

### Important Module Contracts to get familiar with:
- [Platform Core Contract](finrag_ml_tg1/platform_core/platform_core_contract.py)
- [Rag Pipeline Contract](finrag_ml_tg1/rag_modules_src/rag_pipeline/01_pipeline_contract.py)
- [S3 Retriever Contract](finrag_ml_tg1/rag_modules_src/rag_pipeline/s3_retriever_contract.py)
- [Sentence Expander Contract](finrag_ml_tg1/rag_modules_src/rag_pipeline/sentence_expander_contract.py)
- [Synthesis Pipeline Contract](finrag_ml_tg1/rag_modules_src/synthesis_pipeline/models_contract.py)

### **Key Artifacts**
- **Config**: `ml_config.yaml`, `.aws_secrets/` (credentials), `environments/` (specs)
- **Outputs**: `rag_modules_src\exports` (proper final exports), `data_cache/` (intermediate results), `test_outputs/` (some validation artifacts). 

---

## Quick Screenshots/Demo:
1. As a short example, we have the following screenshots or attachments below. One would display a custom rendering of DOM object inside JupyterServe so that you have a very well formatted, pretty display. We currently have a notebook where we serve display tables of a couple of gold test queries. 
2. Secondly, we have two further screenshots: that would be query wise token cost analytics table and model wise token cost analytics table. 
3. If vector data embedding, or sentence-data are missing from dataset, we setup proper guardrails to acknowledge missing data and not hallucinate!
4. Note: *Update*! The project now has scaled to present frontend Streamlit app with Dockerized local setup or AWS ECS deployment. The 'serving' is now comlete with proper frontend UI.


**Image 1**: Gold Test Query Serve Example -
<p align="center">
  <img src="finrag_ml_tg1\demo_images_export\G1PQ002_JCell.png" width="700" alt="Gold Test Query Serve Example">
</p>
<p align="center"><em>Gold Test Query Serve Example</em></p>

**Image 3**: Query Wise Token Cost Analytics -
<p align="center">
  <img src="finrag_ml_tg1\demo_images_export\QueryWise_TokenCostAnalytics.png" width="700" alt="Query Wise Token Cost Analytics">
</p>
<p align="center"><em>Query Wise Token Cost Analytics</em></p>

**Image 4**: Model Wise Token Cost Analytics -
<p align="center">
  <img src="finrag_ml_tg1\demo_images_export\ModelWise_TokenCostAnalytics.png" width="700" alt="Model Wise Token Cost Analytics">
</p>
<p align="center"><em>Model Wise Token Cost Analytics</em></p>
---

## Contact 
**Author**: Joel Markapudi  
**Institution**: Northeastern University | CS AI Masters | IE7374 MLOps 

