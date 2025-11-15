# Metric Pipeline

Standalone pipeline for extracting quantitative financial data from natural language queries.

## Features

- Extract ticker, year, and metric from natural language
- Query structured financial data
- Handle missing data gracefully
- Suggest alternative years when data unavailable

## Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Place your data file
cp /path/to/downloaded_data.json data/
```

## Usage

### Run the pipeline
```bash
python main.py
```

### Example queries
- "What is NVIDIA's revenue in the year 2024?"
- "MSFT total assets 2025"
- "Show me NVDA gross profit margin for 2025"

## Project Structure

- `config/` - Configuration and mappings
- `src/` - Core pipeline logic
- `data/` - Data files
- `tests/` - Unit tests