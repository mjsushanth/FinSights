import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: real-network tests hitting live SEC EDGAR (slow, needs EDGAR_IDENTITY)"
    )
