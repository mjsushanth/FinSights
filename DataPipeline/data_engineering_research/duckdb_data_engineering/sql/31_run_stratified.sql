/*
-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================

--
-- OBJECTIVE:
-- Sample 1M sentences from 71.8M corpus using stratified sampling

-- STRATIFICATION DIMENSIONS:
-- 1. Company (CIK) - 700 target companies
-- 2. Temporal bins - Decide on an A/B/C weighting (2006-2009, 2010-2015, 2016-2020) (Example: 15/20/65.)
-- 3. New item: After 1m sampling, Add GOOGL data manually. We decided that it was important enough to incorporate it manually.


╔══════════════════════════════════════════════════════════════════════════╗
║                    REQUIRED ASSETS BEFORE EXECUTION                      ║
╚══════════════════════════════════════════════════════════════════════════╝

PARQUET FILES (Data Sources):
1. sec_filings_large_full.parquet
   • Location: /data/exports/
   • Source: HuggingFace dataset which has been custom-merged ( JSONL/arrows to Parquet 30x compression. )
   • Content: 71.8M sentences, 4,674 companies, 1993-2020

2. [OPTIONAL] 10-K_merged_YYYY_YYYY_COMPANY_DATE.parquet
   • Location: /data/exports/
   • Purpose: Incremental injection (e.g., GOOGL historical data)
   • Required if: enable_incremental_injection = TRUE

DIMENSION TABLES (Must exist in sampler.main schema):
3. finrag_tgt_comps_75
   • Columns: cik_int (INTEGER), company_name (VARCHAR)
   • Purpose: Defines which 75 companies to sample
   • Created by: Company curation scripts (31_2, 31_4)

4. dim_sec_sections
   • Columns: sec_item_canonical, hf_section_code, section_name, section_category, priority
   • Purpose: Maps HF section codes (0-19) to canonical SEC item names (ITEM_1A, ITEM_7, etc.)
   • Created by: 32_2_SectionName_DimensionCreation.sql

OPTIONAL TABLES (For downstream subsets):
5. finrag_tgt_comps_21 - For 21-company subsets
6. finrag_tgt_comps_51 - For 51-company subsets

╔══════════════════════════════════════════════════════════════════════════╗
║                         EXECUTION PARAMETERS                             ║
╚══════════════════════════════════════════════════════════════════════════╝

MODIFY THESE BEFORE RUNNING (Section A):
- parquet_source_path - Path to sec_filings_large_full.parquet
- result_save_path - Output directory for sample parquet
- company_table - Which company filter table to use (default: finrag_tgt_comps_75)
- sample_size_n - Target sample size (default: 1,000,000)
- enable_incremental_injection - TRUE to merge external data, FALSE to skip


-- ALLOCATION STRATEGY:
--   Priority 1: Take 100% of bin_2016_2020 (modern era)
--   Priority 2: If budget remains, allocate to older bins (60% bin2, 40% bin1)
--   Priority 3: If modern era exceeds budget, sample it and warn

-- DECISIONS:
-- Recency bias: 65% of sample from 2016-2020 (user query patterns)
-- Company filter: Only 700 high-quality companies (S&P 500 + Notable)
-- Random sampling within a company-year could systematically exclude certain sections, creating a biased representation. 
-- The sampling method risks losing critical information from less frequent sections, potentially skewing our dataset's comprehensiveness.

-- Coding Strategies:
Stage 1: Sample sentenceIDs only (lightweight)
Stage 2: Join back to parquet for complete schema


-- SECTION A: Setup & Parameters
   ├─ Create execution_log table
   ├─ Create params table
   └─ Log: START

-- SECTION B: Sampling Logic (Blocks 1-6 from your learning file)
   ├─ Load corpus_tagged
   ├─ Calculate bin_populations
   ├─ Pivot populations
   ├─ Calculate allocations
   ├─ Create bin_allocations
   ├─ Execute sampling → sample_sentenceIDs (lightweight!)
   └─ Log: SAMPLING_COMPLETE

-- SECTION C: Schema Retrieval (Join-back)
   ├─ Join sample_sentenceIDs to parquet (get ALL columns)
   ├─ Add audit columns (created_at, version, etc.)
   └─ Log: SCHEMA_RETRIEVAL_COMPLETE

-- SECTION D: Feature Engineering (Derived Flags)
   ├─ UPDATE: Add features, likely_kpi or numeric flags, increase/decrease indicators, temporal, etc. 
   └─ Log: FEATURE_FLAGS_ADDED

-- SECTION E: Final Validation & Summary
   ├─ Row counts, distributions
   ├─ Coverage checks
   ├─ Display execution_log (all steps)
   └─ Export readiness check


Source Parquet (HF encoding: 0-19)
         ↓
    [31_run Script] ← FIX HERE if any fixes are needed.
         ↓
 sample_1m_finrag (+ section_name or any new columns addition.)
         ↓
    ┌────┴────┬────────────┐
    ↓         ↓            ↓
21_companies  modern_only  future_subsets.. 


┌─────────────────────────────────────────────────────┐
│  SAMPLING LAYER (Computational Domain)              │
│  • Uses: section (integer 0-19)                     │
│  • Focus: Performance, reproducibility, stability   │
│  • Modified: ?  No need (locked HF encoding)        │
└─────────────────────────────────────────────────────┘
                          ↓
                    (Late binding)
                          ↓
┌─────────────────────────────────────────────────────┐
│  SEMANTIC LAYER (Business Domain)                   │
│  • Uses: section_name, sec_item_canonical           │
│  • Focus: Human consumption, integration, queries   │
│  • Modified: As needed (rename labels, add fields)  │
└─────────────────────────────────────────────────────┘

-- ============================================================================
 */


-- ============================================================================
-- SECTION A: SETUP & PARAMETERS
-- ============================================================================


-- Drop all temp tables to ensure fresh start
DROP TABLE IF EXISTS execution_log;
DROP TABLE IF EXISTS params;
DROP TABLE IF EXISTS corpus_tagged;
DROP TABLE IF EXISTS bin_populations;
DROP TABLE IF EXISTS bin_populations_pivoted;
DROP TABLE IF EXISTS allocation_decisions;
DROP TABLE IF EXISTS bin_allocations;
DROP TABLE IF EXISTS sample_sentenceIDs;
DROP TABLE IF EXISTS sample_combined;
-- Drop final table too (test full recreation)
DROP TABLE IF EXISTS sample_1m_finrag;
SELECT 'Clean slate ready' as status;


CREATE OR REPLACE TEMP TABLE execution_log (
    step_number INTEGER,
    step_name VARCHAR,
    status VARCHAR,
    row_count INTEGER,
    message VARCHAR,
    execution_time TIMESTAMP
);

SELECT 'LOG TABLE RESET' as status, 'Ready for new execution' as message;


INSERT INTO execution_log VALUES 
    (0, 'INITIALIZATION', 'STARTED', NULL, 
     'Stratified sampling procedure initiated', 
     CURRENT_TIMESTAMP);


-- Create parameters (modify these when on cloud !!)

-- Same as src file path, duplicated here because of binder-problem in inner query sub query.
SET VARIABLE parquet_source_path  = 
'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_filings_large_full.parquet';

SET VARIABLE result_save_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports';
SET VARIABLE result_parquet_name = 'sec_finrag_1M_sample'; 

-- Sampling parameters
SET VARIABLE company_table = 'finrag_tgt_comps_75';
SET VARIABLE sample_size_n = 1000000;
SET VARIABLE sample_version = 'v1.0_75companies_1M';

-- Temporal bin weights
SET VARIABLE priority_bin = 'bin_2016_2020'; 		-- 100% of latest bins.
SET VARIABLE older_bin2_weight = 0.60;  				-- 60% to 2010-2015
SET VARIABLE older_bin1_weight = 0.40;  				-- 40% to 2006-2009


SELECT 'VARIABLES SET' as status;
SELECT 
    getvariable('parquet_source_path') as parquet_path,
    getvariable('sample_size_n') as sample_size,
    getvariable('sample_version') as version;

-- ══════════════════════════════════════════════════════════════════════════
-- INCREMENTAL DATA INJECTION SETTINGS
-- Enable to merge external data sources (APIs, partners, additional companies)
-- If disabled, script runs normal sampling pipeline only
-- ══════════════════════════════════════════════════════════════════════════

SET VARIABLE enable_incremental_injection = TRUE;  -- Set FALSE to skip injection

SET VARIABLE incremental_data_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/10-K_merged_2015_2019_GOOGL_1025.parquet';

SELECT 
    'Incremental Injection: ' || 
    CASE WHEN getvariable('enable_incremental_injection') THEN '✓ ENABLED' ELSE '○ DISABLED' END 
    as injection_status;
-- ══════════════════════════════════════════════════════════════════════════



CREATE OR REPLACE TEMP TABLE params AS 
SELECT 
    getvariable('company_table') as company_table,                     
    
    CAST(getvariable('sample_size_n') AS INTEGER) as sample_size_n,  
    'bin_2016_2020' as priority_bin,
    CAST(getvariable('older_bin2_weight') AS DOUBLE) as older_bin2_weight,
    CAST(getvariable('older_bin1_weight') AS DOUBLE) as older_bin1_weight,
    
    getvariable('sample_version') as sample_version,
    getvariable('parquet_source_path') as source_file_path;

SELECT 'PARAMETERS TABLE CREATED' as status;

-- ============================================================================
-- QUICK VALIDATION:
SELECT 
    'PARAMS VALIDATION' as check_type,
    sample_size_n,
    CASE 
        WHEN sample_size_n IS NULL THEN '❌ CRITICAL ERROR: sample_size_n is NULL - check variable names!'
        WHEN sample_size_n = 1000000 THEN '✅ Correct: 1M budget loaded'
        ELSE '⚠️ Unexpected: ' || CAST(sample_size_n AS VARCHAR)
    END as validation_status
FROM params;
-- ============================================================================

INSERT INTO execution_log VALUES 
    (1, 'PARAMETERS', 'COMPLETE', 1, 
     'Sample size: ' || (SELECT sample_size_n FROM params) || ', Companies: 75', 
     CURRENT_TIMESTAMP);


-- ============================================================================
-- SECTION B: SAMPLING LOGIC
-- ============================================================================

-- ──────────────────────────────────────────────────────────────────────────
-- STEP B1: Load corpus and tag with temporal bins
-- ──────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TEMP TABLE corpus_tagged AS

SELECT 
    CAST(cik AS VARCHAR) as cik,
    CAST(cik AS INTEGER) as cik_int,
    sentenceID,  -- PRIMARY KEY for join-back
    section,
    docID,
    reportDate,
    YEAR(CAST(reportDate AS DATE)) as report_year,
    
    CASE 
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2009 THEN 'bin_2006_2009'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2010 AND 2015 THEN 'bin_2010_2015'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2016 AND 2020 THEN 'bin_2016_2020'
    END as temporal_bin
    
FROM read_parquet( getvariable('parquet_source_path') )
WHERE CAST(cik AS INTEGER) IN (
    SELECT cik_int FROM finrag_tgt_comps_75
)
AND YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2020
AND section IS NOT NULL
AND sentence IS NOT NULL
AND LENGTH(sentence) > 10;

INSERT INTO execution_log VALUES 
    (2, 'CORPUS_LOAD', 'COMPLETE', 
     (SELECT COUNT(*) FROM corpus_tagged),
     'Loaded ' || (SELECT COUNT(DISTINCT cik_int) FROM corpus_tagged) || ' companies',
     CURRENT_TIMESTAMP);

SELECT 'CORPUS LOADED' as status, COUNT(*) as rows FROM corpus_tagged;


-- ──────────────────────────────────────────────────────────────────────────
-- STEP B2: Calculate bin populations
-- ──────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TEMP TABLE bin_populations AS
SELECT 
    temporal_bin,
    COUNT(*) as bin_population,
    COUNT(DISTINCT cik_int) as n_companies,
    COUNT(DISTINCT docID) as n_filings,
    COUNT(DISTINCT section) as n_sections
FROM corpus_tagged
GROUP BY temporal_bin;

INSERT INTO execution_log VALUES 
    (3, 'BIN_POPULATIONS', 'COMPLETE', 
     (SELECT COUNT(*) FROM bin_populations),
     'Calculated populations for 3 temporal bins',
     CURRENT_TIMESTAMP);

SELECT 'BIN POPULATIONS CALCULATED' as status;
SELECT * FROM bin_populations ORDER BY temporal_bin;


-- ──────────────────────────────────────────────────────────────────────────
-- STEP B3: Pivot bin populations (relational pattern - single scan)
-- ──────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TEMP TABLE bin_populations_pivoted AS
SELECT 
    MAX(CASE WHEN temporal_bin = 'bin_2016_2020' THEN bin_population END) as modern_pop,
    MAX(CASE WHEN temporal_bin = 'bin_2010_2015' THEN bin_population END) as bin2_pop,
    MAX(CASE WHEN temporal_bin = 'bin_2006_2009' THEN bin_population END) as bin1_pop,
    SUM(bin_population) as total_population
FROM bin_populations;

INSERT INTO execution_log VALUES 
    (4, 'PIVOT_POPULATIONS', 'COMPLETE', 1,
     'Modern bin: ' || (SELECT modern_pop FROM bin_populations_pivoted) || ' sentences',
     CURRENT_TIMESTAMP);

SELECT 'POPULATIONS PIVOTED' as status;
SELECT * FROM bin_populations_pivoted;


-- ──────────────────────────────────────────────────────────────────────────
-- STEP B4: Calculate allocation strategy
-- ──────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TEMP TABLE allocation_decisions AS

SELECT 
    p.sample_size_n as target_budget,
    bpp.modern_pop,
    bpp.bin2_pop,
    bpp.bin1_pop,
    bpp.total_population,
    
    -- Allocation mode
    CASE 
        WHEN bpp.modern_pop >= p.sample_size_n THEN 'MODERN_ONLY'
        ELSE 'MODERN_FULL_PLUS_OLDER'
    END as allocation_mode,
    
    -- Modern bin allocation
    CASE 
        WHEN bpp.modern_pop >= p.sample_size_n 
        THEN p.sample_size_n  -- Sample from modern (exceeds budget)
        ELSE bpp.modern_pop   -- Take 100% (within budget)
    END as modern_target,
    
    -- Leftover budget
    GREATEST(0, p.sample_size_n - bpp.modern_pop) as leftover_budget,
    
    -- Older bin allocations (60/40 split)
    CAST(ROUND(GREATEST(0, p.sample_size_n - bpp.modern_pop) * p.older_bin2_weight) AS INTEGER) as bin2_target,
    CAST(ROUND(GREATEST(0, p.sample_size_n - bpp.modern_pop) * p.older_bin1_weight) AS INTEGER) as bin1_target
    
FROM params p
CROSS JOIN bin_populations_pivoted bpp;


INSERT INTO execution_log VALUES 
    (5, 'ALLOCATION_STRATEGY', 'COMPLETE', 1,
     'Mode: ' || (SELECT allocation_mode FROM allocation_decisions) || 
     ', Modern: ' || (SELECT modern_target FROM allocation_decisions),
     CURRENT_TIMESTAMP);



SELECT 'ALLOCATION STRATEGY CALCULATED' as status;

SELECT allocation_mode, modern_target, bin2_target, bin1_target,
       (modern_target + bin2_target + bin1_target) as total_allocated
FROM allocation_decisions;



-- ──────────────────────────────────────────────────────────────────────────
-- STEP B5: Create bin allocations table (unpivot for sampling)
-- ──────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TEMP TABLE bin_allocations AS
SELECT 
    'bin_2016_2020' as temporal_bin,
    ad.modern_target as target_n,
    bpp.modern_pop as population,
    ROUND(ad.modern_target * 100.0 / bpp.modern_pop, 2) as sampling_rate_pct,
    1 as priority_order
FROM allocation_decisions ad
CROSS JOIN bin_populations_pivoted bpp

UNION ALL

SELECT 
    'bin_2010_2015',
    ad.bin2_target,
    bpp.bin2_pop,
    ROUND(ad.bin2_target * 100.0 / bpp.bin2_pop, 2),
    2
FROM allocation_decisions ad
CROSS JOIN bin_populations_pivoted bpp

UNION ALL

SELECT 
    'bin_2006_2009',
    ad.bin1_target,
    bpp.bin1_pop,
    ROUND(ad.bin1_target * 100.0 / bpp.bin1_pop, 2),
    3
FROM allocation_decisions ad
CROSS JOIN bin_populations_pivoted bpp;

INSERT INTO execution_log VALUES 
    (6, 'BIN_ALLOCATIONS', 'COMPLETE', 
     (SELECT COUNT(*) FROM bin_allocations),
     'Allocations prepared for 3 bins',
     CURRENT_TIMESTAMP);

SELECT 'BIN ALLOCATIONS PREPARED' as status;
SELECT temporal_bin, population, target_n, sampling_rate_pct,
       CASE 
           WHEN sampling_rate_pct >= 99 THEN '✓✓ COMPLETE (≥99%)'
           WHEN sampling_rate_pct >= 50 THEN '✓ HIGH (50-99%)'
           WHEN sampling_rate_pct >= 25 THEN '○ MODERATE (25-50%)'
           ELSE '△ LIGHT (<25%)'
       END as coverage_level
FROM bin_allocations
ORDER BY priority_order;


-- ──────────────────────────────────────────────────────────────────────────
-- STEP B6: Execute stratified sampling (all bins, lightweight)
-- ──────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TEMP TABLE sample_sentenceIDs AS
WITH sampling_logic AS (
    SELECT 
        ct.sentenceID,  -- PRIMARY KEY for join-back
        ct.cik_int,
        ct.temporal_bin,
        ct.report_year,
        ct.section,
        ba.target_n as bin_target,
        ba.population as bin_population,
        
        -- Stratification: Random order within each stratum
        ROW_NUMBER() OVER (
            PARTITION BY ct.temporal_bin, ct.cik_int, ct.report_year, ct.section
            ORDER BY RANDOM()
        ) as rn_within_stratum,
        
        COUNT(*) OVER (
            PARTITION BY ct.temporal_bin, ct.cik_int, ct.report_year, ct.section
        ) as stratum_size
        
    FROM corpus_tagged ct
    INNER JOIN bin_allocations ba ON ct.temporal_bin = ba.temporal_bin
    WHERE ba.target_n > 0  -- Only process bins with allocation
),

stratum_sample_sizes AS (
    -- Calculate how many to take from each stratum
    SELECT 
        sentenceID,
        cik_int,
        temporal_bin,
        rn_within_stratum,
        CASE 
            WHEN bin_target >= bin_population THEN stratum_size  
            ELSE GREATEST(1,  
                CAST(ROUND(stratum_size * (bin_target * 1.0 / bin_population)) AS INTEGER)
            )
        END as stratum_sample_n,
        ROUND(bin_target * 100.0 / bin_population, 2) as bin_sampling_rate
    FROM sampling_logic
)

SELECT 
    sentenceID,
    cik_int,
    temporal_bin,
    bin_sampling_rate as sampling_rate_pct
FROM stratum_sample_sizes
WHERE rn_within_stratum <= stratum_sample_n;



INSERT INTO execution_log VALUES 
    (7, 'SAMPLING_EXECUTION', 'COMPLETE', 
     (SELECT COUNT(*) FROM sample_sentenceIDs),
     'Sampled ' || (SELECT COUNT(*) FROM sample_sentenceIDs) || ' sentenceIDs across 3 bins',
     CURRENT_TIMESTAMP);



SELECT 'SAMPLING COMPLETE - sentenceIDs selected' as status, 
       COUNT(*) as n_sampled_IDs 
FROM sample_sentenceIDs;

-- Quick distribution check
SELECT 
    temporal_bin,
    COUNT(*) as n_sampled,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct_of_sample
FROM sample_sentenceIDs
GROUP BY temporal_bin
ORDER BY temporal_bin;

--#,temporal_bin,n_sampled,pct_of_sample
--1,bin_2006_2009,"139,569",13.91
--2,bin_2010_2015,"209,869",20.91
--3,bin_2016_2020,"654,096",65.18


-- ============================================================================
-- SECTION C: SCHEMA RETRIEVAL (Join-back to Source)
-- ============================================================================

-- ──────────────────────────────────────────────────────────────────────────
-- STEP C1: Join sample_sentenceIDs back to parquet for COMPLETE schema
-- ──────────────────────────────────────────────────────────────────────────


CREATE OR REPLACE TABLE sample_1m_finrag AS

	SELECT 
	    ROW_NUMBER() OVER (
	        ORDER BY si.temporal_bin, corpus.reportDate, corpus.cik, corpus.section
	    ) as sample_id,
	    
	    -- ═══════════════════════════════════════════════════════════════════
	    -- ALL ORIGINAL COLUMNS FROM SOURCE (Complete Schema Preservation)
	    -- ═══════════════════════════════════════════════════════════════════
	    corpus.cik,
	    corpus.sentence,
	    
	    corpus.section as section_ID,    
	
	    dim.sec_item_canonical as section_name,  -- ITEM_1A, KEY for sec joins or search clauses
		dim.section_name as section_desc,        -- "Item 1A: Risk Factors" 
		dim.section_category,                    -- P1_RISK
		dim.priority as sec_dim_priority,         -- P1 
		    
	    corpus.labels,
	    corpus.filingDate,
	    corpus.name,
	    corpus.docID,
	    corpus.sentenceID,
	    corpus.sentenceCount,
	    corpus.tickers,
	    corpus.exchanges,
	    corpus.entityType,
	    corpus.sic,
	    corpus.stateOfIncorporation,
	    corpus.tickerCount,
	    corpus.acceptanceDateTime,
	    corpus.form,
	    corpus.reportDate,
	    corpus.returns,
	    
	    -- ═══════════════════════════════════════════════════════════════════
	    -- DERIVED COLUMNS (From Sampling Process)
	    -- ═══════════════════════════════════════════════════════════════════
	    CAST(corpus.cik AS INTEGER) as cik_int,
	    YEAR(CAST(corpus.reportDate AS DATE)) as report_year,
	    si.temporal_bin,
	    si.sampling_rate_pct,
	    
	    -- Text characteristics
	    LENGTH(corpus.sentence) as char_count,
	    LENGTH(corpus.sentence) - LENGTH(REPLACE(corpus.sentence, ' ', '')) + 1 as word_count_approx,
	    
	    -- ═══════════════════════════════════════════════════════════════════
	    -- AUDIT COLUMNS (ETL Pattern - Incremental Load Support)
	    -- ═══════════════════════════════════════════════════════════════════
	    CURRENT_TIMESTAMP as sample_created_at,
	    CURRENT_TIMESTAMP as last_modified_date,  -- For incremental load tracking
	    ( getvariable('sample_version')  ) as sample_version,
	    ( getvariable('parquet_source_path') ) as source_file_path,
	    
	    -- Data lineage tracking
	    'stratified_sampling' as load_method,
	    'complete' as record_status,
	    
	    -- row hash for deduplication in future loads
	    MD5(corpus.sentenceID || corpus.sentence) as row_hash
	    
	FROM sample_sentenceIDs si
	INNER JOIN read_parquet( getvariable('parquet_source_path') ) corpus
	    ON si.sentenceID = corpus.sentenceID
	LEFT JOIN sampler.main.dim_sec_sections dim           -- dim sections standardized table mapping
	    ON corpus.section = dim.hf_section_code           -- 
	ORDER BY sample_id;


INSERT INTO execution_log VALUES 
    (8, 'SCHEMA_RETRIEVAL', 'COMPLETE', 
     (SELECT COUNT(*) FROM sample_1m_finrag),
     'Retrieved complete schema (' || 
     (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'sample_1m_finrag') || 
     ' columns) for ' || (SELECT COUNT(*) FROM sample_1m_finrag) || ' sentences',
     CURRENT_TIMESTAMP);

SELECT 'FINAL TABLE CREATED WITH COMPLETE SCHEMA' as status,
       COUNT(*) as total_rows,
       COUNT(DISTINCT cik_int) as n_companies
FROM sample_1m_finrag;

--#,status,total_rows,n_companies
--1,FINAL TABLE CREATED WITH COMPLETE SCHEMA,"1,003,534",75

--#,status,total_rows,n_companies
--1,FINAL TABLE CREATED WITH COMPLETE SCHEMA,"1,003,534",75





-- ══════════════════════════════════════════════════════════════════════════
-- SECTION C1b: INCREMENTAL DATA INJECTION (API/External Sources)
-- Location: After C1 (main sample created), before C2 (validation)
-- Purpose: Merge additional company data from external sources (APIs, partners) !! 
-- ══════════════════════════════════════════════════════════════════════════

/*
 * Step 1: Compares schemas, shows what columns are missing
 * Step 2: Creates staging_incremental table with proper schema alignment
 * Step 3: Validates for duplicates before merge
 * Step 4: MERGE logic using DELETE + INSERT (DuckDB doesn't support MERGE directly)
 */


-- ══════════════════════════════════════════════════════════════════════════
-- SECTION C1b: INCREMENTAL DATA INJECTION (CONDITIONAL)
-- Only executes if enable_incremental_injection = TRUE
-- ══════════════════════════════════════════════════════════════════════════

-- All queries wrapped in WHERE clause checking the flag

-- ──────────────────────────────────────────────────────────────────────────
-- C1b 0: STEP 0: Check if injection is enabled
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '═════════════════════════════════════════' as separator,
    CASE 
        WHEN getvariable('enable_incremental_injection') 
        THEN 'SECTION C1b: INCREMENTAL DATA INJECTION - ACTIVE'
        ELSE 'SECTION C1b: INCREMENTAL DATA INJECTION - SKIPPED'
    END as status
WHERE getvariable('enable_incremental_injection') = TRUE;  


-- ──────────────────────────────────────────────────────────────────────────
-- C1b 1: STEP 1: Column Comparison (Conditional) (Name-Based Matching, Order-Independent)
-- ──────────────────────────────────────────────────────────────────────────



WITH target_columns AS (
    SELECT 
        UPPER(TRIM(column_name)) as column_normalized,
        column_name as target_column
    FROM information_schema.columns 
    WHERE table_name = 'sample_1m_finrag'
),
source_columns AS (
    SELECT 
        UPPER(TRIM(column_name)) as column_normalized,
        column_name as source_column
    FROM (DESCRIBE SELECT * FROM read_parquet(getvariable('incremental_data_path')))
),
all_columns AS (
    SELECT column_normalized FROM target_columns
    UNION
    SELECT column_normalized FROM source_columns
)
SELECT 
    '📋 SCHEMA COMPARISON' as check,
    COALESCE(t.target_column, a.column_normalized) as column_name,
    t.target_column as in_target,
    s.source_column as in_source,
    CASE 
        WHEN t.target_column IS NOT NULL AND s.source_column IS NOT NULL THEN '✅ Both'
        WHEN t.target_column IS NOT NULL AND s.source_column IS NULL THEN '⚠️ Target only'
        WHEN t.target_column IS NULL AND s.source_column IS NOT NULL THEN '⚠️ Source only'
    END as status
FROM all_columns a
LEFT JOIN target_columns t ON a.column_normalized = t.column_normalized
LEFT JOIN source_columns s ON a.column_normalized = s.column_normalized
WHERE getvariable('enable_incremental_injection') = TRUE
ORDER BY status, column_name;



-- ──────────────────────────────────────────────────────────────────────────
-- C1b 2: STEP 2: Create Staging Table with Schema Alignment
-- Maps incremental data to target schema, handles missing columns
-- ──────────────────────────────────────────────────────────────────────────


-- in this data; 
-- section_name = descriptive text (useless for joins)
-- section_item = canonical ID (what actually need)

DROP TABLE IF EXISTS staging_incremental;


CREATE TEMP TABLE staging_incremental AS

SELECT 
    -- ═══════════════════════════════════════════════════════════════════
    -- Generate new sample_id (continues from existing max)
    -- ═══════════════════════════════════════════════════════════════════
    (SELECT COALESCE(MAX(sample_id), 0) FROM sample_1m_finrag) + 
        ROW_NUMBER() OVER (ORDER BY report_year, sentenceID) as sample_id,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- IDENTIFIERS - Direct mapping from source
    -- ═══════════════════════════════════════════════════════════════════
    src.cik,
    src.sentence,
    src.section_ID,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- SECTION METADATA - Map section_item to section_name + enrich from dim
    -- ═══════════════════════════════════════════════════════════════════
    src.section_item as section_name, 
    
	dim.section_name as section_desc,      		-- ✅ "Item 1A: Risk Factors"
	dim.section_category as section_category,  	-- ✅ P1_RISK
    COALESCE(dim.priority, 'P3') as sec_dim_priority,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- MISSING COLUMNS - Set NULL with proper types
    -- ═══════════════════════════════════════════════════════════════════
    CAST(NULL AS STRUCT("1d" INTEGER, "5d" INTEGER, "30d" INTEGER)) as labels,
    
    src.filingDate,
    src.name,
    src.docID,
    src.sentenceID,
    CAST(NULL AS BIGINT) as sentenceCount,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- COMPANY METADATA - Derive for known companies or use placeholder
    -- ═══════════════════════════════════════════════════════════════════
    CASE 
        WHEN UPPER(src.name) LIKE '%ALPHABET%' OR UPPER(src.name) LIKE '%GOOGLE%' 
        THEN ['GOOGL', 'GOOG']
        ELSE ['MANUAL_REVIEW_REQ']  -- Placeholder for unknown companies
    END as tickers,
    
    CASE 
        WHEN UPPER(src.name) LIKE '%ALPHABET%' OR UPPER(src.name) LIKE '%GOOGLE%' 
        THEN ['NASDAQ']
        ELSE ['EXCHANGE_UNKNOWN']  -- Placeholder
    END as exchanges,
    
    'operating' as entityType,  -- Safe default for public companies
    
    UPPER(COALESCE(src.SIC, src.sic)) as sic,  -- Handle case difference
    
    CASE 
        WHEN UPPER(src.name) LIKE '%ALPHABET%' OR UPPER(src.name) LIKE '%GOOGLE%' 
        THEN 'DE'  -- Alphabet Inc. incorporated in Delaware
        ELSE 'XX'  -- ISO placeholder for unknown state/country
    END as stateOfIncorporation,
    
    CASE 
        WHEN UPPER(src.name) LIKE '%ALPHABET%' OR UPPER(src.name) LIKE '%GOOGLE%' 
        THEN 2  -- GOOGL and GOOG share classes
        ELSE 1  -- Default assumption
    END as tickerCount,
    
    -- Approximate acceptanceDateTime from filingDate
    TRY_CAST(src.filingDate || 'T00:00:00.000Z' AS TIMESTAMP) as acceptanceDateTime,
    
    src.form,
    src.reportDate,
    
    -- Returns struct - NULL (stock price data not available)
    CAST(NULL AS STRUCT("1d" STRUCT(closePriceEndDate DOUBLE, closePriceStartDate DOUBLE, 
                                     endDate VARCHAR, startDate VARCHAR, ret DOUBLE),
                        "5d" STRUCT(closePriceEndDate DOUBLE, closePriceStartDate DOUBLE, 
                                     endDate VARCHAR, startDate VARCHAR, ret DOUBLE),
                        "30d" STRUCT(closePriceEndDate DOUBLE, closePriceStartDate DOUBLE, 
                                      endDate VARCHAR, startDate VARCHAR, ret DOUBLE))) as returns,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- DERIVED COLUMNS - Calculate immediately
    -- ═══════════════════════════════════════════════════════════════════
    TRY_CAST(src.cik AS INTEGER) as cik_int,
    src.report_year,
    src.temporal_bin,  -- Source already has this
    
    CAST(NULL AS DOUBLE) as sampling_rate_pct,  -- N/A for injected data
    
    LENGTH(src.sentence) as char_count,
    LENGTH(src.sentence) - LENGTH(REPLACE(src.sentence, ' ', '')) + 1 as word_count_approx,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- AUDIT COLUMNS - Use source values or override
    -- ═══════════════════════════════════════════════════════════════════
	COALESCE(CAST(src.sample_created_at AS TIMESTAMP), CURRENT_TIMESTAMP) as sample_created_at,
	COALESCE(CAST(src.last_modified_date AS TIMESTAMP), CURRENT_TIMESTAMP) as last_modified_date,
	COALESCE(src.sample_version, 'incremental_v1') as sample_version,
	COALESCE(src.source_file_path, getvariable('incremental_data_path')) as source_file_path,
    
    'incremental_inject' as load_method,  -- Override to track injection
    'staged' as record_status,
    
    MD5(src.sentenceID || src.sentence) as row_hash,
    
    -- ═══════════════════════════════════════════════════════════════════
    -- FEATURE FLAGS - Will be populated by Section D
    -- ═══════════════════════════════════════════════════════════════════
    
FROM read_parquet(getvariable('incremental_data_path')) src
LEFT JOIN sampler.main.dim_sec_sections dim
    ON TRIM(UPPER(src.section_item)) = TRIM(UPPER(dim.sec_item_canonical))  
    
    -- Join on canonical section name
WHERE getvariable('enable_incremental_injection') = TRUE;


-- SELECT * FROM read_parquet(getvariable('incremental_data_path')) src;


SELECT 
    '✓ STAGING TABLE CREATED' as status,
    COUNT(*) as rows_staged,
    COUNT(DISTINCT cik) as companies_staged,
    MIN(report_year) as year_min,
    MAX(report_year) as year_max,
    COUNT(DISTINCT section_name) as sections_present
FROM staging_incremental
WHERE getvariable('enable_incremental_injection') = TRUE;








-- ──────────────────────────────────────────────────────────────────────────
-- C1b 3: STEP 3: Validation
-- ──────────────────────────────────────────────────────────────────────────

WITH duplicate_check AS (
    SELECT 
        sentenceID,
        COUNT(*) as n_occurrences
    FROM (
        SELECT sentenceID FROM sample_1m_finrag
        UNION ALL
        SELECT sentenceID FROM staging_incremental
    )
    GROUP BY sentenceID
    HAVING COUNT(*) > 1
)
SELECT 
    '🔍 DUPLICATE CHECK' as validation,
    COUNT(*) as n_duplicate_sentenceIDs,
    CASE 
        WHEN COUNT(*) = 0 THEN '✅ No duplicates - safe to merge'
        ELSE '⚠️ ' || CAST(COUNT(*) AS VARCHAR) || ' duplicates found - MERGE will update'
    END as status
FROM duplicate_check
WHERE getvariable('enable_incremental_injection') = TRUE;  -- Conditional check



-- Validation: Schema Alignment Check (Staging vs Target)

WITH target_columns AS (
    SELECT 
        UPPER(TRIM(column_name)) as column_normalized,
        column_name as target_column,
        data_type as target_type
    FROM information_schema.columns 
    WHERE table_name = 'sample_1m_finrag'
),
staging_columns AS (
    SELECT 
        UPPER(TRIM(column_name)) as column_normalized,
        column_name as staging_column,
        data_type as staging_type
    FROM information_schema.columns
    WHERE table_name = 'staging_incremental'
),
all_columns AS (
    SELECT column_normalized FROM target_columns
    UNION
    SELECT column_normalized FROM staging_columns
)
SELECT 
    '🔍 STAGING ALIGNMENT CHECK' as validation,
    COALESCE(t.target_column, a.column_normalized) as column_name,
    t.target_column as in_target,
    s.staging_column as in_staging,
    t.target_type as target_type,
    s.staging_type as staging_type,
    CASE 
        WHEN t.target_column IS NOT NULL AND s.staging_column IS NOT NULL THEN '✅ Aligned'
        WHEN t.target_column IS NOT NULL AND s.staging_column IS NULL THEN '❌ Missing in staging'
        WHEN t.target_column IS NULL AND s.staging_column IS NOT NULL THEN '❌ Extra in staging'
    END as alignment_status
FROM all_columns a
LEFT JOIN target_columns t ON a.column_normalized = t.column_normalized
LEFT JOIN staging_columns s ON a.column_normalized = s.column_normalized
WHERE getvariable('enable_incremental_injection') = TRUE
ORDER BY alignment_status, column_name;




-- ──────────────────────────────────────────────────────────────────────────
-- C1b 4: STEP 4: MERGE  MERGE - Upsert Staging Data into Main Table
-- DELETE duplicates → INSERT all staged rows
-- C1b 5: Logging (Conditional)
-- ──────────────────────────────────────────────────────────────────────────

-- Count before merge (for logging)
SET VARIABLE rows_before_merge = (SELECT COUNT(*) FROM sample_1m_finrag);

-- Delete any existing rows with matching sentenceIDs (prepare for upsert)
DELETE FROM sample_1m_finrag
WHERE sentenceID IN (SELECT sentenceID FROM staging_incremental)
  AND getvariable('enable_incremental_injection') = TRUE;

-- Insert all staged rows
INSERT INTO sample_1m_finrag
SELECT * FROM staging_incremental
WHERE getvariable('enable_incremental_injection') = TRUE;

-- Update record_status to mark successful injection
UPDATE sample_1m_finrag
SET record_status = 'injected'
WHERE load_method = 'incremental_inject'
  AND getvariable('enable_incremental_injection') = TRUE;



INSERT INTO execution_log 
	SELECT 
	    9, 
	    'INCREMENTAL_INJECTION', 
	    'COMPLETE', 
	    COUNT(*),
	    'Injected ' || COUNT(*) || ' rows from external source (' || 
	    COUNT(DISTINCT cik) || ' companies, ' || 
	    (MAX(report_year) - MIN(report_year) + 1) || ' years)',
	    CURRENT_TIMESTAMP
	FROM staging_incremental
	WHERE getvariable('enable_incremental_injection') = TRUE;
	

-- ──────────────────────────────────────────────────────────────────────────
-- Post-Merge Validation
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '✓✓ INJECTION COMPLETE' as status,
    getvariable('rows_before_merge') as rows_before,
    COUNT(*) as rows_after,
    COUNT(*) - getvariable('rows_before_merge') as rows_added,
    SUM(CASE WHEN load_method = 'incremental_inject' THEN 1 ELSE 0 END) as injected_rows,
    COUNT(DISTINCT cik_int) as total_companies,
    COUNT(DISTINCT CASE WHEN load_method = 'incremental_inject' THEN cik_int END) as injected_companies
FROM sample_1m_finrag
WHERE getvariable('enable_incremental_injection') = TRUE;


--#,status,rows_before,rows_after,rows_added,injected_rows,total_companies,injected_companies
--1,✓✓ INJECTION COMPLETE,"1,003,534","1,012,044","8,510","8,510",76,1


SELECT 
    '═════════════════════════════════════════' as separator,
    'SECTION C1b COMPLETE - Proceeding to C2 Validation...' as next_step
WHERE getvariable('enable_incremental_injection') = TRUE;

DROP TABLE IF EXISTS staging_incremental;




-- ──────────────────────────────────────────────────────────────────────────
-- END OF STEP C1 !
-- ──────────────────────────────────────────────────────────────────────────




-- ──────────────────────────────────────────────────────────────────────────
-- STEP C2: Validation of join-back completeness
-- ──────────────────────────────────────────────────────────────────────────

-- Verify no sentenceIDs were lost in join
WITH join_check AS (
    SELECT 
        (SELECT COUNT(*) FROM sample_sentenceIDs) as ids_selected,
        (SELECT COUNT(*) FROM sample_1m_finrag) as rows_in_final_table,
        (SELECT COUNT(*) FROM sample_sentenceIDs) - (SELECT COUNT(*) FROM sample_1m_finrag) as lost_rows
)
SELECT 
    *,
    CASE 
        WHEN lost_rows = 0 THEN '✓ Perfect join - no rows lost'
        ELSE '⚠️ WARNING: ' || lost_rows || ' rows lost in join-back'
    END as join_quality
FROM join_check;

--	Example: Perfect Output:
--	#,ids_selected,rows_in_final_table,lost_rows,join_quality
--	1,"1,003,534","1,003,534",0,✓ Perfect join - no rows lost


-- ──────────────────────────────────────────────────────────────────────────
-- Schema Completeness Check
-- ──────────────────────────────────────────────────────────────────────────

-- Verify all original columns present
SELECT 
    'Schema Completeness Check' as validation,
    COUNT(*) as n_columns_in_final_table,
    list(column_name ORDER BY ordinal_position) as column_list
FROM information_schema.columns
WHERE table_name = 'sample_1m_finrag';


-- Verify audit columns populated
SELECT 
    COUNT(CASE WHEN sample_created_at IS NULL THEN 1 END) as null_created_at,
    COUNT(CASE WHEN sample_version IS NULL THEN 1 END) as null_version,
    COUNT(CASE WHEN row_hash IS NULL THEN 1 END) as null_hash,
    COUNT(CASE WHEN last_modified_date IS NULL THEN 1 END) as null_modified_date,
    CASE 
        WHEN COUNT(CASE WHEN sample_created_at IS NULL THEN 1 END) = 0
        THEN '✓ All audit columns populated'
        ELSE '⚠️ Some audit columns have NULLs'
    END as audit_check
FROM sample_1m_finrag;

INSERT INTO execution_log VALUES 
    (9, 'SCHEMA_VALIDATION', 'COMPLETE', NULL,
     'Join-back successful - all columns retrieved',
     CURRENT_TIMESTAMP);


-- ═════════════════════════════════════════════════════════════════════════
-- SECTION C COMPLETE: 1M sample with full schema ready for feature engineering
-- ═════════════════════════════════════════════════════════════════════════

SELECT 
    '═════════════════════════════════════════' as separator,
    'SECTION C COMPLETE' as status,
    'Sample table ready for feature engineering' as next_step;

SELECT 
    'Current table: sample_1m_finrag' as info,
    COUNT(*) as rows,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'sample_1m_finrag') as columns
FROM sample_1m_finrag;


-- ═════════════════════════════════════════════════════════════════════════
-- PROGRESS CHECKPOINT: Display execution log so far
-- ═════════════════════════════════════════════════════════════════════════

SELECT 
    step_number,
    step_name,
    status,
    row_count,
    message,
    execution_time
FROM execution_log
ORDER BY step_number;


--Logging Example:
--	#,step_number,step_name,status,row_count,message,execution_time
--	1,0,INITIALIZATION,STARTED,[NULL],Stratified sampling procedure initiated,2025-10-18 04:14:14.549
--	2,1,PARAMETERS,COMPLETE,1,"Sample size: 1000000, Companies: 75",2025-10-18 04:14:14.557
--	3,2,CORPUS_LOAD,COMPLETE,"1,952,705",Loaded 75 companies,2025-10-18 04:14:17.749
--	4,3,BIN_POPULATIONS,COMPLETE,3,Calculated populations for 3 temporal bins,2025-10-18 04:14:29.685
--	5,4,PIVOT_POPULATIONS,COMPLETE,1,Modern bin: 654096 sentences,2025-10-18 04:14:38.161
--	6,5,ALLOCATION_STRATEGY,COMPLETE,1,"Mode: MODERN_FULL_PLUS_OLDER, Modern: 654096",2025-10-18 04:14:55.777
--	7,5,ALLOCATION_STRATEGY,COMPLETE,1,"Mode: MODERN_FULL_PLUS_OLDER, Modern: 654096",2025-10-18 04:15:36.313
--	8,6,BIN_ALLOCATIONS,COMPLETE,3,Allocations prepared for 3 bins,2025-10-18 04:15:46.113
--	9,7,SAMPLING_EXECUTION,COMPLETE,"1,003,534",Sampled 1003534 sentenceIDs across 3 bins,2025-10-18 04:24:51.131
--	10,8,SCHEMA_RETRIEVAL,COMPLETE,"1,003,534",Retrieved complete schema (33 columns) for 1003534 sentences,2025-10-18 04:29:54.428
--	11,9,SCHEMA_VALIDATION,COMPLETE,[NULL],Join-back successful - all columns retrieved,2025-10-18 04:32:36.447




-- ============================================================================
-- SECTION D: FEATURE ENGINEERING (Derived Flags for RAG)
-- ============================================================================

SELECT 
    '═════════════════════════════════════════' as separator,
    'SECTION D: FEATURE ENGINEERING' as status,
    'Adding derived flags to support RAG retrieval' as purpose;



--: column is no longer necessary!
--ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS section_priority;
--ALTER TABLE sample_1m_finrag ADD COLUMN section_priority VARCHAR;

ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS likely_kpi;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS has_numbers;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS is_table_like;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS has_forward_looking;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS has_comparison;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS is_material;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS mentions_years;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS is_recent;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS has_risk_language;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS is_safe_harbor;
ALTER TABLE sample_1m_finrag DROP COLUMN IF EXISTS retrieval_signal_score;

ALTER TABLE sample_1m_finrag ADD COLUMN likely_kpi BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN has_numbers BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN is_table_like BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN has_forward_looking BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN has_comparison BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN is_material BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN mentions_years BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN is_recent BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN has_risk_language BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN is_safe_harbor BOOLEAN;
ALTER TABLE sample_1m_finrag ADD COLUMN retrieval_signal_score INTEGER;




-- Single batch UPDATE with DuckDB regex syntax
UPDATE sample_1m_finrag
SET 	
	
    likely_kpi = regexp_matches(sentence, 
        '\b(revenue|sales|gross margin|operating margin|net margin|cost|expense|income|earnings|ebitda|cash flow|profit|loss|asset|liability|equity|debt|eps|roe|roa|operating income|net income|gross profit)\b', 
        'i'),
    
    has_numbers = (
        regexp_matches(sentence, '\(?\$?\d{1,3}(,\d{3})*(\.\d+)?\)?\s*(million|billion|thousand|M|B|K|%|percent|bps|basis points)', 'i')
        OR regexp_matches(sentence, '\d{1,3}(,\d{3})+(\.\d+)?')
        OR regexp_matches(sentence, '\$\d+')
    ),
    
    is_table_like = (
        char_count > 1000
        OR regexp_matches(sentence, '(\s{2,}|\t)')
        OR regexp_matches(sentence, '(\d+\s+){5,}')
    ),
    
    has_forward_looking = regexp_matches(sentence,
        '\b(expect(s|ed)?|forecast(s|ed)?|plan(s|ned)?|anticipate(s|d)?|believe(s|d)?|estimate(s|d)?|project(s|ed)?|intend(s|ed)?|guidance|outlook|target(s|ed)?)\b',
        'i'),
    
    has_comparison = regexp_matches(sentence,
        '\b(increas|decreas|compar|prior|previous|year-over-year|yoy|y/y|quarter-over-quarter|qoq|q/q|versus|vs\.|compared to|change|growth|decline)\b',
        'i'),
    
    is_material = regexp_matches(sentence,
        '\b(significant|material|substantially|primarily|approximately|considerable|major|critical|key|important)\b',
        'i'),
    
    mentions_years = regexp_matches(sentence, '\b(19\d{2}|20\d{2})\b'),
    
    is_recent = (report_year >= 2018),
    
    has_risk_language = regexp_matches(sentence,
        '\b(risk(s)?|material adverse|uncertain(ty)?|volatility|exposure to|regulatory (risk|scrutiny)|compliance risk|litigation risk|threat|vulnerab)\b',
        'i'),
    
    is_safe_harbor = regexp_matches(sentence,
        '\b(forward-looking statement|safe harbor|private securities litigation reform act|actual results may differ|risk factors described)\b',
        'i'),
    
    retrieval_signal_score = (
        CAST(likely_kpi AS INTEGER) * 3 +
        CAST(has_numbers AS INTEGER) * 2 +
        CAST(has_comparison AS INTEGER) * 2 +
        CAST(is_material AS INTEGER) * 1 +
        CAST(has_forward_looking AS INTEGER) * 1 +
        CAST(is_recent AS INTEGER) * 1 +
        CAST(is_safe_harbor AS INTEGER) * (-2)
    );

    
    
INSERT INTO execution_log VALUES 
    (10, 'FEATURE_ENGINEERING', 'COMPLETE', 
     (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'sample_1m_finrag'),
     'Added 12 derived flags with word boundaries',
     CURRENT_TIMESTAMP);

SELECT 'Feature engineering complete' as status;





-- ═════════════════════════════════════════════════════════════════════════
-- EXPORT TO PARQUET
-- For param binding, use - PREPARE ... EXECUTE with ? pattern.
-- in COPY … TO … the path must be a string literal, not a variable, macro call, or subquery. all these fail.
-- ═════════════════════════════════════════════════════════════════════════
SELECT 'EXPORTING TO PARQUET' as status;

-- Build full export path in a variable
SET VARIABLE export_full_path = (
    getvariable('result_save_path') || '/' || getvariable('result_parquet_name') || '.parquet'
);

-- Verify path
SELECT 'Export path: ' || getvariable('export_full_path') as export_info;

-- Prepare the COPY statement with ? placeholder
PREPARE export_stmt AS
    COPY sample_1m_finrag 
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

-- Execute with the path parameter
EXECUTE export_stmt(getvariable('export_full_path'));

INSERT INTO execution_log VALUES 
    (11, 'EXPORT_PARQUET', 'COMPLETE', 
     (SELECT COUNT(*) FROM sample_1m_finrag),
     'Exported to: ' || getvariable('export_full_path'),
     CURRENT_TIMESTAMP);

SELECT 
    '✓ EXPORT COMPLETE' as status,
    getvariable('export_full_path') as file_path,
    (SELECT COUNT(*) FROM sample_1m_finrag) as rows_exported;


/*
 * -- Build path
		SET VARIABLE export_full_path = (
		    getvariable('result_save_path') || '/' || getvariable('result_parquet_name') || '.parquet'
		);

-- CRITICAL: Wrap getvariable() in parentheses
		COPY sample_1m_finrag 
		TO (getvariable('export_full_path'))  -- ← Parentheses required!
		(FORMAT PARQUET, COMPRESSION 'ZSTD');
 */

-- ═════════════════════════════════════════════════════════════════════════
-- EXECUTION LOG DISPLAY (Complete Audit Trail)
-- ═════════════════════════════════════════════════════════════════════════

SELECT 
    '═════════════════════════════════════════' as separator,
    'EXECUTION LOG - Complete Audit Trail' as report_title;

SELECT 
    step_number,
    step_name,
    status,
    row_count,
    message,
    execution_time,
    -- Time delta between steps
    execution_time - LAG(execution_time) OVER (ORDER BY step_number) as step_duration
FROM execution_log
ORDER BY step_number;


-- PERFECT FULL RUN ( i.e. entire script. ) -- First time ! omg.
--
--#,step_number,step_name,status,row_count,message,execution_time,step_duration
--1,0,INITIALIZATION,STARTED,[NULL],Stratified sampling procedure initiated,2025-10-18 06:07:09.914,[NULL]
--2,1,PARAMETERS,COMPLETE,1,"Sample size: 1000000, Companies: 75",2025-10-18 06:07:09.926,00:00:00.012763
--3,2,CORPUS_LOAD,COMPLETE,"1,952,705",Loaded 75 companies,2025-10-18 06:07:13.599,00:00:03.672532
--4,3,BIN_POPULATIONS,COMPLETE,3,Calculated populations for 3 temporal bins,2025-10-18 06:07:13.870,00:00:00.271028
--5,4,PIVOT_POPULATIONS,COMPLETE,1,Modern bin: 654096 sentences,2025-10-18 06:07:13.874,00:00:00.003712
--6,5,ALLOCATION_STRATEGY,COMPLETE,1,"Mode: MODERN_FULL_PLUS_OLDER, Modern: 654096",2025-10-18 06:07:13.877,00:00:00.003156
--7,6,BIN_ALLOCATIONS,COMPLETE,3,Allocations prepared for 3 bins,2025-10-18 06:07:13.882,00:00:00.004667
--8,7,SAMPLING_EXECUTION,COMPLETE,"1,003,534",Sampled 1003534 sentenceIDs across 3 bins,2025-10-18 06:07:15.579,00:00:01.697561
--9,8,SCHEMA_RETRIEVAL,COMPLETE,"1,003,534",Retrieved complete schema (33 columns) for 1003534 sentences,2025-10-18 06:07:52.409,00:00:36.830141
--10,9,SCHEMA_VALIDATION,COMPLETE,[NULL],Join-back successful - all columns retrieved,2025-10-18 06:07:52.513,00:00:00.103665
--11,10,FEATURE_ENGINEERING,COMPLETE,45,Added 12 derived flags with word boundaries,2025-10-18 06:07:53.697,00:00:01.184265
--12,11,EXPORT_PARQUET,COMPLETE,"1,003,534",Exported to: D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_finrag_1M_sample.parquet,2025-10-18 06:07:56.762,00:00:03.065056



-- REDO: on section dim modification.
--#,step_number,step_name,status,row_count,message,execution_time,step_duration
--1,0,INITIALIZATION,STARTED,[NULL],Stratified sampling procedure initiated,2025-10-24 16:53:27.429,[NULL]
--2,1,PARAMETERS,COMPLETE,1,[NULL],2025-10-24 16:53:27.448,00:00:00.01843
--3,2,CORPUS_LOAD,COMPLETE,"1,952,705",Loaded 75 companies,2025-10-24 16:53:30.785,00:00:03.337191
--4,3,BIN_POPULATIONS,COMPLETE,3,Calculated populations for 3 temporal bins,2025-10-24 16:53:30.899,00:00:00.114089
--5,4,PIVOT_POPULATIONS,COMPLETE,1,Modern bin: 654096 sentences,2025-10-24 16:53:30.904,00:00:00.00526
--6,5,ALLOCATION_STRATEGY,COMPLETE,1,"Mode: MODERN_FULL_PLUS_OLDER, Modern: 654096",2025-10-24 16:53:30.909,00:00:00.004334
--7,6,BIN_ALLOCATIONS,COMPLETE,3,Allocations prepared for 3 bins,2025-10-24 16:53:30.913,00:00:00.004281
--8,7,SAMPLING_EXECUTION,COMPLETE,"654,096",Sampled 654096 sentenceIDs across 3 bins,2025-10-24 16:53:31.268,00:00:00.355282
--9,8,SCHEMA_RETRIEVAL,COMPLETE,"654,096",Retrieved complete schema (37 columns) for 654096 sentences,2025-10-24 16:53:53.434,00:00:22.165754
--10,9,SCHEMA_VALIDATION,COMPLETE,[NULL],Join-back successful - all columns retrieved,2025-10-24 16:53:53.558,00:00:00.124437
--11,10,FEATURE_ENGINEERING,COMPLETE,48,Added 12 derived flags with word boundaries,2025-10-24 16:53:54.612,00:00:01.05343
--12,11,EXPORT_PARQUET,COMPLETE,"654,096",Exported to: D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_finrag_1M_sample.parquet,2025-10-24 16:53:56.034,00:00:01.422167


--
--#,step_number,step_name,status,row_count,message,execution_time,step_duration
--1,0,INITIALIZATION,STARTED,[NULL],Stratified sampling procedure initiated,2025-10-24 17:33:33.361,[NULL]
--2,1,PARAMETERS,COMPLETE,1,"Sample size: 1000000, Companies: 75",2025-10-24 17:33:33.369,00:00:00.0078
--3,2,CORPUS_LOAD,COMPLETE,"1,952,705",Loaded 75 companies,2025-10-24 17:33:37.426,00:00:04.057197
--4,3,BIN_POPULATIONS,COMPLETE,3,Calculated populations for 3 temporal bins,2025-10-24 17:33:37.711,00:00:00.285137
--5,4,PIVOT_POPULATIONS,COMPLETE,1,Modern bin: 654096 sentences,2025-10-24 17:33:37.714,00:00:00.003032
--6,5,ALLOCATION_STRATEGY,COMPLETE,1,"Mode: MODERN_FULL_PLUS_OLDER, Modern: 654096",2025-10-24 17:33:37.718,00:00:00.003916
--7,6,BIN_ALLOCATIONS,COMPLETE,3,Allocations prepared for 3 bins,2025-10-24 17:33:37.722,00:00:00.003959
--8,7,SAMPLING_EXECUTION,COMPLETE,"1,003,534",Sampled 1003534 sentenceIDs across 3 bins,2025-10-24 17:33:39.060,00:00:01.337917
--9,8,SCHEMA_RETRIEVAL,COMPLETE,"1,003,534",Retrieved complete schema (37 columns) for 1003534 sentences,2025-10-24 17:34:09.256,00:00:30.196102
--10,9,SCHEMA_VALIDATION,COMPLETE,[NULL],Join-back successful - all columns retrieved,2025-10-24 17:34:09.326,00:00:00.069334
--11,10,FEATURE_ENGINEERING,COMPLETE,48,Added 12 derived flags with word boundaries,2025-10-24 17:34:10.408,00:00:01.082718
--12,11,EXPORT_PARQUET,COMPLETE,"1,003,534",Exported to: D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_finrag_1M_sample.parquet,2025-10-24 17:34:12.971,00:00:02.562613
--

/*
 * 	Step 2: CORPUS_LOAD - 1,952,705 rows ✓
	Step 7: SAMPLING_EXECUTION - 654,096 sampled ✓
	Step 8: SCHEMA_RETRIEVAL - 654,096 rows (100% match!) ✓
	Step 9: SCHEMA_VALIDATION - Join successful ✓
	Step 10: FEATURE_ENGINEERING - 48 columns (37 original + 4 dimension + 7 derived) ✓
	Step 11: EXPORT_PARQUET - 654,096 rows exported ✓
 */


/*
 * POST INJECTION - GOOGLE. RUN 3.
 * 
 * 

#,step_number,step_name,status,row_count,message,execution_time,step_duration
1,0,INITIALIZATION,STARTED,[NULL],Stratified sampling procedure initiated,2025-10-26 00:14:56.902,[NULL]
2,1,PARAMETERS,COMPLETE,1,"Sample size: 1000000, Companies: 75",2025-10-26 00:14:56.912,00:00:00.010568
3,2,CORPUS_LOAD,COMPLETE,"1,952,705",Loaded 75 companies,2025-10-26 00:14:59.687,00:00:02.774846
4,3,BIN_POPULATIONS,COMPLETE,3,Calculated populations for 3 temporal bins,2025-10-26 00:14:59.779,00:00:00.092461
5,4,PIVOT_POPULATIONS,COMPLETE,1,Modern bin: 654096 sentences,2025-10-26 00:14:59.782,00:00:00.002482
6,5,ALLOCATION_STRATEGY,COMPLETE,1,"Mode: MODERN_FULL_PLUS_OLDER, Modern: 654096",2025-10-26 00:14:59.784,00:00:00.002234
7,6,BIN_ALLOCATIONS,COMPLETE,3,Allocations prepared for 3 bins,2025-10-26 00:14:59.787,00:00:00.002942
8,7,SAMPLING_EXECUTION,COMPLETE,"1,003,534",Sampled 1003534 sentenceIDs across 3 bins,2025-10-26 00:15:00.576,00:00:00.78895
9,8,SCHEMA_RETRIEVAL,COMPLETE,"1,003,534",Retrieved complete schema (37 columns) for 1003534 sentences,2025-10-26 00:15:33.260,00:00:32.684272
10,9,INCREMENTAL_INJECTION,COMPLETE,"8,510","Injected 8510 rows from external source (1 companies, 5 years)",2025-10-26 00:15:33.896,00:00:00.6354
11,9,SCHEMA_VALIDATION,COMPLETE,[NULL],Join-back successful - all columns retrieved,2025-10-26 00:15:33.996,00:00:00.100272
12,10,FEATURE_ENGINEERING,COMPLETE,48,Added 12 derived flags with word boundaries,2025-10-26 00:15:35.320,00:00:01.324412
13,11,EXPORT_PARQUET,COMPLETE,"1,012,044",Exported to: D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_finrag_1M_sample.parquet,2025-10-26 00:15:38.375,00:00:03.054533


 */

