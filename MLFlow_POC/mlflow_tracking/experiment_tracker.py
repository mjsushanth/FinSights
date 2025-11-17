"""
MLflow integration for experiment tracking and model evaluation.
"""
import mlflow
import mlflow.anthropic
from mlflow.models import infer_signature
from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from config.settings import mlflow_config
from generation.llm_client import LLMResponse
from generation.response_builder import QueryContext


class MLflowTracker:
    """
    Centralized MLflow tracking for the RAG system.
    Tracks prompts, responses, retrieval quality, and costs.
    """
    
    def __init__(
        self,
        experiment_name: str = None,
        tracking_uri: str = None
    ):
        """
        Initialize MLflow tracker.
        
        Args:
            experiment_name: Name of MLflow experiment
            tracking_uri: MLflow tracking URI
        """
        self.experiment_name = experiment_name or mlflow_config.EXPERIMENT_NAME
        self.tracking_uri = tracking_uri or mlflow_config.TRACKING_URI
        
        # Set tracking URI
        mlflow.set_tracking_uri(self.tracking_uri)
        
        # Create or get experiment
        try:
            self.experiment_id = mlflow.create_experiment(
                self.experiment_name,
                artifact_location=mlflow_config.ARTIFACT_LOCATION
            )
        except:
            self.experiment = mlflow.get_experiment_by_name(self.experiment_name)
            self.experiment_id = self.experiment.experiment_id
        
        mlflow.set_experiment(self.experiment_name)
        
        print(f"✅ MLflow initialized: {self.experiment_name}")
        print(f"   Tracking URI: {self.tracking_uri}")
    
    def log_query(
        self,
        query: str,
        response: str,
        query_type: str,
        context: QueryContext,
        llm_response: LLMResponse,
        classification_confidence: float = None,
        evaluation_metrics: Dict[str, float] = None,
        tags: Dict[str, str] = None
    ) -> str:
        """
        Log a complete query-response interaction to MLflow.
        
        Args:
            query: User's question
            response: Generated response
            query_type: Classification result
            context: Retrieved context
            llm_response: LLM response metadata
            classification_confidence: Confidence in classification
            evaluation_metrics: Optional evaluation scores
            tags: Optional tags for the run
            
        Returns:
            Run ID
        """
        with mlflow.start_run() as run:
            # Log parameters
            mlflow.log_param("query_type", query_type)
            mlflow.log_param("model_id", llm_response.model_id)
            mlflow.log_param("query_length", len(query))
            mlflow.log_param("response_length", len(response))
            
            if classification_confidence:
                mlflow.log_param("classification_confidence", classification_confidence)
            
            # Log metrics
            mlflow.log_metric("input_tokens", llm_response.input_tokens)
            mlflow.log_metric("output_tokens", llm_response.output_tokens)
            mlflow.log_metric("total_tokens", llm_response.total_tokens)
            mlflow.log_metric("latency_seconds", llm_response.latency_seconds)
            mlflow.log_metric("cost_usd", llm_response.cost_usd)
            
            # Context retrieval metrics
            mlflow.log_metric("kpi_context_count", len(context.kpi_data))
            mlflow.log_metric("trend_context_count", len(context.trend_data))
            mlflow.log_metric("narrative_context_count", len(context.narrative_data))
            
            # Evaluation metrics if provided
            if evaluation_metrics:
                for metric_name, value in evaluation_metrics.items():
                    mlflow.log_metric(f"eval_{metric_name}", value)
            
            # Log artifacts
            self._log_text_artifact(query, "query.txt")
            self._log_text_artifact(response, "response.txt")
            self._log_json_artifact(context.to_dict(), "context.json")
            
            # Log tags
            default_tags = {
                "framework": "custom_rag",
                "timestamp": datetime.now().isoformat()
            }
            if tags:
                default_tags.update(tags)
            
            mlflow.set_tags(default_tags)
            
            return run.info.run_id
    
    def log_batch_evaluation(
        self,
        evaluation_results: List[Dict[str, Any]],
        run_name: str = None
    ) -> str:
        """
        Log results from batch evaluation run.
        
        Args:
            evaluation_results: List of evaluation result dicts
            run_name: Optional name for the run
            
        Returns:
            Run ID
        """
        with mlflow.start_run(run_name=run_name or f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}") as run:
            # Aggregate metrics
            total_queries = len(evaluation_results)
            
            # Calculate averages
            avg_metrics = self._calculate_average_metrics(evaluation_results)
            
            # Log aggregated metrics
            mlflow.log_metric("total_queries", total_queries)
            for metric_name, value in avg_metrics.items():
                mlflow.log_metric(f"avg_{metric_name}", value)
            
            # Log detailed results as artifact
            self._log_json_artifact(evaluation_results, "evaluation_results.json")
            
            # Tag as evaluation run
            mlflow.set_tag("run_type", "batch_evaluation")
            
            return run.info.run_id
    
    def log_prompt_version(
        self,
        prompt_name: str,
        prompt_template: str,
        version: str,
        metadata: Dict[str, Any] = None
    ):
        """
        Log prompt template version for tracking.
        
        Args:
            prompt_name: Name of the prompt
            prompt_template: Actual prompt text
            version: Version identifier
            metadata: Optional metadata
        """
        with mlflow.start_run(run_name=f"prompt_{prompt_name}_v{version}") as run:
            mlflow.log_param("prompt_name", prompt_name)
            mlflow.log_param("version", version)
            
            if metadata:
                for key, value in metadata.items():
                    mlflow.log_param(f"meta_{key}", value)
            
            self._log_text_artifact(prompt_template, f"prompt_{prompt_name}.txt")
            
            mlflow.set_tag("artifact_type", "prompt_template")
    
    def compare_runs(
        self,
        run_ids: List[str],
        metrics: List[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compare multiple MLflow runs.
        
        Args:
            run_ids: List of run IDs to compare
            metrics: Optional list of specific metrics to compare
            
        Returns:
            Dictionary with comparison data
        """
        comparison = {}
        
        for run_id in run_ids:
            run = mlflow.get_run(run_id)
            
            run_data = {
                "params": run.data.params,
                "metrics": run.data.metrics,
                "tags": run.data.tags
            }
            
            if metrics:
                run_data["metrics"] = {
                    k: v for k, v in run_data["metrics"].items()
                    if k in metrics
                }
            
            comparison[run_id] = run_data
        
        return comparison
    
    def _log_text_artifact(self, content: str, filename: str):
        """Log text content as artifact"""
        with open(filename, "w") as f:
            f.write(content)
        mlflow.log_artifact(filename)
        
        # Clean up
        import os
        os.remove(filename)
    
    def _log_json_artifact(self, data: Dict[str, Any], filename: str):
        """Log JSON data as artifact"""
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        mlflow.log_artifact(filename)
        
        # Clean up
        import os
        os.remove(filename)
    
    def _calculate_average_metrics(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculate average metrics from evaluation results"""
        metrics_to_average = [
            "latency_seconds",
            "input_tokens",
            "output_tokens",
            "cost_usd"
        ]
        
        averages = {}
        
        for metric in metrics_to_average:
            values = [r.get(metric, 0) for r in results if metric in r]
            if values:
                averages[metric] = sum(values) / len(values)
        
        return averages


# Global tracker instance
mlflow_tracker = MLflowTracker()