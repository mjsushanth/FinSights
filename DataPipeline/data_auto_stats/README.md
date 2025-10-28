# SEC Filings Data Validation Pipeline

A data validation and statistics generation system for SEC filings using Great Expectations.

## Quick Start

### 1. Install Dependencies

```bash
# Using conda (recommended)
conda env create -f environment.yml
conda activate data_validation_env
```

### 2. Configure (Optional)

**AWS Credentials:**
```bash
# Edit .aws_secrets with AWS credentials. Please reach out to any team member of Group 4 for the access keys
```

**Email Alerts:**
```bash
# Edit .env.email with your own receiver email address
```

### 3. Run Validation

**Phase 1 - Data Validation (20 columns, raw data)**

```bash
python src/run_validation.py
```

**Phase 2 - Statistics Generation (24 columns, final data)**

```bash
python src/run_statistics.py
```

### 4. Check Results

- Results stored in: `outputs/`
- Email alerts sent automatically (if configured)

## What Each Phase Does

**Phase 1**: Validates 20-column raw data, returns pass/fail with quality score
**Phase 2**: Generates comprehensive statistics on 24-column processed data

**Note**: Docker/Airflow integration coming soon.
