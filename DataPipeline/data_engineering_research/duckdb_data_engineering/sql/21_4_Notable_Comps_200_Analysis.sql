-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


-- ============================================================================
-- VALIDATION QUERIES - For notable_companies_200
-- ============================================================================

-- V1: Basic row count and composition
SELECT 
    COUNT(*) as total_companies,
    COUNT(DISTINCT cik) as unique_ciks,
    COUNT(CASE WHEN selection_method = 'auto_top120' THEN 1 END) as auto_included,
    COUNT(CASE WHEN selection_method = 'hidden_gem' THEN 1 END) as hidden_gems
FROM notable_companies_200;


-- ============================================================================
-- 700 Table Prep - Combine notable_companies_200 and sp500_with_ciks.
-- ============================================================================


SELECT * FROM sp500_with_ciks limit 5;
--spy_company_name,ticker,identifier,sedol,weight_pct,sector,shares_held,local_currency,cik,sec_company_name

SELECT * FROM notable_companies_200 limit 5;
--company_rank,cik,company_name,filing_years,section_coverage,total_sentences,recent_sentences,priority_section_sentences,latest_filing_year,quality_score,company_type,selection_method,priority_ratio,recency_ratio,avg_sentences_per_year

--CIK - join key to corpus
--Company name - human-readable identifier







CREATE OR REPLACE TABLE target_companies_700 AS
WITH sp500_normalized AS (
    SELECT 
        CAST(cik AS VARCHAR) as cik,
        COALESCE(sec_company_name, spy_company_name) as company_name,
        ticker,
        sector,
        weight_pct,
        'sp500' as source,
        -- Tier classification based on ETF weight
        CASE 
            WHEN weight_pct >= 2.0 THEN 'sp500_mega'      -- Top ~10 companies
            WHEN weight_pct >= 0.5 THEN 'sp500_large'     -- Large caps
            WHEN weight_pct >= 0.2 THEN 'sp500_mid'       -- Mid caps
            ELSE 'sp500_small'                            -- Smaller components
        END as tier,
        NULL::INTEGER as filing_years,
        NULL::BIGINT as total_sentences,
        NULL::DOUBLE as quality_score,
        NULL::INTEGER as latest_filing_year
    FROM sp500_with_ciks
),
notable_normalized AS (
    SELECT 
        cik,
        company_name,
        NULL::VARCHAR as ticker,
        NULL::VARCHAR as sector,
        NULL::DOUBLE as weight_pct,
        'notable' as source,
        -- Tier classification based on quality score
        CASE 
            WHEN quality_score >= 1200 THEN 'notable_tier1'  -- Highest quality
            WHEN quality_score >= 1000 THEN 'notable_tier2'  -- High quality
            WHEN quality_score >= 900 THEN 'notable_tier3'   -- Good quality
            ELSE 'notable_tier4'                             -- Standard quality
        END as tier,
        filing_years,
        total_sentences,
        quality_score,
        latest_filing_year
    FROM notable_companies_200
),
combined AS (
    SELECT * FROM sp500_normalized
    UNION ALL
    SELECT * FROM notable_normalized
)
SELECT 
    ROW_NUMBER() OVER (ORDER BY 
        CASE source WHEN 'sp500' THEN 1 ELSE 2 END,
        COALESCE(weight_pct, quality_score / 1000) DESC
    ) as company_id,
    cik,
    company_name,
    ticker,
    sector,
    source,
    tier,
    ROUND(COALESCE(weight_pct, 0.0), 4) as weight_pct,
    filing_years,
    total_sentences,
    ROUND(COALESCE(quality_score, 0.0), 2) as quality_score,
    latest_filing_year,
    -- Derived flags for sampling logic
    CASE WHEN source = 'sp500' THEN 1 ELSE 0 END as is_sp500,
    CASE WHEN tier LIKE '%mega%' OR tier LIKE '%tier1%' THEN 1 ELSE 0 END as is_premium
FROM combined
ORDER BY company_id;



-- ============================================================================
-- VALIDATION QUERIES
-- ============================================================================

-- V1: Row counts by source
-- Expected: sp500=503, notable=200, total=703
SELECT 
    COALESCE(source, 'TOTAL') as source,
    COUNT(*) as n_companies,
    COUNT(DISTINCT cik) as unique_ciks,
    ROUND(AVG(COALESCE(total_sentences, 0)), 0) as avg_corpus_size
FROM target_companies_700
GROUP BY GROUPING SETS (source, ())
ORDER BY 
    CASE WHEN source IS NULL THEN 2 ELSE 1 END,
    source;
--#,source,n_companies,unique_ciks,avg_corpus_size
--1,notable,200,200,"41,183"
--2,sp500,503,500,0
--3,TOTAL,703,700,"11,716"



-- V3: Check for duplicate CIKs (should return 0)
SELECT cik, COUNT(*) as occurrences
FROM target_companies_700
GROUP BY cik
HAVING COUNT(*) > 1;

-- Expected: 0 rows (no duplicates)
--#,cik,occurrences
--1,1754301,2
--2,1652044,2
--3,1564708,2

-- V4: Verify no NULLs in critical fields
SELECT 
    COUNT(*) as total_rows,
    COUNT(CASE WHEN cik IS NULL THEN 1 END) as null_ciks,
    COUNT(CASE WHEN company_name IS NULL THEN 1 END) as null_names,
    COUNT(CASE WHEN source IS NULL THEN 1 END) as null_sources
FROM target_companies_700;
-- Expected: null counts should all be 0
--#,total_rows,null_ciks,null_names,null_sources
--1,703,0,0,0


-- Which companies are duplicated?
SELECT 
    t.cik,
    MAX(CASE WHEN t.source = 'sp500' THEN t.company_name END) as sp500_name,
    MAX(CASE WHEN t.source = 'notable' THEN t.company_name END) as notable_name,
    MAX(CASE WHEN t.source = 'sp500' THEN t.ticker END) as ticker,
    MAX(CASE WHEN t.source = 'sp500' THEN t.weight_pct END) as sp500_weight,
    MAX(CASE WHEN t.source = 'notable' THEN t.quality_score END) as notable_score
FROM target_companies_700 t
WHERE t.cik IN (
    SELECT cik 
    FROM target_companies_700 
    GROUP BY cik 
    HAVING COUNT(*) > 1
)
GROUP BY t.cik
ORDER BY t.cik;


-- legitimate dual-class stocks with the same CIK.
-- Show ALL rows for the 3 duplicate CIKs
SELECT 
    company_id,
    cik,
    company_name,
    ticker,
    sector,
    source,
    tier,
    weight_pct,
    quality_score,
    filing_years,
    total_sentences
FROM target_companies_700
WHERE cik IN ('1564708', '1652044', '1754301')
ORDER BY cik, source;





-- V2: Distribution by tier
SELECT 
    source,
    tier,
    COUNT(*) as n_companies,
    ROUND(AVG(COALESCE(weight_pct, quality_score/1000)), 3) as avg_score_proxy
FROM target_companies_700
GROUP BY source, tier
ORDER BY source, n_companies DESC;




-- V5: Preview top 10 from each source
(SELECT company_id, company_name, ticker, source, tier, 
        COALESCE(weight_pct, quality_score/1000) as score_proxy
 FROM target_companies_700 
 WHERE source = 'sp500'
 ORDER BY weight_pct DESC NULLS LAST
 LIMIT 10)
UNION ALL
(SELECT company_id, company_name, ticker, source, tier,
        COALESCE(weight_pct, quality_score/1000) as score_proxy
 FROM target_companies_700 
 WHERE source = 'notable'
 ORDER BY quality_score DESC NULLS LAST
 LIMIT 10);

-- CIK is the join key for sampling
-- Company name is the same ("Alphabet Inc.")



DELETE FROM target_companies_700
WHERE company_id IN (
    503,  -- News Corp NWS (Class B, 0.0064%)
    9,    -- Alphabet GOOG (Class C, 2.0646%)  
    491   -- Fox Corp FOX (Class B, 0.0133%)
);


SELECT COUNT(*) as total_rows, 
       COUNT(DISTINCT cik) as unique_ciks
FROM target_companies_700;









