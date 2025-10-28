-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================




-- ============================================================================
-- CREATE CLEAN TABLE: 613 Matched Companies Only
-- Includes CIK corrections for the 2 ticker matches
-- ============================================================================


CREATE OR REPLACE TABLE target_companies_613_clean AS
WITH company_dim AS (
    -- Build company dimension (ONE ROW PER CIK)
    SELECT 
        CAST(cik AS INTEGER) as cik_int,
        LPAD(CAST(cik AS VARCHAR), 10, '0') as cik10,
        ARG_MAX(name, reportDate) as company_name,
        list(DISTINCT ticker) as all_tickers,
        MAX(CAST(reportDate AS DATE)) as latest_filing_date,
        COUNT(DISTINCT docID) as n_filings
    FROM (
        SELECT 
            cik, name, reportDate, docID,
            UNNEST(tickers) as ticker
        FROM read_parquet(parquet_path())
        WHERE cik IS NOT NULL 
          AND tickers IS NOT NULL
          AND len(tickers) > 0
    )
    GROUP BY cik
),

target_canonical AS (
    SELECT 
        cik as target_cik_original,
        CAST(cik AS INTEGER) as target_cik_int,
        company_name,
        ticker,
        source,
        tier,
        weight_pct,
        quality_score
    FROM target_companies_700
),

tier1_matches AS (
    SELECT 
        tc.target_cik_original,
        tc.target_cik_int as final_cik_int,
        tc.company_name,
        tc.ticker,
        tc.source,
        tc.tier,
        tc.weight_pct,
        tc.quality_score,
        'CIK_MATCH' as match_method
    FROM target_canonical tc
    INNER JOIN company_dim cd ON tc.target_cik_int = cd.cik_int
),

tier2_matches AS (
    SELECT 
        tu.target_cik_original,
        cd.cik_int as final_cik_int,  -- CORRECTED CIK from corpus
        tu.company_name,
        tu.ticker,
        tu.source,
        tu.tier,
        tu.weight_pct,
        tu.quality_score,
        'TICKER_MATCH' as match_method
    FROM target_canonical tu
    INNER JOIN company_dim cd ON list_contains(cd.all_tickers, UPPER(COALESCE(tu.ticker, '')))
    WHERE NOT EXISTS (
        SELECT 1 FROM tier1_matches t1 WHERE t1.target_cik_original = tu.target_cik_original
    )
    AND tu.ticker IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY tu.target_cik_original ORDER BY cd.latest_filing_date DESC) = 1
)

-- Combine and format
SELECT 
    ROW_NUMBER() OVER (ORDER BY 
        CASE source WHEN 'sp500' THEN 1 ELSE 2 END,
        COALESCE(weight_pct, quality_score/1000) DESC
    ) as company_id,
    LPAD(CAST(final_cik_int AS VARCHAR), 10, '0') as cik,
    final_cik_int as cik_int,
    company_name,
    ticker,
    source,
    tier,
    weight_pct,
    quality_score,
    match_method
FROM (
    SELECT * FROM tier1_matches
    UNION ALL
    SELECT * FROM tier2_matches
)
ORDER BY company_id;


-- V1: Row count (should be 613)
SELECT COUNT(*) as total_companies FROM target_companies_613_clean;
--#,total_companies
--1,613


-- V2: Distribution by match method
SELECT 
    match_method,
    COUNT(*) as n_companies
FROM target_companies_613_clean
GROUP BY match_method;
-- Expected: CIK_MATCH=611, TICKER_MATCH=2
--#,match_method,n_companies
--1,CIK_MATCH,611
--2,TICKER_MATCH,2


-- V3: Check the 2 corrected companies
SELECT 
    company_id,
    cik,
    cik_int,
    company_name,
    ticker,
    match_method
FROM target_companies_613_clean
WHERE match_method = 'TICKER_MATCH';
-- Should show BlackRock and Bunge with CORRECTED CIKs from corpus
--#,company_id,cik,cik_int,company_name,ticker,match_method
--1,46,0001364742,"1,364,742","BlackRock, Inc.",BLK,TICKER_MATCH
--2,358,0001144519,"1,144,519",Bunge Global SA,BG,TICKER_MATCH


-- V4: Verify no duplicates
SELECT cik_int, COUNT(*) as occurrences
FROM target_companies_613_clean
GROUP BY cik_int
HAVING COUNT(*) > 1;
-- Expected: 0 rows
--
--#,cik_int,occurrences
--1,"1,141,391",2
--2,"922,224",2
--3,"352,541",2
--4,"51,644",2
--5,"62,709",2
--6,"4,977",2
--7,"1,039,684",2
--8,"783,325",2
--9,"72,741",2
--10,"1,130,310",2
--11,"77,476",2
--12,"1,059,556",2
--13,"914,208",2
--14,"21,344",2
--15,"51,434",2
--16,"1,031,296",2
--17,"2,488",2
--18,"1,393,818",2
--19,"1,163,165",2
--20,"1,133,421",2
--21,"769,397",2
--22,"715,957",2
--23,"106,040",2
--24,"72,903",2
--25,"1,002,047",2
--26,"1,037,540",2
--27,"319,201",2
--28,"796,343",2
--29,"1,103,982",2
--30,"823,768",2
--31,"33,213",2
--32,"936,468",2
--33,"1,060,391",2
--34,"96,021",2
--35,"1,140,536",2
--36,"1,002,910",2
--37,"920,760",2
--38,"1,126,328",2
--39,"1,324,404",2
--40,"1,070,750",2
--41,"12,927",2
--42,"1,067,701",2
--43,"814,547",2
--44,"33,185",2
--45,"764,622",2
--46,"66,740",2
--47,"47,217",2
--48,"60,086",2
--49,"1,164,727",2
--50,"1,137,789",2
--51,"712,515",2
--52,"1,090,872",2
--53,"896,878",2
--54,"107,263",2
--55,"1,109,357",2
--56,"1,138,118",2
--57,"1,047,862",2
--58,"20,286",2
--59,"879,169",2
--60,"68,505",2
--61,"820,027",2
--62,"49,071",2
--63,"891,103",2
--64,"310,158",2
--65,"1,156,039",2
--66,"86,312",2
--67,"26,172",2
--68,"788,784",2
--69,"56,873",2
--70,"46,080",2
--71,"315,293",2
--72,"1,050,915",2
--73,"858,470",2

--V1: total_companies = 540 (613 - 73 duplicates)
--V2: CIK_MATCH = 538, TICKER_MATCH = 2



