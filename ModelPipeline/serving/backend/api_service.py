"""
FastAPI application for FinRAG backend.

This is the main HTTP server that wraps the ML orchestrator.

Architecture:
    HTTP Request → FastAPI → answer_query() → HTTP Response
    
Endpoints:
    POST /query - Main query endpoint
    GET /health - Health check
    GET /docs - Auto-generated API documentation

Usage:
    uvicorn backend.api_service:app --reload --host 0.0.0.0 --port 8000


 FastAPI Application (api_service.py)
   ├── GET  /          → Service info
   ├── GET  /health    → Health check
   ├── GET  /docs      → Auto-generated API docs
   ├── POST /query     → Main query endpoint
   └── Uvicorn server running on port 8000

 Configuration Management (config.py)
   ├── Auto-detects ModelPipeline root
   ├── Validates paths on startup
   └── Singleton pattern for efficiency

 Request/Response Models (models.py)
   ├── QueryRequest - Input validation
   ├── QueryResponse - Success response
   ├── ErrorResponse - Error handling
   └── HealthResponse - Health status

"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from backend.models import (
    QueryRequest,
    QueryResponse,
    ErrorResponse,
    HealthResponse
)
from backend.config import get_config

# ============================================================================
# IMPORT ORCHESTRATOR
# ============================================================================


# Get ModelPipeline root from config
config = get_config()
MODEL_PIPELINE_ROOT = config.model_pipeline_root  

# Add ModelPipeline to sys.path (matches notebook pattern)
if str(MODEL_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_PIPELINE_ROOT))
    logger.info(f"Added to Python path: {MODEL_PIPELINE_ROOT}")

# Import using absolute path from ModelPipeline
try:
    from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.orchestrator import answer_query
    logger.info(f" Successfully imported orchestrator")
except ImportError as e:
    logger.error(f"❌ Failed to import orchestrator: {e}")
    logger.error(f"   ModelPipeline root: {MODEL_PIPELINE_ROOT}")
    logger.error(f"   sys.path: {sys.path[:3]}")
    raise


# ============================================================================
# FASTAPI APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="FinRAG API",
    description="Financial document intelligence API powered by RAG",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI at /docs
    redoc_url="/redoc"  # ReDoc at /redoc
)

# CORS middleware (allows frontend to call backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],  # Streamlit
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on server startup."""
    logger.info("=" * 60)
    logger.info("🚀 Starting FinRAG Backend")
    logger.info("=" * 60)
    logger.info(f"ModelPipeline root: {config.model_pipeline_root}")  # ← NEW NAME
    logger.info(f"Backend host: {config.backend_host}:{config.backend_port}")
    logger.info(f"Cache enabled: {config.enable_cache}")
    logger.info(f"Log level: {config.log_level}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Run on server shutdown."""
    logger.info("👋 Shutting down FinRAG Backend")


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint - basic info about the API.
    """
    return {
        "service": "FinRAG API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    
    Verifies server is running and can access model files.
    AWS credentials are validated by orchestrator on first query.
    """
    return HealthResponse(
        status="healthy",
        model_root_exists=config.model_pipeline_root.exists(),
        aws_configured=None,  
        timestamp=datetime.utcnow().isoformat() + "Z"
    )





@app.post("/query", response_model=QueryResponse, tags=["Query"])
def query_endpoint(request: QueryRequest):
    """
    Main query endpoint - processes user questions.

    Deliberately a sync `def`, not `async def` (Tier 1 Change 2, 2026-08-01):
    answer_query() is fully synchronous and blocks for ~9.6s+ with zero
    `await` points. Under `async def`, that blocks the entire event loop for
    the whole call - one query in flight per container, /health unanswerable
    during a query, streaming structurally impossible. Under plain `def`,
    FastAPI runs this in its threadpool instead, so the event loop stays
    free. See TIER1_LATENCY_DESIGN.md section 0.4 / Change 2.

    This endpoint:
    1. Validates the request (Pydantic does this automatically)
    2. Calls the orchestrator with validated parameters
    3. Returns structured response or error
    
    Args:
        request: QueryRequest with question and options
        
    Returns:
        QueryResponse with answer and metadata
        
    Raises:
        HTTPException: If query processing fails
        
    Example:
        POST /query
        {
            "question": "What was Apple's revenue in 2023?",
            "include_kpi": true,
            "include_rag": true
        }
    """
    logger.info(f"📥 Received query: {request.question[:50]}...")
    
    try:
        # Pass ModelPipeline root to orchestrator (!)
        result = answer_query(
            query=request.question,
            model_root=MODEL_PIPELINE_ROOT,  
            include_kpi=request.include_kpi,
            include_rag=request.include_rag,
            model_key=request.model_key,
            export_context=config.enable_exports,
            export_response=config.enable_exports
        )
        
        # Check if orchestrator returned an error
        if result.get("error"):
            logger.error(
                f"❌ Orchestrator error: {result['error']} "
                f"(stage: {result.get('stage', 'unknown')})"
            )
            
            # Return error response with appropriate HTTP status
            error_response = ErrorResponse(
                query=request.question,
                error=result["error"],
                error_type=result.get("error_type", "UnknownError"),
                stage=result.get("stage", "unknown"),
                timestamp=result.get("timestamp", datetime.utcnow().isoformat() + "Z")
            )
            
            # Map error stages to HTTP status codes
            status_code = _get_status_code_for_error(result.get("stage"))
            
            return JSONResponse(
                status_code=status_code,
                content=error_response.model_dump()
            )
        
        # Success - log metrics and return
        logger.info(
            f" Query successful: "
            f"cost=${result['metadata']['llm']['cost']:.4f}, "
            f"tokens={result['metadata']['llm']['total_tokens']}, "
            f"time={result['metadata'].get('processing_time_ms', 0):.0f}ms"
        )
        
        return result
        
    except Exception as e:
        # Catch unexpected errors (orchestrator should handle most errors)
        logger.exception(f"💥 Unexpected error processing query: {e}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": str(e),
                "error_type": type(e).__name__,
                "stage": "unexpected",
                "query": request.question
            }
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_status_code_for_error(stage: str) -> int:
    """
    Map error stage to appropriate HTTP status code.
    
    Args:
        stage: Error stage from orchestrator
        
    Returns:
        HTTP status code
    """
    error_map = {
        "initialization": status.HTTP_503_SERVICE_UNAVAILABLE,  # Service not ready
        "context_building": status.HTTP_500_INTERNAL_SERVER_ERROR,  # Server error
        "prompt_formatting": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "llm_invocation": status.HTTP_502_BAD_GATEWAY,  # External service failed
        "response_packaging": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "unexpected": status.HTTP_500_INTERNAL_SERVER_ERROR
    }
    
    return error_map.get(stage, status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# MAIN (for direct execution)
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "backend.api_service:app",
        host=config.backend_host,
        port=config.backend_port,
        reload=config.backend_reload,
        log_level=config.log_level.lower()
    )