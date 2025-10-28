-- ============================================================================
-- DYNAMIC N-COMPANY TABLE CREATION -- DIMENSION.
-- What this does? Configuring this macro makes you have a dynamic dimension table 
-- with X snp companies, and Y non-snp quality companies, and +1 manual addition.

-- The reason we are manually adding google is - for its absence in hist data.
-- ============================================================================

/*
 * SET VARIABLE ... / getvariable('...') = DuckDB engine values (good for expressions/filters).
 * ${var} and the “Bind parameter(s)” popup = DBeaver client-side substitution (for identifiers/paths before SQL is sent).
 * 
 * DBeaver sees sampler.main.${target_table_name} and tries to bind a client variable. 
 * It has no idea that we computed target_table_name inside DuckDB, so it prompts. isn’t “user-execution friendly”.
 * 
 * Dynamic table naming in DDL (DROP TABLE, CREATE TABLE) is fundamentally impossible in DuckDB without client-side preprocessing.
 * ❌ PREPARE ... EXECUTE → Only works for data values, not identifiers
 * ❌ EXECUTE IMMEDIATE → Doesn't exist in DuckDB
 * ❌ getvariable() in DDL → Parser expects literal identifier, not function call
 * ❌ String concatenation in DDL → No dynamic SQL execution support
 */

-- ============================================================================
-- DYNAMIC N-COMPANY TABLE CREATION (Macro Encapsulation Pattern)
-- All logic encapsulated in macro, table name chosen at creation time
-- ============================================================================


CREATE OR REPLACE MACRO tgt_companies(n_snp, n_quality, include_google) AS TABLE (
    WITH google_company AS (
        SELECT 
            1652044 as cik_int,
            '0001652044' as cik,
            'Alphabet Inc.' as company_name,
            'GOOGL' as ticker,
            'MANUAL' as source,
            'TIER_PRIORITY' as tier,
            999999.0 as quality_score,
            'GOOGLE_MANDATORY_MANUAL' as selection_source,
            0 as rank_within_group
        WHERE include_google = 1
    ),
    
    snp_ranked AS (
        SELECT 
            cik_int,
            cik,
            company_name,
            ticker,
            source,
            tier,
            weight_pct * 1000 as quality_score,
            'SNP500_TOP' || CAST(n_snp AS VARCHAR) as selection_source,
            ROW_NUMBER() OVER (ORDER BY weight_pct DESC) as rank_within_group
        FROM sampler.main.finrag_tgt_comps_75
        WHERE TRIM(UPPER(source)) = 'SP500'
          AND cik_int != 1652044
    ),
    
    quality_ranked AS (
        SELECT 
            cik_int,
            cik,
            company_name,
            ticker,
            source,
            tier,
            quality_score,
            'QUALITY_TOP' || CAST(n_quality AS VARCHAR) as selection_source,
            ROW_NUMBER() OVER (ORDER BY quality_score DESC, cik_int) as rank_within_group
        FROM sampler.main.finrag_tgt_comps_75
        WHERE TRIM(UPPER(source)) != 'SP500'
          AND cik_int != 1652044
    )
    
    SELECT 
        ROW_NUMBER() OVER (ORDER BY 
            CASE 
                WHEN selection_source LIKE 'GOOGLE%' THEN 1 
                WHEN selection_source LIKE 'SNP500%' THEN 2 
                WHEN selection_source LIKE 'QUALITY%' THEN 3 
            END,
            rank_within_group
        ) as company_id,
        cik_int,
        cik,
        company_name,
        ticker,
        source,
        tier,
        quality_score,
        selection_source,
        rank_within_group,
        CURRENT_TIMESTAMP as selected_at,
        'v2.0_prod_' || CAST(n_snp + n_quality + include_google AS VARCHAR) || 'companies' as version
    FROM (
        SELECT * FROM google_company
        UNION ALL
        SELECT * FROM snp_ranked WHERE rank_within_group <= n_snp
        UNION ALL
        SELECT * FROM quality_ranked WHERE rank_within_group <= n_quality
    )
    ORDER BY company_id
);

SELECT '✓ Macro tgt_companies() created' as status;


-- ──────────────────────────────────────────────────────────────────────────
-- USAGE EXAMPLES: Create specific company tables
-- User chooses table name, macro provides the data
-- ──────────────────────────────────────────────────────────────────────────

-- Example 1: 21 companies (15 SNP + 5 Quality + 1 Google)
--CREATE OR REPLACE TABLE sampler.main.finrag_tgt_comps_21 AS
--SELECT * FROM tgt_companies(15, 5, 1);

-- Example 2: 20 companies (15 SNP + 5 Quality, no Google)
-- CREATE OR REPLACE TABLE sampler.main.finrag_tgt_comps_20 AS
-- SELECT * FROM tgt_companies(15, 5, 0);

-- Example 3: 30 companies (20 SNP + 10 Quality, no Google)
-- CREATE OR REPLACE TABLE sampler.main.finrag_tgt_comps_30 AS
-- SELECT * FROM tgt_companies(20, 10, 0);

-- Example 4: 51 companies (50 SNP + 0 Quality + 1 Google)
-- CREATE OR REPLACE TABLE sampler.main.finrag_tgt_comps_51 AS
-- SELECT * FROM tgt_companies(50, 0, 1);


DROP TABLE IF EXISTS sampler.main.finrag_tgt_comps_51;
CREATE OR REPLACE TABLE sampler.main.finrag_tgt_comps_51 AS
	SELECT * FROM tgt_companies(30, 20, 1);

SELECT 
    '✓✓ TABLE CREATED' as status,
    COUNT(*) as n_companies
FROM sampler.main.finrag_tgt_comps_51;


-- ============================================================================
-- VALIDATION 1: Selection Breakdown
-- ============================================================================

SELECT 
    '1. SELECTION BREAKDOWN' as check_type,
    selection_source,
    COUNT(*) as n_companies,
    ROUND(AVG(quality_score), 1) as avg_quality
FROM sampler.main.finrag_tgt_comps_51
GROUP BY selection_source
ORDER BY CASE 
    WHEN selection_source LIKE 'GOOGLE%' THEN 1 
    WHEN selection_source LIKE 'SNP500%' THEN 2 
    ELSE 3 
END;


-- ============================================================================
-- VALIDATION 2: Total Count Check
-- ============================================================================


SET VARIABLE CHCK = 51;

SELECT 
    '2. FINAL VERIFICATION' as check_type,
    COUNT(*) as total_companies,
    COUNT(DISTINCT cik_int) as unique_ciks,
    21 as expected_count,
    CASE 
        WHEN COUNT(*) = getvariable('CHCK')  AND COUNT(DISTINCT cik_int) = getvariable('CHCK') 
        THEN '✓ Perfect'
        ELSE '⚠️ Count mismatch'
    END as status
FROM sampler.main.finrag_tgt_comps_51;


-- ============================================================================
-- VIEW RESULTS
-- ============================================================================

SELECT 
    company_id,
    cik_int,
    company_name,
    ticker,
    selection_source,
    quality_score
FROM sampler.main.finrag_tgt_comps_51
ORDER BY company_id;













