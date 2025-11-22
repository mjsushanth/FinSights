# setup_finrag.ps1
# FinRAG Setup Script for Windows
# Automates environment creation and dependency installation using UV

# ==============================================================================
# CONFIGURATION
# ==============================================================================

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND_DIR = Join-Path $SCRIPT_DIR "finrag_ml_tg1"
$FRONTEND_DIR = Join-Path $SCRIPT_DIR "serving\frontend"
$BACKEND_ENV = Join-Path $BACKEND_DIR "venv_ml_rag"
$FRONTEND_ENV = Join-Path $FRONTEND_DIR "venv_frontend"

# ==============================================================================
# HELPER FUNCTION: FORCE DELETE LOCKED DIRECTORY
# ==============================================================================

function Remove-LockedDirectory {
    param(
        [string]$Path,
        [string]$Name
    )
    
    Write-Host "[*] Attempting to remove $Name environment..." -ForegroundColor Yellow
    
    # Try 1: Normal deletion
    try {
        Remove-Item -Recurse -Force $Path -ErrorAction Stop
        Write-Host "[OK] $Name environment removed successfully" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[WARNING] Normal deletion failed (files locked)" -ForegroundColor Yellow
    }
    
    # Try 2: Kill Python processes and retry
    Write-Host "[*] Killing Python processes and retrying..." -ForegroundColor Yellow
    
    try {
        # Kill all Python processes
        Get-Process -Name python,pythonw,uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
        
        # Retry deletion
        Remove-Item -Recurse -Force $Path -ErrorAction Stop
        Write-Host "[OK] $Name environment removed after killing processes" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[WARNING] Still locked after killing processes" -ForegroundColor Yellow
    }
    
    # Try 3: Rename and mark for deletion (Windows workaround)
    Write-Host "[*] Using Windows rename workaround..." -ForegroundColor Yellow
    
    $tempName = "$Path.old_$(Get-Date -Format 'yyyyMMddHHmmss')"
    
    try {
        Rename-Item $Path $tempName -ErrorAction Stop
        Write-Host "[OK] Environment renamed to: $(Split-Path $tempName -Leaf)" -ForegroundColor Green
        Write-Host "   (Will be cleaned up manually later or on reboot)" -ForegroundColor Cyan
        return $true
    } catch {
        Write-Host "[ERROR] Could not remove or rename environment!" -ForegroundColor Red
        Write-Host ""
        Write-Host "Manual fix required:" -ForegroundColor Yellow
        Write-Host "   1. Close ALL terminal windows" -ForegroundColor White
        Write-Host "   2. Open Task Manager (Ctrl+Shift+Esc)" -ForegroundColor White
        Write-Host "   3. End all 'python.exe' processes" -ForegroundColor White
        Write-Host "   4. Manually delete: $Path" -ForegroundColor White
        Write-Host "   5. Run this script again" -ForegroundColor White
        Write-Host ""
        return $false
    }
}

# ==============================================================================
# BANNER
# ==============================================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "           FinRAG Setup - Environment Configuration         " -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ==============================================================================
# CHECK PYTHON
# ==============================================================================

Write-Host "[*] Checking Python installation..." -ForegroundColor Yellow

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $version = & $cmd --version 2>&1
        if ($version -match "Python 3\.(\d+)") {
            $minorVersion = [int]$matches[1]
            if ($minorVersion -ge 11) {
                $pythonCmd = $cmd
                Write-Host "[OK] Found Python: $version" -ForegroundColor Green
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $pythonCmd) {
    Write-Host "[ERROR] Python 3.11+ not found!" -ForegroundColor Red
    Write-Host "   Please install Python 3.11 or higher from python.org" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# ==============================================================================
# CHECK/INSTALL UV
# ==============================================================================

Write-Host "[*] Checking for UV package installer..." -ForegroundColor Yellow

$uvInstalled = $false
try {
    $uvVersion = uv --version 2>&1
    if ($uvVersion -match "uv") {
        Write-Host "[OK] UV already installed: $uvVersion" -ForegroundColor Green
        $uvInstalled = $true
    }
} catch {
    Write-Host "[INFO] UV not found, will install..." -ForegroundColor Yellow
}

if (-not $uvInstalled) {
    Write-Host ""
    Write-Host "[*] Installing UV (fast package installer)..." -ForegroundColor Cyan
    Write-Host "   This will make dependency installation 10-20x faster!" -ForegroundColor White
    Write-Host ""
    
    try {
        # Install UV using the official installer
        Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing | Invoke-Expression
        
        # Refresh PATH to include UV
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        
        Write-Host "[OK] UV installed successfully!" -ForegroundColor Green
        
        # Verify installation
        $uvVersion = uv --version 2>&1
        Write-Host "   Version: $uvVersion" -ForegroundColor Cyan
        $uvInstalled = $true
    } catch {
        Write-Host "[WARNING] Failed to install UV automatically" -ForegroundColor Yellow
        Write-Host "   Falling back to pip (will be slower)" -ForegroundColor Yellow
        Write-Host ""
        $uvInstalled = $false
    }
}

Write-Host ""

# ==============================================================================
# SETUP BACKEND ENVIRONMENT
# ==============================================================================

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[BACKEND] Setting up ML environment" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Location: $BACKEND_ENV" -ForegroundColor Yellow
Write-Host ""

$skipBackend = $false

# Check if environment already exists
if (Test-Path $BACKEND_ENV) {
    Write-Host "[WARNING] Backend environment already exists!" -ForegroundColor Yellow
    $response = Read-Host "   Delete and recreate? (y/n)"
    if ($response -eq "y") {
        # Use the robust deletion function
        $deleted = Remove-LockedDirectory -Path $BACKEND_ENV -Name "Backend"
        
        if (-not $deleted) {
            Write-Host "[ERROR] Failed to remove backend environment" -ForegroundColor Red
            Write-Host "[SKIP] Cannot proceed with backend setup" -ForegroundColor Cyan
            $skipBackend = $true
        }
    } else {
        Write-Host "[SKIP] Keeping existing backend environment" -ForegroundColor Cyan
        $skipBackend = $true
    }
}

if (-not $skipBackend) {
    # Create virtual environment
    Write-Host ""
    Write-Host "[*] Creating virtual environment..." -ForegroundColor Yellow
    & $pythonCmd -m venv $BACKEND_ENV
    
    if (-not (Test-Path $BACKEND_ENV)) {
        Write-Host "[ERROR] Failed to create backend environment!" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "[OK] Virtual environment created" -ForegroundColor Green
    Write-Host ""
    
    # Activate and install dependencies
    $activateScript = Join-Path $BACKEND_ENV "Scripts\Activate.ps1"
    
    Write-Host "[*] Installing dependencies (this may take 1-2 minutes with UV)..." -ForegroundColor Yellow
    Write-Host "   Requirements: finrag_ml_tg1\environments\requirements.txt" -ForegroundColor Cyan
    Write-Host ""
    
    $requirementsFile = Join-Path $BACKEND_DIR "environments\requirements.txt"
    
    if ($uvInstalled) {
        # Use UV for fast installation
        Write-Host "[UV] Using fast package installer..." -ForegroundColor Cyan
        & $activateScript
        uv pip install -r $requirementsFile
    } else {
        # Fallback to pip
        Write-Host "[PIP] Using standard pip (slower)..." -ForegroundColor Yellow
        & $activateScript
        python -m pip install --upgrade pip
        pip install -r $requirementsFile
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "[OK] Backend dependencies installed successfully!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[ERROR] Failed to install backend dependencies!" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# ==============================================================================
# SETUP FRONTEND ENVIRONMENT
# ==============================================================================

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[FRONTEND] Setting up UI environment" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Location: $FRONTEND_ENV" -ForegroundColor Yellow
Write-Host ""

$skipFrontend = $false

# Check if environment already exists
if (Test-Path $FRONTEND_ENV) {
    Write-Host "[WARNING] Frontend environment already exists!" -ForegroundColor Yellow
    $response = Read-Host "   Delete and recreate? (y/n)"
    if ($response -eq "y") {
        # Use the robust deletion function
        $deleted = Remove-LockedDirectory -Path $FRONTEND_ENV -Name "Frontend"
        
        if (-not $deleted) {
            Write-Host "[ERROR] Failed to remove frontend environment" -ForegroundColor Red
            Write-Host "[SKIP] Cannot proceed with frontend setup" -ForegroundColor Cyan
            $skipFrontend = $true
        }
    } else {
        Write-Host "[SKIP] Keeping existing frontend environment" -ForegroundColor Cyan
        $skipFrontend = $true
    }
}

if (-not $skipFrontend) {
    # Create virtual environment
    Write-Host ""
    Write-Host "[*] Creating virtual environment..." -ForegroundColor Yellow
    & $pythonCmd -m venv $FRONTEND_ENV
    
    if (-not (Test-Path $FRONTEND_ENV)) {
        Write-Host "[ERROR] Failed to create frontend environment!" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "[OK] Virtual environment created" -ForegroundColor Green
    Write-Host ""
    
    # Activate and install dependencies
    $activateScript = Join-Path $FRONTEND_ENV "Scripts\Activate.ps1"
    
    Write-Host "[*] Installing dependencies (this should be fast)..." -ForegroundColor Yellow
    Write-Host "   Requirements: serving\frontend\requirements.txt" -ForegroundColor Cyan
    Write-Host ""
    
    $requirementsFile = Join-Path $FRONTEND_DIR "requirements.txt"
    
    if ($uvInstalled) {
        # Use UV for fast installation
        Write-Host "[UV] Using fast package installer..." -ForegroundColor Cyan
        & $activateScript
        uv pip install -r $requirementsFile
    } else {
        # Fallback to pip
        Write-Host "[PIP] Using standard pip..." -ForegroundColor Yellow
        & $activateScript
        python -m pip install --upgrade pip
        pip install -r $requirementsFile
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "[OK] Frontend dependencies installed successfully!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[ERROR] Failed to install frontend dependencies!" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# ==============================================================================
# VERIFY AWS CREDENTIALS
# ==============================================================================

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[CONFIG] Checking AWS credentials" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$awsCredsFile = Join-Path $BACKEND_DIR ".aws_secrets\aws_credentials.env"

if (Test-Path $awsCredsFile) {
    Write-Host "[OK] AWS credentials file found" -ForegroundColor Green
    Write-Host "   Location: $awsCredsFile" -ForegroundColor Cyan
} else {
    Write-Host "[WARNING] AWS credentials file not found!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Expected location: $awsCredsFile" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Please create this file with your AWS credentials:" -ForegroundColor White
    Write-Host "   AWS_ACCESS_KEY_ID=your_key_here" -ForegroundColor Cyan
    Write-Host "   AWS_SECRET_ACCESS_KEY=your_secret_here" -ForegroundColor Cyan
    Write-Host "   AWS_REGION=us-east-1" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   The backend will not work without AWS credentials!" -ForegroundColor Red
}

Write-Host ""

# ==============================================================================
# CLEANUP OLD RENAMED ENVIRONMENTS (OPTIONAL)
# ==============================================================================

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[CLEANUP] Checking for old renamed environments" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$oldDirs = Get-ChildItem -Path $SCRIPT_DIR -Recurse -Directory -Filter "*.old_*" -ErrorAction SilentlyContinue

if ($oldDirs.Count -gt 0) {
    Write-Host "[INFO] Found $($oldDirs.Count) old renamed environment(s)" -ForegroundColor Yellow
    foreach ($dir in $oldDirs) {
        Write-Host "   - $($dir.FullName)" -ForegroundColor Cyan
    }
    Write-Host ""
    $response = Read-Host "   Delete these old directories? (y/n)"
    if ($response -eq "y") {
        foreach ($dir in $oldDirs) {
            try {
                Remove-Item -Recurse -Force $dir.FullName -ErrorAction Stop
                Write-Host "[OK] Deleted: $($dir.Name)" -ForegroundColor Green
            } catch {
                Write-Host "[WARNING] Could not delete: $($dir.Name)" -ForegroundColor Yellow
            }
        }
    }
} else {
    Write-Host "[OK] No old environments to clean up" -ForegroundColor Green
}

Write-Host ""

# ==============================================================================
# COMPLETION
# ==============================================================================

Write-Host "============================================================" -ForegroundColor Green
Write-Host "[SUCCESS] FinRAG Setup Complete!" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Environment Locations:" -ForegroundColor Yellow
Write-Host "   Backend:  $BACKEND_ENV" -ForegroundColor Cyan
Write-Host "   Frontend: $FRONTEND_ENV" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "   1. Verify AWS credentials are configured" -ForegroundColor White
Write-Host "   2. Run 'start_finrag.bat' to launch FinRAG" -ForegroundColor White
Write-Host "   3. Browser will auto-open to http://localhost:8501" -ForegroundColor White
Write-Host ""
Write-Host "[READY] Setup complete! You can now start FinRAG." -ForegroundColor Green
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")