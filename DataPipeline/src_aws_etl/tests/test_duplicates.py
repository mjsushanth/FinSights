"""
Duplicate Checker - Quick analysis of Historical and Incremental files
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


def check_duplicates():
    """Quick duplicate analysis"""
    
    # Load config (credentials auto-loaded via fallback!)
    config = ETLConfig()
    
    # Get storage options from config
    storage_options = config.get_storage_options()
    
    print("=" * 70)
    print("DUPLICATE ANALYSIS")
    print("=" * 70)
    
    # Load data
    hist_uri = config.s3_uri(config.hist_path)
    incr_uri = config.s3_uri(config.incr_path)
    
    print(f"\n⏳ Loading data...")
    hist_df = pl.read_parquet(hist_uri, storage_options=storage_options)
    incr_df = pl.read_parquet(incr_uri, storage_options=storage_options)
    
    print(f"✓ Historical: {len(hist_df):,} rows")
    print(f"✓ Incremental: {len(incr_df):,} rows")
    
    # Check 1: Historical duplicates
    print("\n" + "=" * 70)
    print("CHECK 1: Historical File")
    print("=" * 70)
    
    hist_total = len(hist_df)
    hist_unique = hist_df['sentenceID'].n_unique()
    hist_dupes = hist_total - hist_unique
    
    print(f"  Total rows: {hist_total:,}")
    print(f"  Unique IDs: {hist_unique:,}")
    print(f"  Duplicates: {hist_dupes:,}")
    
    if hist_dupes > 0:
        print(f"  ⚠️  Internal duplicates found!")
    else:
        print(f"  finsight-venv Clean (no duplicates)")
    
    # Check 2: Incremental duplicates
    print("\n" + "=" * 70)
    print("CHECK 2: Incremental File")
    print("=" * 70)
    
    incr_total = len(incr_df)
    incr_unique = incr_df['sentenceID'].n_unique()
    incr_dupes = incr_total - incr_unique
    
    print(f"  Total rows: {incr_total:,}")
    print(f"  Unique IDs: {incr_unique:,}")
    print(f"  Duplicates: {incr_dupes:,}")
    
    if incr_dupes > 0:
        print(f"  ⚠️  Internal duplicates found!")
    else:
        print(f"  finsight-venv Clean (no duplicates)")
    
    # Check 3: Overlap
    print("\n" + "=" * 70)
    print("CHECK 3: Cross-File Overlap")
    print("=" * 70)
    
    hist_ids = set(hist_df['sentenceID'].to_list())
    incr_ids = set(incr_df['sentenceID'].to_list())
    overlap = hist_ids & incr_ids
    
    print(f"  Historical IDs: {len(hist_ids):,}")
    print(f"  Incremental IDs: {len(incr_ids):,}")
    print(f"  Overlapping: {len(overlap):,}")
    
    if len(overlap) > 0:
        overlap_pct = (len(overlap) / len(incr_ids)) * 100
        print(f"  Overlap: {overlap_pct:.1f}% of incremental")
        print(f"  finsight-venv  Expected (incremental updates historical)")
    else:
        print(f"  finsight-venv No overlap (100% new data)")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total_input = hist_total + incr_total
    total_unique = len(hist_ids | incr_ids)
    
    print(f"\nMerge Projection:")
    print(f"  Total input rows: {total_input:,}")
    print(f"  Expected output: {total_unique:,}")
    print(f"  Duplicates to remove: {total_input - total_unique:,}")
    
    print(f"\n Duplicate Sources:")
    print(f"  Internal (Historical): {hist_dupes:,}")
    print(f"  Internal (Incremental): {incr_dupes:,}")
    print(f"  Cross-file overlap: {len(overlap):,}")
    print(f"  Total: {hist_dupes + incr_dupes + len(overlap):,}")
    
    # Verdict
    print("\n" + "=" * 70)
    if hist_dupes == 0 and incr_dupes == 0:
        print("CLEAN: All duplicates from expected overlap")
    else:
        print("WARNING: Internal duplicates detected")
        if incr_dupes > 0:
            print(f"   Incremental file has {incr_dupes:,} duplicate rows")
            print(f"   Consider deduplicating at source")
    print("=" * 70)


if __name__ == "__main__":
    try:
        check_duplicates()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)