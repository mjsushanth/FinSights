"""
FastAPI server for the Financial RAG system.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import uvicorn

from main import FinancialRAGOrchestrator, QueryResult


# Initialize FastAPI app
app = FastAPI(
    title="Financial RAG API",
    description="AI-powered financial analysis system with unified context",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global orchestrator instance
orchestrator: Optional[FinancialRAGOrchestrator] = None


# Request/Response models
class QueryRequest(BaseModel):
    """Request model for query endpoint"""
    query: str = Field(..., description="Financial question to ask")
    ticker: str = Field(default=None, description="Stock ticker symbol (optional, will be extracted)")
    metrics: Optional[List[str]] = Field(default=None, description="Specific metrics to retrieve (optional)")
    enable_evaluation: bool = Field(default=False, description="Whether to evaluate response")


class QueryResponse(BaseModel):
    """Response model for query endpoint"""
    query: str
    response: str
    
    # Extracted entities
    ticker: str
    metrics: List[str]
    years: List[int]
    
    # Metadata
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    cost_usd: float
    
    # Optional fields
    mlflow_run_id: Optional[str] = None
    evaluation_score: Optional[float] = None
    evaluation_passed: Optional[bool] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    message: str


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize the orchestrator on startup"""
    global orchestrator
    
    print("🚀 Starting Financial RAG API (Unified Context)...")
    
    orchestrator = FinancialRAGOrchestrator(
        enable_mlflow=True,
        enable_evaluation=False
    )
    
    print("✅ API Ready!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("👋 Shutting down Financial RAG API...")


# Endpoints
@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint"""
    return HealthResponse(
        status="ok",
        message="Financial RAG API is running (Unified Context - No Classification)"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    return HealthResponse(
        status="healthy",
        message="All systems operational"
    )


@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Process a financial query with unified context.
    
    Args:
        request: QueryRequest with query details
        
    Returns:
        QueryResponse with answer and metadata
    """
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    try:
        # Process query
        result = orchestrator.query(
            question=request.query,
            ticker=request.ticker,
            metrics=request.metrics
        )
        
        # Build response
        response = QueryResponse(
            query=result.query,
            response=result.response,
            ticker=result.entities.ticker,
            metrics=result.entities.metrics or [],
            years=result.entities.years or [],
            input_tokens=result.llm_response.input_tokens,
            output_tokens=result.llm_response.output_tokens,
            latency_seconds=result.total_latency,
            cost_usd=result.llm_response.cost_usd,
            mlflow_run_id=result.mlflow_run_id
        )
        
        # Add evaluation if available
        if result.evaluation:
            response.evaluation_score = result.evaluation.overall_score
            response.evaluation_passed = result.evaluation.passed
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@app.get("/available-tickers")
async def get_available_tickers():
    """Get list of available stock tickers"""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    from data.loaders import data_loader
    
    tickers = data_loader.get_available_tickers()
    return {"tickers": tickers}


@app.get("/available-metrics/{ticker}")
async def get_available_metrics(ticker: str):
    """Get list of available metrics for a ticker"""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    from data.loaders import data_loader
    
    metrics = data_loader.get_available_metrics(ticker)
    return {"ticker": ticker, "metrics": metrics}


# Run server
def start_server(host: str = "0.0.0.0", port: int = 8000):
    """
    Start the FastAPI server.
    
    Args:
        host: Host address
        port: Port number
    """
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    start_server()