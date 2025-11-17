from evaluation.run_evaluation import EvaluationRunner
from evaluation.gold_dataset import gold_dataset
import time

print("Testing MLflow Batch Evaluation...")
print("=" * 70)

# Using only 2 test cases to avoid rate limits
print("\n📝 Preparing test cases...")
if not gold_dataset.test_cases:
    gold_dataset.create_sample_dataset()

# Limit to 2 queries
original_cases = gold_dataset.test_cases.copy()
gold_dataset.test_cases = gold_dataset.test_cases[:2]

print(f"   Testing with {len(gold_dataset.test_cases)} queries")
print("   (Limited to avoid rate limits)")

# Wait before starting
print("\n⏳ Waiting 10 seconds for rate limit reset...")
time.sleep(10)

# Run evaluation
runner = EvaluationRunner()

results = runner.run_full_evaluation(run_name="mlflow_test_batch")

# Check results
print("\n" + "=" * 70)
print("📊 MLFLOW BATCH LOGGING CHECK")
print("=" * 70)

mlflow_run_id = results['aggregate_metrics'].get('mlflow_run_id')

if mlflow_run_id:
    print(f"\n✅ MLflow Batch Run ID: {mlflow_run_id}")
    
    import mlflow
    run = mlflow.get_run(mlflow_run_id)
    
    print(f"\n📊 Aggregate Metrics Logged:")
    for key, value in run.data.metrics.items():
        print(f"   • {key}: {value:.3f}")
    
    print(f"\n📁 Artifacts:")
    artifacts = mlflow.artifacts.list_artifacts(mlflow_run_id)
    for artifact in artifacts:
        print(f"   • {artifact.path}")
    
    print("\n✅ Batch Evaluation MLflow Test PASSED")
else:
    print("\n❌ No MLflow Run ID - batch logging failed!")

# Restore original test cases
gold_dataset.test_cases = original_cases
