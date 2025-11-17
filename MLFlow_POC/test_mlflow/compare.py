from main import FinancialRAGOrchestrator
from mlflow_tracking.experiment_tracker import mlflow_tracker
import mlflow
import time

print("Testing MLflow Run Comparison...")
print("=" * 70)

# Wait for rate limits
print("\n⏳ Waiting 15 seconds...")
time.sleep(15)

orchestrator = FinancialRAGOrchestrator(
    enable_mlflow=True,
    enable_evaluation=False
)

# Run 2 different queries
queries = [
    "Show me NVDA's operating cash flow in 2023.",
    "Show me year-over-year growth in operating income for NVDA."
]

run_ids = []

for i, query in enumerate(queries, 1):
    print(f"\n[{i}/2] Running query: {query}")
    
    result = orchestrator.query(query)
    run_ids.append(result.mlflow_run_id)
    
    print(f"   ✅ MLflow Run ID: {result.mlflow_run_id}")
    
    # Wait between queries
    if i < len(queries):
        print("   ⏳ Waiting 10 seconds...")
        time.sleep(10)

# Compare runs
print("\n" + "=" * 70)
print("📊 COMPARING RUNS")
print("=" * 70)

comparison = mlflow_tracker.compare_runs(
    run_ids=run_ids,
    metrics=["input_tokens", "latency_seconds", "cost_usd"]
)

for run_id, data in comparison.items():
    print(f"\n🔹 Run: {run_id[:8]}...")
    print(f"   Query Type: {data['params'].get('query_type', 'N/A')}")
    print(f"   Metrics:")
    for metric, value in data['metrics'].items():
        print(f"      • {metric}: {value:.4f}")

