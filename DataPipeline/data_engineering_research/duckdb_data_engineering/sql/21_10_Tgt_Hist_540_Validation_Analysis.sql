-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


-- ============================================================================
-- VALIDATION: target_companies_613_clean
-- ============================================================================

-- V1: Grain verification (all counts should match)
SELECT 
    'Total Rows' as metric,
    COUNT(*) as count
FROM target_companies_613_clean

UNION ALL

SELECT 
    'Unique CIKs (cik column)',
    COUNT(DISTINCT cik)
FROM target_companies_613_clean

UNION ALL

SELECT 
    'Unique CIKs (cik_int column)',
    COUNT(DISTINCT cik_int)
FROM target_companies_613_clean

UNION ALL

SELECT 
    'Unique company_id',
    COUNT(DISTINCT company_id)
FROM target_companies_613_clean;

-- Expected: All 4 counts should be 540 (clean grain)

--#,metric,count
--1,Total Rows,540
--2,Unique CIKs (cik column),540
--3,Unique CIKs (cik_int column),540
--4,Unique company_id,540

-- ============================================================================
-- V2: Check for duplicates (should return 0 rows)
-- ============================================================================

SELECT 
    cik_int,
    COUNT(*) as occurrences,
    list(company_name) as duplicate_names,
    list(source) as duplicate_sources
FROM target_companies_613_clean
GROUP BY cik_int
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;

-- Expected: 0 rows (no duplicates)
-- Returned: 0 Rows

-- ============================================================================
-- V3: NULL check on critical fields
-- ============================================================================

SELECT 
    COUNT(*) as total_rows,
    COUNT(CASE WHEN cik IS NULL THEN 1 END) as null_ciks,
    COUNT(CASE WHEN cik_int IS NULL THEN 1 END) as null_cik_ints,
    COUNT(CASE WHEN company_name IS NULL THEN 1 END) as null_names,
    COUNT(CASE WHEN source IS NULL THEN 1 END) as null_sources,
    COUNT(CASE WHEN match_method IS NULL THEN 1 END) as null_match_methods
FROM target_companies_613_clean;

-- Expected: All null counts = 0
--#,total_rows,null_ciks,null_cik_ints,null_names,null_sources,null_match_methods
--1,540,0,0,0,0,0


CREATE TABLE finrag_tgt_comps_540 AS 
	SELECT * FROM target_companies_613_clean;
