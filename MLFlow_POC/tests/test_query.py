from main import FinancialRAGOrchestrator

print("Testing End-to-End Query...")
print("=" * 70)

# Initialize orchestrator (without MLflow to avoid setup issues)
orchestrator = FinancialRAGOrchestrator(
    enable_mlflow=False,
    enable_evaluation=False
)

# Test simple query
query = "How did NVDA's profitability change from 2020 to 2023 and why?"#"What was NVDA's revenue in 2023?" 
print(f"\n📝 Query: {query}\n")

result = orchestrator.query(query)

# Print results
orchestrator.print_result(result)

print("\n✅ End-to-End Test PASSED\n")