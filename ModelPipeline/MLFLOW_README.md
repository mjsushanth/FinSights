# FinRAG MLflow Experiment Tracking

## Overview

The FinRAG synthesis pipeline integrates MLflow for comprehensive experiment tracking, enabling systematic monitoring of query performance, cost analysis, and model comparison across different configurations.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MLflow Integration Layer                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   main.py                        mlflow_utils.py                        │
│   ┌──────────────┐              ┌─────────────────────────────────┐    │
│   │   CLI Entry  │──────────────│  run_with_mlflow_tracking()     │    │
│   │    Point     │              │  - Orchestrates pipeline        │    │
│   └──────────────┘              │  - Extracts metrics             │    │
│                                 │  - Logs to MLflow               │    │
│                                 └───────────────┬─────────────────┘    │
│                                                 │                       │
│                                                 ▼                       │
│                                 ┌─────────────────────────────────┐    │
│                                 │      mlflow_tracker.py          │    │
│                                 │  - Experiment management        │    │
│                                 │  - Run lifecycle                │    │
│                                 │  - Parameter/metric logging     │    │
│                                 │  - Artifact storage             │    │
│                                 └─────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## What We Are Tracking

### 1. Parameters (Logged Once Per Run)

Configuration settings that define how the query was processed:

| Parameter | Description | Example Value |
|-----------|-------------|---------------|
| `model_key` | Model configuration key from ml_config.yaml | `development_CH45` |
| `model_id` | Full AWS Bedrock model identifier | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `temperature` | LLM temperature setting | `0.1` |
| `max_tokens` | Maximum output tokens allowed | `8192` |
| `cost_per_1k_input` | Cost per 1000 input tokens (USD) | `0.001` |
| `cost_per_1k_output` | Cost per 1000 output tokens (USD) | `0.005` |
| `system_prompt_version` | Version of system prompt template | `v1` |
| `query_template_version` | Version of query template | `v1` |
| `include_kpi` | Whether KPI data retrieval is enabled | `True` |
| `include_rag` | Whether RAG retrieval is enabled | `True` |
| `query_length` | Character length of user query | `273` |
| `query_preview` | First 100 characters of query | `For NVIDIA and Microsoft, what were revenue...` |

### 2. Metrics (Numerical Measurements)

Performance and usage metrics from each query execution:

| Metric | Description | Unit |
|--------|-------------|------|
| `latency_total_seconds` | End-to-end pipeline execution time | seconds |
| `input_tokens` | Number of tokens sent to LLM | count |
| `output_tokens` | Number of tokens in LLM response | count |
| `total_tokens` | Sum of input + output tokens | count |
| `cost_usd` | Total cost of the LLM call | USD |
| `context_length_chars` | Size of assembled context | characters |
| `answer_length_chars` | Size of LLM response | characters |
| `kpi_matches_count` | Number of structured KPI data points retrieved | count |
| `rag_chunks_count` | Number of semantic text chunks retrieved | count |

### 3. Tags (Categorical Labels for Filtering)

Metadata tags for organizing and filtering runs:

| Tag | Description | Example Value |
|-----|-------------|---------------|
| `status` | Run outcome | `success` / `failed` |
| `environment` | Deployment environment | `development` / `production` |
| `run_date` | Date of execution | `2025-11-28` |
| `tickers` | Company ticker symbols in query | `NVDA,MSFT` |
| `years` | Fiscal years referenced | `2018,2019,2020` |
| `error_message` | Error details (if failed) | `Bedrock throttling error...` |

### 4. Artifacts (Saved Files)

Full content saved for debugging and reproducibility:

```
artifacts/
├── prompts/
│   └── original_query.txt     # Raw user question
├── context/
│   └── assembled_context.txt  # KPI + RAG context assembled
└── response/
    └── full_response.json     # Complete pipeline response with metadata
```

---

## Experiment Structure

```
MLflow Tracking Server
│
└── Experiment: "FinRAG-Integration"
    │
    ├── Run: query_20241128_143052_development_CH45
    │   ├── Parameters: model_key, temperature, max_tokens, ...
    │   ├── Metrics: latency, tokens, cost, retrieval counts, ...
    │   ├── Tags: status=success, tickers=NVDA,MSFT, ...
    │   └── Artifacts: prompts/, context/, response/
    │
    ├── Run: query_20241128_144510_development_CL_SONN_4_5
    │   └── ...
    │
    └── Run: query_20241128_150023_production_balanced
        └── ...
```

---

## Quick Start

### 1. Installation

```bash
pip install mlflow>=2.9.0
```

### 2. Run Pipeline with Tracking

```bash
cd ModelPipeline

# Default run (MLflow enabled)
python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main

# Custom query
python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main \
    --query "What was NVIDIA's revenue in 2020?"

# Different model
python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main \
    --model development_CL_SONN_4_5

# Custom experiment name
python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main \
    --experiment "FinRAG-Model-Comparison"

# Disable tracking
python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --no-tracking
```

### 3. View Results in MLflow UI

```bash
cd ModelPipeline
mlflow ui --backend-store-uri mlruns
```

Then open: **http://localhost:5000**

---

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--query, -q` | User question | Production test query |
| `--model, -m` | Model key from ml_config.yaml | `development_CH45` |
| `--experiment, -e` | MLflow experiment name | `FinRAG-Synthesis` |
| `--environment` | Environment tag | `development` |
| `--no-tracking` | Disable MLflow tracking | Enabled |
| `--no-export-context` | Skip context file export | Export enabled |
| `--export-response` | Export full response JSON | Enabled |

---

## Use Cases

### 1. Model Comparison

Compare performance across different LLM models:

```bash
# Test Haiku 4.5 (fast, cheap)
python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main \
    --model development_CH45 \
    --experiment "Model-Comparison-Nov2024"

# Test Sonnet 4.5 (slower, higher quality)
python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main \
    --model development_CL_SONN_4_5 \
    --experiment "Model-Comparison-Nov2024"

# Test Nova Micro (budget option)
python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main \
    --model production_budget \
    --experiment "Model-Comparison-Nov2024"
```

**Compare in MLflow UI:**
- Select all runs → Click "Compare"
- View side-by-side: cost_usd, latency, answer_length

### 2. Prompt Engineering

Track different prompt versions:

```bash
# After creating system_financial_rag_v2.yaml
# Update PromptLoader to use v2, then run:

python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main \
    --experiment "Prompt-V2-Evaluation"
```

**Analyze in MLflow UI:**
- Filter by `system_prompt_version`
- Compare answer quality via artifacts

### 3. Cost Monitoring

Track spend across queries:

```bash
# In MLflow UI, use search:
metrics.cost_usd > 0.01
```

**Aggregate in Python:**
```python
import mlflow
runs = mlflow.search_runs(experiment_names=["FinRAG-Integration"])
total_cost = runs["metrics.cost_usd"].sum()
print(f"Total spend: ${total_cost:.2f}")
```

### 4. Retrieval Analysis

Identify queries with poor retrieval:

```bash
# In MLflow UI, filter:
metrics.rag_chunks_count < 3
metrics.kpi_matches_count = 0
```

### 5. Latency Optimization

Find slow queries:

```bash
# In MLflow UI, filter:
metrics.latency_total_seconds > 30
```

---

## File Structure

```
synthesis_pipeline/
├── main.py              # CLI entry point
├── orchestrator.py      # Core pipeline logic (unchanged)
├── mlflow_tracker.py    # MLflow tracking class
├── mlflow_utils.py      # Metric extraction & integration
├── supply_lines.py      # KPI + RAG retrieval
├── bedrock_client.py    # AWS Bedrock LLM client (unchanged)
├── models.py            # Response data models (unchanged)
└── query_logger.py      # S3/Parquet logging (unchanged)

mlruns/                  # MLflow tracking data (auto-created)
├── 0/                   # Default experiment
└── {experiment_id}/     
    └── {run_id}/
        ├── params/
        ├── metrics/
        ├── tags/
        └── artifacts/
```

---
