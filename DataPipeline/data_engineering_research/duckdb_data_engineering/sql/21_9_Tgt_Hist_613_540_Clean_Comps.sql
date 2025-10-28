-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================



-- ============================================================================
-- Same query as before, but add QUALIFY at the end
-- ============================================================================


CREATE OR REPLACE TABLE target_companies_613_clean AS
WITH company_dim AS (
    SELECT 
        CAST(cik AS INTEGER) as cik_int,
        list(DISTINCT ticker) as all_tickers,
        MAX(CAST(reportDate AS DATE)) as latest_filing_date
    FROM (
        SELECT cik, reportDate, UNNEST(tickers) as ticker
        FROM read_parquet(parquet_path())
        WHERE cik IS NOT NULL AND tickers IS NOT NULL AND len(tickers) > 0
    )
    GROUP BY cik
),

target_canonical AS (
    SELECT 
        cik as target_cik_original,
        CAST(cik AS INTEGER) as target_cik_int,
        company_name, ticker, source, tier, weight_pct, quality_score
    FROM target_companies_700
),

tier1_matches AS (
    SELECT 
        tc.target_cik_original, tc.target_cik_int as final_cik_int,
        tc.company_name, tc.ticker, tc.source, tc.tier, tc.weight_pct, tc.quality_score,
        'CIK_MATCH' as match_method
    FROM target_canonical tc
    INNER JOIN company_dim cd ON tc.target_cik_int = cd.cik_int
),

tier2_matches AS (
    SELECT 
        tu.target_cik_original, cd.cik_int as final_cik_int,
        tu.company_name, tu.ticker, tu.source, tu.tier, tu.weight_pct, tu.quality_score,
        'TICKER_MATCH' as match_method
    FROM target_canonical tu
    INNER JOIN company_dim cd ON list_contains(cd.all_tickers, UPPER(COALESCE(tu.ticker, '')))
    WHERE NOT EXISTS (SELECT 1 FROM tier1_matches t1 WHERE t1.target_cik_original = tu.target_cik_original)
      AND tu.ticker IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY tu.target_cik_original ORDER BY cd.latest_filing_date DESC) = 1
),

combined_matches AS (
    SELECT * FROM tier1_matches
    UNION ALL
    SELECT * FROM tier2_matches
)

SELECT 
    ROW_NUMBER() OVER (ORDER BY 
        CASE source WHEN 'sp500' THEN 1 ELSE 2 END,
        COALESCE(weight_pct, quality_score/1000) DESC
    ) as company_id,
    LPAD(CAST(final_cik_int AS VARCHAR), 10, '0') as cik,
    final_cik_int as cik_int,
    company_name, ticker, source, tier, weight_pct, quality_score, match_method
FROM combined_matches
-- DEDUPLICATION: Keep sp500 version when CIK appears in both sources
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY final_cik_int 
    ORDER BY CASE source WHEN 'sp500' THEN 1 ELSE 2 END
) = 1
ORDER BY company_id;


SELECT * FROM target_companies_613_clean;












