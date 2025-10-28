-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================

-- ============================================================================
-- Early Dev/Analysis and Table creation attempts:
-- Code for making 150 Target company DIM table, and then 75 Target company.
-- ============================================================================

--Top 50: Weight ≥ 0.35% (captures ~60% of index weight)
--Top 100: Weight ≥ 0.14% (captures ~80% of index weight)
--Rows 100-413: Long tail (<0.14% each)

CREATE OR REPLACE TABLE finrag_tgt_comps_150 AS
WITH sp500_top100 AS (
    -- Top 100 S&P 500 by weight
    SELECT 
        company_id, cik, cik_int, company_name, ticker, 
        source, tier, weight_pct, quality_score, match_method,
        'sp500_top100' as selection_reason
    FROM finrag_tgt_comps_540
    WHERE source = 'sp500'
    ORDER BY weight_pct DESC
    LIMIT 100
),

notable_top50 AS (
    -- Top 50 Notable by quality score
    SELECT 
        company_id, cik, cik_int, company_name, ticker,
        source, tier, weight_pct, quality_score, match_method,
        'notable_top50' as selection_reason
    FROM finrag_tgt_comps_540
    WHERE source = 'notable'
    ORDER BY quality_score DESC
    LIMIT 50
)

SELECT 
    ROW_NUMBER() OVER (ORDER BY 
        CASE source WHEN 'sp500' THEN 1 ELSE 2 END,
        COALESCE(weight_pct, quality_score/1000) DESC
    ) as company_id,
    cik, cik_int, company_name, ticker, source, tier,
    weight_pct, quality_score, match_method, selection_reason
FROM (
    SELECT * FROM sp500_top100
    UNION ALL
    SELECT * FROM notable_top50
)
ORDER BY company_id;



SELECT 
    CASE 
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2009 THEN 'bin_2006_2009'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2010 AND 2015 THEN 'bin_2010_2015'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2016 AND 2020 THEN 'bin_2016_2020'
    END as temporal_bin,
    
    -- Sentence counts
    COUNT(*) as n_sentences,
    COUNT(DISTINCT sentenceID) as n_unique_sentences,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct_of_total,
    
    -- Company/filing coverage
    COUNT(DISTINCT CAST(cik AS INTEGER)) as n_companies,
    COUNT(DISTINCT docID) as n_filings,
    COUNT(DISTINCT YEAR(CAST(reportDate AS DATE))) as n_years,
    COUNT(DISTINCT section) as n_sections,
    
    -- Per-company averages
    ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT CAST(cik AS INTEGER)), 0) as avg_sentences_per_company,
    ROUND(COUNT(DISTINCT docID) * 1.0 / COUNT(DISTINCT CAST(cik AS INTEGER)), 1) as avg_filings_per_company,
    
    -- Text characteristics
    ROUND(AVG(LENGTH(sentence)), 1) as avg_char_length,
    MIN(LENGTH(sentence)) as min_char_length,
    MAX(LENGTH(sentence)) as max_char_length,
    
    -- Year range within bin
    MIN(YEAR(CAST(reportDate AS DATE))) as earliest_year,
    MAX(YEAR(CAST(reportDate AS DATE))) as latest_year

	FROM read_parquet(parquet_path())
		WHERE CAST(cik AS INTEGER) IN (
		    SELECT DISTINCT cik_int FROM finrag_tgt_comps_150
		)

	AND YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2020
	AND section IS NOT NULL
	AND sentence IS NOT NULL
	AND LENGTH(sentence) > 10

GROUP BY temporal_bin
ORDER BY temporal_bin;

--#,temporal_bin,n_sentences,n_unique_sentences,pct_of_total,n_companies,n_filings,n_years,n_sections,avg_sentences_per_company,avg_filings_per_company,avg_char_length,min_char_length,max_char_length,earliest_year,latest_year
--1,bin_2006_2009,"910,953","910,953",24.27,135,520,4,20,"6,748",3.9,181.2,11,"13,265","2,006","2,009"
--2,bin_2010_2015,"1,531,864","1,531,864",40.81,144,834,6,20,"10,638",5.8,188.6,11,"14,867","2,010","2,015"
--3,bin_2016_2020,"1,310,629","1,310,629",34.92,149,708,5,20,"8,796",4.8,191.9,11,"15,718","2,016","2,020"






CREATE OR REPLACE TABLE finrag_tgt_comps_75 AS
WITH sp500_top50 AS (
    -- Top 50 S&P 500 by market weight
    SELECT 
        company_id, cik, cik_int, company_name, ticker, 
        source, tier, weight_pct, quality_score, match_method,
        'sp500_top50' as selection_reason
    FROM finrag_tgt_comps_540
    WHERE source = 'sp500'
    ORDER BY weight_pct DESC
    LIMIT 50
),

notable_top25 AS (
    -- Top 25 Notable by quality score
    SELECT 
        company_id, cik, cik_int, company_name, ticker,
        source, tier, weight_pct, quality_score, match_method,
        'notable_top25' as selection_reason
    FROM finrag_tgt_comps_540
    WHERE source = 'notable'
    ORDER BY quality_score DESC
    LIMIT 25
)

SELECT 
    ROW_NUMBER() OVER (ORDER BY 
        CASE source WHEN 'sp500' THEN 1 ELSE 2 END,
        COALESCE(weight_pct, quality_score/1000) DESC
    ) as company_id,
    cik, cik_int, company_name, ticker, source, tier,
    weight_pct, quality_score, match_method, selection_reason
FROM (
    SELECT * FROM sp500_top50
    UNION ALL
    SELECT * FROM notable_top25
)
ORDER BY company_id;




SELECT 
    CASE 
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2009 THEN 'bin_2006_2009'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2010 AND 2015 THEN 'bin_2010_2015'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2016 AND 2020 THEN 'bin_2016_2020'
    END as temporal_bin,
    
    -- Sentence counts
    COUNT(*) as n_sentences,
    COUNT(DISTINCT sentenceID) as n_unique_sentences,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct_of_total,
    
    -- Company/filing coverage
    COUNT(DISTINCT CAST(cik AS INTEGER)) as n_companies,
    COUNT(DISTINCT docID) as n_filings,
    COUNT(DISTINCT YEAR(CAST(reportDate AS DATE))) as n_years,
    COUNT(DISTINCT section) as n_sections,
    
    -- Per-company averages
    ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT CAST(cik AS INTEGER)), 0) as avg_sentences_per_company,
    ROUND(COUNT(DISTINCT docID) * 1.0 / COUNT(DISTINCT CAST(cik AS INTEGER)), 1) as avg_filings_per_company,
    
    -- Text characteristics
    ROUND(AVG(LENGTH(sentence)), 1) as avg_char_length,
    MIN(LENGTH(sentence)) as min_char_length,
    MAX(LENGTH(sentence)) as max_char_length,
    
    -- Year range within bin
    MIN(YEAR(CAST(reportDate AS DATE))) as earliest_year,
    MAX(YEAR(CAST(reportDate AS DATE))) as latest_year

	FROM read_parquet(parquet_path())
		WHERE CAST(cik AS INTEGER) IN (
		    SELECT DISTINCT cik_int FROM finrag_tgt_comps_75
		)

	AND YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2020
	AND section IS NOT NULL
	AND sentence IS NOT NULL
	AND LENGTH(sentence) > 10

GROUP BY temporal_bin
ORDER BY temporal_bin;



SELECT * FROM finrag_tgt_comps_75;








