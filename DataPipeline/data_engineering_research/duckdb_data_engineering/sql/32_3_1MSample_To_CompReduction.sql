
-- ============================================================================
-- 1Mil table to finrag_tgt_comps_21 CREATION. Modular Dev work for table creation.
-- Later, in a different file, this is made into a dynamic N-company creation macro.

-- EXPLORE: TABLES, QUICK GROUPING. 
-- ============================================================================

select * FROM  sampler.main.finrag_tgt_comps_75;

SELECT * 
FROM sampler.main.sec_company_tickers 
WHERE UPPER(TRIM(company_name)) LIKE '%GOOG%' 
   OR UPPER(TRIM(company_name)) LIKE '%ALPHABET%';

--#,cik,ticker,company_name
--1,"1,652,044",GOOG,Alphabet Inc.
--2,"1,652,044",GOOGL,Alphabet Inc.


select * from sampler.main.finrag_tgt_comps_540;

SELECT * FROM sampler.main.finrag_tgt_comps_75 order by weight_pct desc LIMIT 30;

SELECT * FROM sample_1m_finrag;

SELECT distinct section from sample_1m_finrag;

DESCRIBE sampler.main.finrag_tgt_comps_75;


-- See what labels and returns actually contain
SELECT 
    sentenceID,
    sentence[1:100] as sentence_preview,
    labels,
    returns,
    form,
    sic
FROM sample_1m_finrag
WHERE likely_kpi = true
LIMIT 10;



-- ============================================================================
-- INSPECTION QUERY 1: What's in LABELS and RETURNS?
-- Sample: Apple, Amazon, Nvidia, Visa, Walmart
-- ============================================================================

WITH target_companies AS (
    SELECT cik_int, name FROM (VALUES
        (320193, 'Apple Inc.'),
        (1018724, 'Amazon.com Inc.'),
        (1045810, 'NVIDIA Corp.'),
        (1403161, 'Visa Inc.'),
        (104169, 'Walmart Inc.')
    ) AS t(cik_int, name)
)
SELECT 
    sf.cik_int,
    tc.name as company_name,
    sf.sentenceID,
    sf.sentence[1:150] as sentence_preview,
    
    -- Inspect labels (nested column)
    sf.labels,
    TYPEOF(sf.labels) as labels_type,
    TRY_CAST(sf.labels AS VARCHAR) as labels_as_text,
    
    -- Inspect returns (nested column)
    sf.returns,
    TYPEOF(sf.returns) as returns_type,
    TRY_CAST(sf.returns AS VARCHAR) as returns_as_text,
    
    -- Context
    sf.section,
    sf.form,
    sf.report_year
    
FROM sample_1m_finrag sf
INNER JOIN target_companies tc ON sf.cik_int = tc.cik_int
WHERE sf.likely_kpi = true  -- Only look at KPI-flagged sentences
LIMIT 50;


-- ============================================================================
-- INSPECTION QUERY 2: How often are LABELS and RETURNS actually populated?
-- ============================================================================

SELECT 
    '1. NULL CHECK' as inspection,
    COUNT(*) as total_rows,
    
    -- Labels analysis
    COUNT(labels) as labels_non_null,
    COUNT(*) - COUNT(labels) as labels_null,
    ROUND((COUNT(labels) * 100.0 / COUNT(*)), 2) as labels_populated_pct,
    
    -- Returns analysis
    COUNT(returns) as returns_non_null,
    COUNT(*) - COUNT(returns) as returns_null,
    ROUND((COUNT(returns) * 100.0 / COUNT(*)), 2) as returns_populated_pct
    
FROM sample_1m_finrag
WHERE cik_int IN (320193, 1018724, 1045810, 1403161, 104169);


-- ============================================================================
-- INSPECTION QUERY 3: Sample values when NOT NULL
-- ============================================================================

-- Check LABELS when populated
SELECT 
    '2a. LABELS SAMPLE (when not null)' as inspection,
    cik_int,
    sentence[1:200] as sentence_preview,
    labels,
    section,
    report_year
FROM sample_1m_finrag
WHERE cik_int IN (320193, 1018724, 1045810, 1403161, 104169)
  AND labels IS NOT NULL
LIMIT 20;

-- Check RETURNS when populated
SELECT 
    '2b. RETURNS SAMPLE (when not null)' as inspection,
    cik_int,
    sentence[1:200] as sentence_preview,
    returns,
    section,
    report_year
FROM sample_1m_finrag
WHERE cik_int IN (320193, 1018724, 1045810, 1403161, 104169)
  AND returns IS NOT NULL
LIMIT 20;

-- ============================================================================
-- OTHER COLUMN INSPECTION: Are these useful?
-- ============================================================================

-- Q1: How variable is sentenceCount? (If always ~same, drop it)
SELECT 
    '4. SENTENCE COUNT DISTRIBUTION' as inspection,
    MIN(sentenceCount) as min_count,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY sentenceCount) as p25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY sentenceCount) as median,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY sentenceCount) as p75,
    MAX(sentenceCount) as max_count,
    COUNT(DISTINCT sentenceCount) as unique_values
FROM sample_1m_finrag
WHERE cik_int IN (320193, 1018724, 1045810, 1403161, 104169);


-- Q2: How many tickers per company? (Usually just 1-2)
SELECT 
    '5. TICKERS ANALYSIS' as inspection,
    cik_int,
    name,
    tickers,
    COUNT(*) as n_sentences_with_this_ticker
FROM sample_1m_finrag
WHERE cik_int IN (320193, 1018724, 1045810, 1403161, 104169)
GROUP BY cik_int, name, tickers
ORDER BY cik_int, n_sentences_with_this_ticker DESC;


-- Q3: Is docID unique per filing? (Essential for citation/traceability)
SELECT 
    '6. DOCID CARDINALITY' as inspection,
    cik_int,
    name,
    COUNT(DISTINCT docID) as n_filings,
    COUNT(DISTINCT report_year) as n_years,
    MIN(report_year) as earliest_year,
    MAX(report_year) as latest_year
FROM sample_1m_finrag
WHERE cik_int IN (320193, 1018724, 1045810, 1403161, 104169)
GROUP BY cik_int, name
ORDER BY cik_int;


-- Q4: Show sample docID structure
SELECT 
    '7. DOCID SAMPLE VALUES' as inspection,
    cik_int,
    docID,
    report_year,
    form,
    COUNT(*) as n_sentences_in_filing
FROM sample_1m_finrag
WHERE cik_int IN (320193, 1018724, 1045810)
GROUP BY cik_int, docID, report_year, form
ORDER BY cik_int, report_year DESC
LIMIT 15;



-- ============================================================================
-- SELECT TOP 20 COMPANIES FOR FINRAG v2.0
-- Strategy: 15 from S&P 500 (by market cap/quality) + 5 from custom quality score
-- + 1 google
-- ============================================================================


SELECT 
    source,
    tier,
    COUNT(*) as n_companies,
    MIN(quality_score) as min_quality,
    MAX(quality_score) as max_quality
FROM sampler.main.finrag_tgt_comps_75
GROUP BY source, tier
ORDER BY source, tier;


-- ============================================================================
-- CREATE finrag_tgt_comps_21 - Production Subset with Google
-- ============================================================================

DROP TABLE IF EXISTS sampler.main.finrag_tgt_comps_21;


CREATE TABLE sampler.main.finrag_tgt_comps_21 AS

WITH google_company AS (
    -- Force-include Google/Alphabet (CIK: 1652044)
    SELECT 
        1652044 as cik_int,
        '0001652044' as cik,
        'Alphabet Inc.' as company_name,
        'GOOGL' as ticker,
        'MANUAL' as source,
        'TIER_PRIORITY' as tier,
        999999.0 as quality_score,  -- Placeholder since not in original 75
        'GOOGLE_MANDATORY_MANUAL' as selection_source,
        0 as rank_within_group
),

snp_ranked AS (

    SELECT 
        cik_int,
        cik,
        company_name,
        ticker,
        source,
        tier,
        weight_pct * 1000 as quality_score,
        'SNP500_TOP15' as selection_source,
        ROW_NUMBER() OVER (ORDER BY weight_pct DESC) as rank_within_group
    FROM sampler.main.finrag_tgt_comps_75
    WHERE cik_int IN (
        1045810,  -- NVIDIA
        789019,   -- MICROSOFT
        320193,   -- APPLE
        1018724,  -- AMAZON
        1326801,  -- META
        1318605,  -- TESLA
        59478,    -- ELI LILLY
        1403161,  -- VISA
        1065280,  -- NETFLIX
        1341439,  -- ORACLE
        104169,   -- WALMART
        34088,    -- EXXON MOBIL
        1141391,  -- MASTERCARD
        200406,   -- JOHNSON & JOHNSON
        909832    -- COSTCO
    )
    
),

quality_ranked AS (
    -- Top 5 from custom quality score (non-S&P 500, excluding Google)
    SELECT 
        cik_int,
        cik,
        company_name,
        ticker,
        source,
        tier,
        quality_score,
        'QUALITY_TOP5' as selection_source,
        ROW_NUMBER() OVER (ORDER BY quality_score DESC, cik_int) as rank_within_group
    FROM sampler.main.finrag_tgt_comps_75
    WHERE TRIM(UPPER(source)) != 'SP500'
      AND cik_int != 1652044  -- Exclude Google from quality ranking
)

SELECT 
    ROW_NUMBER() OVER (ORDER BY 
        CASE selection_source 
            WHEN 'GOOGLE_MANDATORY' THEN 1 
            WHEN 'SNP500_TOP15' THEN 2 
            WHEN 'QUALITY_TOP5' THEN 3 
        END,
        rank_within_group
    ) as company_id,
    cik_int,
    cik,
    company_name,
    ticker,
    source,
    tier,
    quality_score,
    selection_source,
    rank_within_group,
    CURRENT_TIMESTAMP as selected_at,
    'v2.0_prod_21companies' as version
FROM (
    SELECT * FROM google_company
    UNION ALL
    SELECT * FROM snp_ranked WHERE rank_within_group <= 15
    UNION ALL
    SELECT * FROM quality_ranked WHERE rank_within_group <= 5
)
ORDER BY company_id;


-- ============================================================================
-- VALIDATION CHECKS
-- ============================================================================

-- V1: Verify company count and selection breakdown
SELECT 
    '1. COMPANY COUNT BY SOURCE' as validation_check,
    selection_source,
    COUNT(*) as n_companies,
    MIN(quality_score) as min_quality,
    MAX(quality_score) as max_quality,
    ROUND(AVG(quality_score), 2) as avg_quality
FROM sampler.main.finrag_tgt_comps_21
GROUP BY selection_source
ORDER BY CASE selection_source 
    WHEN 'GOOGLE_MANDATORY' THEN 1 
    WHEN 'SNP500_TOP15' THEN 2 
    WHEN 'QUALITY_TOP5' THEN 3 
END;

-- Expected output:
-- GOOGLE_MANDATORY: 1 company
-- SNP500_TOP15: 15 companies
-- QUALITY_TOP5: 5 companies
-- TOTAL: 21 companies


-- V2: Verify Google is included
SELECT 
    '2. GOOGLE VERIFICATION' as validation_check,
    COUNT(*) as google_count,
    MAX(company_name) as google_name,
    MAX(ticker) as google_ticker
FROM sampler.main.finrag_tgt_comps_21
WHERE cik_int = 1652044;

-- Expected: 1 row with "Alphabet Inc." and ticker "GOOG" or "GOOGL"


-- V3: Full company list (for your records)
SELECT 
    company_id,
    cik_int,
    company_name,
    ticker,
    source,
    tier,
    quality_score,
    selection_source,
    rank_within_group
FROM sampler.main.finrag_tgt_comps_21
ORDER BY company_id;


-- V4: Check for duplicates (should return 0)
SELECT 
    '4. DUPLICATE CHECK' as validation_check,
    cik_int,
    COUNT(*) as duplicate_count
FROM sampler.main.finrag_tgt_comps_21
GROUP BY cik_int
HAVING COUNT(*) > 1;

-- Expected: Empty result (no duplicates)


-- V5: Total count verification
SELECT 
    '5. FINAL COUNT' as validation_check,
    COUNT(*) as total_companies,
    COUNT(DISTINCT cik_int) as unique_ciks,
    CASE 
        WHEN COUNT(*) = 21 AND COUNT(DISTINCT cik_int) = 21 
        THEN '✓ Perfect - 21 companies selected'
        ELSE '⚠️ Issue detected'
    END as status
FROM sampler.main.finrag_tgt_comps_21;




           