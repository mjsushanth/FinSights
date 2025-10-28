-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================

-- Which company from our 540 has no data in 2006-2020?
SELECT 
    tc.cik_int,
    tc.company_name,
    tc.ticker,
    tc.source,
    COUNT(corpus.sentenceID) as n_sentences_in_window
FROM finrag_tgt_comps_540 tc
LEFT JOIN read_parquet(parquet_path()) corpus
    ON tc.cik_int = CAST(corpus.cik AS INTEGER)
    AND YEAR(CAST(corpus.reportDate AS DATE)) BETWEEN 2006 AND 2020
    AND corpus.section IS NOT NULL
    AND corpus.sentence IS NOT NULL
GROUP BY tc.cik_int, tc.company_name, tc.ticker, tc.source
HAVING COUNT(corpus.sentenceID) = 0
ORDER BY tc.source;

--#,cik_int,company_name,ticker,source,n_sentences_in_window
--1,"732,712",VERIZON COMMUNICATIONS INC,VZ,sp500,0



-- Q1: Does this CIK exist at all in corpus?
SELECT 
    COUNT(*) as total_sentences,
    COUNT(DISTINCT docID) as n_filings,
    COUNT(DISTINCT YEAR(CAST(reportDate AS DATE))) as n_years,
    MIN(CAST(reportDate AS DATE)) as earliest_filing,
    MAX(CAST(reportDate AS DATE)) as latest_filing
FROM read_parquet(parquet_path())
WHERE CAST(cik AS INTEGER) = 732712;

--#,total_sentences,n_filings,n_years,earliest_filing,latest_filing
--1,"5,581",7,7,1993-12-31 00:00:00.000,2002-12-31 00:00:00.000

-- Q2: Year distribution (if data exists)
SELECT 
    YEAR(CAST(reportDate AS DATE)) as report_year,
    COUNT(*) as n_sentences,
    COUNT(DISTINCT docID) as n_filings
FROM read_parquet(parquet_path())
WHERE CAST(cik AS INTEGER) = 732712
GROUP BY report_year
ORDER BY report_year;

--#,report_year,n_sentences,n_filings
--1,"1,993",747,1
--2,"1,994",557,1
--3,"1,996",573,1
--4,"1,997",492,1
--5,"1,998","1,880",1
--6,"2,001",690,1
--7,"2,002",642,1

-- Q3: Sample a few sentences (if any exist)
SELECT 
    cik,
    name,
    docID,
    reportDate,
    section,
    LEFT(sentence, 100) as sentence_preview
FROM read_parquet(parquet_path())
WHERE CAST(cik AS INTEGER) = 732712
ORDER BY reportDate DESC
LIMIT 10;

--#,cik,name,docID,reportDate,section,sentence_preview
--1,0000732712,VERIZON COMMUNICATIONS INC,0000732712_10-K_2002,2002-12-31,0,Item 1. Business General Verizon Communications Inc. is one of the world’s leading providers of comm
--2,0000732712,VERIZON COMMUNICATIONS INC,0000732712_10-K_2002,2002-12-31,0,Verizon companies are the largest providers of wireline and wireless communications in the United St


-- Q4: Check in 2006-2020 window specifically with all filters
SELECT 
    COUNT(*) as n_sentences_2006_2020
FROM read_parquet(parquet_path())
WHERE CAST(cik AS INTEGER) = 732712
  AND YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2020
  AND section IS NOT NULL
  AND sentence IS NOT NULL
  AND LENGTH(sentence) > 10;

--#,n_sentences_2006_2020
--1,0



-- ============================================================================
-- DELETE Verizon (0 sentences in 2006-2020 window)
-- ============================================================================

DELETE FROM finrag_tgt_comps_540
WHERE cik_int = 732712;

-- DELETE FROM finrag_tgt_comps_540
-- WHERE cik = '0000732712';


-- ============================================================================
-- VALIDATION: Verify deletion and new count
-- ============================================================================

SELECT 
    COUNT(*) as total_companies,
    COUNT(DISTINCT cik_int) as unique_ciks
FROM finrag_tgt_comps_540;
-- Expected: total=539, unique=539


-- Verify Verizon is gone
SELECT * FROM finrag_tgt_comps_540
WHERE cik_int = 732712;
-- Expected: 0 rows


-- Final distribution check
SELECT 
    source,
    COUNT(*) as n_companies
FROM finrag_tgt_comps_540
GROUP BY source;
-- Expected: sp500=~412, notable=127, total=539

