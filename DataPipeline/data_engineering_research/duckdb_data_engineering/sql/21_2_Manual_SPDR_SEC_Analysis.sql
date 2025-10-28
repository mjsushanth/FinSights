-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================

-- Initial SPDR -> SEC Join and Manual Anamoly / Result Analysis.
-- joined table (S&P 500 with CIK mappings)
CREATE OR REPLACE TABLE sp500_with_ciks AS
SELECT 

    spy.company_name as spy_company_name,
    spy.ticker,
    spy.identifier,
    spy.sedol,
    spy.weight_pct,
    spy.sector,
    spy.shares_held,
    spy.local_currency,
    
    sec.cik,
    sec.company_name as sec_company_name
    
FROM spy_holdings_15OCT spy
LEFT JOIN sec_company_tickers sec 
    ON UPPER(TRIM(spy.ticker)) = UPPER(TRIM(sec.ticker))
ORDER BY spy.weight_pct DESC;



-- Validation 1: Check row count (should be 503)
SELECT COUNT(*) as total_rows FROM sp500_with_ciks;

-- Validation 2: Check for duplicates (should return 0)
SELECT ticker, COUNT(*) as occurrences
FROM sp500_with_ciks
GROUP BY ticker
HAVING COUNT(*) > 1;

-- Validation 3: Check for failed matches (tickers without CIKs)
SELECT ticker, spy_company_name, weight_pct
FROM sp500_with_ciks
WHERE cik IS NULL
ORDER BY weight_pct DESC;
--#,ticker,spy_company_name,weight_pct
--1,BRK.B,BERKSHIRE HATHAWAY INC CL B,1.598795
--2,BF.B,BROWN FORMAN CORP CLASS B,0.008742

-- Validation 4: Summary statistics
SELECT 
    COUNT(*) as total_companies,
    COUNT(DISTINCT cik) as unique_ciks,
    COUNT(CASE WHEN cik IS NULL THEN 1 END) as failed_matches,
    SUM(weight_pct) as total_weight_coverage
FROM sp500_with_ciks;
--#,total_companies,unique_ciks,failed_matches,total_weight_coverage
--1,503,498,2,99.943638



-- Search for Berkshire Hathaway in SEC table
-- Search for Brown Forman in SEC table

SELECT cik, ticker, company_name
FROM sec_company_tickers
WHERE UPPER(company_name) LIKE '%BERKSHIRE%'
ORDER BY company_name;

--#,cik,ticker,company_name
--1,"1,067,983",BRK-A,BERKSHIRE HATHAWAY INC
--2,"1,067,983",BRK-B,BERKSHIRE HATHAWAY INC

SELECT cik, ticker, company_name
FROM sec_company_tickers
WHERE UPPER(company_name) LIKE '%BROWN%FORMAN%'
ORDER BY company_name;
--#,cik,ticker,company_name
--1,"1,067,983",BRK-A,BERKSHIRE HATHAWAY INC
--2,"1,067,983",BRK-B,BERKSHIRE HATHAWAY INC

SELECT cik, ticker, company_name
FROM sec_company_tickers
WHERE ticker IN ('BRK.B', 'BRKB', 'BRK-B', 'BRK B', 'BF.B', 'BFB', 'BF-B', 'BF B');
--#,cik,ticker,company_name
--1,"14,693",BF-B,BROWN FORMAN CORP
--2,"1,067,983",BRK-B,BERKSHIRE HATHAWAY INC



-- Manual fix for the 2 ticker mismatches
UPDATE sp500_with_ciks 
SET cik = 1067983,
    sec_company_name = 'BERKSHIRE HATHAWAY INC'
WHERE ticker = 'BRK.B';

UPDATE sp500_with_ciks 
SET cik = 14693,
    sec_company_name = 'BROWN FORMAN CORP'
WHERE ticker = 'BF.B';


-- Re-validate: Should now show 0 failed matches, 500 unique CIKs
SELECT 
    COUNT(*) as total_companies,
    COUNT(DISTINCT cik) as unique_ciks,
    COUNT(CASE WHEN cik IS NULL THEN 1 END) as failed_matches,
    SUM(weight_pct) as total_weight_coverage
FROM sp500_with_ciks;

--#,total_companies,unique_ciks,failed_matches,total_weight_coverage
--1,503,500,0,99.943638

-- Final check: View the fixed rows
SELECT ticker, spy_company_name, cik, sec_company_name, weight_pct
FROM sp500_with_ciks
WHERE ticker IN ('BRK.B', 'BF.B');


