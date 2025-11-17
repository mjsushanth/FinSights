## MLFlow Integration


### 1. Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file:

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret

MLFLOW_TRACKING_URI=mlruns
```

### 3. Run CLI

```bash
python main.py
```
### 4. Run Evaluation

```bash
python evaluation/run_evaluation.py
```

## 📁 Project Structure

```
financial-rag-system/
├── config/
│   ├── settings.py          # Centralized configuration
│   └── prompts.py            # Versioned prompt templates
├── data/
│   ├── loaders.py            # Data loading with caching
│   └── preprocessors.py      # Data transformations
├── retrieval/
│   ├── kpi_retriever.py      # Structured KPI queries **(to be replaced)**
│   ├── vector_search.py      # FAISS semantic search **(to be replaced)**
│   └── trend_calculator.py   # Pandas-based trend analysis **(experimental tool)**
├── generation/
│   ├── llm_client.py         # AWS Bedrock wrapper
│   └── response_builder.py   # Context assembly + generation
├── mlflow_tracking/
│   ├── experiment_tracker.py # MLflow integration
├── evaluation/
│   ├── metrics.py            # Evaluation metrics
│   ├── gold_dataset.py       # Test case management
│   └── run_evaluation.py     # Automated evaluation
├── api/
│   └── main.py               # FastAPI server **(not functional for now)**
├── main.py                   # CLI orchestrator
└── requirements.txt
```

### MLflow Integration

Comprehensive experiment tracking:

```python
from mlflow_tracking.experiment_tracker import mlflow_tracker

mlflow_tracker.log_query(
    query="What was revenue?",
    response="Revenue in 2023 was...",
    query_type="kpi",
    context=context,
    llm_response=llm_response
)
```

## 📊 MLflow Tracking

### What's Tracked

**Parameters:**
- Query type
- Model ID
- Query/response lengths
- Classification confidence

**Metrics:**
- Token counts (input/output/total)
- Latency (seconds)
- Cost (USD)
- Context retrieval counts
- Evaluation scores

**Artifacts:**
- Query text
- Response text
- Context JSON
- Prompt versions

### View Results

```bash
# Start MLflow UI
mlflow ui

# Navigate to http://localhost:5000
```

### Compare Runs

```python
from mlflow_tracking.experiment_tracker import mlflow_tracker

comparison = mlflow_tracker.compare_runs(
    run_ids=["run1", "run2"],
    metrics=["pass_rate", "avg_latency_seconds"]
)
```

## 🎯 Evaluation System

### Gold Dataset

Create test cases:

```python
from evaluation.gold_dataset import gold_dataset, GoldTestCase

test_case = GoldTestCase(
    query="What was NVDA's revenue in 2023?",
    expected_type="kpi",
    ticker="NVDA",
    expected_facts=["2023", "revenue", "$26.9B"],
    metrics_involved=["Revenue"]
)

gold_dataset.add_test_case(test_case)
gold_dataset.save()
```

### Run Evaluation

```python
from evaluation.run_evaluation import EvaluationRunner

runner = EvaluationRunner()

# Full evaluation
results = runner.run_full_evaluation()
```

### Metrics Calculated

- **Factual Accuracy**: Presence of expected facts
- **Completeness**: Coverage of ground truth
- **Relevance**: Query term alignment
- **Conciseness**: Response length appropriateness
- **Overall Score**: Weighted average

### 🧪 Testing

```bash
# Test MLFlow integration
pytest test_mlflow/basic.py
pytest test_mlflow/single_query.py
pytest test_mlflow/eval.py
pytest test_mlflow/compare.py
```

### Customize Prompts

```python
# config/prompts.py
class PromptTemplates:
    @staticmethod
    def get_custom_prompt(context):
        return f"Custom prompt with {context}"
```

