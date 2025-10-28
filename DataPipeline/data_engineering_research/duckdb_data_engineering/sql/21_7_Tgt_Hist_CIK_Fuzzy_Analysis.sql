-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================




-- ============================================================================
-- Fix Attempt: CIK doesn't match, try fuzzy company name matching or CIK tickers.
-- ============================================================================


-- STEP 1: Company Dimension (already verified ✓)
WITH company_dim AS (
    SELECT 
        CAST(cik AS INTEGER) as cik_int,
        LPAD(CAST(cik AS VARCHAR), 10, '0') as cik10,
        ARG_MAX(name, reportDate) as company_name,
        list(DISTINCT ticker) as all_tickers,
        MAX(CAST(reportDate AS DATE)) as latest_filing_date,
        COUNT(DISTINCT docID) as n_filings
    FROM (
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
),

-- STEP 2: Canonicalize Target List (700 companies)
target_canonical AS (
    SELECT 
        cik as target_cik_original,
        CAST(cik AS INTEGER) as target_cik_int,
        LPAD(cik, 10, '0') as target_cik10,
        company_name as target_name,
        ticker as target_ticker_original,
        UPPER(COALESCE(ticker, '')) as target_ticker_norm,
        source,
        tier,
        weight_pct,
        quality_score
    FROM target_companies_700
),

-- STEP 3: Tier 1 - Match on CIK (integer)
tier1_cik_matches AS (
    SELECT 
        tc.target_cik_original,
        tc.target_cik_int,
        tc.target_name,
        tc.target_ticker_original,
        tc.source,
        tc.tier,
        cd.cik_int as matched_cik_int,
        cd.cik10 as matched_cik10,
        cd.company_name as matched_name,
        cd.all_tickers as matched_tickers,
        cd.latest_filing_date,
        cd.n_filings,
        'CIK_MATCH' as match_method
    FROM target_canonical tc
    INNER JOIN company_dim cd
        ON tc.target_cik_int = cd.cik_int
),

-- STEP 4: Identify Unmatched After Tier 1
tier1_unmatched AS (
    SELECT *
    FROM target_canonical tc
    WHERE NOT EXISTS (
        SELECT 1 
        FROM tier1_cik_matches t1
        WHERE t1.target_cik_original = tc.target_cik_original
    )
    AND tc.target_ticker_norm != ''  -- Only try ticker if ticker exists
),

-- STEP 5: Tier 2 - Match Unmatched on TICKER
tier2_ticker_matches AS (
    SELECT 
        tu.target_cik_original,
        tu.target_cik_int,
        tu.target_name,
        tu.target_ticker_original,
        tu.source,
        tu.tier,
        cd.cik_int as matched_cik_int,
        cd.cik10 as matched_cik10,
        cd.company_name as matched_name,
        cd.all_tickers as matched_tickers,
        cd.latest_filing_date,
        cd.n_filings,
        'TICKER_MATCH' as match_method
    FROM tier1_unmatched tu
    INNER JOIN company_dim cd
        ON list_contains(cd.all_tickers, tu.target_ticker_norm)
    -- Deduplicate if ticker maps to multiple CIKs
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY tu.target_cik_original 
        ORDER BY cd.latest_filing_date DESC NULLS LAST, cd.n_filings DESC
    ) = 1
)



-- VALIDATION QUERIES (Run these to check Steps 1-5)
-- V1: How many matched in Tier 1 (CIK)?
SELECT 'Tier 1: CIK Matches' as validation_step, COUNT(*) as n_companies
FROM tier1_cik_matches

UNION ALL

-- V2: How many unmatched after Tier 1?
SELECT 'After Tier 1: Unmatched' as validation_step, COUNT(*) as n_companies
FROM tier1_unmatched

UNION ALL

-- V3: How many matched in Tier 2 (Ticker)?
SELECT 'Tier 2: Ticker Matches' as validation_step, COUNT(*) as n_companies
FROM tier2_ticker_matches

UNION ALL

-- V4: Total matched so far (Tier 1 + Tier 2)
SELECT 'Total Matched (Tier 1+2)' as validation_step, COUNT(*) as n_companies
FROM (
    SELECT target_cik_original FROM tier1_cik_matches
    UNION
    SELECT target_cik_original FROM tier2_ticker_matches
)

UNION ALL

-- V5: Still unmatched after both tiers
SELECT 'Still Unmatched' as validation_step, COUNT(*) as n_companies
FROM target_canonical tc
WHERE NOT EXISTS (
    SELECT 1 FROM tier1_cik_matches t1 WHERE t1.target_cik_original = tc.target_cik_original
)
AND NOT EXISTS (
    SELECT 1 FROM tier2_ticker_matches t2 WHERE t2.target_cik_original = tc.target_cik_original
);

--#,validation_step,n_companies
--1,Tier 1: CIK Matches,611
--2,After Tier 1: Unmatched,89
--3,Tier 2: Ticker Matches,2
--4,Total Matched (Tier 1+2),613
--5,Still Unmatched,87

-- DETAILED VIEW: Tier 2 Ticker Matches (for review)
-- Show the companies recovered via ticker matching
SELECT 
    target_cik_original,
    target_name,
    target_ticker_original,
    tier,
    '→' as arrow,
    matched_cik_int,
    matched_name,
    matched_tickers,
    latest_filing_date
FROM tier2_ticker_matches
ORDER BY tier, target_name;

--#,target_cik_original,target_name,target_ticker_original,tier,arrow,matched_cik_int,matched_name,matched_tickers,latest_filing_date
--1,2012383,"BlackRock, Inc.",BLK,sp500_mid,→,"1,364,742",BlackRock Inc.,{'BLK'},2020-12-31 00:00:00.000
--2,1996862,Bunge Global SA,BG,sp500_small,→,"1,144,519",BUNGELTD,{'BG'},2020-12-31 00:00:00.000





-- ============================================================================
-- SPOT CHECK: Major companies (are they matched correctly?)
-- ============================================================================

SELECT 
    tc.target_name,
    tc.target_ticker_original,
    tc.tier,
    CASE 
        WHEN t1.target_cik_original IS NOT NULL THEN 'CIK_MATCH'
        WHEN t2.target_cik_original IS NOT NULL THEN 'TICKER_MATCH'
        ELSE 'NO_MATCH'
    END as match_status,
    COALESCE(t1.matched_name, t2.matched_name) as matched_to
FROM target_canonical tc
LEFT JOIN tier1_cik_matches t1 ON tc.target_cik_original = t1.target_cik_original
LEFT JOIN tier2_ticker_matches t2 ON tc.target_cik_original = t2.target_cik_original
WHERE tc.target_name IN (
    'Alphabet Inc.',
    'JPMORGAN CHASE & CO',
    'BERKSHIRE HATHAWAY INC',
    'BANK OF AMERICA CORP /DE/',
    'Broadcom Inc.',
    'WELLS FARGO & COMPANY/MN'
)
ORDER BY tc.target_name;

--#,target_name,target_ticker_original,tier,match_status,matched_to
--1,Alphabet Inc.,GOOGL,sp500_mega,NO_MATCH,[NULL]
--2,BANK OF AMERICA CORP /DE/,BAC,sp500_large,NO_MATCH,[NULL]
--3,BERKSHIRE HATHAWAY INC,BRK.B,sp500_large,NO_MATCH,[NULL]
--4,Broadcom Inc.,AVGO,sp500_mega,NO_MATCH,[NULL]
--5,JPMORGAN CHASE & CO,JPM,sp500_large,NO_MATCH,[NULL]
--6,WELLS FARGO & COMPANY/MN,WFC,sp500_mid,NO_MATCH,[NULL]






