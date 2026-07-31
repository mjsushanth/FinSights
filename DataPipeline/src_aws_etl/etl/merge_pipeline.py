"""
FinRAG ETL Merge Pipeline - CORRECTED LOGIC
Merges base data (historical or previous final) with incremental data
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
import polars as pl
import hashlib
import tempfile
from io import StringIO

project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src_aws_etl.etl.config_loader import ETLConfig
from src_aws_etl.etl.preflight_check import PreflightChecker



class MergePipeline:
    """Handles data merge operations"""
    
    def __init__(self):
        # Load config (credentials loaded automatically!)
        self.config = ETLConfig()
        
        # Get storage options from config
        self.storage_options = self.config.get_storage_options()
        
        # Initialize S3 client ONCE (reuse throughout class)
        self.s3 = self.config.get_s3_client()
        
        # Tracking for logs
        self.stats = {}
    
    def run(self):
        """Execute full merge pipeline"""
        start_time = datetime.now()
        
        print("=" * 70)
        print("FINRAG ETL MERGE PIPELINE")
        print("=" * 70)
        print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # ================================================================
            # STEP 1: PRE-FLIGHT CHECKS
            # ================================================================
            checker = PreflightChecker()
            if not checker.run_checks():
                raise RuntimeError("Pre-flight checks failed!")
            
            # Check if final fact table exists
            final_exists, final_size = checker.file_exists(self.config.final_path)
            
            # Archive existing final if it exists
            if final_exists:
                checker.archive_existing()
            
            # ================================================================
            # STEP 2: DETERMINE MERGE STRATEGY
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 2: DETERMINE MERGE INPUTS")
            print("=" * 70)
            
            if final_exists:
                # NORMAL RUN: Merge existing final + new incremental
                print("\n✓ Final fact table EXISTS")
                print(f"  Size: {final_size:.2f} MB")
                print("  Strategy: FINAL + INCREMENTAL (incremental update)")
                base_path = self.config.final_path
                base_label = "Current Final"
                self.stats['merge_type'] = 'incremental_update'
            else:
                # FIRST RUN: Bootstrap from historical
                print("\n✓ Final fact table DOES NOT EXIST (first run)")
                print("  Strategy: HISTORICAL + INCREMENTAL (bootstrap)")
                base_path = self.config.hist_path
                base_label = "Historical Baseline"
                self.stats['merge_type'] = 'initial_bootstrap'
            
            # ================================================================
            # STEP 3: LOAD DATA FROM S3
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 3: LOADING DATA")
            print("=" * 70)
            
            base_uri = self.config.s3_uri(base_path)
            incr_uri = self.config.s3_uri(self.config.incr_path)
            
            print(f"\n Reading {base_label}...")
            print(f"   {base_path}")
            base_df = pl.read_parquet(base_uri, storage_options=self.storage_options)
            self.stats['base_rows'] = len(base_df)
            print(f"   ✓ {len(base_df):,} rows")
            
            print(f"\n Reading incremental...")
            print(f"   {self.config.incr_path}")
            incr_df = pl.read_parquet(incr_uri, storage_options=self.storage_options)
            self.stats['incr_rows'] = len(incr_df)
            print(f"   ✓ {len(incr_df):,} rows")
            
            # ================================================================
            # STEP 4: TRANSFORM INCREMENTAL (Inline Schema Alignment)
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 4: TRANSFORM INCREMENTAL DATA")
            print("=" * 70)
            
            # Rename columns for alignment
            rename_map = {}
            
            if 'SIC' in incr_df.columns:
                rename_map['SIC'] = 'sic'
                print("  Renaming: SIC → sic")
            
            # Handle section_item → section_name (special case)
            if 'section_item' in incr_df.columns:
                if 'section_name' in incr_df.columns:
                    print("  Dropping existing section_name (section_item is canonical)")
                    incr_df = incr_df.drop('section_name')
                
                rename_map['section_item'] = 'section_name'
                print("  Mapping: section_item → section_name")
            
            if rename_map:
                incr_df = incr_df.rename(rename_map)
            
            # Drop columns not in base schema
            if 'sentence_index' in incr_df.columns:
                print("  Dropping: sentence_index (not in base schema)")
                incr_df = incr_df.drop('sentence_index')
            
            # Normalize datetime types (ns → us + UTC)
            print("  Normalizing datetime columns...")
            for col in incr_df.columns:
                if incr_df[col].dtype == pl.Datetime('ns'):
                    incr_df = incr_df.with_columns(
                        pl.col(col).dt.cast_time_unit('us').dt.replace_time_zone('UTC')
                    )
            
            # Add derived columns + align to base schema
            print("  Adding derived columns...")

            incr_df = incr_df.with_columns([
                pl.col('cik').cast(pl.Int32).alias('cik_int'),

                (pl.col('sentenceID') + pl.col('sentence'))
                    .map_elements(lambda x: hashlib.md5(x.encode()).hexdigest(), return_dtype=pl.String)
                    .alias('row_hash'),
            ])

            # Placeholder for text analysis features / company metadata - only
            # injected if the incremental source doesn't already provide them.
            # Newer incremental sources (e.g. src_edgar_incremental) compute
            # these for real; only fill with None for older sources that never
            # populated them at all.
            placeholder_defaults = {
                'has_numbers': pl.lit(None).cast(pl.Boolean),
                'has_comparison': pl.lit(None).cast(pl.Boolean),
                'likely_kpi': pl.lit(None).cast(pl.Boolean),
                'tickers': pl.lit(None).cast(pl.List(pl.String)),
            }
            missing_cols = [
                expr.alias(name) for name, expr in placeholder_defaults.items()
                if name not in incr_df.columns
            ]
            if missing_cols:
                incr_df = incr_df.with_columns(missing_cols)
            
            # Ensure column order matches base
            print("  Reordering columns...")
            incr_df = incr_df.select(base_df.columns)
            
            print("  ✓ Schema aligned!")
            
            # ================================================================
            # STEP 5: MERGE (CONCAT + DEDUPE)
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 5: MERGE DATA")
            print("=" * 70)
            
            print(f"  {base_label}: {len(base_df):,} rows")
            print(f"  Incremental: {len(incr_df):,} rows")

            # Replace on the exact (cik_int, report_year) key before
            # concatenating - NOT just sentenceID dedup. An incremental batch
            # that re-supplies a company-year already in base (e.g. a fresh
            # full-history rebuild for one company, or a newer pass at a
            # year already covered) will only PARTIALLY collide by
            # sentenceID if its sentence-splitting differs at all from
            # whatever produced the base rows - sentenceID-only dedup then
            # leaves the non-colliding remainder behind as stale orphan rows
            # mixed in with the new ones. Removing every base row whose
            # (cik_int, report_year) the incremental data touches, before
            # concatenating, avoids that regardless of splitting differences.
            replaced_keys = incr_df.select(['cik_int', 'report_year']).unique()
            base_df = base_df.join(replaced_keys, on=['cik_int', 'report_year'], how='anti')

            # Concatenate
            merged_df = pl.concat([base_df, incr_df])

            # Deduplicate on sentenceID as a final safety net (should be a
            # no-op given the replacement above; catches any real leftover
            # ID collisions instead of silently dropping data).
            print(f"\n Deduplicating on sentenceID...")
            merged_df = merged_df.unique(subset=['sentenceID'], keep='last')

            self.stats['duplicates_removed'] = len(base_df) + len(incr_df) - len(merged_df)
            self.stats['final_rows'] = len(merged_df)
            
            print(f"  ✓ Removed {self.stats['duplicates_removed']:,} duplicates")
            print(f"  ✓ Final: {len(merged_df):,} rows")
            
            # Sort for consistency
            merged_df = merged_df.sort(['report_year', 'sentenceID'])
            
            # ================================================================
            # STEP 6: VALIDATE
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 6: VALIDATION")
            print("=" * 70)
            
            # Check 1: Row count
            assert len(merged_df) <= len(base_df) + len(incr_df), "Row count exceeds inputs!"
            print("  ✓ Row count valid")
            
            # Check 2: No null primary keys
            assert merged_df['sentenceID'].null_count() == 0, "Null sentenceIDs found!"
            print("  ✓ No null sentenceIDs")
            
            # Check 3: No duplicates
            assert merged_df['sentenceID'].n_unique() == len(merged_df), "Duplicates found!"
            print("  ✓ All sentenceIDs unique")
            
            # Stats
            self.stats['companies'] = merged_df['name'].n_unique()
            self.stats['year_min'] = int(merged_df['report_year'].min())
            self.stats['year_max'] = int(merged_df['report_year'].max())
            self.stats['size_mb'] = round(merged_df.estimated_size('mb'), 2)
            
            print(f"\n  Companies: {self.stats['companies']}")
            print(f"  Year range: {self.stats['year_min']} - {self.stats['year_max']}")
            print(f"  Size: {self.stats['size_mb']} MB")
            
            # ================================================================
            # STEP 7: WRITE TO S3
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 7: WRITE OUTPUT")
            print("=" * 70)
            
            print(f"\n Writing to S3...")
            
            # Write to local temp file first
            with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
                tmp_path = tmp.name
                merged_df.write_parquet(tmp_path, compression=self.config.compression)
            
            # Upload to S3 using instance S3 client
            self.s3.upload_file(tmp_path, self.config.bucket, self.config.final_path)
            print(f"  ✓ Written: {self.config.final_path}")

            # ================================================================
            # STEP 7b: SYNC LOCAL DATA_CACHE
            # ================================================================
            # Cloud is the source of truth; local data_cache/ copies are a
            # brief, automatic mirror of it - not a separate thing someone
            # has to remember to update by hand after every merge.
            print("\n" + "=" * 70)
            print("STEP 7b: SYNC LOCAL DATA_CACHE")
            print("=" * 70)
            self.sync_local_data_cache(tmp_path)

            # Clean up temp file
            os.remove(tmp_path)

            # ================================================================
            # STEP 8: LOG SUCCESS
            # ================================================================
            end_time = datetime.now()
            self.stats['duration_sec'] = round((end_time - start_time).total_seconds(), 2)
            self.stats['timestamp'] = end_time.strftime('%Y-%m-%d %H:%M:%S')
            self.stats['status'] = 'SUCCESS'
            
            self.write_log()
            
            # Done!
            print("\n" + "=" * 70)
            print(" MERGE COMPLETED SUCCESSFULLY!")
            print("=" * 70)
            print(f"  Merge type: {self.stats['merge_type']}")
            print(f"  Duration: {self.stats['duration_sec']} seconds")
            print("=" * 70)
            
            return True
        
        except Exception as e:
            # Log failure
            end_time = datetime.now()
            self.stats['duration_sec'] = round((end_time - start_time).total_seconds(), 2)
            self.stats['timestamp'] = end_time.strftime('%Y-%m-%d %H:%M:%S')
            self.stats['status'] = 'FAILED'
            self.stats['error'] = str(e)
            
            self.write_log()
            
            print("\n" + "=" * 70)
            print(" MERGE FAILED!")
            print("=" * 70)
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def sync_local_data_cache(self, written_local_path):
        """Copies the just-uploaded final table to the two local data_cache
        mirrors - DataPipeline's own copy and ModelPipeline's RAG-serving
        copy. Best-effort: a sync failure is logged but does not fail the
        merge, since S3 (already written above) remains the real result."""
        filename = Path(self.config.final_path).name
        project_root = Path(__file__).parent.parent.parent  # DataPipeline/
        targets = [
            project_root / "data_cache" / "stage1_facts" / filename,
            project_root.parent / "ModelPipeline" / "finrag_ml_tg1" / "data_cache" / "stage1_facts" / filename,
        ]
        for target in targets:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(written_local_path, target)
                print(f"  ✓ Synced: {target}")
            except Exception as e:
                print(f"  Warning: local sync failed for {target} - {e}")

    def write_log(self):
        """Append merge results to CSV log file on S3"""
        print("\n Writing log entry...")
        
        log_key = f"{self.config.log_path}/merge_history.csv"
        
        # Create log entry
        log_entry = pl.DataFrame({
            'timestamp': [self.stats.get('timestamp', '')],
            'status': [self.stats.get('status', 'UNKNOWN')],
            'merge_type': [self.stats.get('merge_type', 'unknown')],
            'base_rows': [self.stats.get('base_rows', 0)],
            'incr_rows': [self.stats.get('incr_rows', 0)],
            'final_rows': [self.stats.get('final_rows', 0)],
            'duplicates_removed': [self.stats.get('duplicates_removed', 0)],
            'companies': [self.stats.get('companies', 0)],
            'year_min': [self.stats.get('year_min', 0)],
            'year_max': [self.stats.get('year_max', 0)],
            'size_mb': [self.stats.get('size_mb', 0)],
            'duration_sec': [self.stats.get('duration_sec', 0)],
            'error': [self.stats.get('error', '')]
        })
        
        try:
            # Try to read existing log from S3
            obj = self.s3.get_object(Bucket=self.config.bucket, Key=log_key)
            existing_csv = obj['Body'].read().decode('utf-8')
            existing_log = pl.read_csv(StringIO(existing_csv))
            updated_log = pl.concat([existing_log, log_entry])
        except self.s3.exceptions.NoSuchKey:
            # First run - create new log
            updated_log = log_entry
        except Exception as e:
            print(f"  Warning: Could not read existing log ({e}), creating new one")
            updated_log = log_entry
        
        # Write CSV to string buffer
        csv_buffer = StringIO()
        updated_log.write_csv(csv_buffer)
        
        # Upload to S3
        self.s3.put_object(
            Bucket=self.config.bucket,
            Key=log_key,
            Body=csv_buffer.getvalue().encode('utf-8')
        )
        
        print(f"  ✓ Log updated: {log_key}")


def main():
    """Run merge pipeline"""
    pipeline = MergePipeline()
    success = pipeline.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()