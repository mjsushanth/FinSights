import pandas as pd
import numpy as np
from datetime import datetime
import os

# -----------------------------
# Configuration
# -----------------------------
INPUT_FILE = "scripts/sentence/sec_rag_data/10k_sentences_cleaned.parquet"
OUTPUT_FILE = "scripts/sentence/sec_rag_data/10k_sentences_validated.parquet"
OUTPUT_CSV = "scripts/sentence/sec_rag_data/10k_sentences_validated.csv"
REPORT_FILE = "scripts/sentence/sec_rag_data/validation_report.txt"

# Validation thresholds
MIN_SENTENCE_LENGTH = 10  # Minimum characters
MAX_SENTENCE_LENGTH = 5000  # Maximum characters
MIN_WORD_COUNT = 3  # Minimum words per sentence


def validate_and_clean_data(df):
    """
    Comprehensive validation and cleaning of SEC filing data.
    Returns cleaned dataframe and validation report.
    """
    report = []
    initial_count = len(df)
    report.append(f"Initial row count: {initial_count:,}")
    report.append("=" * 60)
    
    # 1. Check for required columns
    required_cols = ['cik', 'sentence', 'section_name', 'filingDate', 'reportDate']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        report.append(f"⚠️  WARNING: Missing required columns: {missing_cols}")
    report.append(f"✅ Columns present: {list(df.columns)}")
    report.append("")
    
    # 2. Remove exact duplicate rows
    report.append("🔍 DUPLICATE REMOVAL")
    report.append("-" * 60)
    before_dedup = len(df)
    df = df.drop_duplicates()
    exact_dupes = before_dedup - len(df)
    report.append(f"Exact duplicate rows removed: {exact_dupes:,}")
    
    # 3. Remove duplicate sentences within same company/section
    if 'cik' in df.columns and 'section_name' in df.columns:
        before_sent_dedup = len(df)
        df = df.drop_duplicates(subset=['cik', 'section_name', 'sentence'], keep='first')
        sent_dupes = before_sent_dedup - len(df)
        report.append(f"Duplicate sentences (same CIK/section) removed: {sent_dupes:,}")
    
    report.append(f"Rows after deduplication: {len(df):,}")
    report.append("")
    
    # 4. Sentence quality checks
    report.append("🧹 SENTENCE QUALITY CHECKS")
    report.append("-" * 60)
    
    # Remove null/empty sentences
    before_null = len(df)
    df = df[df['sentence'].notna()]
    df = df[df['sentence'].str.strip() != '']
    null_removed = before_null - len(df)
    report.append(f"Null/empty sentences removed: {null_removed:,}")
    
    # Calculate sentence metrics
    df['sentence_length'] = df['sentence'].str.len()
    df['word_count'] = df['sentence'].str.split().str.len()
    
    # Remove too short sentences
    before_short = len(df)
    df = df[df['sentence_length'] >= MIN_SENTENCE_LENGTH]
    short_removed = before_short - len(df)
    report.append(f"Too short sentences removed (< {MIN_SENTENCE_LENGTH} chars): {short_removed:,}")
    
    # Remove too long sentences (likely parsing errors)
    before_long = len(df)
    df = df[df['sentence_length'] <= MAX_SENTENCE_LENGTH]
    long_removed = before_long - len(df)
    report.append(f"Too long sentences removed (> {MAX_SENTENCE_LENGTH} chars): {long_removed:,}")
    
    # Remove sentences with too few words
    before_words = len(df)
    df = df[df['word_count'] >= MIN_WORD_COUNT]
    word_removed = before_words - len(df)
    report.append(f"Low word count sentences removed (< {MIN_WORD_COUNT} words): {word_removed:,}")
    
    report.append(f"Rows after quality checks: {len(df):,}")
    report.append("")
    
    # 5. Data type validation and fixes
    report.append("🔧 DATA TYPE VALIDATION")
    report.append("-" * 60)
    
    # Fix CIK to integer
    if 'cik' in df.columns:
        try:
            df['cik'] = pd.to_numeric(df['cik'], errors='coerce')
            null_ciks = df['cik'].isna().sum()
            if null_ciks > 0:
                report.append(f"⚠️  Rows with invalid CIK: {null_ciks}")
                df = df[df['cik'].notna()]
            df['cik'] = df['cik'].astype(int)
            report.append(f"✅ CIK column converted to integer")
        except Exception as e:
            report.append(f"⚠️  Error converting CIK: {e}")
    
    # Fix dates
    for date_col in ['filingDate', 'reportDate']:
        if date_col in df.columns:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                null_dates = df[date_col].isna().sum()
                if null_dates > 0:
                    report.append(f"⚠️  Rows with invalid {date_col}: {null_dates}")
                report.append(f"✅ {date_col} column converted to datetime")
            except Exception as e:
                report.append(f"⚠️  Error converting {date_col}: {e}")
    
    # Fix section_ID to integer
    if 'section_ID' in df.columns:
        try:
            df['section_ID'] = pd.to_numeric(df['section_ID'], errors='coerce')
            df['section_ID'] = df['section_ID'].fillna(0).astype(int)
            report.append(f"✅ section_ID column converted to integer")
        except Exception as e:
            report.append(f"⚠️  Error converting section_ID: {e}")
    
    report.append("")
    
    # 6. Check for data anomalies
    report.append("🔍 DATA QUALITY CHECKS")
    report.append("-" * 60)
    
    # Check for suspiciously repetitive content
    if len(df) > 0:
        # Check for sentences that appear too many times (likely boilerplate)
        sentence_counts = df['sentence'].value_counts()
        high_freq = sentence_counts[sentence_counts > 100]
        if len(high_freq) > 0:
            report.append(f"⚠️  Found {len(high_freq)} sentences appearing >100 times")
            report.append(f"   Top repetitive sentence (appears {high_freq.iloc[0]} times):")
            report.append(f"   {sentence_counts.index[0][:100]}...")
            
            # Optionally remove highly repetitive boilerplate
            # df = df[~df['sentence'].isin(high_freq.index)]
    
    # Check for missing values
    for col in df.columns:
        null_count = df[col].isna().sum()
        if null_count > 0:
            null_pct = (null_count / len(df)) * 100
            report.append(f"   {col}: {null_count:,} nulls ({null_pct:.2f}%)")
    
    report.append("")
    
    # 7. Summary statistics
    report.append("📊 SUMMARY STATISTICS")
    report.append("-" * 60)
    report.append(f"Final row count: {len(df):,}")
    report.append(f"Total rows removed: {initial_count - len(df):,}")
    report.append(f"Retention rate: {(len(df) / initial_count * 100):.2f}%")
    report.append("")
    
    if 'cik' in df.columns:
        report.append(f"Unique companies (CIKs): {df['cik'].nunique():,}")
    
    if 'section_name' in df.columns:
        report.append(f"Unique sections: {df['section_name'].nunique()}")
        report.append("\nSection distribution:")
        for section, count in df['section_name'].value_counts().items():
            report.append(f"   {section}: {count:,}")
    
    if 'sentence_length' in df.columns:
        report.append(f"\nSentence length statistics:")
        report.append(f"   Mean: {df['sentence_length'].mean():.1f} characters")
        report.append(f"   Median: {df['sentence_length'].median():.1f} characters")
        report.append(f"   Min: {df['sentence_length'].min()}")
        report.append(f"   Max: {df['sentence_length'].max()}")
    
    if 'word_count' in df.columns:
        report.append(f"\nWord count statistics:")
        report.append(f"   Mean: {df['word_count'].mean():.1f} words")
        report.append(f"   Median: {df['word_count'].median():.1f} words")
    
    if 'filingDate' in df.columns and df['filingDate'].dtype == 'datetime64[ns]':
        report.append(f"\nDate range:")
        report.append(f"   Earliest filing: {df['filingDate'].min()}")
        report.append(f"   Latest filing: {df['filingDate'].max()}")
    
    # 8. Flag potential issues
    report.append("")
    report.append("⚠️  POTENTIAL ISSUES")
    report.append("-" * 60)
    
    issues_found = False
    
    # Check for very long sentences (possible parsing errors)
    if 'sentence_length' in df.columns:
        long_sentences = df[df['sentence_length'] > 2000]
        if len(long_sentences) > 0:
            report.append(f"   {len(long_sentences)} sentences > 2000 characters (may be parsing errors)")
            issues_found = True
    
    # Check for sentences with unusual character patterns
    if 'sentence' in df.columns:
        # Check for sentences with lots of numbers (might be tables)
        df['digit_ratio'] = df['sentence'].str.count(r'\d') / df['sentence_length']
        high_digit = df[df['digit_ratio'] > 0.3]
        if len(high_digit) > 0:
            report.append(f"   {len(high_digit)} sentences with >30% digits (may be tables/data)")
            issues_found = True
        df = df.drop(columns=['digit_ratio'])
    
    if not issues_found:
        report.append("   No major issues detected ✅")
    
    return df, report


def main():
    print("=" * 80)
    print("SEC FILING DATA VALIDATION & DEDUPLICATION")
    print("=" * 80)
    print()
    
    # Load data
    print(f"📂 Loading data from: {INPUT_FILE}")
    if not os.path.exists(INPUT_FILE):
        print(f"❌ ERROR: File not found: {INPUT_FILE}")
        return
    
    try:
        if INPUT_FILE.endswith('.parquet'):
            df = pd.read_parquet(INPUT_FILE)
        elif INPUT_FILE.endswith('.csv'):
            df = pd.read_csv(INPUT_FILE)
        else:
            print(f"❌ ERROR: Unsupported file format. Use .parquet or .csv")
            return
    except Exception as e:
        print(f"❌ ERROR loading file: {e}")
        return
    
    print(f"✅ Loaded {len(df):,} rows with {len(df.columns)} columns")
    print()
    
    # Validate and clean
    print("🔄 Running validation and cleaning pipeline...")
    print()
    df_cleaned, report = validate_and_clean_data(df)
    
    # Print report
    print("\n".join(report))
    
    # removing wrd_count and sentence_length

    df_cleaned = df_cleaned.drop(columns=['word_count','sentence_length','section_description'])



    # Save report to file
    print()
    print(f"💾 Saving validation report to: {REPORT_FILE}")
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("SEC FILING DATA VALIDATION REPORT\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("=" * 80 + "\n\n")
        f.write("\n".join(report))
    
    # Save cleaned data
    print(f"💾 Saving cleaned data to: {OUTPUT_FILE}")
    df_cleaned.to_parquet(OUTPUT_FILE, index=False)
    
    print(f"💾 Saving cleaned data to: {OUTPUT_CSV}")
    df_cleaned.to_csv(OUTPUT_CSV, index=False)
    
    print()
    print("=" * 80)
    print("✅ VALIDATION COMPLETE")
    print("=" * 80)
    print(f"Input rows:  {len(df):,}")
    print(f"Output rows: {len(df_cleaned):,}")
    print(f"Removed:     {len(df) - len(df_cleaned):,} ({((len(df) - len(df_cleaned)) / len(df) * 100):.2f}%)")
    print()
    print(f"📄 Files saved:")
    print(f"   - {OUTPUT_FILE}")
    print(f"   - {OUTPUT_CSV}")
    print(f"   - {REPORT_FILE}")


if __name__ == "__main__":
    main()