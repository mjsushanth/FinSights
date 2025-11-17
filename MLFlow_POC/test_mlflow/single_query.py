from main import FinancialRAGOrchestrator
import time
import mlflow

print("Testing MLflow with Single Query...")
print("=" * 70)

# Wait for rate limits
print("\n⏳ Waiting 10 seconds...")
time.sleep(10)

# Initialize with MLflow ENABLED
orchestrator = FinancialRAGOrchestrator(
    enable_mlflow=True,  # IMPORTANT: Enable MLflow
    enable_evaluation=False
)

# Run single query
query = "What was NVDA's revenue in 2023?"
print(f"\n📊 Query: {query}\n")

result = orchestrator.query(query)

# Check MLflow logging
print("\n" + "=" * 70)
print("📊 MLFLOW LOGGING CHECK")
print("=" * 70)

if result.mlflow_run_id:
    print(f"\n✅ MLflow Run ID: {result.mlflow_run_id}")
    
    # Retrieve the run    
    run = mlflow.get_run(result.mlflow_run_id)
    
    print(f"\n📋 Logged Parameters:")
    for key, value in run.data.params.items():
        print(f"   • {key}: {value}")
    
    print(f"\n📊 Logged Metrics:")
    for key, value in run.data.metrics.items():
        print(f"   • {key}: {value}")
    
    print(f"\n🏷️  Logged Tags:")
    for key, value in run.data.tags.items():
        print(f"   • {key}: {value}")
    
    print(f"\n📁 Logged Artifacts:")
    artifacts = mlflow.artifacts.list_artifacts(result.mlflow_run_id)
    for artifact in artifacts:
        print(f"   • {artifact.path}")
    
    print("\n✅ MLflow Integration Test PASSED")
else:
    print("\n❌ No MLflow Run ID - logging failed!")
