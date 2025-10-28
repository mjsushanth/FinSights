-- ============================================================================
-- BLOCK 1: Corpus Loading and Temporal Tagging
-- Read 71M corpus, filter to 75 companies, add temporal bins
-- ============================================================================

-- Set parameters 
CREATE OR REPLACE TEMP TABLE params AS 
SELECT 
    'finrag_tgt_comps_75' as company_table,
    1000000 as sample_size_n;


-- Load and tag
CREATE OR REPLACE TEMP TABLE corpus_tagged AS
SELECT 
    CAST(cik AS VARCHAR) as cik,
    CAST(cik AS INTEGER) as cik_int,
    sentence,
    section,
    docID,
    sentenceID,
    reportDate,
    name as company_name,
    YEAR(CAST(reportDate AS DATE)) as report_year,
    
    CASE 
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2009 THEN 'bin_2006_2009'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2010 AND 2015 THEN 'bin_2010_2015'
        WHEN YEAR(CAST(reportDate AS DATE)) BETWEEN 2016 AND 2020 THEN 'bin_2016_2020'
    END as temporal_bin,
    
    LENGTH(sentence) as char_count
    
FROM read_parquet(parquet_path())
WHERE CAST(cik AS INTEGER) IN (
    SELECT cik_int FROM finrag_tgt_comps_75
)
AND YEAR(CAST(reportDate AS DATE)) BETWEEN 2006 AND 2020
AND section IS NOT NULL
AND sentence IS NOT NULL
AND LENGTH(sentence) > 10;


-- VALIDATION: Check what was loaded
SELECT 
    'Corpus loaded' as step,
    COUNT(*) as total_rows,
    COUNT(DISTINCT cik_int) as n_companies,
    COUNT(DISTINCT temporal_bin) as n_bins
FROM corpus_tagged;


SELECT * FROM corpus_tagged LIMIT 50;

-- Validation: Count of distinct comps matches our chosen - 75
--#,step,total_rows,n_companies,n_bins
--1,Corpus loaded,"1,952,705",75,3


-- ===========================================================================================================================================
-- ===========================================================================================================================================



-- ============================================================================
-- BLOCK 2: Bin Population Statistics
-- Count how many sentences exist in each temporal bin
-- ============================================================================

CREATE OR REPLACE TEMP TABLE bin_populations AS
SELECT 
    temporal_bin,
    COUNT(*) as bin_population,
    COUNT(DISTINCT cik_int) as n_companies,
    COUNT(DISTINCT docID) as n_filings,
    COUNT(DISTINCT section) as n_sections,
    ROUND(AVG(char_count), 1) as avg_char_length
FROM corpus_tagged
GROUP BY temporal_bin;

-- DISPLAY: See population sizes
SELECT 
    temporal_bin,
    bin_population,
    n_companies,
    n_filings,
    ROUND(bin_population * 100.0 / SUM(bin_population) OVER (), 2) as pct_of_total
FROM bin_populations
ORDER BY temporal_bin;



-- INSIGHT: Which bin is largest?
SELECT 
    CASE 
        WHEN (SELECT bin_population FROM bin_populations WHERE temporal_bin = 'bin_2016_2020') 
            > (SELECT sample_size_n FROM params)
        THEN '⚠️ MODERN BIN EXCEEDS BUDGET - Will need to sample it'
        ELSE '✓ MODERN BIN WITHIN BUDGET - Can take 100%'
    END as budget_check,
    (SELECT bin_population FROM bin_populations WHERE temporal_bin = 'bin_2016_2020') as modern_bin_size,
    (SELECT sample_size_n FROM params) as target_budget;

--#,budget_check,modern_bin_size,target_budget
--1,✓ MODERN BIN WITHIN BUDGET - Can take 100%,"654,096","1,000,000"


SELECT * FROM bin_populations;

--#,temporal_bin,bin_population,n_companies,n_filings,n_sections,avg_char_length
--1,bin_2016_2020,"654,096",74,349,20,191.2
--2,bin_2006_2009,"483,913",67,257,20,180.5
--3,bin_2010_2015,"814,696",71,416,20,187.9



-- ============================================================================
-- BLOCK 3: Allocation Decision Logic (CLEAN RELATIONAL VERSION)
-- Pattern: PIVOT using MAX(CASE WHEN) - single table scan, no cross joins
-- ============================================================================

-- Step 3A: Pivot bin populations into columns (single scan)


CREATE OR REPLACE TEMP TABLE bin_populations_pivoted AS

SELECT 
    MAX(CASE WHEN temporal_bin = 'bin_2016_2020' THEN bin_population END) as modern_pop,
    MAX(CASE WHEN temporal_bin = 'bin_2016_2020' THEN n_companies END) as modern_companies,
    
    MAX(CASE WHEN temporal_bin = 'bin_2010_2015' THEN bin_population END) as bin2_pop,
    MAX(CASE WHEN temporal_bin = 'bin_2010_2015' THEN n_companies END) as bin2_companies,
    
    MAX(CASE WHEN temporal_bin = 'bin_2006_2009' THEN bin_population END) as bin1_pop,
    MAX(CASE WHEN temporal_bin = 'bin_2006_2009' THEN n_companies END) as bin1_companies,
    
    -- Total population (for reference)
    SUM(bin_population) as total_population
FROM bin_populations;



-- VALIDATION: See pivoted values (should be 1 row)
SELECT * FROM bin_populations_pivoted;

-- Expected: 1 row with modern_pop=654096, bin2_pop=814696, bin1_pop=483913



-- Step 3B: Calculate allocations with business logic
CREATE OR REPLACE TEMP TABLE allocation_decisions AS

SELECT 
    -- Input parameters
    p.sample_size_n as target_budget,
    bpp.modern_pop,
    bpp.bin2_pop,
    bpp.bin1_pop,
    bpp.total_population,
    
    -- Decision mode
    CASE 
        WHEN bpp.modern_pop >= p.sample_size_n THEN 'MODERN_ONLY'
        ELSE 'MODERN_FULL_PLUS_OLDER'
    END as allocation_mode,
    
    -- Modern bin allocation
    CASE 
        WHEN bpp.modern_pop >= p.sample_size_n 
        THEN p.sample_size_n  -- Cap at budget, will need to sample
        ELSE bpp.modern_pop   -- Take 100% (all of it)
    END as modern_target,
    
    -- Modern sampling rate
    CASE 
        WHEN bpp.modern_pop >= p.sample_size_n 
        THEN ROUND(p.sample_size_n * 100.0 / bpp.modern_pop, 2)
        ELSE 100.00  -- Taking all = 100%
    END as modern_sampling_rate,
    
    -- Leftover budget for older bins
    GREATEST(0, p.sample_size_n - bpp.modern_pop) as leftover_budget,
    
    -- Older bin allocations (60/40 split of leftover)
    CAST(ROUND(
        GREATEST(0, p.sample_size_n - bpp.modern_pop) * 0.60
    ) AS INTEGER) as bin2_target,
    
    CAST(ROUND(
        GREATEST(0, p.sample_size_n - bpp.modern_pop) * 0.40
    ) AS INTEGER) as bin1_target,
    
    -- Older bin sampling rates
    ROUND(
        GREATEST(0, p.sample_size_n - bpp.modern_pop) * 0.60 * 100.0 / NULLIF(bpp.bin2_pop, 0), 
        2
    ) as bin2_sampling_rate,
    
    ROUND(
        GREATEST(0, p.sample_size_n - bpp.modern_pop) * 0.40 * 100.0 / NULLIF(bpp.bin1_pop, 0), 
        2
    ) as bin1_sampling_rate
    
-- SELECT * 
FROM params p
CROSS JOIN bin_populations_pivoted bpp;  -- 1 × 1 = 1 row (acceptable)




-- VALIDATION: See allocation decisions
SELECT * FROM allocation_decisions;



-- INTERPRETATION: What mode are we in?
SELECT 
    allocation_mode,
    CASE allocation_mode
        WHEN 'MODERN_ONLY' THEN 
            '⚠️ Modern bin (' || modern_pop || ' sentences) exceeds budget (' || target_budget || 
            '). Will randomly sample ' || modern_target || ' from modern bin. Older bins EXCLUDED.'
        WHEN 'MODERN_FULL_PLUS_OLDER' THEN 
            '✓ Taking 100% of modern bin (' || modern_pop || ' sentences = ' || modern_target || 
            '). Remaining budget (' || leftover_budget || ') split 60/40 to older bins.'
    END as strategy_explanation,
    modern_target as modern_allocation,
    bin2_target as bin2_allocation,
    bin1_target as bin1_allocation,
    (modern_target + bin2_target + bin1_target) as total_will_sample
FROM allocation_decisions;



-- QUALITY: Do allocations sum correctly?
SELECT 
    target_budget,
    modern_target + bin2_target + bin1_target as actual_allocation,
    (modern_target + bin2_target + bin1_target) - target_budget as difference,
    CASE 
        WHEN ABS((modern_target + bin2_target + bin1_target) - target_budget) <= 100 
        THEN '✓ Within tolerance (±100 rows due to rounding)'
        ELSE '⚠️ Allocation error detected'
    END as allocation_check
FROM allocation_decisions;



-- ============================================================================
-- BLOCK 4: Final Bin Allocations Table
-- Transform allocation_decisions into per-bin allocation rows
-- Pattern: UNPIVOT the wide allocation row into long format (one row per bin)
-- ============================================================================

CREATE OR REPLACE TEMP TABLE bin_allocations AS
SELECT 
    'bin_2016_2020' as temporal_bin,
    ad.modern_target as target_n,
    bpp.modern_pop as population,
    ad.modern_sampling_rate as sampling_rate_pct,
    1 as priority_order,
    'PRIORITY: Modern era - target 100% if possible' as allocation_note
FROM allocation_decisions ad
CROSS JOIN bin_populations_pivoted bpp

UNION ALL

SELECT 
    'bin_2010_2015',
    ad.bin2_target,
    bpp.bin2_pop,
    ad.bin2_sampling_rate,
    2,
    '60% of leftover budget'
FROM allocation_decisions ad
CROSS JOIN bin_populations_pivoted bpp

UNION ALL

SELECT 
    'bin_2006_2009',
    ad.bin1_target,
    bpp.bin1_pop,
    ad.bin1_sampling_rate,
    3,
    '40% of leftover budget'
FROM allocation_decisions ad
CROSS JOIN bin_populations_pivoted bpp;



-- DISPLAY: Clean allocation plan
SELECT 
    temporal_bin,
    population as bin_population,
    target_n as target_allocation,
    sampling_rate_pct,
    allocation_note,
    CASE 
        WHEN sampling_rate_pct >= 99 THEN '✓✓ COMPLETE (100%)'
        WHEN sampling_rate_pct >= 75 THEN '✓ HIGH (75-99%)'
        WHEN sampling_rate_pct >= 50 THEN '○ MODERATE (50-75%)'
        WHEN sampling_rate_pct >= 25 THEN '△ LIGHT (25-50%)'
        WHEN sampling_rate_pct > 0 THEN '▽ SPARSE (<25%)'
        ELSE '✗ EXCLUDED'
    END as coverage_level
FROM bin_allocations
ORDER BY priority_order;



-- SUMMARY: Total check
SELECT 
    SUM(target_n) as total_to_sample,
    (SELECT target_budget FROM allocation_decisions) as budget,
    SUM(target_n) - (SELECT target_budget FROM allocation_decisions) as difference,
    CASE 
        WHEN ABS(SUM(target_n) - (SELECT target_budget FROM allocation_decisions)) <= 100
        THEN '✓ Allocations sum correctly'
        ELSE '⚠️ Rounding error detected'
    END as validation_status
FROM bin_allocations;




--#,temporal_bin,bin_population,target_allocation,sampling_rate_pct,allocation_note,coverage_level
--1,bin_2016_2020,"654,096","654,096",100,PRIORITY: Modern era - target 100% if possible,✓✓ COMPLETE (100%)
--2,bin_2010_2015,"814,696","207,542",25.47,60% of leftover budget,△ LIGHT (25-50%)
--3,bin_2006_2009,"483,913","138,362",28.59,40% of leftover budget,△ LIGHT (25-50%)

-- ============================================================================
-- BLOCK 5: Sample Modern Era (2016-2020)
-- ============================================================================

CREATE OR REPLACE TEMP TABLE sample_combined AS
WITH sampling_logic AS (
    
	-- For each sentence, determine if it should be sampled
    SELECT 
        ct.*,
        ba.target_n as bin_target,
        ba.population as bin_population,
        
        -- Stratum information (CIK × Year × Section)
        ROW_NUMBER() OVER (
            PARTITION BY ct.temporal_bin, ct.cik_int, ct.report_year, ct.section
            ORDER BY RANDOM()
        ) as rn_within_stratum,
        
        COUNT(*) OVER (
            PARTITION BY ct.temporal_bin, ct.cik_int, ct.report_year, ct.section
        ) as stratum_size
        
    FROM corpus_tagged ct
    INNER JOIN bin_allocations ba ON ct.temporal_bin = ba.temporal_bin
    WHERE ba.target_n > 0  -- process bins with allocation
    
),

stratum_allocations AS (
    -- Calculate how many to sample from each stratum
    SELECT 
        *,
        -- Simple logic: If target >= population, take all. Else, proportional.
        CASE 
            WHEN bin_target >= bin_population THEN stratum_size  -- Take 100%
            ELSE GREATEST(1,  -- Minimum 1 per stratum
                CAST(ROUND(stratum_size * (bin_target * 1.0 / bin_population)) AS INTEGER)
            )
        END as stratum_sample_n
    FROM sampling_logic
)


SELECT 
    cik, cik_int, company_name, sentence, section,
    reportDate, report_year, temporal_bin, docID, sentenceID, char_count,
    -- Store actual sampling rate achieved (for validation)
    ROUND(bin_target * 100.0 / bin_population, 2) as sampling_rate_pct
FROM stratum_allocations
WHERE rn_within_stratum <= stratum_sample_n;  





-- VALIDATION: Check each bin
SELECT 
    temporal_bin,
    COUNT(*) as n_sampled,
    (SELECT target_n FROM bin_allocations ba WHERE ba.temporal_bin = sf.temporal_bin) as target,
    COUNT(*) - (SELECT target_n FROM bin_allocations ba WHERE ba.temporal_bin = sf.temporal_bin) as difference,
    COUNT(DISTINCT cik_int) as n_companies,
    COUNT(DISTINCT section) as n_sections
FROM sample_combined sf
GROUP BY temporal_bin
ORDER BY temporal_bin;

--#,temporal_bin,n_sampled,target,difference,n_companies,n_sections
--1,bin_2006_2009,"139,569","138,362","1,207",67,20
--2,bin_2010_2015,"209,869","207,542","2,327",71,20
--3,bin_2016_2020,"654,096","654,096",0,74,20

-- VALIDATION: Total
SELECT 
    COUNT(*) as total_sampled,
    (SELECT target_budget FROM allocation_decisions) as target,
    COUNT(*) - (SELECT target_budget FROM allocation_decisions) as difference
FROM sample_combined;
--#,total_sampled,target,difference
--1,"1,003,534","1,000,000","3,534"



-- ============================================================================
-- BLOCK 6: Create Final Persistent Table
-- ============================================================================

CREATE OR REPLACE TABLE sample_1m_finrag_dev AS
SELECT 
    ROW_NUMBER() OVER (ORDER BY temporal_bin, report_year, cik_int, section) as sample_id,
    cik, cik_int, company_name, sentence, section,
    reportDate, report_year, temporal_bin, docID, sentenceID,
    char_count, sampling_rate_pct,
    LENGTH(sentence) - LENGTH(REPLACE(sentence, ' ', '')) + 1 as word_count_approx
FROM sample_combined
ORDER BY sample_id;



SELECT 
    'TABLE CREATED' as status,
    COUNT(*) as total_rows
FROM sample_1m_finrag_dev;



-- ============================================================================
-- Validation 
-- ============================================================================

-- Overall check
SELECT 
    COUNT(*) as total,
    COUNT(DISTINCT cik_int) as companies,
    COUNT(DISTINCT section) as sections,
    COUNT(DISTINCT report_year) as years
FROM sample_1m_finrag_dev;


-- Bin distribution
SELECT 
    temporal_bin,
    COUNT(*) as n_sentences,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct
FROM sample_1m_finrag_dev
GROUP BY temporal_bin
ORDER BY temporal_bin;

--#,temporal_bin,n_sentences,pct
--1,bin_2006_2009,"139,569",13.91
--2,bin_2010_2015,"209,869",20.91
--3,bin_2016_2020,"654,096",65.18


-- Modern era completeness
SELECT 
    ROUND(COUNT(*) * 100.0 / 654096, 2) as modern_coverage_pct
FROM sample_1m_finrag_dev
WHERE temporal_bin = 'bin_2016_2020';






