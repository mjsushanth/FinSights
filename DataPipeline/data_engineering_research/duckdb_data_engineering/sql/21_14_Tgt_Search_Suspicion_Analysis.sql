-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================
-- ============================================================================
-- SEARCH: Find Tesla, Netflix, Salesforce, and other suspected ??
-- ============================================================================


-- ============================================================================
-- CREATE COMPANY DIMENSION: All companies in corpus (one row per CIK)
-- Purpose: Fast lookups without scanning 71M rows repeatedly
-- ============================================================================


CREATE OR REPLACE TABLE corpus_company_dimension AS
SELECT 
    CAST(cik AS INTEGER) as cik_int,
    LPAD(CAST(cik AS VARCHAR), 10, '0') as cik10,
    cik as cik_original,
    
    -- Company identification
    ARG_MAX(name, reportDate) as company_name,
    
    -- All tickers (flattened and deduplicated)
    list(DISTINCT ticker ORDER BY ticker) as all_tickers,
    
    -- Temporal coverage
    MIN(CAST(reportDate AS DATE)) as earliest_filing_date,
    MAX(CAST(reportDate AS DATE)) as latest_filing_date,
    MIN(YEAR(CAST(reportDate AS DATE))) as earliest_year,
    MAX(YEAR(CAST(reportDate AS DATE))) as latest_year,
    
    -- Filing statistics
    COUNT(DISTINCT docID) as n_filings,
    COUNT(DISTINCT YEAR(CAST(reportDate AS DATE))) as n_years_covered,
    COUNT(DISTINCT section) as n_sections_covered,
    COUNT(DISTINCT sentenceID) as n_sentences,
    
    -- Text statistics
    ROUND(AVG(LENGTH(sentence)), 1) as avg_char_length,
    
    -- Normalized for searching
    UPPER(TRIM(REGEXP_REPLACE(
        ARG_MAX(name, reportDate), 
        ' INC\.?$| CORP\.?$| CO\.?$| LTD\.?$| LLC\.?$| PLC\.?$', 
        '', 'g'
    ))) as name_normalized

FROM (
    SELECT 
        cik, name, reportDate, docID, section, sentence, sentenceID,
        UNNEST(COALESCE(tickers, [])) as ticker
    FROM read_parquet(parquet_path())
    WHERE cik IS NOT NULL
)
GROUP BY cik
ORDER BY n_sentences DESC;





-- ============================================================================
-- VALIDATION
-- ============================================================================

SELECT COUNT(*) as total_companies FROM corpus_company_dimension;
-- Expected: 4,674


SELECT 
    MIN(n_filings) as min_filings,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY n_filings) as median_filings,
    MAX(n_filings) as max_filings,
    ROUND(AVG(n_filings), 1) as avg_filings
FROM corpus_company_dimension;
-- Expected: avg ~11.8

--#,min_filings,median_filings,max_filings,avg_filings
--1,1,11,28,11.8


SELECT * FROM corpus_company_dimension ORDER BY n_sentences DESC LIMIT 10;




-- ============================================================================
-- SEARCH: Suspected missing caps 
-- ============================================================================

WITH suspected AS (
    SELECT cik_int, name_pattern, ticker FROM (VALUES
        (1318605, 'TESLA', 'TSLA'),
        (1065280, 'NETFLIX', 'NFLX'),
        (1466258, 'UBER', 'UBER'),
        (1759509, 'LYFT', 'LYFT'),
        (1467373, 'TWITTER', 'TWTR'),
        (1018724, 'AMAZON', 'AMZN'),
        (1045810, 'NVIDIA', 'NVDA'),
        (1326801, 'META', 'META'),
        (1108524, 'SALESFORCE', 'CRM'),
        (1273685, 'SERVICENOW', 'NOW'),
        (1679788, 'COINBASE', 'COIN'),
        (1783879, 'ROBINHOOD', 'HOOD'),
        (1616318, 'PINTEREST', 'PINS'),
        (1534675, 'BLOCK', 'SQ'),
        (1441675, 'SNAP', 'SNAP'),
        (1559720, 'ROKU', 'ROKU'),
        (1585521, 'ZOOM', 'ZM'),
        (1467623, 'SPOTIFY', 'SPOT'),
        (1490281, 'SHOPIFY', 'SHOP'),
        (1533523, 'DOORDASH', 'DASH'),
        (1594109, 'PELOTON', 'PTON'),
        (1764925, 'AIRBNB', 'ABNB'),
        (1688568, 'SNOWFLAKE', 'SNOW'),
        (1579684, 'DATADOG', 'DDOG'),
        (1611820, 'CROWDSTRIKE', 'CRWD')
    ) AS t(cik_int, name_pattern, ticker)
)

SELECT 
    s.cik_int as suspected_cik,
    s.name_pattern as suspected_name,
    s.ticker as suspected_ticker,
    
    CASE 
        WHEN cd.cik_int IS NULL THEN '❌ MISSING'
        ELSE '✅ PRESENT'
    END as status,
    
    cd.company_name as found_name,
    cd.all_tickers as found_tickers,
    cd.n_sentences,
    cd.n_filings,
    cd.earliest_year,
    cd.latest_year
    
FROM suspected s
LEFT JOIN corpus_company_dimension cd
    ON s.cik_int = cd.cik_int
    OR UPPER(cd.name_normalized) LIKE '%' || s.name_pattern || '%'
    OR list_contains(cd.all_tickers, s.ticker)
ORDER BY 
    CASE WHEN cd.cik_int IS NULL THEN 1 ELSE 2 END,
    s.name_pattern;

WITH suspected AS (
    SELECT cik_int, name_pattern, ticker FROM (VALUES
        (1318605, 'TESLA', 'TSLA'),
        (1065280, 'NETFLIX', 'NFLX'),
        (1466258, 'UBER', 'UBER'),
        (1759509, 'LYFT', 'LYFT'),
        (1467373, 'TWITTER', 'TWTR'),
        (1018724, 'AMAZON', 'AMZN'),
        (1045810, 'NVIDIA', 'NVDA'),
        (1326801, 'META', 'META'),
        (1108524, 'SALESFORCE', 'CRM'),
        (1273685, 'SERVICENOW', 'NOW'),
        (1679788, 'COINBASE', 'COIN'),
        (1783879, 'ROBINHOOD', 'HOOD'),
        (1616318, 'PINTEREST', 'PINS'),
        (1534675, 'BLOCK', 'SQ'),
        (1441675, 'SNAP', 'SNAP'),
        (1559720, 'ROKU', 'ROKU'),
        (1585521, 'ZOOM', 'ZM'),
        (1467623, 'SPOTIFY', 'SPOT'),
        (1490281, 'SHOPIFY', 'SHOP'),
        (1533523, 'DOORDASH', 'DASH'),
        (1594109, 'PELOTON', 'PTON'),
        (1764925, 'AIRBNB', 'ABNB'),
        (1688568, 'SNOWFLAKE', 'SNOW'),
        (1579684, 'DATADOG', 'DDOG'),
        (1611820, 'CROWDSTRIKE', 'CRWD')
    ) AS t(cik_int, name_pattern, ticker)
)
-- Summary
SELECT 
    CASE WHEN cd.cik_int IS NULL THEN 'MISSING' ELSE 'PRESENT' END as status,
    COUNT(*) as n_companies
FROM suspected s
LEFT JOIN corpus_company_dimension cd
    ON s.cik_int = cd.cik_int
GROUP BY status;

--
--#,status,n_companies
--1,MISSING,9
--2,PRESENT,16
--





-- ============================================================================
-- SEARCH: Which of OUR 539 companies are actually in corpus?
-- Use finrag_tgt_comps_540 as source of truth 
-- ============================================================================

SELECT 
    tc.cik_int as target_cik,
    tc.company_name as target_name,
    tc.ticker as target_ticker,
    tc.source,
    tc.tier,
    
    CASE 
        WHEN cd.cik_int IS NULL THEN '❌ MISSING FROM CORPUS'
        ELSE '✅ IN CORPUS'
    END as corpus_status,
    
    cd.company_name as corpus_name,
    cd.all_tickers as corpus_tickers,
    cd.n_sentences,
    cd.n_filings,
    cd.earliest_year,
    cd.latest_year
    
FROM finrag_tgt_comps_540 tc
LEFT JOIN corpus_company_dimension cd
    ON tc.cik_int = cd.cik_int
ORDER BY 
    CASE WHEN cd.cik_int IS NULL THEN 1 ELSE 2 END,
    tc.tier,
    tc.company_name;


-- ============================================================================
-- SUMMARY: How many of our 539 are actually present in corpus?
-- ============================================================================

SELECT 
    CASE WHEN cd.cik_int IS NULL THEN 'MISSING' ELSE 'PRESENT' END as status,
    COUNT(*) as n_companies
FROM finrag_tgt_comps_540 tc
LEFT JOIN corpus_company_dimension cd
    ON tc.cik_int = cd.cik_int
GROUP BY status;

--
--#,status,n_companies
--1,PRESENT,539




