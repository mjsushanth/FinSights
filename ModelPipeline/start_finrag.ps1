# start_finrag.ps1
# FinRAG Startup Script for Windows
# Launches both backend (FastAPI) and frontend (Streamlit) servers

# ==============================================================================
# CONFIGURATION
# ==============================================================================

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND_ENV = Join-Path $SCRIPT_DIR "finrag_ml_tg1\venv_ml_rag\Scripts\Activate.ps1"
$FRONTEND_ENV = Join-Path $SCRIPT_DIR "serving\frontend\venv_frontend\Scripts\Activate.ps1"
$SERVING_DIR = Join-Path $SCRIPT_DIR "serving"

$BACKEND_PORT = 8000
$FRONTEND_PORT = 8501

# ==============================================================================
# BANNER
# ==============================================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "           FinRAG - Financial Document Intelligence         " -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ==============================================================================
# VALIDATION
# ==============================================================================

Write-Host "[*] Validating environment..." -ForegroundColor Yellow

# Check if backend environment exists
if (-not (Test-Path $BACKEND_ENV)) {
    Write-Host "[ERROR] Backend virtual environment not found!" -ForegroundColor Red
    Write-Host "   Expected: $BACKEND_ENV" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Please create the backend environment first:" -ForegroundColor Yellow
    Write-Host "   cd finrag_ml_tg1" -ForegroundColor Yellow
    Write-Host "   python -m venv venv_ml_rag" -ForegroundColor Yellow
    Write-Host "   .\venv_ml_rag\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "   pip install -r environments\requirements.txt" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# Check if frontend environment exists
if (-not (Test-Path $FRONTEND_ENV)) {
    Write-Host "[ERROR] Frontend virtual environment not found!" -ForegroundColor Red
    Write-Host "   Expected: $FRONTEND_ENV" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Please create the frontend environment first:" -ForegroundColor Yellow
    Write-Host "   cd serving\frontend" -ForegroundColor Yellow
    Write-Host "   python -m venv venv_frontend" -ForegroundColor Yellow
    Write-Host "   .\venv_frontend\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "   pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "[OK] Environments validated" -ForegroundColor Green
Write-Host ""

# ==============================================================================
# PORT CHECKING
# ==============================================================================

Write-Host "[*] Checking if ports are available..." -ForegroundColor Yellow

# Check backend port
$backendInUse = Get-NetTCPConnection -LocalPort $BACKEND_PORT -ErrorAction SilentlyContinue
if ($backendInUse) {
    Write-Host "[WARNING] Port $BACKEND_PORT is already in use!" -ForegroundColor Yellow
    Write-Host "   Backend may already be running or port is occupied." -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "   Continue anyway? (y/n)"
    if ($response -ne "y") {
        Write-Host "[CANCELLED] Startup cancelled" -ForegroundColor Red
        exit 1
    }
}

# Check frontend port
$frontendInUse = Get-NetTCPConnection -LocalPort $FRONTEND_PORT -ErrorAction SilentlyContinue
if ($frontendInUse) {
    Write-Host "[WARNING] Port $FRONTEND_PORT is already in use!" -ForegroundColor Yellow
    Write-Host "   Frontend may already be running or port is occupied." -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "   Continue anyway? (y/n)"
    if ($response -ne "y") {
        Write-Host "[CANCELLED] Startup cancelled" -ForegroundColor Red
        exit 1
    }
}

Write-Host "[OK] Ports available" -ForegroundColor Green
Write-Host ""

# ==============================================================================
# START BACKEND SERVER
# ==============================================================================

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[BACKEND] Starting Backend Server (FastAPI + ML Pipeline)" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Port: $BACKEND_PORT" -ForegroundColor Yellow
Write-Host "   URL:  http://localhost:$BACKEND_PORT" -ForegroundColor Yellow
Write-Host "   Docs: http://localhost:$BACKEND_PORT/docs" -ForegroundColor Yellow
Write-Host ""

# Start backend in new PowerShell window
$backendScript = @"
& '$BACKEND_ENV'
cd '$SERVING_DIR'
Write-Host 'Backend environment activated' -ForegroundColor Green
Write-Host 'Starting uvicorn server...' -ForegroundColor Yellow
Write-Host ''
uvicorn backend.api_service:app --reload --host 0.0.0.0 --port $BACKEND_PORT
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendScript

Write-Host "[*] Backend starting... (waiting 8 seconds)" -ForegroundColor Yellow
Start-Sleep -Seconds 8

# ==============================================================================
# START FRONTEND SERVER
# ==============================================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[FRONTEND] Starting Frontend Server (Streamlit UI)" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Port: $FRONTEND_PORT" -ForegroundColor Yellow
Write-Host "   URL:  http://localhost:$FRONTEND_PORT" -ForegroundColor Yellow
Write-Host ""

# Start frontend in new PowerShell window (with auto-open browser flag)
$frontendScript = @"
& '$FRONTEND_ENV'
cd '$SERVING_DIR'
Write-Host 'Frontend environment activated' -ForegroundColor Green
Write-Host 'Starting Streamlit server...' -ForegroundColor Yellow
Write-Host 'Browser will open automatically...' -ForegroundColor Cyan
Write-Host ''
streamlit run frontend/app.py --server.port $FRONTEND_PORT --server.address localhost
"@

## ============= ===================== Was causing double browser open issue =====================
## streamlit run frontend/app.py --server.port $FRONTEND_PORT --server.address localhost --server.headless false

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendScript

Write-Host "[*] Frontend starting... (waiting 6 seconds)" -ForegroundColor Yellow
Start-Sleep -Seconds 6

# ==============================================================================
# OPEN BROWSER (BACKUP)
# ==============================================================================

Write-Host ""
Write-Host "[*] Opening browser..." -ForegroundColor Cyan
Start-Sleep -Seconds 2

# Open browser (backup in case Streamlit didn't auto-open)
Start-Process "http://localhost:$FRONTEND_PORT"

# ==============================================================================
# COMPLETION
# ==============================================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "[SUCCESS] FinRAG Successfully Started!" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access Points:" -ForegroundColor Yellow
Write-Host "   Backend API:  http://localhost:$BACKEND_PORT" -ForegroundColor Cyan
Write-Host "   API Docs:     http://localhost:$BACKEND_PORT/docs" -ForegroundColor Cyan
Write-Host "   Frontend UI:  http://localhost:$FRONTEND_PORT" -ForegroundColor Cyan
Write-Host ""
Write-Host "Status:" -ForegroundColor Yellow
Write-Host "   [OK] Backend server started in separate window" -ForegroundColor Green
Write-Host "   [OK] Frontend server started in separate window" -ForegroundColor Green
Write-Host "   [OK] Browser opened automatically" -ForegroundColor Green
Write-Host ""
Write-Host "Tips:" -ForegroundColor Yellow
Write-Host "   - Both servers are running in separate windows" -ForegroundColor White
Write-Host "   - Close those windows to stop the servers" -ForegroundColor White
Write-Host "   - If browser didn't open, visit: http://localhost:$FRONTEND_PORT" -ForegroundColor White
Write-Host ""
Write-Host "[READY] Ready to analyze SEC 10-K filings!" -ForegroundColor Green
Write-Host ""
Write-Host "Press any key to exit this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")