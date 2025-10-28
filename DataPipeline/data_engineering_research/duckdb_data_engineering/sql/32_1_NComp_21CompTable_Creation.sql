/*
 * 
-- ═══════════════════════════════════════════════════════════════════
-- Dynamic FACT tables creation ( i.e. Data Table Subsets.)
-- N or 21 Companies with Lean Column Selection.
-- Create tables like: finrag_21companies_allbins and modern era,
-- from the sample 1m table which has already been created. 

-- We hope to get missing company data merged in ETL/S3 layer.
-- ═══════════════════════════════════════════════════════════════════
	┌─────────────────────────────────────────────┐
	│  CONFIGURATION LAYER                        │
	│  • subset_configs table (declarative)       │
	│  • User defines: table name, filters, etc.  │
	└─────────────────────────────────────────────┘
	                    ↓
	┌─────────────────────────────────────────────┐
	│  ABSTRACTION LAYER                          │
	│  • v_sample_1m_core (canonical columns)     │
	│  • Single source of truth for schema        │
	└─────────────────────────────────────────────┘
	                    ↓
	┌─────────────────────────────────────────────┐
	│  EXECUTION LAYER                            │
	│  • CREATE TABLE statements (simple WHERE)   │
	│  • Validation queries (generic pattern)     │
	│  • Export logic (PREPARE/EXECUTE pattern)   │
	└─────────────────────────────────────────────┘	
-- ═══════════════════════════════════════════════════════════════════
*
*
*	TEST QUERIES / MODULES:
*
*	V1: Row counts and coverage
*	V2: Temporal distribution check
*	V3: Section coverage check
*	V4: Incremental Injection Impact Check
*
*/

-- ============================================================================
-- PARAMETERIZED TABLE SUBSETTING SYSTEM v2.1
-- Author: Joel Markapudi
-- Date: October 2025
-- Purpose: Create subset tables with centralized schema and reusable patterns
-- ============================================================================

-- ══════════════════════════════════════════════════════════════════════════
-- SECTION 1: CONFIGURATION LAYER
-- Define all subset table configurations in one place
-- ══════════════════════════════════════════════════════════════════════════


DROP TABLE IF EXISTS subset_configs;

CREATE TEMP TABLE subset_configs (
    config_id INTEGER,
    table_name VARCHAR,
    export_filename VARCHAR,
    company_filter_table VARCHAR,
    temporal_filter VARCHAR,
    description VARCHAR,
    enabled BOOLEAN
);


INSERT INTO subset_configs VALUES
    -- Config 1: 21 companies, all temporal bins
    (1, 'finrag_21companies_allbins', 'finrag_21companies_allbins.parquet',
     'finrag_tgt_comps_21', 'ALL_BINS', 
     '21 companies, all temporal bins (2006-2020)', TRUE),
    
    -- Config 2: 21 companies, modern era only
    (2, 'finrag_21companies_modern', 'finrag_21companies_modern.parquet',
     'finrag_tgt_comps_21', 'MODERN_ONLY',
     '21 companies, modern era (2016-2020)', TRUE),
    
    -- Config 3: 50 companies, all bins (set enabled=FALSE if table doesn't exist)
    (3, 'finrag_50companies_allbins', 'finrag_50companies_allbins.parquet',
     'finrag_tgt_comps_51', 'ALL_BINS',
     '50 companies, all temporal bins (2006-2020)', FALSE);

    
-- Display active configurations
SELECT 
    '═══════════════════════════════════════════════════════' as separator,
    '          ACTIVE CONFIGURATIONS                        ' as header,
    '═══════════════════════════════════════════════════════' as separator2;
SELECT 
    config_id,
    table_name,
    company_filter_table,
    temporal_filter,
    description,
    CASE WHEN enabled THEN '✓ ACTIVE' ELSE '○ Disabled' END as status
FROM subset_configs
ORDER BY config_id;




-- DESCRIBE sample_1m_finrag;

-- ══════════════════════════════════════════════════════════════════════════
-- SECTION 2: ABSTRACTION LAYER - Canonical Column Selection
-- ══════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS v_sample_1m_core;


CREATE OR REPLACE VIEW v_sample_1m_core AS
SELECT 
    -- ═══════════════════════════════════════════════════════════════════
    -- IDENTIFIERS (13 columns)
    -- ═══════════════════════════════════════════════════════════════════
    cik,
    cik_int,
    name,
    tickers,
    docID,
    sentenceID,
    
    -- Section fields (original + enriched)
    section_ID,            
    section_name,              -- : ITEM_1A (canonical ID)

	-- ## keep things lean. optional. 
	--    section_desc,              -- : "Item 1A: Risk Factors" (human-readable)
	--    section_category,          -- P1_RISK
	--    sec_dim_priority,          -- P1
    
    form,
    sic,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- CONTENT (1 column)
    -- ═══════════════════════════════════════════════════════════════════
    sentence,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- TEMPORAL (4 columns)
    -- ═══════════════════════════════════════════════════════════════════
    filingDate,
    report_year,
    reportDate,
    temporal_bin,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- RAG FEATURES (3 columns)
    -- ═══════════════════════════════════════════════════════════════════
    likely_kpi,
    has_numbers,
    has_comparison,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- AUDIT (6 columns)
    -- ═══════════════════════════════════════════════════════════════════
    sample_created_at,
    last_modified_date,
    sample_version,
    source_file_path,
    load_method,
    row_hash
    
FROM sample_1m_finrag;


SELECT '✓ View created: v_sample_1m_core' as status;





-- ──────────────────────────────────────────────────────────────────────────
-- B) Filter Template Reference
-- (Documentation only - used in execution section)
-- ──────────────────────────────────────────────────────────────────────────

/*
TEMPORAL FILTER TEMPLATES:

ALL_BINS:
    -- No temporal filter (include all bins)

MODERN_ONLY:
    AND temporal_bin = 'bin_2016_2020'

HISTORICAL_ONLY:
    AND temporal_bin IN ('bin_2006_2009', 'bin_2010_2015')

CUSTOM_YEAR_RANGE:
    AND report_year BETWEEN {start_year} AND {end_year}
*/



-- ══════════════════════════════════════════════════════════════════════════
-- SECTION 3: EXECUTION LAYER - Table Creation Template
-- 
-- TEMPLATE PATTERN (apply for each enabled config):
-- 
	-- DROP TABLE IF EXISTS {table_name};
	-- CREATE TABLE {table_name} AS
	-- SELECT * FROM v_sample_1m_core
	-- WHERE cik_int IN (SELECT cik_int FROM {company_filter_table})
	--   {temporal_filter}
	-- ORDER BY cik_int, report_year DESC, section_ID, sentenceID;
-- ══════════════════════════════════════════════════════════════════════════

-- ──────────────────────────────────────────────────────────────────────────
-- APPLY TEMPLATE: Config 1
-- table_name: finrag_21companies_allbins
-- company_filter_table: finrag_tgt_comps_21
-- temporal_filter: ALL_BINS (no filter)
-- ──────────────────────────────────────────────────────────────────────────


DROP TABLE IF EXISTS finrag_21companies_allbins;

CREATE TABLE finrag_21companies_allbins AS
SELECT * FROM v_sample_1m_core
WHERE cik_int IN (SELECT cik_int FROM finrag_tgt_comps_21)
-- temporal_filter: ALL_BINS → no additional filter
ORDER BY cik_int, report_year DESC, section_ID, sentenceID;

SELECT 
    '✓ Config 1 Complete' as status,
    'finrag_21companies_allbins' as table_name,
    COUNT(*) as rows,
    COUNT(DISTINCT cik_int) as companies,
    MIN(report_year) as year_min,
    MAX(report_year) as year_max
FROM finrag_21companies_allbins;


-- ──────────────────────────────────────────────────────────────────────────
-- APPLY TEMPLATE: Config 2
-- table_name: finrag_21companies_modern
-- company_filter_table: finrag_tgt_comps_21
-- temporal_filter: MODERN_ONLY
-- ──────────────────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS finrag_21companies_modern;

CREATE TABLE finrag_21companies_modern AS
SELECT * FROM v_sample_1m_core
WHERE cik_int IN (SELECT cik_int FROM finrag_tgt_comps_21)
  AND temporal_bin = 'bin_2016_2020'  -- temporal_filter: MODERN_ONLY
ORDER BY cik_int, report_year DESC, section_ID, sentenceID;

SELECT 
    '✓ Config 2 Complete' as status,
    'finrag_21companies_modern' as table_name,
    COUNT(*) as rows,
    COUNT(DISTINCT cik_int) as companies,
    MIN(report_year) as year_min,
    MAX(report_year) as year_max
FROM finrag_21companies_modern;


-- ──────────────────────────────────────────────────────────────────────────
-- APPLY TEMPLATE: Config 3 (OPTIONAL - uncomment if needed)
-- table_name: finrag_50companies_allbins
-- company_filter_table: finrag_tgt_comps_51
-- temporal_filter: ALL_BINS
-- ──────────────────────────────────────────────────────────────────────────

/*
DROP TABLE IF EXISTS finrag_50companies_allbins;

CREATE TABLE finrag_50companies_allbins AS
SELECT * FROM v_sample_1m_core
WHERE cik_int IN (SELECT cik_int FROM finrag_tgt_comps_51)
-- temporal_filter: ALL_BINS → no additional filter
ORDER BY cik_int, report_year DESC, section_ID, sentenceID;

SELECT 
    '✓ Config 3 Complete' as status,
    'finrag_50companies_allbins' as table_name,
    COUNT(*) as rows,
    COUNT(DISTINCT cik_int) as companies,
    MIN(report_year) as year_min,
    MAX(report_year) as year_max
FROM finrag_50companies_allbins;
*/


-- ══════════════════════════════════════════════════════════════════════════
-- SECTION 4: VALIDATION - Generic Pattern
-- Works for any table created above
-- ══════════════════════════════════════════════════════════════════════════

SELECT 
    '═══════════════════════════════════════════════════════' as separator,
    '          COMPREHENSIVE VALIDATION SUMMARY              ' as header,
    '═══════════════════════════════════════════════════════' as separator2;

-- ──────────────────────────────────────────────────────────────────────────
-- V1: Row counts and coverage
-- ──────────────────────────────────────────────────────────────────────────

WITH table_stats AS (
    SELECT 
        'finrag_21companies_allbins' as table_name,
        COUNT(*) as rows,
        COUNT(DISTINCT cik_int) as companies,
        COUNT(DISTINCT docID) as filings,
        COUNT(DISTINCT temporal_bin) as bins,
        MIN(report_year) as year_min,
        MAX(report_year) as year_max
    FROM finrag_21companies_allbins
    
    UNION ALL
    
    SELECT 
        'finrag_21companies_modern',
        COUNT(*),
        COUNT(DISTINCT cik_int),
        COUNT(DISTINCT docID),
        COUNT(DISTINCT temporal_bin),
        MIN(report_year),
        MAX(report_year)
    FROM finrag_21companies_modern
)
SELECT 
    table_name,
    rows,
    companies,
    filings,
    bins as temporal_bins,
    year_min || '-' || year_max as year_range,
    ROUND(rows * 1.0 / companies, 0) as avg_sentences_per_company
FROM table_stats;


-- ──────────────────────────────────────────────────────────────────────────
-- V2: Temporal distribution check
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    'finrag_21companies_allbins' as table_name,
    temporal_bin,
    COUNT(*) as n_sentences,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct_of_table
FROM finrag_21companies_allbins
GROUP BY temporal_bin
ORDER BY temporal_bin;


-- ──────────────────────────────────────────────────────────────────────────
-- V3: Section coverage check
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    'finrag_21companies_allbins' as table_name,
    COUNT(DISTINCT section_name) as unique_sections,
    CASE 
        WHEN COUNT(DISTINCT section_name) >= 16 THEN '✓ Good coverage'
        ELSE '⚠️ Limited sections'
    END as coverage_status
FROM finrag_21companies_allbins

UNION ALL

SELECT 
    'finrag_21companies_modern',
    COUNT(DISTINCT section_name),
    CASE 
        WHEN COUNT(DISTINCT section_name) >= 16 THEN '✓ Good coverage'
        ELSE '⚠️ Limited sections'
    END
FROM finrag_21companies_modern;


-- ──────────────────────────────────────────────────────────────────────────
-- V4: Incremental Injection Impact Check
-- ──────────────────────────────────────────────────────────────────────────


WITH subset_quality AS (
    SELECT 
        'finrag_21companies_allbins' as table_name,
        load_method,
        COUNT(*) as n_rows,
        COUNT(DISTINCT cik_int) as n_companies,
        
        -- Check for NULL/placeholder values in critical fields
        SUM(CASE WHEN tickers IS NULL THEN 1 ELSE 0 END) as null_tickers,
        SUM(CASE WHEN tickers = ['MANUAL_REVIEW_REQ'] THEN 1 ELSE 0 END) as placeholder_tickers,
        SUM(CASE WHEN sic IS NULL THEN 1 ELSE 0 END) as null_sic,
        SUM(CASE WHEN filingDate IS NULL THEN 1 ELSE 0 END) as null_filingDate,
        
        -- Feature flags should be populated by Section D
        SUM(CASE WHEN likely_kpi IS NULL THEN 1 ELSE 0 END) as null_kpi_flags,
        SUM(CASE WHEN has_numbers IS NULL THEN 1 ELSE 0 END) as null_number_flags,
        
        -- Check if GOOGL data is present
        MAX(CASE WHEN cik_int = 1652044 THEN 'GOOGL PRESENT' ELSE NULL END) as googl_status
        
    FROM finrag_21companies_allbins
    GROUP BY load_method
    
    UNION ALL
    
    SELECT 
        'finrag_21companies_modern',
        load_method,
        COUNT(*),
        COUNT(DISTINCT cik_int),
        SUM(CASE WHEN tickers IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN tickers = ['MANUAL_REVIEW_REQ'] THEN 1 ELSE 0 END),
        SUM(CASE WHEN sic IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN filingDate IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN likely_kpi IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN has_numbers IS NULL THEN 1 ELSE 0 END),
        MAX(CASE WHEN cik_int = 1652044 THEN 'GOOGL PRESENT' ELSE NULL END)
    FROM finrag_21companies_modern
    GROUP BY load_method
)
SELECT 
    '═══ SUBSET QUALITY VALIDATION ═══' as validation_type,
    table_name,
    load_method,
    n_rows,
    n_companies,
    googl_status,
    null_tickers,
    placeholder_tickers,
    null_sic,
    null_filingDate,
    null_kpi_flags,
    null_number_flags,
    CASE 
        WHEN null_tickers = 0 AND null_filingDate = 0 AND null_kpi_flags = 0 
        THEN '✅ All critical fields populated'
        WHEN null_tickers > 0 OR placeholder_tickers > 0
        THEN '⚠️ Ticker metadata needs review'
        WHEN null_kpi_flags > 0
        THEN '❌ Feature engineering failed for some rows'
        ELSE '○ Acceptable quality'
    END as quality_status
FROM subset_quality
ORDER BY table_name, load_method;



--#,validation_type,table_name,load_method,n_rows,n_companies,googl_status,null_tickers,placeholder_tickers,null_sic,null_filingDate,null_kpi_flags,null_number_flags,quality_status
--1,═══ SUBSET QUALITY VALIDATION ═══,finrag_21companies_allbins,incremental_inject,"8,510",1,GOOGL PRESENT,0,0,0,0,0,0,✅ All critical fields populated
--2,═══ SUBSET QUALITY VALIDATION ═══,finrag_21companies_allbins,stratified_sampling,"278,556",20,[NULL],0,0,0,0,0,0,✅ All critical fields populated
--3,═══ SUBSET QUALITY VALIDATION ═══,finrag_21companies_modern,incremental_inject,"6,702",1,GOOGL PRESENT,0,0,0,0,0,0,✅ All critical fields populated
--4,═══ SUBSET QUALITY VALIDATION ═══,finrag_21companies_modern,stratified_sampling,"175,619",20,[NULL],0,0,0,0,0,0,✅ All critical fields populated



-- ══════════════════════════════════════════════════════════════════════════
-- SECTION 5: EXPORT - Template Pattern
-- 
-- EXPORT TEMPLATE (apply for each table):
	
	-- SET VARIABLE export_name = '{export_filename}';
	-- SET VARIABLE export_path = (export_base_path || '/' || export_name);
	-- PREPARE export_stmt AS COPY {table_name} TO ? (FORMAT PARQUET, COMPRESSION 'ZSTD');
	-- EXECUTE export_stmt(export_path);
-- ══════════════════════════════════════════════════════════════════════════


SET VARIABLE export_base_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports';


-- ──────────────────────────────────────────────────────────────────────────
-- EXPORT: Config 1
-- ──────────────────────────────────────────────────────────────────────────

SET VARIABLE export_name_1 = 'finrag_21companies_allbins.parquet';
SET VARIABLE export_path_1 = (getvariable('export_base_path') || '/' || getvariable('export_name_1'));

SELECT 'Exporting Config 1...' as status, getvariable('export_path_1') as destination;

PREPARE export_table1 AS
    COPY finrag_21companies_allbins TO ? (FORMAT PARQUET, COMPRESSION 'ZSTD', ROW_GROUP_SIZE 100000);

EXECUTE export_table1(getvariable('export_path_1'));

SELECT 
    '✓ Export Complete' as status,
    'finrag_21companies_allbins' as table_name,
    getvariable('export_name_1') as filename,
    COUNT(*) as rows_exported
FROM finrag_21companies_allbins;


-- ──────────────────────────────────────────────────────────────────────────
-- EXPORT: Config 2
-- ──────────────────────────────────────────────────────────────────────────

SET VARIABLE export_name_2 = 'finrag_21companies_modern.parquet';
SET VARIABLE export_path_2 = (getvariable('export_base_path') || '/' || getvariable('export_name_2'));

SELECT 'Exporting Config 2...' as status, getvariable('export_path_2') as destination;

PREPARE export_table2 AS
    COPY finrag_21companies_modern TO ? (FORMAT PARQUET, COMPRESSION 'ZSTD', ROW_GROUP_SIZE 100000);

EXECUTE export_table2(getvariable('export_path_2'));

SELECT 
    '✓ Export Complete' as status,
    'finrag_21companies_modern' as table_name,
    getvariable('export_name_2') as filename,
    COUNT(*) as rows_exported
FROM finrag_21companies_modern;


-- ══════════════════════════════════════════════════════════════════════════
-- SECTION 6: FINAL SUCCESS SUMMARY
-- ══════════════════════════════════════════════════════════════════════════

SELECT 
    '═══════════════════════════════════════════════════════' as separator,
    '     ✓✓✓ TABLE SUBSETTING COMPLETE ✓✓✓                 ' as status,
    '═══════════════════════════════════════════════════════' as separator2;

SELECT 
    config_id,
    table_name,
    export_filename,
    description,
    CASE WHEN enabled THEN '✓ Created & Exported' ELSE '○ Skipped' END as result
FROM subset_configs
WHERE enabled = TRUE
ORDER BY config_id;





