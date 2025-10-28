-- ============================================================================
-- FIX MISSING TICKERS: Update Notable Companies from SEC Master File
-- Bug: Notable tier companies have NULL tickers in dimension tables
-- ============================================================================

SET VARIABLE sec_tickers_json = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/webdata/sec_company_tickers.json';

select count(*), count(distinct(cik)) from sampler.main.sec_company_tickers;
--#,count_star(),count(DISTINCT cik)
--1,"10,142","7,900"

-- ============================================================================
-- PREPARE CLEAN CIK → TICKER MAPPING (One Ticker per CIK)
-- Source: sampler.main.sec_company_tickers (10k rows, 7.9k distinct CIKs)
-- Strategy: For CIKs with multiple tickers, pick the first alphabetically ?
-- ============================================================================

CREATE OR REPLACE TEMP TABLE dim_sec_all_tickers AS
SELECT 
    CAST(cik AS INTEGER) as cik_int,
    -- Pick first ticker alphabetically if multiple exist for same CIK
    MIN(ticker) as ticker,
    -- Pick corresponding company name
    MIN(company_name) as company_name
FROM sampler.main.sec_company_tickers
WHERE cik IS NOT NULL 
  AND ticker IS NOT NULL
GROUP BY cik;

-- Validation
SELECT 
    '✓ CLEAN TICKER MAPPING CREATED' as status,
    COUNT(*) as unique_ciks,
    COUNT(DISTINCT ticker) as unique_tickers,
    COUNT(*) - COUNT(DISTINCT ticker) as duplicate_tickers
FROM dim_sec_all_tickers;

-- Preview
SELECT * FROM dim_sec_all_tickers LIMIT 10;





-- ============================================================================
-- UPDATE MISSING TICKERS: Apply to All Three Company Dimension Tables
-- ============================================================================

-- ══════════════════════════════════════════════════════════════════════════
-- CHECK: Which tables have missing tickers (BEFORE UPDATE)
-- ══════════════════════════════════════════════════════════════════════════

SELECT 
    'finrag_tgt_comps_540' as table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN ticker IS NULL THEN 1 END) as missing_tickers,
    ROUND(COUNT(CASE WHEN ticker IS NULL THEN 1 END) * 100.0 / COUNT(*), 1) || '%' as pct_missing
FROM sampler.main.finrag_tgt_comps_540

UNION ALL

SELECT 
    'finrag_tgt_comps_75',
    COUNT(*),
    COUNT(CASE WHEN ticker IS NULL THEN 1 END),
    ROUND(COUNT(CASE WHEN ticker IS NULL THEN 1 END) * 100.0 / COUNT(*), 1) || '%'
FROM sampler.main.finrag_tgt_comps_75

UNION ALL

SELECT 
    'finrag_tgt_comps_21',
    COUNT(*),
    COUNT(CASE WHEN ticker IS NULL THEN 1 END),
    ROUND(COUNT(CASE WHEN ticker IS NULL THEN 1 END) * 100.0 / COUNT(*), 1) || '%'
FROM sampler.main.finrag_tgt_comps_21;


-- ══════════════════════════════════════════════════════════════════════════
-- UPDATE 1: finrag_tgt_comps_540
-- ══════════════════════════════════════════════════════════════════════════

UPDATE sampler.main.finrag_tgt_comps_540 AS target
SET ticker = source.ticker
FROM dim_sec_all_tickers AS source
WHERE target.cik_int = source.cik_int
  AND target.ticker IS NULL;

SELECT 
    '✓ UPDATE 1 COMPLETE' as status,
    'finrag_tgt_comps_540' as table_name,
    COUNT(CASE WHEN ticker IS NULL THEN 1 END) as still_missing,
    CASE 
        WHEN COUNT(CASE WHEN ticker IS NULL THEN 1 END) = 0 
        THEN '✓ All tickers populated'
        ELSE '⚠️ ' || COUNT(CASE WHEN ticker IS NULL THEN 1 END) || ' still missing'
    END as result
FROM sampler.main.finrag_tgt_comps_540;



SELECT 
    '1. CIK LOOKUP IN SEC MASTER FILE' as check_type,
    CAST(cik AS INTEGER) as cik_int,
    ticker,
    company_name
FROM sampler.main.sec_company_tickers
WHERE CAST(cik AS INTEGER) IN (101778, 1033012)
ORDER BY cik_int;



-- ══════════════════════════════════════════════════════════════════════════
-- UPDATE 2: finrag_tgt_comps_75
-- ══════════════════════════════════════════════════════════════════════════

UPDATE sampler.main.finrag_tgt_comps_75 AS target
SET ticker = source.ticker
FROM dim_sec_all_tickers AS source
WHERE target.cik_int = source.cik_int
  AND target.ticker IS NULL;

SELECT 
    '✓ UPDATE 2 COMPLETE' as status,
    'finrag_tgt_comps_75' as table_name,
    COUNT(CASE WHEN ticker IS NULL THEN 1 END) as still_missing,
    CASE 
        WHEN COUNT(CASE WHEN ticker IS NULL THEN 1 END) = 0 
        THEN '✓ All tickers populated'
        ELSE '⚠️ ' || COUNT(CASE WHEN ticker IS NULL THEN 1 END) || ' still missing'
    END as result
FROM sampler.main.finrag_tgt_comps_75;


SELECT * FROM sampler.main.finrag_tgt_comps_75;

-- ══════════════════════════════════════════════════════════════════════════
-- UPDATE 3: finrag_tgt_comps_21
-- ══════════════════════════════════════════════════════════════════════════

UPDATE sampler.main.finrag_tgt_comps_21 AS target
SET ticker = source.ticker
FROM dim_sec_all_tickers AS source
WHERE target.cik_int = source.cik_int
  AND target.ticker IS NULL;

SELECT 
    '✓ UPDATE 3 COMPLETE' as status,
    'finrag_tgt_comps_21' as table_name,
    COUNT(CASE WHEN ticker IS NULL THEN 1 END) as still_missing,
    CASE 
        WHEN COUNT(CASE WHEN ticker IS NULL THEN 1 END) = 0 
        THEN '✓ All tickers populated'
        ELSE '⚠️ ' || COUNT(CASE WHEN ticker IS NULL THEN 1 END) || ' still missing'
    END as result
FROM sampler.main.finrag_tgt_comps_21;


-- ══════════════════════════════════════════════════════════════════════════
-- FINAL VALIDATION: Show ticker status for notable companies
-- ══════════════════════════════════════════════════════════════════════════

SELECT 
    '═══ NOTABLE COMPANIES - TICKER STATUS ═══' as validation,
    cik_int,
    company_name,
    ticker,
    source,
    CASE 
        WHEN ticker IS NOT NULL THEN '✓ Populated'
        ELSE '✗ Still NULL'
    END as status
FROM sampler.main.finrag_tgt_comps_75
WHERE source = 'notable'
ORDER BY company_name;




-- ============================================================================
-- SECONDARY TICKER MAPPING: Extract from HuggingFace Parquet Dataset
-- Source: Original sec_filings_large_full.parquet (71.8M sentences, clean data)
-- ============================================================================

SET VARIABLE hf_parquet_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_filings_large_full.parquet';


-- ══════════════════════════════════════════════════════════════════════════
-- CREATE SECONDARY TICKER DIMENSION (From HuggingFace Dataset)
-- ══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE TEMP TABLE dim_hf_tickers AS
SELECT DISTINCT
    CAST(cik AS INTEGER) as cik_int,
    name as company_name,
    -- Tickers is an array, extract first ticker
    tickers[1] as ticker
FROM read_parquet(getvariable('hf_parquet_path'))
WHERE cik IS NOT NULL
  AND tickers IS NOT NULL
  AND len(tickers) > 0;

SELECT 
    '✓ HUGGINGFACE TICKER MAPPING CREATED' as status,
    COUNT(*) as unique_ciks,
    COUNT(DISTINCT ticker) as unique_tickers
FROM dim_hf_tickers;


-- ══════════════════════════════════════════════════════════════════════════
-- UPDATE 1: finrag_tgt_comps_540 (Using HF Data)
-- ══════════════════════════════════════════════════════════════════════════

UPDATE sampler.main.finrag_tgt_comps_540 AS target
SET ticker = source.ticker
FROM dim_hf_tickers AS source
WHERE target.cik_int = source.cik_int
  AND target.ticker IS NULL;


-- ══════════════════════════════════════════════════════════════════════════
-- UPDATE 2: finrag_tgt_comps_75 (Using HF Data)
-- ══════════════════════════════════════════════════════════════════════════

UPDATE sampler.main.finrag_tgt_comps_75 AS target
SET ticker = source.ticker
FROM dim_hf_tickers AS source
WHERE target.cik_int = source.cik_int
  AND target.ticker IS NULL;


-- ══════════════════════════════════════════════════════════════════════════
-- UPDATE 3: finrag_tgt_comps_21 (Using HF Data)
-- ══════════════════════════════════════════════════════════════════════════

UPDATE sampler.main.finrag_tgt_comps_21 AS target
SET ticker = source.ticker
FROM dim_hf_tickers AS source
WHERE target.cik_int = source.cik_int
  AND target.ticker IS NULL;

SELECT '✓✓✓ ALL UPDATES COMPLETE (HF DATA SOURCE)' as status;






-- ============================================================================
-- VALIDATION: Check Ticker Population Across All Three Tables
-- ============================================================================

SELECT 
    '═══ TICKER POPULATION STATUS ═══' as validation_type,
    'finrag_tgt_comps_540' as table_name,
    COUNT(*) as total_companies,
    COUNT(CASE WHEN ticker IS NOT NULL THEN 1 END) as tickers_populated,
    COUNT(CASE WHEN ticker IS NULL THEN 1 END) as tickers_missing,
    ROUND(COUNT(CASE WHEN ticker IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) || '%' as pct_complete,
    CASE 
        WHEN COUNT(CASE WHEN ticker IS NULL THEN 1 END) = 0 
        THEN '✓ All tickers populated'
        ELSE '⚠️ ' || COUNT(CASE WHEN ticker IS NULL THEN 1 END) || ' missing'
    END as status
FROM sampler.main.finrag_tgt_comps_540

UNION ALL

SELECT 
    '═══ TICKER POPULATION STATUS ═══',
    'finrag_tgt_comps_75',
    COUNT(*),
    COUNT(CASE WHEN ticker IS NOT NULL THEN 1 END),
    COUNT(CASE WHEN ticker IS NULL THEN 1 END),
    ROUND(COUNT(CASE WHEN ticker IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) || '%',
    CASE 
        WHEN COUNT(CASE WHEN ticker IS NULL THEN 1 END) = 0 
        THEN '✓ All tickers populated'
        ELSE '⚠️ ' || COUNT(CASE WHEN ticker IS NULL THEN 1 END) || ' missing'
    END
FROM sampler.main.finrag_tgt_comps_75

UNION ALL

SELECT 
    '═══ TICKER POPULATION STATUS ═══',
    'finrag_tgt_comps_21',
    COUNT(*),
    COUNT(CASE WHEN ticker IS NOT NULL THEN 1 END),
    COUNT(CASE WHEN ticker IS NULL THEN 1 END),
    ROUND(COUNT(CASE WHEN ticker IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) || '%',
    CASE 
        WHEN COUNT(CASE WHEN ticker IS NULL THEN 1 END) = 0 
        THEN '✓ All tickers populated'
        ELSE '⚠️ ' || COUNT(CASE WHEN ticker IS NULL THEN 1 END) || ' missing'
    END
FROM sampler.main.finrag_tgt_comps_21;


-- ============================================================================
-- EXPORT: finrag_dim_companies_21 (Updated with Complete Tickers)
-- ============================================================================

SET VARIABLE export_base_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports';

SET VARIABLE dim_companies_export = (
    getvariable('export_base_path') || '/finrag_dim_companies_21.parquet'
);

SELECT 
    'Exporting updated company dimension...' as status, 
    getvariable('dim_companies_export') as destination;

PREPARE export_dim_companies AS
    COPY sampler.main.finrag_tgt_comps_21 
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

EXECUTE export_dim_companies(getvariable('dim_companies_export'));

SELECT 
    '✓✓ EXPORT COMPLETE' as status,
    'finrag_dim_companies_21.parquet' as filename,
    COUNT(*) as companies_exported,
    COUNT(CASE WHEN ticker IS NOT NULL THEN 1 END) as with_tickers
FROM sampler.main.finrag_tgt_comps_21;








