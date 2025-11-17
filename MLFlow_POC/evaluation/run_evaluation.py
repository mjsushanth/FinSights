"""
Automated evaluation runner using gold dataset.
"""
import time
from typing import List, Dict, Any
from datetime import datetime

from main import FinancialRAGOrchestrator
from evaluation.gold_dataset import gold_dataset, GoldTestCase
from evaluation.metrics import metrics_evaluator
from mlflow_tracking.experiment_tracker import mlflow_tracker


class EvaluationRunner:
    """
    Run automated evaluations against gold dataset.
    """
    
    def __init__(self):
        """Initialize evaluation runner"""
        self.orchestrator = FinancialRAGOrchestrator(
            enable_mlflow=True,
            enable_evaluation=True
        )
        
        # Load or create gold dataset
        if not gold_dataset.test_cases:
            print("📝 Creating sample gold dataset...")
            gold_dataset.create_sample_dataset()
        
        print(f"✅ Loaded {len(gold_dataset.test_cases)} test cases")
    
    def run_full_evaluation(
        self,
        run_name: str = None
    ) -> Dict[str, Any]:
        """
        Run evaluation on all test cases in gold dataset.
        
        Args:
            run_name: Optional name for the evaluation run
            
        Returns:
            Dictionary with evaluation results and metrics
        """
        if run_name is None:
            run_name = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print("\n" + "="*70)
        print(f"🎯 Running Full Evaluation: {run_name}")
        print("="*70)
        
        results = []
        start_time = time.time()
        
        for i, test_case in enumerate(gold_dataset.test_cases, 1):
            print(f"\n[{i}/{len(gold_dataset.test_cases)}] {test_case.query}")
            
            try:
                # Run query
                result = self.orchestrator.query(
                    question=test_case.query,
                    ticker=test_case.ticker,
                    metrics=test_case.metrics_involved,
                    ground_truth=test_case.ground_truth,
                    expected_facts=test_case.expected_facts
                )
                
                # Package result
                eval_result = {
                    "test_case": test_case.to_dict(),
                    "query": result.query,
                    "response": result.response,
                    "extracted_ticker": result.entities.ticker,
                    "extracted_metrics": result.entities.metrics,
                    "latency_seconds": result.total_latency,
                    "input_tokens": result.llm_response.input_tokens,
                    "output_tokens": result.llm_response.output_tokens,
                    "cost_usd": result.llm_response.cost_usd,
                    "mlflow_run_id": result.mlflow_run_id,
                    "passed": False  # Default value
                }
                
                # Add evaluation scores
                if result.evaluation:
                    eval_result["factual_accuracy"] = result.evaluation.factual_accuracy
                    eval_result["completeness"] = result.evaluation.completeness
                    eval_result["relevance"] = result.evaluation.relevance
                    eval_result["conciseness"] = result.evaluation.conciseness
                    eval_result["overall_score"] = result.evaluation.overall_score
                    eval_result["passed"] = result.evaluation.passed
                    eval_result["failure_reason"] = result.evaluation.failure_reason
                
                results.append(eval_result)
                
                # Print quick summary
                status = "✅" if eval_result.get("passed", False) else "❌"
                score = eval_result.get("overall_score")
                if score is not None:
                    print(f"   {status} Score: {score:.2f}")
                else:
                    print(f"   {status} No score available")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                import traceback
                traceback.print_exc()
                results.append({
                    "test_case": test_case.to_dict(),
                    "query": test_case.query,
                    "error": str(e),
                    "passed": False
                })
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Calculate aggregate metrics
        aggregate = self._calculate_aggregates(results)
        aggregate["total_time_seconds"] = total_time
        aggregate["run_name"] = run_name
        
        # Log to MLflow
        print("\n📊 Logging evaluation to MLflow...")
        try:
            mlflow_run_id = mlflow_tracker.log_batch_evaluation(
                evaluation_results=results,
                run_name=run_name
            )
            aggregate["mlflow_run_id"] = mlflow_run_id
        except Exception as e:
            print(f"⚠️ MLflow logging failed: {e}")
            aggregate["mlflow_run_id"] = None
        
        # Print summary
        self._print_summary(aggregate, results)
        
        return {
            "aggregate_metrics": aggregate,
            "detailed_results": results
        }
    
    def run_by_ticker(
        self,
        ticker: str
    ) -> Dict[str, Any]:
        """
        Run evaluation for specific ticker only.
        
        Args:
            ticker: Ticker to evaluate
            
        Returns:
            Evaluation results
        """
        filtered_cases = gold_dataset.get_by_ticker(ticker)
        
        if not filtered_cases:
            print(f"⚠️ No test cases found for ticker: {ticker}")
            return {}
        
        # Temporarily swap dataset
        original_cases = gold_dataset.test_cases
        gold_dataset.test_cases = filtered_cases
        
        result = self.run_full_evaluation(
            run_name=f"eval_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        # Restore original dataset
        gold_dataset.test_cases = original_cases
        
        return result
    
    def compare_configurations(
        self,
        configs: List[Dict[str, Any]],
        comparison_name: str = None
    ) -> Dict[str, Any]:
        """
        Compare different system configurations.
        
        Args:
            configs: List of configuration dicts
            comparison_name: Name for the comparison
            
        Returns:
            Comparison results
        """
        if comparison_name is None:
            comparison_name = f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print("\n" + "="*70)
        print(f"⚖️  Running Configuration Comparison: {comparison_name}")
        print("="*70)
        
        all_results = {}
        
        for i, config in enumerate(configs, 1):
            config_name = config.get("name", f"config_{i}")
            print(f"\n▶️  Testing configuration: {config_name}")
            
            # Run evaluation
            result = self.run_full_evaluation(
                run_name=f"{comparison_name}_{config_name}"
            )
            
            all_results[config_name] = result["aggregate_metrics"]
        
        # Print comparison
        self._print_comparison(all_results)
        
        return all_results
    
    def _calculate_aggregates(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculate aggregate statistics"""
        successful = [r for r in results if not r.get("error")]
        
        if not successful:
            return {
                "error": "No successful results",
                "total_queries": len(results),
                "successful_queries": 0,
                "failed_queries": len(results),
                "success_rate": 0.0
            }
        
        aggregates = {
            "total_queries": len(results),
            "successful_queries": len(successful),
            "failed_queries": len(results) - len(successful),
            "success_rate": len(successful) / len(results),
        }
        
        # Quality metrics
        passed = sum(1 for r in successful if r.get("passed", False))
        aggregates["pass_rate"] = passed / len(successful) if successful else 0.0
        
        # Average scores
        score_fields = ["factual_accuracy", "completeness", "relevance", "conciseness", "overall_score"]
        for field in score_fields:
            scores = [r.get(field) for r in successful if r.get(field) is not None]
            if scores:
                aggregates[f"avg_{field}"] = sum(scores) / len(scores)
            else:
                aggregates[f"avg_{field}"] = 0.0
        
        # Performance metrics
        perf_fields = ["latency_seconds", "input_tokens", "output_tokens", "cost_usd"]
        for field in perf_fields:
            values = [r.get(field) for r in successful if r.get(field) is not None]
            if values:
                aggregates[f"avg_{field}"] = sum(values) / len(values)
                aggregates[f"total_{field}"] = sum(values)
            else:
                aggregates[f"avg_{field}"] = 0.0
                aggregates[f"total_{field}"] = 0.0
        
        return aggregates
    
    def _print_summary(
        self,
        aggregates: Dict[str, float],
        results: List[Dict[str, Any]]
    ):
        """Print evaluation summary"""
        print("\n" + "="*70)
        print("📊 EVALUATION SUMMARY")
        print("="*70)
        
        print(f"\n📈 Overall Metrics:")
        print(f"   • Total Queries: {aggregates.get('total_queries', 0)}")
        print(f"   • Successful: {aggregates.get('successful_queries', 0)}")
        print(f"   • Failed: {aggregates.get('failed_queries', 0)}")
        print(f"   • Success Rate: {aggregates.get('success_rate', 0)*100:.1f}%")
        print(f"   • Pass Rate: {aggregates.get('pass_rate', 0)*100:.1f}%")
        
        if aggregates.get("avg_overall_score", 0) > 0:
            print(f"\n🎯 Quality Scores:")
            print(f"   • Overall: {aggregates.get('avg_overall_score', 0):.3f}")
            print(f"   • Factual Accuracy: {aggregates.get('avg_factual_accuracy', 0):.3f}")
            print(f"   • Completeness: {aggregates.get('avg_completeness', 0):.3f}")
            print(f"   • Relevance: {aggregates.get('avg_relevance', 0):.3f}")
            print(f"   • Conciseness: {aggregates.get('avg_conciseness', 0):.3f}")
        
        if aggregates.get("avg_latency_seconds", 0) > 0:
            print(f"\n⚡ Performance:")
            print(f"   • Avg Latency: {aggregates.get('avg_latency_seconds', 0):.2f}s")
            print(f"   • Avg Tokens: {aggregates.get('avg_input_tokens', 0):.0f} in / "
                  f"{aggregates.get('avg_output_tokens', 0):.0f} out")
            print(f"   • Total Cost: ${aggregates.get('total_cost_usd', 0):.4f}")
        
        # Show breakdown of passed/failed
        print(f"\n📋 Results Breakdown:")
        passed_count = sum(1 for r in results if r.get("passed", False))
        failed_count = sum(1 for r in results if not r.get("passed", False) and not r.get("error"))
        error_count = sum(1 for r in results if r.get("error"))
        
        print(f"   • Passed: {passed_count}")
        print(f"   • Failed Quality Check: {failed_count}")
        print(f"   • Errors: {error_count}")
        
        print("\n" + "="*70 + "\n")
    
    def _print_comparison(self, all_results: Dict[str, Dict[str, float]]):
        """Print configuration comparison"""
        print("\n" + "="*70)
        print("⚖️  CONFIGURATION COMPARISON")
        print("="*70)
        
        # Compare key metrics
        metrics_to_compare = [
            "pass_rate",
            "avg_overall_score",
            "avg_latency_seconds",
            "avg_cost_usd"
        ]
        
        for metric in metrics_to_compare:
            print(f"\n{metric}:")
            for config_name, results in all_results.items():
                value = results.get(metric, 0)
                if value is not None:
                    print(f"   • {config_name}: {value:.3f}")
                else:
                    print(f"   • {config_name}: N/A")
        
        print("\n" + "="*70 + "\n")


def main():
    """Main entry point for evaluation"""
    try:
        runner = EvaluationRunner()
        
        # Run full evaluation
        results = runner.run_full_evaluation()
        
        print("\n✅ Evaluation complete!")
        if results['aggregate_metrics'].get('mlflow_run_id'):
            print(f"📊 MLflow Run ID: {results['aggregate_metrics']['mlflow_run_id']}")
        
        # Print final stats
        print(f"\n📈 Final Statistics:")
        print(f"   Total Queries: {results['aggregate_metrics']['total_queries']}")
        print(f"   Pass Rate: {results['aggregate_metrics'].get('pass_rate', 0)*100:.1f}%")
        print(f"   Avg Score: {results['aggregate_metrics'].get('avg_overall_score', 0):.2f}")
        
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    main()