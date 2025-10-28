-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


-- ============================================================================
-- VALIDATION: 540 Companies - Uniqueness in CIK
-- ============================================================================

SELECT * FROM finrag_tgt_comps_540;

-- Validation after rename
SELECT 
    COUNT(*) as total_companies,
    COUNT(DISTINCT cik_int) as unique_ciks,
    COUNT(CASE WHEN source = 'sp500' THEN 1 END) as n_sp500,
    COUNT(CASE WHEN source = 'notable' THEN 1 END) as n_notable
FROM finrag_tgt_comps_540;

-- Output:
--#,total_companies,unique_ciks,n_sp500,n_notable
--1,540,540,413,127


-- ============================================================================
-- DATA INVENTORY: 540 Companies × 2006-2020 Window
-- ============================================================================

SELECT 
    -- Overall totals
    COUNT(*) as total_sentences,
    COUNT(DISTINCT CAST(cik AS VARCHAR)) as n_companies,
    COUNT(DISTINCT docID) as n_filings,
    COUNT(DISTINCT sentenceID) as n_unique_sentences,
    COUNT(DISTINCT YEAR(CAST(reportDate AS DATE))) as n_years,
    COUNT(DISTINCT section) as n_sections,
    
    -- Temporal breakdown
    MIN(CAST(reportDate AS DATE)) as earliest_report_date,
    MAX(CAST(reportDate AS DATE)) as latest_report_date,
    
    -- Sentence characteristics
    ROUND(AVG(LENGTH(sentence)), 1) as avg_char_length,
    MIN(LENGTH(sentence)) as min_char_length,
    MAX(LENGTH(sentence)) as max_char_length,
    
    -- Sampling feasibility check
    ROUND(1000000.0 / COUNT(*) * 100, 2) as sampling_rate_for_1m_pct

FROM read_parquet(parquet_path())
WHERE CAST(cik AS INTEGER) IN (
    SELECT DISTINCT cik_int 
    FROM finrag_tgt_comps_540
)
AND YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2020
AND section IS NOT NULL
AND sentence IS NOT NULL
AND LENGTH(sentence) > 10;

--#,total_sentences,n_companies,n_filings,n_unique_sentences,n_years,n_sections,earliest_report_date,latest_report_date,avg_char_length,min_char_length,max_char_length,sampling_rate_for_1m_pct
--1,"12,400,445",539,"7,270","12,400,445",15,20,2006-01-28 00:00:00.000,2020-12-31 00:00:00.000,187.8,11,"35,666",8.06




-- ============================================================================
-- DATA INVENTORY: 539 Companies × Temporal Bins (2006-2020)
-- Grouped by temporal bins to inform sampling strategy
-- ============================================================================

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
    SELECT DISTINCT cik_int 
    FROM finrag_tgt_comps_540
)
AND YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2020
AND section IS NOT NULL
AND sentence IS NOT NULL
AND LENGTH(sentence) > 10

GROUP BY temporal_bin
ORDER BY temporal_bin;



-- ============================================================================
-- SUPPLEMENTAL: Year-by-year breakdown within bins
-- ============================================================================

SELECT 
    YEAR(CAST(reportDate AS DATE)) as report_year,
    CASE 
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2009 THEN 'bin_2006_2009'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2010 AND 2015 THEN 'bin_2010_2015'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2016 AND 2020 THEN 'bin_2016_2020'
    END as temporal_bin,
    
    COUNT(*) as n_sentences,
    COUNT(DISTINCT CAST(cik AS INTEGER)) as n_companies,
    COUNT(DISTINCT docID) as n_filings,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct_of_total

FROM read_parquet(parquet_path())
WHERE CAST(cik AS INTEGER) IN (SELECT cik_int FROM finrag_tgt_comps_540)
  AND YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2020
  AND section IS NOT NULL
  AND sentence IS NOT NULL
  AND LENGTH(sentence) > 10

GROUP BY report_year, temporal_bin
ORDER BY report_year;









