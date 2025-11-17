import mlflow
from mlflow_tracking.experiment_tracker import mlflow_tracker

print("Testing MLflow Integration...")
print("=" * 70)

# Check experiment setup
print("\n1. Testing Experiment Setup:")
print("-" * 70)
print(f"   Experiment: {mlflow_tracker.experiment_name}")
print(f"   Tracking URI: {mlflow_tracker.tracking_uri}")
print(f"   Experiment ID: {mlflow_tracker.experiment_id}")

# Log a simple run
print("\n2. Testing Simple Run Logging:")
print("-" * 70)
with mlflow.start_run(run_name="basic_test") as run:
    mlflow.log_param("test_param", "test_value")
    mlflow.log_metric("test_metric", 0.95)
    mlflow.log_metric("test_latency", 5.2)
    mlflow.set_tag("test_tag", "basic_test")
    
    print(f"   ✅ Run ID: {run.info.run_id}")
    print(f"   ✅ Logged params, metrics, and tags")

# Retrieve the run
print("\n3. Testing Run Retrieval:")
print("-" * 70)
retrieved_run = mlflow.get_run(run.info.run_id)
print(f"   ✅ Retrieved run: {retrieved_run.info.run_id}")
print(f"   ✅ Params: {retrieved_run.data.params}")
print(f"   ✅ Metrics: {retrieved_run.data.metrics}")
