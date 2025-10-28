-- ============================================================================
-- VALIDATION & ANALYTICS: Alphabet (Google) 2017-2024 API Data
-- ============================================================================
-- Purpose: Quality checks for API-sourced 10-K data before DuckDB merge
-- Dataset: sec_10k_static_alphabet_2017_20_api_data.parquet
-- Author: Joel Markapudi
-- ============================================================================

/*
 * 	✅ Query 1: High-level summary (8,510 sentences, 5 years, 1 company)
	✅ Query 2: Filings per year (1 filing/year, all passing)
	✅ Query 3: Section coverage (shows if 20/20 sections present per year)
 */

-- ============================================================================
-- SECTION 0: SETUP & LOAD
-- ============================================================================

-- Drop any existing temp tables
DROP TABLE IF EXISTS api_alphabet_raw;
DROP TABLE IF EXISTS validation_results;


SET VARIABLE apipath = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/10-K_merged_2015_2019_GOOGL_1025.parquet';

SELECT * FROM read_parquet(getvariable(apipath));

DESCRIBE SELECT * FROM read_parquet(getvariable(apipath));

--#,column_name,column_type,null,key,default,extra
--1,cik,VARCHAR,YES,[NULL],[NULL],[NULL]
--2,name,VARCHAR,YES,[NULL],[NULL],[NULL]
--3,report_year,BIGINT,YES,[NULL],[NULL],[NULL]
--4,docID,VARCHAR,YES,[NULL],[NULL],[NULL]
--5,sentenceID,VARCHAR,YES,[NULL],[NULL],[NULL]
--6,section_name,VARCHAR,YES,[NULL],[NULL],[NULL]
--7,section_item,VARCHAR,YES,[NULL],[NULL],[NULL]
--8,section_ID,BIGINT,YES,[NULL],[NULL],[NULL]
--9,form,VARCHAR,YES,[NULL],[NULL],[NULL]
--10,sentence_index,BIGINT,YES,[NULL],[NULL],[NULL]
--11,sentence,VARCHAR,YES,[NULL],[NULL],[NULL]
--12,SIC,VARCHAR,YES,[NULL],[NULL],[NULL]
--13,filingDate,VARCHAR,YES,[NULL],[NULL],[NULL]
--14,reportDate,VARCHAR,YES,[NULL],[NULL],[NULL]
--15,temporal_bin,VARCHAR,YES,[NULL],[NULL],[NULL]
--16,sample_created_at,TIMESTAMP_NS,YES,[NULL],[NULL],[NULL]
--17,last_modified_date,TIMESTAMP_NS,YES,[NULL],[NULL],[NULL]
--18,sample_version,VARCHAR,YES,[NULL],[NULL],[NULL]
--19,source_file_path,VARCHAR,YES,[NULL],[NULL],[NULL]
--20,load_method,VARCHAR,YES,[NULL],[NULL],[NULL]






DROP TABLE IF EXISTS api_alphabet_raw;

-- DROP TEMP TABLE IF EXISTS api_alphabet_raw_2015era;



-- Load the parquet file
CREATE OR REPLACE TEMP TABLE api_alphabet_raw_2015era AS
	SELECT * FROM read_parquet(getvariable(apipath));
	

SELECT 'Data loaded successfully' AS status, 
	       COUNT(*) AS total_rows,
	       COUNT(DISTINCT cik) AS unique_ciks
	FROM api_alphabet_raw_2015era;


--  Manual Inspection.
-- SELECT * FROM api_alphabet_raw_2015era;


select cik, name, sentenceID, docID, filingDate, reportDate, acceptanceDateTime from sampler.main.sample_1m_finrag;


/* -- ============================================================================
 * ⚠️ Missing columns vs sample_1m_finrag:
	Likely missing: tickers, exchanges, entityType, stateOfIncorporation, labels, returns
	-- ============================================================================
 */

-- ============================================================================
-- SECTION 1: BASIC INVENTORY CHECKS
-- ============================================================================

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║ QUERY 1: High-Level Summary                                         ║
-- ╚══════════════════════════════════════════════════════════════════════╝

SELECT 
    '📊 DATASET OVERVIEW' AS check_category,
    COUNT(*) AS total_sentences,
    COUNT(DISTINCT docID) AS unique_filings,
    COUNT(DISTINCT report_year) AS years_covered,
    MIN(report_year) AS earliest_year,
    MAX(report_year) AS latest_year,
    COUNT(DISTINCT section_ID) AS unique_sections,
    COUNT(DISTINCT cik) AS unique_companies,
    ROUND(AVG(LENGTH(sentence)), 2) AS avg_sentence_length
FROM api_alphabet_raw_2015era;


--#,check_category,total_sentences,unique_filings,years_covered,earliest_year,latest_year,unique_sections,unique_companies,avg_sentence_length
--1,📊 DATASET OVERVIEW,"8,510",5,5,"2,015","2,019",20,1,159.73

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║ QUERY 2: Year-by-Year Filing Count (CRITICAL)                       ║
-- ╚══════════════════════════════════════════════════════════════════════╝
-- Expected: 1 filing per year (10-K is annual)

SELECT 
    '📅 FILINGS PER YEAR' AS check_category,
    report_year,
    COUNT(DISTINCT docID) AS filings_count,
    COUNT(*) AS total_sentences,
    ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT docID), 0) AS avg_sentences_per_filing,
    COUNT(DISTINCT(SECTION_ITEM)) as distSections, 
    CASE 
        WHEN COUNT(DISTINCT docID) = 1 THEN '✅ PASS'
        WHEN COUNT(DISTINCT docID) > 1 THEN '❌ FAIL - Multiple filings!'
        ELSE '⚠️ WARNING - No filing'
    END AS validation_status
FROM api_alphabet_raw_2015era
GROUP BY report_year
ORDER BY report_year;


--#,check_category,report_year,filings_count,total_sentences,avg_sentences_per_filing,distSections,validation_status
--1,📅 FILINGS PER YEAR,"2,015",1,"1,808","1,808",20,✅ PASS
--2,📅 FILINGS PER YEAR,"2,016",1,"1,611","1,611",20,✅ PASS
--3,📅 FILINGS PER YEAR,"2,017",1,"1,690","1,690",20,✅ PASS
--4,📅 FILINGS PER YEAR,"2,018",1,"1,695","1,695",20,✅ PASS
--5,📅 FILINGS PER YEAR,"2,019",1,"1,706","1,706",20,✅ PASS

SELECT * FROM api_alphabet_raw_2015era;





-- ============================================================================
-- SECTION 2: SECTION COVERAGE VALIDATION
-- ============================================================================

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║ QUERY 3: Section Coverage by Year (CRITICAL)                        ║
-- ╚══════════════════════════════════════════════════════════════════════╝
-- Expected: 20 sections (section_ID 0-19) per filing
-- Note: Some years might have 19 sections if one is empty/not extracted


WITH section_coverage AS (
    SELECT 
        report_year,
        docID,
        COUNT(DISTINCT section_ID) AS sections_present,
        STRING_AGG(DISTINCT CAST(section_ID AS VARCHAR), ', ' ORDER BY CAST(section_ID AS VARCHAR)) AS section_ids_list
    FROM api_alphabet_raw_2015era
    GROUP BY report_year, docID
)
SELECT 
    '📑 SECTION COVERAGE' AS check_category,
    report_year,
    docID,
    sections_present,
    CASE 
        WHEN sections_present = 20 THEN '✅ COMPLETE (20/20)'
        WHEN sections_present = 19 THEN '⚠️ ACCEPTABLE (19/20)'
        WHEN sections_present >= 15 THEN '⚠️ PARTIAL (15+/20)'
        ELSE '❌ FAIL (<15 sections)'
    END AS coverage_status,
    section_ids_list AS sections_found
FROM section_coverage
ORDER BY report_year;


--#,check_category,report_year,docID,sections_present,coverage_status,sections_found
--1,📑 SECTION COVERAGE,"2,015",0001652044_10-K_2015,20,✅ COMPLETE (20/20),"0, 1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 2, 3, 4, 5, 6, 7, 8, 9"
--2,📑 SECTION COVERAGE,"2,016",0001652044_10-K_2016,20,✅ COMPLETE (20/20),"0, 1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 2, 3, 4, 5, 6, 7, 8, 9"
--3,📑 SECTION COVERAGE,"2,017",0001652044_10-K_2017,20,✅ COMPLETE (20/20),"0, 1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 2, 3, 4, 5, 6, 7, 8, 9"
--4,📑 SECTION COVERAGE,"2,018",0001652044_10-K_2018,20,✅ COMPLETE (20/20),"0, 1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 2, 3, 4, 5, 6, 7, 8, 9"
--5,📑 SECTION COVERAGE,"2,019",0001652044_10-K_2019,20,✅ COMPLETE (20/20),"0, 1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 2, 3, 4, 5, 6, 7, 8, 9"







-- ============================================================================
-- END OF VALIDATION SCRIPT
-- ============================================================================