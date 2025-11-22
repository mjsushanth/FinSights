from backend.models import QueryRequest, QueryResponse
from backend.config import get_config

# Test models
request = QueryRequest(question="What was Apple's revenue?")
print(f"✅ Valid request: {request.question}")

# Test config
config = get_config()
print(f"✅ Model root: {config.model_root}")
print(f"✅ Backend port: {config.backend_port}")


## python .\backend\test_models_01.py

"""
cd ModelPipeline/serving
..\finrag_ml_tg1\venv_ml_rag\Scripts\Activate.ps1
python -m backend.test_models_01
"""

