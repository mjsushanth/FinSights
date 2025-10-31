import logging
import os
import pandas as pd
import numpy as np

def setup_logger(name="pipeline_logger", log_file="pipeline.log", level=logging.INFO):
    """Configures a named logger for all modules."""
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", log_file)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # File handler
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Stream handler (console)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

def safe_div(numerator, denominator):
    """Safely divide two values, handling division by zero and NaN values."""
    if isinstance(numerator, pd.Series) and isinstance(denominator, pd.Series):
        result = numerator.div(denominator).replace([np.inf, -np.inf], np.nan)
        return result
    elif denominator == 0 or denominator is None or (isinstance(denominator, float) and np.isnan(denominator)):
        return 0.0
    elif numerator is None or (isinstance(numerator, float) and np.isnan(numerator)):
        return 0.0
    else:
        try:
            return numerator / denominator
        except (TypeError, ZeroDivisionError):
            return 0.0

# Example usage:
# logger = setup_logger()
# logger.info("Logger initialized successfully.")
