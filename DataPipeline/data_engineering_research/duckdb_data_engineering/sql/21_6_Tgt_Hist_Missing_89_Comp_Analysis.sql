-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================
-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================



-- ============================================================================
-- EDA: IDENTIFY THE 89 MISSING COMPANIES
-- ============================================================================


SELECT 
    tc.cik,
    tc.company_name,
    tc.source,
    tc.tier,
    tc.ticker,
    tc.weight_pct,
    tc.quality_score
FROM target_companies_700 tc
LEFT JOIN read_parquet(parquet_path()) corpus
    ON CAST(tc.cik AS INTEGER) = CAST(corpus.cik AS INTEGER)
WHERE corpus.cik IS NULL
ORDER BY tc.source, tc.weight_pct DESC NULLS LAST;


SELECT 
    tc.source,
    tc.tier,
    COUNT(*) as n_missing
FROM target_companies_700 tc
LEFT JOIN read_parquet(parquet_path()) corpus
    ON CAST(tc.cik AS INTEGER) = CAST(corpus.cik AS INTEGER)
WHERE corpus.cik IS NULL
GROUP BY tc.source, tc.tier
ORDER BY tc.source, n_missing DESC;

--#,source,tier,n_missing
--1,sp500,sp500_small,69
--2,sp500,sp500_mid,15
--3,sp500,sp500_large,3
--4,sp500,sp500_mega,2

--#,target_cik,target_name,ticker,tier,separator,corpus_cik,corpus_name,match_type,target_normalized,corpus_normalized
--1,2012383,"BlackRock, Inc.",BLK,sp500_mid,  ||  ,0001364742,BlackRock Inc.,EXACT,BLACKROCK INC,BLACKROCK INC


-- ============================================================================
-- COMPANY: Flatten and deduplicate tickers
-- ============================================================================


WITH company_dim AS (
    SELECT
        CAST(cik AS INTEGER) as cik_int,
        LPAD(CAST(cik AS VARCHAR), 10, '0') as cik10,
        ARG_MAX(name, reportDate) as company_name,
        -- Flatten tickers: UNNEST then aggregate with DISTINCT
        list(DISTINCT ticker) as all_tickers,
        MAX(CAST(reportDate AS DATE)) as latest_filing_date,
        COUNT(DISTINCT docID) as n_filings
    FROM (
        -- explode tickers array into individual ticker rows
        SELECT 
            cik,
            name,
            reportDate,
            docID,
            UNNEST(tickers) as ticker
        FROM read_parquet(parquet_path())
        WHERE cik IS NOT NULL 
          AND tickers IS NOT NULL
          AND len(tickers) > 0
    )
    GROUP BY cik
)

SELECT 
    cik_int,
    cik10,
    company_name,
    all_tickers,
    len(all_tickers) as n_tickers, 
    latest_filing_date,
    n_filings
FROM company_dim
ORDER BY n_filings DESC;



-- Quick Validation:

--SELECT 
--    COUNT(*) as total_rows,
--    COUNT(DISTINCT cik_int) as unique_ciks,
--    COUNT(DISTINCT cik10) as unique_cik10s
--FROM company_dim;
--
--#,total_rows,unique_ciks,unique_cik10s
--1,"4,674","4,674","4,674"


--SELECT 
--    len(all_tickers) as n_tickers_per_company,
--    COUNT(*) as n_companies
--FROM company_dim
--GROUP BY len(all_tickers)
--ORDER BY n_tickers_per_company;
--
--#,n_tickers_per_company,n_companies
--1,1,"4,674"



