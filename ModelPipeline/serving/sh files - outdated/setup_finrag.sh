#!/bin/bash
# setup_finrag.sh
# FinRAG Setup Script for Mac/Linux
# Automates environment creation and dependency installation using UV

# ==============================================================================
# CONFIGURATION
# ==============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/finrag_ml_tg1"
FRONTEND_DIR="$SCRIPT_DIR/serving/frontend"
BACKEND_ENV="$BACKEND_DIR/venv_ml_rag"
FRONTEND_ENV="$FRONTEND_DIR/venv_frontend"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# ==============================================================================
# BANNER
# ==============================================================================

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${WHITE}           FinRAG Setup - Environment Configuration         ${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# ==============================================================================
# CHECK PYTHON
# ==============================================================================

echo -e "${YELLOW}[*] Checking Python installation...${NC}"

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo $version | cut -d. -f1)
        minor=$(echo $version | cut -d. -f2)
        
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON_CMD=$cmd
            echo -e "${GREEN}[OK] Found Python: $($cmd --version)${NC}"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}[ERROR] Python 3.11+ not found!${NC}"
    echo -e "${YELLOW}   Please install Python 3.11 or higher${NC}"
    exit 1
fi

echo ""

# ==============================================================================
# CHECK/INSTALL UV
# ==============================================================================

echo -e "${YELLOW}[*] Checking for UV package installer...${NC}"

UV_INSTALLED=false
if command -v uv &> /dev/null; then
    UV_VERSION=$(uv --version 2>&1)
    echo -e "${GREEN}[OK] UV already installed: $UV_VERSION${NC}"
    UV_INSTALLED=true
else
    echo -e "${YELLOW}[INFO] UV not found, will install...${NC}"
fi

if [ "$UV_INSTALLED" = false ]; then
    echo ""
    echo -e "${CYAN}[*] Installing UV (fast package installer)...${NC}"
    echo -e "${WHITE}   This will make dependency installation 10-20x faster!${NC}"
    echo ""
    
    # Install UV using the official installer
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add UV to PATH for current session
    export PATH="$HOME/.cargo/bin:$PATH"
    
    if command -v uv &> /dev/null; then
        echo -e "${GREEN}[OK] UV installed successfully!${NC}"
        UV_VERSION=$(uv --version 2>&1)
        echo -e "${CYAN}   Version: $UV_VERSION${NC}"
        UV_INSTALLED=true
    else
        echo -e "${YELLOW}[WARNING] Failed to install UV automatically${NC}"
        echo -e "${YELLOW}   Falling back to pip (will be slower)${NC}"
        echo ""
        UV_INSTALLED=false
    fi
fi

echo ""

# ==============================================================================
# SETUP BACKEND ENVIRONMENT
# ==============================================================================

echo -e "${CYAN}============================================================${NC}"
echo -e "${WHITE}[BACKEND] Setting up ML environment${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo -e "${YELLOW}   Location: $BACKEND_ENV${NC}"
echo ""

SKIP_BACKEND=false

# Check if environment already exists
if [ -d "$BACKEND_ENV" ]; then
    echo -e "${YELLOW}[WARNING] Backend environment already exists!${NC}"
    read -p "   Delete and recreate? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}[*] Removing existing environment...${NC}"
        rm -rf "$BACKEND_ENV"
    else
        echo -e "${CYAN}[SKIP] Keeping existing backend environment${NC}"
        SKIP_BACKEND=true
    fi
fi

if [ "$SKIP_BACKEND" = false ]; then
    # Create virtual environment
    echo -e "${YELLOW}[*] Creating virtual environment...${NC}"
    $PYTHON_CMD -m venv "$BACKEND_ENV"
    
    if [ ! -d "$BACKEND_ENV" ]; then
        echo -e "${RED}[ERROR] Failed to create backend environment!${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}[OK] Virtual environment created${NC}"
    echo ""
    
    # Activate and install dependencies
    source "$BACKEND_ENV/bin/activate"
    
    echo -e "${YELLOW}[*] Installing dependencies (this may take 1-2 minutes with UV)...${NC}"
    echo -e "${CYAN}   Requirements: finrag_ml_tg1/environments/requirements.txt${NC}"
    echo ""
    
    REQUIREMENTS_FILE="$BACKEND_DIR/environments/requirements.txt"
    
    if [ "$UV_INSTALLED" = true ]; then
        # Use UV for fast installation
        echo -e "${CYAN}[UV] Using fast package installer...${NC}"
        uv pip install -r "$REQUIREMENTS_FILE"
    else
        # Fallback to pip
        echo -e "${YELLOW}[PIP] Using standard pip (slower)...${NC}"
        python -m pip install --upgrade pip
        pip install -r "$REQUIREMENTS_FILE"
    fi
    
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}[OK] Backend dependencies installed successfully!${NC}"
    else
        echo ""
        echo -e "${RED}[ERROR] Failed to install backend dependencies!${NC}"
        exit 1
    fi
    
    deactivate
fi

echo ""

# ==============================================================================
# SETUP FRONTEND ENVIRONMENT
# ==============================================================================

echo -e "${CYAN}============================================================${NC}"
echo -e "${WHITE}[FRONTEND] Setting up UI environment${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo -e "${YELLOW}   Location: $FRONTEND_ENV${NC}"
echo ""

SKIP_FRONTEND=false

# Check if environment already exists
if [ -d "$FRONTEND_ENV" ]; then
    echo -e "${YELLOW}[WARNING] Frontend environment already exists!${NC}"
    read -p "   Delete and recreate? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}[*] Removing existing environment...${NC}"
        rm -rf "$FRONTEND_ENV"
    else
        echo -e "${CYAN}[SKIP] Keeping existing frontend environment${NC}"
        SKIP_FRONTEND=true
    fi
fi

if [ "$SKIP_FRONTEND" = false ]; then
    # Create virtual environment
    echo -e "${YELLOW}[*] Creating virtual environment...${NC}"
    $PYTHON_CMD -m venv "$FRONTEND_ENV"
    
    if [ ! -d "$FRONTEND_ENV" ]; then
        echo -e "${RED}[ERROR] Failed to create frontend environment!${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}[OK] Virtual environment created${NC}"
    echo ""
    
    # Activate and install dependencies
    source "$FRONTEND_ENV/bin/activate"
    
    echo -e "${YELLOW}[*] Installing dependencies (this should be fast)...${NC}"
    echo -e "${CYAN}   Requirements: serving/frontend/requirements.txt${NC}"
    echo ""
    
    REQUIREMENTS_FILE="$FRONTEND_DIR/requirements.txt"
    
    if [ "$UV_INSTALLED" = true ]; then
        # Use UV for fast installation
        echo -e "${CYAN}[UV] Using fast package installer...${NC}"
        uv pip install -r "$REQUIREMENTS_FILE"
    else
        # Fallback to pip
        echo -e "${YELLOW}[PIP] Using standard pip...${NC}"
        python -m pip install --upgrade pip
        pip install -r "$REQUIREMENTS_FILE"
    fi
    
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}[OK] Frontend dependencies installed successfully!${NC}"
    else
        echo ""
        echo -e "${RED}[ERROR] Failed to install frontend dependencies!${NC}"
        exit 1
    fi
    
    deactivate
fi

echo ""

# ==============================================================================
# VERIFY AWS CREDENTIALS
# ==============================================================================

echo -e "${CYAN}============================================================${NC}"
echo -e "${WHITE}[CONFIG] Checking AWS credentials${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

AWS_CREDS_FILE="$BACKEND_DIR/.aws_secrets/aws_credentials.env"

if [ -f "$AWS_CREDS_FILE" ]; then
    echo -e "${GREEN}[OK] AWS credentials file found${NC}"
    echo -e "${CYAN}   Location: $AWS_CREDS_FILE${NC}"
else
    echo -e "${YELLOW}[WARNING] AWS credentials file not found!${NC}"
    echo ""
    echo -e "${YELLOW}   Expected location: $AWS_CREDS_FILE${NC}"
    echo ""
    echo -e "${WHITE}   Please create this file with your AWS credentials:${NC}"
    echo -e "${CYAN}   AWS_ACCESS_KEY_ID=your_key_here${NC}"
    echo -e "${CYAN}   AWS_SECRET_ACCESS_KEY=your_secret_here${NC}"
    echo -e "${CYAN}   AWS_REGION=us-east-1${NC}"
    echo ""
    echo -e "${RED}   The backend will not work without AWS credentials!${NC}"
fi

echo ""

# ==============================================================================
# MAKE STARTUP SCRIPT EXECUTABLE
# ==============================================================================

echo -e "${CYAN}============================================================${NC}"
echo -e "${WHITE}[CONFIG] Making startup script executable${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

STARTUP_SCRIPT="$SCRIPT_DIR/start_finrag.sh"

if [ -f "$STARTUP_SCRIPT" ]; then
    chmod +x "$STARTUP_SCRIPT"
    echo -e "${GREEN}[OK] Startup script is now executable${NC}"
    echo -e "${CYAN}   You can double-click start_finrag.sh to launch FinRAG${NC}"
else
    echo -e "${YELLOW}[WARNING] Startup script not found: $STARTUP_SCRIPT${NC}"
fi

echo ""

# ==============================================================================
# COMPLETION
# ==============================================================================

echo -e "${GREEN}============================================================${NC}"
echo -e "${WHITE}[SUCCESS] FinRAG Setup Complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "${YELLOW}Environment Locations:${NC}"
echo -e "${CYAN}   Backend:  $BACKEND_ENV${NC}"
echo -e "${CYAN}   Frontend: $FRONTEND_ENV${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "${WHITE}   1. Verify AWS credentials are configured${NC}"
echo -e "${WHITE}   2. Run './start_finrag.sh' to launch FinRAG${NC}"
echo -e "${WHITE}   3. Browser will auto-open to http://localhost:8501${NC}"
echo ""
echo -e "${GREEN}[READY] Setup complete! You can now start FinRAG.${NC}"
echo ""