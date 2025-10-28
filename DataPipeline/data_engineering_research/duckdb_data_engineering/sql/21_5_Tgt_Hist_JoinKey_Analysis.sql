-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


SELECT * FROM target_companies_700;

-- ============================================================================
-- EDA: Queries to check for join-key true matches, table match consistency,
-- before preparing the final 1M table.
-- ============================================================================


SELECT DISTINCT cik, LENGTH(cik) as cik_length, TYPEOF(cik) as cik_type, company_name 
FROM target_companies_700 ORDER BY LENGTH(cik) DESC ;
--#,cik,cik_length,cik_type,company_name
--1,0000061986,10,VARCHAR,MANITOWOC CO INC
--2,0001005757,10,VARCHAR,CSG SYSTEMS INTERNATIONAL INC
--3,0000040888,10,VARCHAR,"AEROJET ROCKETDYNE HOLDINGS, INC."


SELECT DISTINCT cik, LENGTH(cik) as cik_length, TYPEOF(cik) as cik_type, name as company_name 
FROM read_parquet(parquet_path()) ORDER BY LENGTH(cik) DESC ;
--#,cik,cik_length,cik_type,company_name
--1,0001455863,10,VARCHAR,AMERICOLD REALTY TRUST
--2,0001478320,10,VARCHAR,Adaptive Biotechnologies Corp
--3,0001563756,10,VARCHAR,"Lightstone Value Plus REIT III, Inc."


SELECT 
    tc.source,
    COUNT(DISTINCT tc.cik) as n_companies,
    COUNT(DISTINCT corpus.cik) as n_matched
FROM target_companies_700 tc
LEFT JOIN read_parquet(parquet_path()) corpus
    ON CAST(tc.cik AS VARCHAR) = CAST(corpus.cik AS VARCHAR)
GROUP BY tc.source;
--#,source,n_companies,n_matched
--1,notable,200,200
--2,sp500,500,0


SELECT 
    CASE WHEN corpus.cik IS NULL THEN 'not_matched' ELSE 'matched' END as status,
    COUNT(DISTINCT tc.cik) as n_companies
FROM target_companies_700 tc
LEFT JOIN read_parquet(parquet_path()) corpus
    ON CAST(tc.cik AS INTEGER) = CAST(corpus.cik AS INTEGER)  -- Try INTEGER join
GROUP BY status;
--#,status,n_companies
--1,matched,611
--2,not_matched,89


