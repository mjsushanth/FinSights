"""
Schema Inspector for S3 Parquet Files
Compare historical and incremental data schemas with smart matching
"""

import sys
from pathlib import Path
import polars as pl

# Add project root
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# Import config (credentials loaded automatically!)
sys.path.append(str(Path(__file__).parent.parent / 'etl'))

from src_aws_etl.etl.config_loader import ETLConfig
from src_aws_etl.etl.preflight_check import PreflightChecker


# Column mapping rules
COLUMN_MAPPINGS = {
    'SIC': 'sic',
    'section_item': 'section_name',
}

# Derived columns (can be computed, not critical for merge)
DERIVED_COLUMNS = {
    'cik_int', 'has_comparison', 'has_numbers', 'likely_kpi',
    'row_hash', 'tickers', 'sentence_index',
}


def normalize_column_name(col):
    """Normalize column name: trim whitespace, uppercase"""
    return col.strip().upper()


def apply_mapping(col, mappings):
    """Apply column mapping rules"""
    return mappings.get(col, col)


def inspect_schemas():
    """Load and display schemas with smart comparison"""
    
    # Load config (credentials auto-loaded via fallback!)
    config = ETLConfig()
    
    # Get storage options from config
    storage_options = config.get_storage_options()
    
    print("=" * 100)
    print("SCHEMA INSPECTOR - Historical vs Incremental")
    print("=" * 100)
    
    # Get S3 URIs
    hist_uri = config.s3_uri(config.hist_path)
    incr_uri = config.s3_uri(config.incr_path)
    
    print(f"\n📁 Historical: {config.hist_path}")
    print(f"📁 Incremental: {config.incr_path}")
    
    # Read schemas
    print("\n⏳ Reading schemas...")
    hist_df = pl.read_parquet(hist_uri, n_rows=1, storage_options=storage_options)
    incr_df = pl.read_parquet(incr_uri, n_rows=1, storage_options=storage_options)
    
    hist_schema = hist_df.schema
    incr_schema = incr_df.schema
    
    print(f"✓ Historical: {len(hist_schema)} columns")
    print(f"✓ Incremental: {len(incr_schema)} columns")
    
    # Apply column mappings to incremental
    incr_mapped = {}
    for col, dtype in incr_schema.items():
        mapped_col = apply_mapping(col, COLUMN_MAPPINGS)
        incr_mapped[mapped_col] = (col, dtype)
    
    # Get all unique columns (after mapping)
    all_cols = sorted(set(hist_schema.keys()) | set(incr_mapped.keys()))
    
    print("\n" + "=" * 100)
    print("COLUMN MAPPING RULES APPLIED")
    print("=" * 100)
    for incr_col, hist_col in COLUMN_MAPPINGS.items():
        if incr_col in incr_schema:
            print(f"  {incr_col:20s} → {hist_col:20s} (Mapped)")
    
    print("\n" + "=" * 100)
    print("COLUMN COMPARISON (Side-by-Side)")
    print("=" * 100)
    print(f"{'Column Name':<30} | {'Historical Type':<35} | {'Incremental Type':<35} | {'Status':<15}")
    print("-" * 100)
    
    matches = []
    hist_only = []
    incr_only = []
    type_diffs = []
    
    for col in all_cols:
        hist_type = str(hist_schema.get(col, "MISSING"))
        
        # Check if incremental has this column (after mapping)
        incr_orig_col, incr_type_val = incr_mapped.get(col, (None, None))
        incr_type = str(incr_type_val) if incr_type_val else "MISSING"
        
        # Normalize datetime types for comparison
        hist_type_norm = hist_type.replace('time_unit=\'us\'', 'TIME_UNIT').replace('time_unit=\'ns\'', 'TIME_UNIT')
        incr_type_norm = incr_type.replace('time_unit=\'us\'', 'TIME_UNIT').replace('time_unit=\'ns\'', 'TIME_UNIT')
        hist_type_norm = hist_type_norm.replace('time_zone=\'UTC\'', 'TZ').replace('time_zone=None', 'TZ')
        incr_type_norm = incr_type_norm.replace('time_zone=\'UTC\'', 'TZ').replace('time_zone=None', 'TZ')
        
        # Determine status
        if col not in hist_schema:
            status = " Derived" if col in DERIVED_COLUMNS else " Incr Only"
            incr_only.append(col)
        elif incr_orig_col is None:
            status = " Derived" if col in DERIVED_COLUMNS else " Hist Only"
            hist_only.append(col)
        elif hist_type_norm == incr_type_norm:
            status = " Match"
            matches.append(col)
        else:
            if 'Datetime' in hist_type and 'Datetime' in incr_type:
                status = " Match"
            else:
                status = " Type Diff"
            type_diffs.append(col)
        
        # Show mapped name if different
        display_col = col
        if incr_orig_col and incr_orig_col != col:
            display_col = f"{col} ({incr_orig_col}→)"
        
        print(f"{display_col:<30} | {hist_type:<35} | {incr_type:<35} | {status:<15}")
    
    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    
    print(f"\nColumn Counts:")
    print(f"  Matching columns: {len(matches)}")
    print(f"  Derived (OK to differ): {len([c for c in (hist_only + incr_only) if c in DERIVED_COLUMNS])}")
    
    # Derived columns info
    derived_present = [c for c in (hist_only + incr_only) if c in DERIVED_COLUMNS]
    if derived_present:
        print(f"\nDerived Columns (computed during merge):")
        for col in sorted(derived_present):
            if col == 'cik_int':
                print(f"  - {col:<30} → CAST(cik AS INT)")
            elif col == 'row_hash':
                print(f"  - {col:<30} → MD5(sentenceID || sentence)")
            elif col == 'tickers':
                print(f"  - {col:<30} → Company lookup")
            elif col in ['has_comparison', 'has_numbers', 'likely_kpi']:
                print(f"  - {col:<30} → Text analysis")
            elif col == 'sentence_index':
                print(f"  - {col:<30} → Position/ordering")
    
    # Final verdict
    print("\n" + "=" * 100)
    print("MERGE COMPATIBILITY")
    print("=" * 100)
    
    critical_hist = [c for c in hist_only if c not in DERIVED_COLUMNS]
    critical_incr = [c for c in incr_only if c not in DERIVED_COLUMNS]
    critical_type = [c for c in type_diffs if 'Datetime' not in str(hist_schema.get(c, ''))]
    
    if not critical_hist and not critical_incr and not critical_type:
        print("\n SCHEMAS COMPATIBLE FOR MERGE!")
        print("   - All critical columns present")
        print("   - Derived columns will be computed")
        print("\n Ready to proceed with merge pipeline!")
    else:
        print(f"\n ISSUES NEED ATTENTION:")
        if critical_hist:
            print(f"   Columns only in Historical: {critical_hist}")
        if critical_incr:
            print(f"   Columns only in Incremental: {critical_incr}")
        if critical_type:
            print(f"   Type mismatches: {critical_type}")
    
    print("=" * 100)


if __name__ == "__main__":
    try:
        inspect_schemas()
    except Exception as e:
        print(f"\n Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)