"""
Main orchestrator for the simplified RAG workflow.
No classification - all queries get unified context.
"""
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from config.settings import aws_config
from data.loaders import data_loader
from generation.llm_client import create_llm_client, LLMResponse
from generation.response_builder import ResponseBuilder, QueryContext
from retrieval.entity_extractor import entity_extractor, ExtractedEntities
from mlflow_tracking.experiment_tracker import mlflow_tracker
from evaluation.metrics import metrics_evaluator, EvaluationResult


@dataclass
class QueryResult:
    """Complete query result with all metadata"""
    query: str
    response: str
    entities: ExtractedEntities
    context_used: QueryContext
    llm_response: LLMResponse
    total_latency: float
    mlflow_run_id: Optional[str] = None
    evaluation: Optional[EvaluationResult] = None


class FinancialRAGOrchestrator:
    """
    Main orchestrator implementing the simplified workflow:
    1. Entity Extraction (ticker, metrics, years)
    2. Unified Retrieval (KPI + Vector + Trend for all queries)
    3. Single LLM Call with Complete Context
    """
    
    def __init__(
        self,
        enable_mlflow: bool = True,
        enable_evaluation: bool = False
    ):
        """
        Initialize orchestrator.
        
        Args:
            enable_mlflow: Whether to log to MLflow
            enable_evaluation: Whether to evaluate responses
        """
        print("\n" + "="*70)
        print("🚀 Initializing Financial RAG System")
        print("="*70)
        
        self.enable_mlflow = enable_mlflow
        self.enable_evaluation = enable_evaluation
        
        # Initialize components
        print("\n1️⃣ Loading data...")
        self.data_context = data_loader.load_all()
        
        print("\n2️⃣ Initializing LLM client...")
        self.llm_client = create_llm_client()
        
        # Test connection
        if not self.llm_client.test_connection():
            raise RuntimeError("Failed to connect to Bedrock")
        
        print("\n3️⃣ Setting up response builder...")
        self.response_builder = ResponseBuilder(self.llm_client)
        
        if self.enable_mlflow:
            print("\n4️⃣ Initializing MLflow tracking...")
            # mlflow_tracker is already initialized as global instance
        
        print("\n" + "="*70)
        print("✅ System Ready!")
        print("="*70 + "\n")
    
    def query(
        self,
        question: str,
        ticker: str = None,
        metrics: Optional[list] = None,
        ground_truth: Optional[str] = None,
        expected_facts: Optional[list] = None
    ) -> QueryResult:
        """
        Process a user query through the complete workflow.
        
        Args:
            question: User's financial question
            ticker: Optional ticker override
            metrics: Optional specific metrics to retrieve
            ground_truth: Optional expected answer (for evaluation)
            expected_facts: Optional facts to check (for evaluation)
            
        Returns:
            QueryResult with response and metadata
        """
        # print("\n" + "="*70)
        # print(f"📊 Query: {question}")
        # print("="*70)
        
        total_start = time.time()
        
        # Extract entities from query
        print("\n1️⃣ Extracting entities...")
        entities = entity_extractor.extract(question)
        if ticker:
            entities.ticker = ticker
        if metrics:
            entities.metrics = metrics
        
        print(f"   Ticker: {entities.ticker}")
        print(f"   Metrics: {entities.metrics if entities.metrics else 'Auto-detected'}")
        print(f"   Years: {entities.years if entities.years else 'All available'}")
        
        # Retrieve unified context and generate response
        print(f"\n2️⃣ Retrieving unified context (KPI + Narrative)...")
        
        response_text, context, llm_response = self.response_builder.generate_response(
            query=question,
            ticker=entities.ticker,
            metrics=entities.metrics
        )
        
        total_end = time.time()
        total_latency = total_end - total_start
        
        print(f"\n⏱️  Total Workflow Latency: {total_latency:.2f}s")
        
        # Create result object
        result = QueryResult(
            query=question,
            response=response_text,
            entities=entities,
            context_used=context,
            llm_response=llm_response,
            total_latency=total_latency
        )
        
        # Evaluate (if enabled and ground truth provided)
        if self.enable_evaluation and (ground_truth or expected_facts):
            print("\n3️⃣ Evaluating response...")
            result.evaluation = metrics_evaluator.evaluate_response(
                query=question,
                response=response_text,
                ground_truth=ground_truth,
                expected_facts=expected_facts,
                context_used=context.kpi_data + context.narrative_data
            )
            
            if result.evaluation.overall_score:
                print(f"   Overall Score: {result.evaluation.overall_score:.2f}")
                print(f"   Passed: {'✅' if result.evaluation.passed else '❌'}")
        
        # Log to MLflow (if enabled)
        if self.enable_mlflow:
            print("\n4️⃣ Logging to MLflow...")
            
            eval_metrics = None
            if result.evaluation:
                eval_metrics = {
                    "overall_score": result.evaluation.overall_score,
                    "passed": 1.0 if result.evaluation.passed else 0.0
                }
            
            result.mlflow_run_id = mlflow_tracker.log_query(
                query=question,
                response=response_text,
                query_type="unified",  # No classification
                context=context,
                llm_response=llm_response,
                classification_confidence=1.0,  # N/A
                evaluation_metrics=eval_metrics,
                tags={
                    "ticker": entities.ticker,
                    "metrics_count": len(entities.metrics) if entities.metrics else 0
                }
            )
            
            print(f"   Run ID: {result.mlflow_run_id}")
        
        print("\n" + "="*70)
        print("✅ Query Complete!")
        print("="*70 + "\n")
        
        return result
    
    def print_result(self, result: QueryResult):
        """
        Pretty print query result.
        
        Args:
            result: QueryResult to print
        """
        print("\n" + "="*70)
        print("📋 QUERY RESULT")
        print("="*70)
        
        print(f"\n❓ Question: {result.query}")
        
        print(f"\n🔍 Extracted Entities:")
        print(f"   • Ticker: {result.entities.ticker}")
        print(f"   • Metrics: {result.entities.metrics if result.entities.metrics else 'Auto-detected'}")
        print(f"   • Years: {result.entities.years if result.entities.years else 'All'}")
        
        print(f"\n💬 Response:")
        print("-" * 70)
        print(result.response)
        print("-" * 70)
        
        print(f"\n📊 Metadata:")
        print(f"   • Tokens: {result.llm_response.input_tokens} in / "
              f"{result.llm_response.output_tokens} out")
        print(f"   • Latency: {result.total_latency:.2f}s")
        print(f"   • Cost: ${result.llm_response.cost_usd}")
        
        if result.context_used.has_content():
            print(f"\n📚 Context Used:")
            print(f"   • KPIs: {len(result.context_used.kpi_data)}")
            print(f"   • Trends: {len(result.context_used.trend_data)}")
            print(f"   • Narratives: {len(result.context_used.narrative_data)}")
        
        if result.evaluation:
            print(f"\n🎯 Evaluation:")
            print(f"   • Overall: {result.evaluation.overall_score:.2f}")
            print(f"   • Passed: {'✅ Yes' if result.evaluation.passed else '❌ No'}")
            
            if result.evaluation.failure_reason:
                print(f"   • Reason: {result.evaluation.failure_reason}")
        
        if result.mlflow_run_id:
            print(f"\n🔗 MLflow Run: {result.mlflow_run_id}")
        
        print("\n" + "="*70 + "\n")


def main():
    """Main entry point for CLI usage"""
    
    # Initialize orchestrator
    orchestrator = FinancialRAGOrchestrator(
        enable_mlflow=True,
        enable_evaluation=False
    )
    
    # Example queries
    test_queries = [
        "What was NVDA's revenue in 2023?",
        "Why did revenue grow for NVDA?",
        "What were the main drivers of revenue growth for NVDA from 2020 to 2023?"
    ]
    
    print("\n" + "="*70)
    print("🧪 Running Test Queries")
    print("="*70)
    
    for query in test_queries:
        result = orchestrator.query(query)
        orchestrator.print_result(result)
        time.sleep(1)  # Brief pause between queries


if __name__ == "__main__":
    main()