-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================

-- ============================================================================
-- ALL 700 COMPANIES: Match Status Flag
-- ============================================================================

WITH corpus_ciks AS (
    -- Get all distinct CIKs from corpus
    SELECT DISTINCT CAST(cik AS INTEGER) as cik_int
    FROM read_parquet(parquet_path())
    WHERE cik IS NOT NULL
)

SELECT 
    -- Original target data
    tc.cik as target_cik,
    CAST(tc.cik AS INTEGER) as target_cik_int,
    tc.company_name,
    tc.ticker,
    tc.source,
    tc.tier,
    tc.weight_pct,
    tc.quality_score,
    
    -- MATCH STATUS FLAG
    CASE 
        WHEN cc.cik_int IS NOT NULL THEN 'MATCHED'
        ELSE 'UNMATCHED'
    END as match_status,
    
    -- Normalized fields for manual searching
    UPPER(REGEXP_REPLACE(tc.company_name, ' INC\.?$| CORP\.?$| CO\.?$| /.*$', '', 'g')) as name_normalized,
    UPPER(COALESCE(tc.ticker, '')) as ticker_normalized
    
FROM target_companies_700 tc
LEFT JOIN corpus_ciks cc
    ON CAST(tc.cik AS INTEGER) = cc.cik_int
ORDER BY 
    CASE WHEN cc.cik_int IS NULL THEN 1 ELSE 2 END,  -- Unmatched first
    tc.source,
    COALESCE(tc.weight_pct, tc.quality_score/1000) DESC NULLS LAST;


-- ============================================================================
-- Summary
-- ============================================================================

SELECT 
    match_status,
    source,
    COUNT(*) as n_companies
FROM (
    SELECT 
        tc.source,
        CASE WHEN cc.cik_int IS NOT NULL THEN 'MATCHED' ELSE 'UNMATCHED' END as match_status
    FROM target_companies_700 tc
    LEFT JOIN (
        SELECT DISTINCT CAST(cik AS INTEGER) as cik_int
        FROM read_parquet(parquet_path())
    ) cc ON CAST(tc.cik AS INTEGER) = cc.cik_int
)
GROUP BY match_status, source
ORDER BY match_status, source;



