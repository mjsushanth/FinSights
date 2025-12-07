"""
FinSight Pipeline Runner

Standalone pipeline runner that executes the same tasks as the Airflow DAG.
Can be run in Docker via GitHub Actions or locally.

Usage:
    python pipeline_runner.py --full              # Run full pipeline
    python pipeline_runner.py --task download     # Run specific task
    python pipeline_runner.py --dry-run           # Validate without running
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

# ============================================================================
# Configuration
# ============================================================================

# Paths - configurable via environment
# Default to the directory containing this script (project root)
def get_base_dir() -> Path:
    """Determine the base directory for the pipeline."""
    # # First check environment variable
    # if "PIPELINE_BASE_DIR" in os.environ:
    #     return Path(os.environ["PIPELINE_BASE_DIR"])
    
    # Otherwise use the directory containing this script
    return Path(__file__).parent.resolve()

BASE_DIR = get_base_dir()
# Force pipeline to run from DataPipeline folder
if (BASE_DIR.name != "DataPipeline") and (BASE_DIR / "DataPipeline").exists():
    BASE_DIR = BASE_DIR / "DataPipeline"
    
DATASETS_DIR = BASE_DIR / "datasets"
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATASETS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskResult:
    """Result of a task execution."""
    task_name: str
    status: TaskStatus
    duration_seconds: float = 0.0
    message: str = ""
    output: dict = field(default_factory=dict)


@dataclass
class PipelineContext:
    """Shared context passed between tasks."""
    execution_id: str
    execution_date: str
    environment: str
    config: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "execution_date": self.execution_date,
            "environment": self.environment,
            "results": {k: v.status.value for k, v in self.results.items()}
        }


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(execution_id: str) -> logging.Logger:
    """Configure logging for the pipeline run."""
    log_file = LOGS_DIR / f"pipeline_{execution_id}.log"
    
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler (UTF-8 encoding for full unicode support)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler with safe encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Root logger
    logger = logging.getLogger("finsight")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# ============================================================================
# Task Definitions
# ============================================================================

def run_module(module: str, args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run a Python module as subprocess."""
    cmd = [sys.executable, "-m", module]
    if args:
        cmd.extend(args)
    
    # Set PYTHONPATH to include the base directory
    env = os.environ.copy()
    python_path = str(BASE_DIR)
    if "PYTHONPATH" in env:
        python_path = f"{python_path}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = python_path
    
    return subprocess.run(
        cmd,
        check=True,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        env=env
    )


def task_get_companies_list(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Download companies list from S3."""
    logger.info("Downloading companies list from S3...")
    
    try:
        result = run_module("src.download_from_s3")
        if result.stdout:
            logger.debug(f"stdout: {result.stdout}")
        
        # Verify file exists
        companies_file = CONFIG_DIR / "companies.csv"
        if not companies_file.exists():
            raise FileNotFoundError("companies.csv not downloaded")
        
        # Count companies
        with open(companies_file) as f:
            company_count = sum(1 for _ in f) - 1  # Subtract header
        
        return TaskResult(
            task_name="get_companies_list",
            status=TaskStatus.SUCCESS,
            message=f"Downloaded {company_count} companies",
            output={"company_count": company_count}
        )
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error(f"Failed: {error_msg}")
        if e.stdout:
            logger.error(f"stdout: {e.stdout}")
        return TaskResult(
            task_name="get_companies_list",
            status=TaskStatus.FAILED,
            message=error_msg
        )


def task_check_inputs(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Validate required files and directories exist."""
    logger.info("Checking required inputs...")
    
    required_paths = [
        CONFIG_DIR / "config.json",
        CONFIG_DIR / "companies.csv",
        DATASETS_DIR,
    ]
    
    missing = [str(p) for p in required_paths if not p.exists()]
    
    if missing:
        return TaskResult(
            task_name="check_inputs",
            status=TaskStatus.FAILED,
            message=f"Missing: {missing}"
        )
    
    return TaskResult(
        task_name="check_inputs",
        status=TaskStatus.SUCCESS,
        message="All inputs validated"
    )


def task_download_filings(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Download SEC filings from EDGAR."""
    logger.info("Downloading SEC filings...")
    
    try:
        result = run_module("src.download_filings")
        logger.debug(f"stdout: {result.stdout}")
        
        return TaskResult(
            task_name="download_filings",
            status=TaskStatus.SUCCESS,
            message="Filings downloaded"
        )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed: {e.stderr}")
        return TaskResult(
            task_name="download_filings",
            status=TaskStatus.FAILED,
            message=str(e.stderr)
        )


def task_extract_and_convert(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Extract items from filings and convert to parquet."""
    logger.info("Extracting and converting filings...")
    
    try:
        result = run_module("src.extract_and_convert")
        logger.debug(f"stdout: {result.stdout}")
        
        return TaskResult(
            task_name="extract_and_convert",
            status=TaskStatus.SUCCESS,
            message="Extraction complete"
        )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed: {e.stderr}")
        return TaskResult(
            task_name="extract_and_convert",
            status=TaskStatus.FAILED,
            message=str(e.stderr)
        )


def task_validate_data(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Validate extracted data using Great Expectations."""
    logger.info("Validating data...")
    
    try:
        result = run_module("data_auto_stats.src.run_validation")
        logger.debug(f"stdout: {result.stdout}")
        
        return TaskResult(
            task_name="validate_data",
            status=TaskStatus.SUCCESS,
            message="Validation passed"
        )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Validation failed: {e.stderr}")
        return TaskResult(
            task_name="validate_data",
            status=TaskStatus.FAILED,
            message=str(e.stderr)
        )


def task_upload_to_s3(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Upload processed files to S3."""
    logger.info("Uploading to S3...")
    
    try:
        result = run_module("src.upload_to_s3")
        logger.debug(f"stdout: {result.stdout}")
        
        return TaskResult(
            task_name="upload_to_s3",
            status=TaskStatus.SUCCESS,
            message="Upload complete"
        )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed: {e.stderr}")
        return TaskResult(
            task_name="upload_to_s3",
            status=TaskStatus.FAILED,
            message=str(e.stderr)
        )


def task_cleanup(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Clean up temporary files."""
    logger.info("Cleaning up temporary files...")
    
    dirs_to_clean = [
        DATASETS_DIR / "CSV_FILES",
        DATASETS_DIR / "PARQUET_FILES",
        DATASETS_DIR / "MERGED_EXTRACTED_FILINGS",
        DATASETS_DIR / "RAW_FILINGS" / "10-K",
        DATASETS_DIR / "EXTRACTED_FILINGS" / "10-K",
    ]
    
    cleaned = 0
    for d in dirs_to_clean:
        if d.exists():
            try:
                shutil.rmtree(d)
                cleaned += 1
                logger.debug(f"Deleted: {d}")
            except Exception as e:
                logger.warning(f"Failed to delete {d}: {e}")
    
    # Clean specific files
    files_to_clean = [
        DATASETS_DIR / "FILINGS_METADATA.csv",
        CONFIG_DIR / "companies.csv",
    ]
    
    for f in files_to_clean:
        if f.exists():
            try:
                f.unlink()
                cleaned += 1
            except Exception as e:
                logger.warning(f"Failed to delete {f}: {e}")
    
    return TaskResult(
        task_name="cleanup",
        status=TaskStatus.SUCCESS,
        message=f"Cleaned {cleaned} items"
    )


def task_merge_s3_data(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Merge incremental data on S3."""
    logger.info("Merging S3 data...")
    
    try:
        result = run_module("src_aws_etl.etl.merge_pipeline")
        logger.debug(f"stdout: {result.stdout}")
        
        return TaskResult(
            task_name="merge_s3_data",
            status=TaskStatus.SUCCESS,
            message="Merge complete"
        )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed: {e.stderr}")
        return TaskResult(
            task_name="merge_s3_data",
            status=TaskStatus.FAILED,
            message=str(e.stderr)
        )


def task_generate_statistics(ctx: PipelineContext, logger: logging.Logger) -> TaskResult:
    """Generate statistics from processed data."""
    logger.info("Generating statistics...")
    
    try:
        result = run_module("data_auto_stats.src.run_statistics")
        logger.debug(f"stdout: {result.stdout}")
        
        return TaskResult(
            task_name="generate_statistics",
            status=TaskStatus.SUCCESS,
            message="Statistics generated"
        )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed: {e.stderr}")
        return TaskResult(
            task_name="generate_statistics",
            status=TaskStatus.FAILED,
            message=str(e.stderr)
        )


# ============================================================================
# Pipeline Orchestration
# ============================================================================

# Task registry with dependencies
TASKS: dict[str, dict] = {
    "get_companies": {
        "function": task_get_companies_list,
        "depends_on": [],
    },
    "check_inputs": {
        "function": task_check_inputs,
        "depends_on": ["get_companies"],
    },
    "download": {
        "function": task_download_filings,
        "depends_on": ["check_inputs"],
    },
    "extract": {
        "function": task_extract_and_convert,
        "depends_on": ["download"],
    },
    "validate": {
        "function": task_validate_data,
        "depends_on": ["extract"],
    },
    "upload": {
        "function": task_upload_to_s3,
        "depends_on": ["validate"],
    },
    "cleanup": {
        "function": task_cleanup,
        "depends_on": ["upload"],
    },
    "merge": {
        "function": task_merge_s3_data,
        "depends_on": ["cleanup"],
    },
    "statistics": {
        "function": task_generate_statistics,
        "depends_on": ["merge"],
    },
}


def get_execution_order() -> list[str]:
    """Return tasks in dependency order."""
    return [
        "get_companies",
        "check_inputs",
        "download",
        "extract",
        "validate",
        "upload",
        "cleanup",
        "merge",
        "statistics",
    ]


def run_pipeline(
    ctx: PipelineContext,
    logger: logging.Logger,
    tasks_to_run: list[str] | None = None,
    stop_on_failure: bool = True,
) -> bool:
    """
    Run the pipeline tasks in order.
    
    Returns True if all tasks succeeded.
    """
    execution_order = tasks_to_run or get_execution_order()
    
    logger.info("=" * 60)
    logger.info(f"Starting Pipeline: {ctx.execution_id}")
    logger.info(f"Environment: {ctx.environment}")
    logger.info(f"Tasks: {execution_order}")
    logger.info("=" * 60)
    
    all_success = True
    start_time = datetime.now()
    
    for task_name in execution_order:
        if task_name not in TASKS:
            logger.error(f"Unknown task: {task_name}")
            continue
        
        task_info = TASKS[task_name]
        task_func = task_info["function"]
        
        # Check dependencies
        for dep in task_info["depends_on"]:
            if dep in ctx.results and ctx.results[dep].status == TaskStatus.FAILED:
                logger.warning(f"Skipping {task_name}: dependency {dep} failed")
                ctx.results[task_name] = TaskResult(
                    task_name=task_name,
                    status=TaskStatus.SKIPPED,
                    message=f"Dependency {dep} failed"
                )
                continue
        
        # Run task
        logger.info(f"\n{'-' * 40}")
        logger.info(f">> Task: {task_name}")
        logger.info(f"{'-' * 40}")
        
        task_start = datetime.now()
        
        try:
            result = task_func(ctx, logger)
            result.duration_seconds = (datetime.now() - task_start).total_seconds()
            ctx.results[task_name] = result
            
            if result.status == TaskStatus.SUCCESS:
                logger.info(f"[OK] {task_name}: {result.message} ({result.duration_seconds:.1f}s)")
            else:
                logger.error(f"[FAILED] {task_name}: {result.message}")
                all_success = False
                
                if stop_on_failure:
                    logger.error("Stopping pipeline due to failure")
                    break
                    
        except Exception as e:
            logger.exception(f"[FAILED] {task_name}: Unexpected error")
            ctx.results[task_name] = TaskResult(
                task_name=task_name,
                status=TaskStatus.FAILED,
                message=str(e),
                duration_seconds=(datetime.now() - task_start).total_seconds()
            )
            all_success = False
            
            if stop_on_failure:
                break
    
    # Summary
    total_duration = (datetime.now() - start_time).total_seconds()
    
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 60)
    
    for task_name, result in ctx.results.items():
        status_icon = {
            TaskStatus.SUCCESS: "[OK]",
            TaskStatus.FAILED: "[FAILED]",
            TaskStatus.SKIPPED: "[SKIPPED]",
        }.get(result.status, "[?]")
        logger.info(f"  {status_icon} {task_name}: {result.status.value} ({result.duration_seconds:.1f}s)")
    
    logger.info(f"\nTotal Duration: {total_duration:.1f}s")
    logger.info(f"Status: {'SUCCESS' if all_success else 'FAILED'}")
    logger.info("=" * 60)
    
    return all_success


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="FinSight SEC Filings ETL Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python pipeline_runner.py --full                    Run complete pipeline
    python pipeline_runner.py --task download           Run single task
    python pipeline_runner.py --tasks download,extract  Run multiple tasks
    python pipeline_runner.py --dry-run                 Validate configuration
    python pipeline_runner.py --list-tasks              List available tasks
        """
    )
    
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the complete pipeline"
    )
    
    parser.add_argument(
        "--task",
        type=str,
        help="Run a specific task"
    )
    
    parser.add_argument(
        "--tasks",
        type=str,
        help="Run specific tasks (comma-separated)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without running"
    )
    
    parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="List available tasks"
    )
    
    parser.add_argument(
        "--env",
        type=str,
        default=os.environ.get("ENVIRONMENT", "dev"),
        choices=["dev", "prod"],
        help="Environment (default: dev)"
    )
    
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue running tasks even if one fails"
    )
    
    args = parser.parse_args()
    
    # List tasks
    if args.list_tasks:
        print("\nAvailable Tasks:")
        print("-" * 40)
        for name, info in TASKS.items():
            deps = ", ".join(info["depends_on"]) or "none"
            print(f"  {name:20} (depends on: {deps})")
        print()
        return 0
    
    # Setup execution context
    execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = setup_logging(execution_id)
    
    # Log startup information
    logger.info(f"Pipeline Runner Starting")
    logger.info(f"  Python: {sys.executable}")
    logger.info(f"  Base directory: {BASE_DIR}")
    logger.info(f"  Working directory: {os.getcwd()}")
    
    # Validate that src module exists
    src_dir = BASE_DIR / "src"
    if not src_dir.exists():
        logger.error(f"ERROR: 'src' directory not found at {src_dir}")
        logger.error(f"Make sure you're running from the project root directory")
        return 1
    
    if not (src_dir / "__init__.py").exists():
        logger.warning(f"WARNING: 'src/__init__.py' not found - creating empty file")
        (src_dir / "__init__.py").touch()
    
    ctx = PipelineContext(
        execution_id=execution_id,
        execution_date=datetime.now().isoformat(),
        environment=args.env,
    )
    
    # Load config
    config_file = CONFIG_DIR / f"config.json"
    if config_file.exists():
        with open(config_file) as f:
            ctx.config = json.load(f)
        logger.info(f"Loaded config: {config_file}")
    else:
        logger.warning(f"Config file not found: {config_file}")
    
    # Dry run
    if args.dry_run:
        logger.info("DRY RUN - Validating configuration")
        logger.info(f"  Base directory: {BASE_DIR}")
        logger.info(f"  Config directory: {CONFIG_DIR}")
        logger.info(f"  Datasets directory: {DATASETS_DIR}")
        logger.info(f"  Environment: {args.env}")
        logger.info(f"  Tasks: {get_execution_order()}")
        
        # Verify modules can be found
        logger.info("  Checking modules...")
        for module_path in ["src", "src_aws_etl", "data_auto_stats"]:
            module_dir = BASE_DIR / module_path
            if module_dir.exists():
                logger.info(f"    [OK] {module_path}: {module_dir}")
            else:
                logger.warning(f"    [MISSING] {module_path}: NOT FOUND")
        
        logger.info("Configuration valid - OK")
        return 0
    
    # Determine tasks to run
    tasks_to_run = None
    
    if args.task:
        if args.task not in TASKS:
            logger.error(f"Unknown task: {args.task}")
            return 1
        tasks_to_run = [args.task]
    
    elif args.tasks:
        tasks_to_run = [t.strip() for t in args.tasks.split(",")]
        unknown = [t for t in tasks_to_run if t not in TASKS]
        if unknown:
            logger.error(f"Unknown tasks: {unknown}")
            return 1
    
    elif not args.full:
        parser.print_help()
        return 1
    
    # Run pipeline
    success = run_pipeline(
        ctx=ctx,
        logger=logger,
        tasks_to_run=tasks_to_run,
        stop_on_failure=not args.continue_on_failure,
    )
    
    # Save execution summary
    summary_file = LOGS_DIR / f"summary_{execution_id}.json"
    with open(summary_file, "w") as f:
        json.dump(ctx.to_dict(), f, indent=2)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
