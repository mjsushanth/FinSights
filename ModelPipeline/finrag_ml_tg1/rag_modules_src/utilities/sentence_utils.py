"""
Sentence utilities for FinRAG pipeline.

Provides helper functions for working with sentenceID structure and extraction.
"""

import polars as pl


def extract_sentence_position(df: pl.DataFrame, sentenceid_col: str = 'sentenceID') -> pl.DataFrame:
    """
    Extract sentence position from sentenceID string.
    
    sentenceID format: {docID}_{section}_{sequence}
    Example: "0001045810_10-K_2020_section_1A_45" → pos=45
    
    Logic:
    - Split by '_', take last segment
    - Cast to int16 (strict=False allows NULL on failure)
    - Fill NULL with -1 (sentinel value for malformed IDs)
    
    Sentinel value -1 indicates:
    - Malformed sentenceID (no numeric suffix)
    - Requires special handling in window expansion
    
    Args:
        df: DataFrame with sentenceID column
        sentenceid_col: Name of sentenceID column (default: 'sentenceID')
    
    Returns:
        DataFrame with new 'sentence_pos' column (Int16)
    
    Example:
        >>> df = extract_sentence_position(meta_df)
        >>> df.filter(pl.col('sentence_pos') == -1)  # Find malformed IDs
    """
    return df.with_columns([
        pl.col(sentenceid_col)
          .str.split('_')
          .list.last()
          .cast(pl.Int16, strict=False)  # strict=False → NULL on cast failure
          .fill_null(-1)                  # NULL → -1 sentinel
          .alias('sentence_pos')
    ])