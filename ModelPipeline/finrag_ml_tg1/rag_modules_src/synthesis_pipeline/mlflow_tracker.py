# ModelPipeline/finrag_ml_tg1/rag_modules_src/synthesis_pipeline/mlflow_tracker.py

"""
MLflow Integration for FinRAG Pipeline.

Provides centralized experiment tracking for:
- Query latency and performance metrics
- Model configurations and costs
- Retrieved document metadata (KPI matches, RAG chunks)
- Artifacts (prompts, contexts, responses)

Usage:
    from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.mlflow_tracker import FinRAGTracker
    
    tracker = FinRAGTracker(experiment_name="FinRAG-Production")
    
    with tracker.start_run(query="What is NVIDIA's revenue?", model_key="development_CH45"):
        # ... pipeline execution ...
        tracker.log_retrieval_metrics(kpi_count=12, rag_count=8)
        tracker.log_llm_metrics(input_tokens=1000, output_tokens=500, cost=0.01)
        tracker.log_artifacts(system_prompt=prompt, context=ctx, response=resp)
"""

import json
import logging
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import mlflow
#from mlflow.tracking import MlflowClient

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class MLflowConfig:
    """MLflow configuration settings."""
    
    # Tracking URI - local file storage by default    
    tracking_uri: str = "mlruns"  # Local directory
    
    # Default experiment name
    default_experiment: str = "FinRAG-Integration"
    
    # Artifact logging settings
    log_prompts: bool = True
    log_context: bool = True
    log_response: bool = True
    
    # Context truncation 
    max_context_artifact_chars: int = 100_000  # ~100KB; to avoid huge files
    
    # Auto-tagging
    auto_tag_environment: bool = True
    environment: str = "development"


# ============================================================================
# DATA CLASSES FOR METRICS
# ============================================================================

@dataclass
class RetrievalMetrics:
    """Metrics from the retrieval phase."""
    kpi_matches_count: int = 0
    rag_chunks_count: int = 0
    tickers_found: List[str] = field(default_factory=list)
    years_found: List[int] = field(default_factory=list)
    sections_retrieved: List[str] = field(default_factory=list)


@dataclass
class LLMMetrics:
    """Metrics from LLM inference."""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_id: str = ""
    temperature: float = 0.0
    max_tokens: int = 0


@dataclass 
class LatencyMetrics:
    """Timing breakdown."""
    total_seconds: float = 0.0
    retrieval_seconds: float = 0.0
    llm_seconds: float = 0.0


# ============================================================================
# MAIN TRACKER CLASS
# ============================================================================

class FinRAGTracker:
    """
    MLflow tracker for FinRAG synthesis pipeline.
        
    """
    
    def __init__(
        self,
        experiment_name: Optional[str] = None,
        config: Optional[MLflowConfig] = None,
        model_root: Optional[Path] = None
    ):
        """
        Initialize MLflow tracker.
        
        Args:
            experiment_name: MLflow experiment name (creates if doesn't exist)
            config: MLflow configuration settings
            model_root: Path to ModelPipeline root (for artifact paths)
        """
        self.config = config or MLflowConfig()
        self.model_root = model_root or self._find_model_root()
        
        # Set tracking URI
        tracking_path = self.model_root / self.config.tracking_uri
        tracking_uri = tracking_path.as_uri()
        mlflow.set_tracking_uri(str(tracking_uri))
        logger.info(f"MLflow tracking URI: {tracking_uri}")
        
        # Set/create experiment
        self.experiment_name = experiment_name or self.config.default_experiment
        self._setup_experiment()
        
        # Run state
        self._active_run = None
        self._run_start_time: Optional[float] = None
        self._current_query: Optional[str] = None
        
        # Accumulated metrics (for logging at end)
        self._retrieval_metrics: Optional[RetrievalMetrics] = None
        self._llm_metrics: Optional[LLMMetrics] = None
        self._latency_metrics: Optional[LatencyMetrics] = None
    
    
    def _find_model_root(self) -> Path:
        """Find ModelPipeline root directory."""
        current = Path.cwd()
        for parent in [current] + list(current.parents):
            if parent.name == "ModelPipeline":
                return parent
        raise RuntimeError("Cannot find 'ModelPipeline' root directory")
    
    
    def _setup_experiment(self):
        """Create or get experiment."""
        experiment = mlflow.get_experiment_by_name(self.experiment_name)
        
        if experiment is None:
            experiment_id = mlflow.create_experiment(
                self.experiment_name,
                tags={
                    "project": "FinRAG",
                    "pipeline": "integration",
                    "created_by": "FinSights Team"
                }
            )
            logger.info(f"Created MLflow experiment: {self.experiment_name} (ID: {experiment_id})")
        else:
            logger.info(f"Using existing experiment: {self.experiment_name} (ID: {experiment.experiment_id})")
        
        mlflow.set_experiment(self.experiment_name)
    
    
    # ========================================================================
    # RUN LIFECYCLE
    # ========================================================================
    
    @contextmanager
    def start_run(
        self,
        query: str,
        model_key: str,
        model_config: Optional[Dict[str, Any]] = None,
        prompt_versions: Optional[Dict[str, str]] = None,
        include_kpi: bool = True,
        include_rag: bool = True,
        run_name: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ):
        """
        Context manager for MLflow run lifecycle.
        
        Args:
            query: User query being processed
            model_key: Key from ml_config.yaml (e.g., "development_CH45")
            model_config: Full model configuration dict
            prompt_versions: {"system": "v1", "query": "v1"}
            include_kpi: Whether KPI retrieval is enabled
            include_rag: Whether RAG retrieval is enabled
            run_name: Optional custom run name
            tags: Additional tags to log
        
        Yields:
            run_id: The MLflow run ID
        
        Example:
            with tracker.start_run(query="...", model_key="dev") as run_id:
                # pipeline code
                pass  # Run ends automatically
        """
        # Generate run name if not provided
        if run_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = f"query_{timestamp}_{model_key}"
        
        self._current_query = query
        self._run_start_time = time.time()
        
        # Reset metric accumulators
        self._retrieval_metrics = RetrievalMetrics()
        self._llm_metrics = LLMMetrics()
        self._latency_metrics = LatencyMetrics()
        
        try:
            # Start MLflow run
            self._active_run = mlflow.start_run(run_name=run_name)
            run_id = self._active_run.info.run_id
            logger.info(f"Started MLflow run: {run_name} (ID: {run_id[:8]}...)")
            
            # Log parameters
            self._log_parameters(
                query=query,
                model_key=model_key,
                model_config=model_config,
                prompt_versions=prompt_versions,
                include_kpi=include_kpi,
                include_rag=include_rag
            )
            
            # Log initial tags
            self._log_tags(tags)
            
            yield run_id
            
            # Success path - log final metrics and status
            self._finalize_run(status="success")
            
        except Exception as e:
            # Error path - log error info
            logger.error(f"Run failed with error: {e}")
            self._finalize_run(status="failed", error=str(e))
            raise
        
        finally:
            if self._active_run:
                mlflow.end_run()
                self._active_run = None
                self._run_start_time = None
    
    
    def _log_parameters(
        self,
        query: str,
        model_key: str,
        model_config: Optional[Dict],
        prompt_versions: Optional[Dict],
        include_kpi: bool,
        include_rag: bool
    ):
        """Log run parameters."""
        # Core parameters
        params = {
            "query_length": len(query),
            "query_preview": query[:100] + "..." if len(query) > 100 else query,
            "model_key": model_key,
            "include_kpi": include_kpi,
            "include_rag": include_rag,
        }
        
        # Model config parameters
        if model_config:
            params.update({
                "model_id": model_config.get("model_id", "unknown"),
                "temperature": model_config.get("temperature", 0.0),
                "max_tokens": model_config.get("max_tokens", 0),
                "cost_per_1k_input": model_config.get("cost_per_1k_input", 0),
                "cost_per_1k_output": model_config.get("cost_per_1k_output", 0),
            })
        
        # Prompt versions
        if prompt_versions:
            params["system_prompt_version"] = prompt_versions.get("system", "v1")
            params["query_template_version"] = prompt_versions.get("query", "v1")
        
        mlflow.log_params(params)
        logger.debug(f"Logged {len(params)} parameters")
    
    
    def _log_tags(self, additional_tags: Optional[Dict[str, str]] = None):
        """Log run tags."""
        tags = {}
        
        # Auto-tag environment
        if self.config.auto_tag_environment:
            tags["environment"] = self.config.environment
        
        # Add timestamp tag
        tags["run_date"] = datetime.now().strftime("%Y-%m-%d")
        
        # Add additional tags
        if additional_tags:
            tags.update(additional_tags)
        
        mlflow.set_tags(tags)
    
    
    def _finalize_run(self, status: str, error: Optional[str] = None):
        """Finalize run with final metrics and status."""
        # Calculate total latency
        if self._run_start_time:
            total_time = time.time() - self._run_start_time
            if self._latency_metrics:
                self._latency_metrics.total_seconds = total_time
        
        # Log accumulated metrics
        self._log_final_metrics()
        
        # Log status
        mlflow.set_tag("status", status)
        
        if error:
            mlflow.set_tag("error_message", error[:250])  # Truncate long errors
        
        logger.info(f"Finalized run with status: {status}")
    
    
    def _log_final_metrics(self):
        """Log all accumulated metrics."""
        metrics = {}
        
        # Latency metrics
        if self._latency_metrics:
            metrics["latency_total_seconds"] = self._latency_metrics.total_seconds
            if self._latency_metrics.retrieval_seconds > 0:
                metrics["latency_retrieval_seconds"] = self._latency_metrics.retrieval_seconds
            if self._latency_metrics.llm_seconds > 0:
                metrics["latency_llm_seconds"] = self._latency_metrics.llm_seconds
        
        # Retrieval metrics
        if self._retrieval_metrics:
            metrics["kpi_matches_count"] = self._retrieval_metrics.kpi_matches_count
            metrics["rag_chunks_count"] = self._retrieval_metrics.rag_chunks_count
            
            # Log tickers/years as tags (not metrics)
            if self._retrieval_metrics.tickers_found:
                mlflow.set_tag("tickers", ",".join(self._retrieval_metrics.tickers_found))
            if self._retrieval_metrics.years_found:
                mlflow.set_tag("years", ",".join(map(str, self._retrieval_metrics.years_found)))
        
        # LLM metrics
        if self._llm_metrics:
            metrics["input_tokens"] = self._llm_metrics.input_tokens
            metrics["output_tokens"] = self._llm_metrics.output_tokens
            metrics["total_tokens"] = self._llm_metrics.input_tokens + self._llm_metrics.output_tokens
            metrics["cost_usd"] = self._llm_metrics.cost_usd
        
        if metrics:
            mlflow.log_metrics(metrics)
            logger.debug(f"Logged {len(metrics)} final metrics")
    
    
    # ========================================================================
    # METRIC LOGGING METHODS (Called during pipeline execution)
    # ========================================================================
    
    def log_retrieval_metrics(
        self,
        kpi_count: int = 0,
        rag_count: int = 0,
        tickers: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
        sections: Optional[List[str]] = None
    ):
        """
        Log retrieval phase metrics.
        
        Args:
            kpi_count: Number of KPI matches found
            rag_count: Number of RAG chunks retrieved
            tickers: List of ticker symbols found
            years: List of fiscal years found
            sections: List of SEC sections retrieved
        """
        if self._retrieval_metrics is None:
            self._retrieval_metrics = RetrievalMetrics()
        
        self._retrieval_metrics.kpi_matches_count = kpi_count
        self._retrieval_metrics.rag_chunks_count = rag_count
        
        if tickers:
            self._retrieval_metrics.tickers_found = tickers
        if years:
            self._retrieval_metrics.years_found = years
        if sections:
            self._retrieval_metrics.sections_retrieved = sections
        
        logger.debug(f"Logged retrieval metrics: KPI={kpi_count}, RAG={rag_count}")
    
    
    def log_llm_metrics(
        self,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        model_id: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ):
        """
        Log LLM inference metrics.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens  
            cost: Cost in USD
            model_id: Model identifier (optional, for verification)
            temperature: Temperature used (optional)
            max_tokens: Max tokens setting (optional)
        """
        if self._llm_metrics is None:
            self._llm_metrics = LLMMetrics()
        
        self._llm_metrics.input_tokens = input_tokens
        self._llm_metrics.output_tokens = output_tokens
        self._llm_metrics.cost_usd = cost
        
        if model_id:
            self._llm_metrics.model_id = model_id
        if temperature is not None:
            self._llm_metrics.temperature = temperature
        if max_tokens is not None:
            self._llm_metrics.max_tokens = max_tokens
        
        logger.debug(f"Logged LLM metrics: {input_tokens}in/{output_tokens}out, ${cost:.4f}")
    
    
    def log_latency(
        self,
        total: Optional[float] = None,
        retrieval: Optional[float] = None,
        llm: Optional[float] = None
    ):
        """
        Log latency breakdown.
        
        Args:
            total: Total pipeline latency (seconds)
            retrieval: Retrieval phase latency (seconds)
            llm: LLM inference latency (seconds)
        """
        if self._latency_metrics is None:
            self._latency_metrics = LatencyMetrics()
        
        if total is not None:
            self._latency_metrics.total_seconds = total
        if retrieval is not None:
            self._latency_metrics.retrieval_seconds = retrieval
        if llm is not None:
            self._latency_metrics.llm_seconds = llm
    
    
    def log_context_metrics(self, context_length: int, answer_length: int):
        """
        Log context and answer size metrics.
        
        Args:
            context_length: Length of assembled context in characters
            answer_length: Length of LLM response in characters
        """
        mlflow.log_metrics({
            "context_length_chars": context_length,
            "answer_length_chars": answer_length
        })
    
    
    # ========================================================================
    # ARTIFACT LOGGING
    # ========================================================================
    
    def log_artifacts(
        self,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        assembled_context: Optional[str] = None,
        full_response: Optional[Dict] = None,
        query: Optional[str] = None
    ):
        """
        Log artifacts (prompts, context, response).
        
        Args:
            system_prompt: System prompt text
            user_prompt: User prompt (with context)
            assembled_context: Raw assembled context
            full_response: Complete response dict from answer_query()
            query: Original user query
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Log prompts
            if self.config.log_prompts:
                prompts_dir = tmppath / "prompts"
                prompts_dir.mkdir(exist_ok=True)
                
                if system_prompt:
                    (prompts_dir / "system_prompt.txt").write_text(
                        system_prompt, encoding="utf-8"
                    )
                
                if user_prompt:
                    # Truncate if too large
                    if len(user_prompt) > self.config.max_context_artifact_chars:
                        user_prompt = user_prompt[:self.config.max_context_artifact_chars]
                        user_prompt += f"\n\n[TRUNCATED - Original length: {len(user_prompt)} chars]"
                    
                    (prompts_dir / "user_prompt.txt").write_text(
                        user_prompt, encoding="utf-8"
                    )
                
                if query:
                    (prompts_dir / "original_query.txt").write_text(
                        query, encoding="utf-8"
                    )
                
                mlflow.log_artifacts(str(prompts_dir), "prompts")
            
            # Log context
            if self.config.log_context and assembled_context:
                context_dir = tmppath / "context"
                context_dir.mkdir(exist_ok=True)
                
                # Truncate if too large
                ctx_text = assembled_context
                if len(ctx_text) > self.config.max_context_artifact_chars:
                    ctx_text = ctx_text[:self.config.max_context_artifact_chars]
                    ctx_text += f"\n\n[TRUNCATED - Original length: {len(assembled_context)} chars]"
                
                (context_dir / "assembled_context.txt").write_text(
                    ctx_text, encoding="utf-8"
                )
                
                mlflow.log_artifacts(str(context_dir), "context")
            
            # Log response
            if self.config.log_response and full_response:
                response_dir = tmppath / "response"
                response_dir.mkdir(exist_ok=True)
                
                (response_dir / "full_response.json").write_text(
                    json.dumps(full_response, indent=2, default=str),
                    encoding="utf-8"
                )
                
                mlflow.log_artifacts(str(response_dir), "response")
        
        logger.debug("Logged artifacts to MLflow")
    
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_run_url(self) -> Optional[str]:
        """Get URL to current run in MLflow UI (if available)."""
        if self._active_run:
            tracking_uri = mlflow.get_tracking_uri()
            run_id = self._active_run.info.run_id
            experiment_id = self._active_run.info.experiment_id
            
            # For local tracking, provide file path
            if tracking_uri.startswith("file:") or not tracking_uri.startswith("http"):
                return f"Local: {tracking_uri}/experiments/{experiment_id}/runs/{run_id}"
            
            # For remote server
            return f"{tracking_uri}/#/experiments/{experiment_id}/runs/{run_id}"
        
        return None
    
    
    @staticmethod
    def get_experiment_runs(
        experiment_name: str,
        max_results: int = 100,
        filter_string: Optional[str] = None
    ) -> List[Dict]:
        """
        Query runs from an experiment.
        
        Args:
            experiment_name: Name of experiment
            max_results: Maximum runs to return
            filter_string: MLflow filter string (e.g., "params.model_key = 'development'")
        
        Returns:
            List of run info dicts
        """
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            return []
        
        runs = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            max_results=max_results,
            filter_string=filter_string
        )
        
        return runs.to_dict(orient="records")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_tracker(
    experiment_name: str = "FinRAG-Synthesis",
    model_root: Optional[Path] = None,
    environment: str = "development"
) -> FinRAGTracker:
    """
    Factory function to create a configured tracker.
    
    Args:
        experiment_name: MLflow experiment name
        model_root: Path to ModelPipeline root
        environment: Environment tag (development/staging/production)
    
    Returns:
        Configured FinRAGTracker instance
    """
    config = MLflowConfig(
        default_experiment=experiment_name,
        environment=environment
    )
    
    return FinRAGTracker(
        experiment_name=experiment_name,
        config=config,
        model_root=model_root
    )


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    """
    Test MLflow tracker independently.
    
    Run:
        cd ModelPipeline
        python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.mlflow_tracker
    """
    import sys
    
    print("=" * 70)
    print("MLFLOW TRACKER TEST")
    print("=" * 70)
    
    try:
        # Find model root
        current = Path.cwd()
        model_root = None
        for parent in [current] + list(current.parents):
            if parent.name == "ModelPipeline":
                model_root = parent
                break
        
        if model_root is None:
            print("ERROR: Run from within ModelPipeline directory")
            sys.exit(1)
        
        print(f"\nModel root: {model_root}")
        
        # Create tracker
        tracker = create_tracker(
            experiment_name="FinRAG-Test",
            model_root=model_root,
            environment="testing"
        )
        print(f"Created tracker for experiment: FinRAG-Test")
        
        # Test run
        test_query = "What was NVIDIA's revenue in 2020?"
        
        with tracker.start_run(
            query=test_query,
            model_key="development_CH45",
            model_config={
                "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                "temperature": 0.1,
                "max_tokens": 8192,
                "cost_per_1k_input": 0.001,
                "cost_per_1k_output": 0.005
            },
            prompt_versions={"system": "v1", "query": "v1"},
            include_kpi=True,
            include_rag=True
        ) as run_id:
            print(f"\nStarted run: {run_id[:8]}...")
            
            # Simulate pipeline execution
            import time
            time.sleep(0.5)  # Simulate work
            
            # Log retrieval metrics
            tracker.log_retrieval_metrics(
                kpi_count=8,
                rag_count=12,
                tickers=["NVDA"],
                years=[2019, 2020]
            )
            print("  Logged retrieval metrics")
            
            # Log LLM metrics
            tracker.log_llm_metrics(
                input_tokens=5000,
                output_tokens=800,
                cost=0.009
            )
            print("  Logged LLM metrics")
            
            # Log context metrics
            tracker.log_context_metrics(
                context_length=25000,
                answer_length=1500
            )
            print("  Logged context metrics")
            
            # Log artifacts
            tracker.log_artifacts(
                system_prompt="You are a financial analyst...",
                query=test_query,
                full_response={
                    "query": test_query,
                    "answer": "NVIDIA's revenue in 2020 was $10.9 billion...",
                    "metadata": {"tokens": 5800}
                }
            )
            print("  Logged artifacts")
            
            # Get run URL
            run_url = tracker.get_run_url()
            print(f"\n  Run location: {run_url}")
        
        print("\n" + "=" * 70)
        print("SUCCESS - Run completed and logged")
        print("=" * 70)
        
        # Show how to view results
        tracking_path = model_root / "mlruns"
        print(f"\nTo view results:")
        print(f"  cd {model_root}")
        print(f"  mlflow ui --backend-store-uri {tracking_path}")
        print(f"  Then open: http://localhost:5000")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)