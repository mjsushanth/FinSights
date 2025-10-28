

/*
 * 	-- POST-SAMPLING VALIDATION SUITE
	-- Author: Joel Markapudi
 *
 *
 *	VALIDATION QUERY INDEX:
 *	V1:  OVERALL STATISTICS - Row counts, company/filing/section diversity, avg text length (expect: 1M+ rows, 75+ companies, 20 sections, 15 years)
*	V2:  TEMPORAL DISTRIBUTION - Actual vs target allocation per bin, validates 15/21/65 weighting achieved within ±5K tolerance
*	V3:  MODERN ERA COVERAGE - Verifies 100% capture of 2016-2020 bin (654K sentences, most critical period for query relevance)
*	V4:  SECTION COVERAGE PER BIN - Confirms all 20 SEC sections present in each temporal bin (detects systematic exclusion bias)
*	V5:  COMPANY COVERAGE - Validates all 75 target companies present (or 76 if GOOGL injected), flags missing companies
*	V6:  FEATURE FLAG STATISTICS - Counts RAG features (KPIs, numbers, comparisons), validates Section D execution (expect: 30-40% numeric)
*	V7:  SIGNAL SCORE DISTRIBUTION - Histogram of retrieval_signal_score composite metric (range: -2 to 10+, higher = more relevant)
*	V9:  DATA QUALITY CHECKS - NULL detection in critical fields (cik, sentence, section_ID), flags corruption or join failures
*	V10: COMPANY DISTRIBUTION BALANCE - Per-company sentence counts (min/median/max), acceptable imbalance <10x ratio
*	V11: SECTION METADATA INTEGRITY - Validates dimension join, canonical naming (ITEM_* format), P0/P1 priority corpus % (target: 80-90%)
*/
-- ============================================================================
-- section_ID E: FINAL VALIDATION & SUMMARY
-- ============================================================================

SELECT 
    '═════════════════════════════════════════' as separator,
    'section_ID E: FINAL VALIDATION' as status;

SELECT * FROM sample_1m_finrag;

SELECT * FROM sampler.main.sample_1m_finrag;
sampler.main.sample_1m_finrag

SELECT * FROM sampler.main.sample_1m_finrag;


-- 1. Check what schemas exist
SHOW SCHEMAS;

-- 2. Check what tables exist in current context
SHOW TABLES;

-- 3. Check tables in 'sampler' schema specifically
SELECT * FROM information_schema.tables 
WHERE table_schema = 'sampler';


SELECT * FROM sampler.main.sample_1m_finrag_dev;

-- ──────────────────────────────────────────────────────────────────────────
-- V1: Overall statistics
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '1. OVERALL STATISTICS' as validation_check,
    COUNT(*) as total_sentences,
    COUNT(DISTINCT cik_int) as unique_companies,
    COUNT(DISTINCT docID) as unique_filings,
    COUNT(DISTINCT section_ID) as unique_section_IDs,
    COUNT(DISTINCT report_year) as unique_years,
    ROUND(AVG(char_count), 1) as avg_char_length,
    ROUND(AVG(word_count_approx), 1) as avg_word_count
FROM sample_1m_finrag;


-- ──────────────────────────────────────────────────────────────────────────
-- V2: Temporal distribution vs targets
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '2. TEMPORAL DISTRIBUTION' as validation_check,
    sf.temporal_bin,
    COUNT(*) as actual_sampled,
    ba.target_n as target,
    COUNT(*) - ba.target_n as difference,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct_of_sample,
    ba.sampling_rate_pct as planned_rate,
    CASE 
        WHEN ABS(COUNT(*) - ba.target_n) <= 5000 THEN '✓ Within tolerance'
        ELSE 'Exceeds tolerance (With Manual Injeciton/Google - Fine.)'
    END as target_check
FROM sample_1m_finrag sf
LEFT JOIN bin_allocations ba ON sf.temporal_bin = ba.temporal_bin
GROUP BY sf.temporal_bin, ba.target_n, ba.sampling_rate_pct
ORDER BY sf.temporal_bin;


-- ──────────────────────────────────────────────────────────────────────────
-- V3: Modern era completeness (CRITICAL)
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '3. MODERN ERA COVERAGE (CRITICAL)' as validation_check,
    COUNT(*) as sentences_sampled,
    654096 as population_available,
    ROUND(COUNT(*) * 100.0 / 654096, 2) as coverage_pct,
    CASE 
        WHEN COUNT(*) >= 654096 * 0.99 THEN '✓✓ COMPLETE (≥99%)'
        WHEN COUNT(*) >= 654096 * 0.95 THEN '✓ NEAR-COMPLETE (95-99%)'
        WHEN COUNT(*) >= 654096 * 0.90 THEN '○ HIGH (90-95%)'
        ELSE '△ PARTIAL (<90%)'
    END as completeness_level
FROM sample_1m_finrag
WHERE temporal_bin = 'bin_2016_2020';


-- ──────────────────────────────────────────────────────────────────────────
-- V4: section_ID coverage (all 20 section_IDs should be present in all bins)
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '4. section_ID COVERAGE PER BIN' as validation_check,
    temporal_bin,
    COUNT(DISTINCT section_ID) as n_section_IDs_present,
    CASE 
        WHEN COUNT(DISTINCT section_ID) = 20 THEN '✓ Complete (20/20)'
        ELSE '⚠️ Missing ' || (20 - COUNT(DISTINCT section_ID)) || ' section_IDs'
    END as section_ID_completeness
FROM sample_1m_finrag
GROUP BY temporal_bin
ORDER BY temporal_bin;


DESCRIBE (SELECT * FROM sampler.sample_1m_finrag);

-- ──────────────────────────────────────────────────────────────────────────
-- V5: Company coverage
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '5. COMPANY COVERAGE' as validation_check,
    COUNT(DISTINCT cik_int) as companies_in_sample,
    75 as companies_expected,
    CASE WHEN  (75 - COUNT(DISTINCT cik_int)) > 1 THEN (75 - COUNT(DISTINCT cik_int))
    		 ELSE 0 
		 END 
    		 as missing_companies,
    CASE 
        WHEN COUNT(DISTINCT cik_int) >= 75 THEN '✓ All companies present'
        ELSE '⚠️ Missing ' || (75 - COUNT(DISTINCT cik_int)) || ' companies'
    END as coverage_status
FROM sample_1m_finrag;


-- ──────────────────────────────────────────────────────────────────────────
-- V6: Feature flag distribution
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '6. FEATURE FLAG STATISTICS' as validation_check,
    COUNT(CASE WHEN likely_kpi = true THEN 1 END) as n_kpi_sentences,
    COUNT(CASE WHEN has_numbers = true THEN 1 END) as n_numeric_sentences,
    COUNT(CASE WHEN is_table_like = true THEN 1 END) as n_table_sentences,
    COUNT(CASE WHEN has_forward_looking = true THEN 1 END) as n_forward_looking,
    COUNT(CASE WHEN has_comparison = true THEN 1 END) as n_comparative,
    COUNT(CASE WHEN is_material = true THEN 1 END) as n_material,
    COUNT(CASE WHEN mentions_years = true THEN 1 END) as n_year_mentions,
    COUNT(CASE WHEN has_risk_language = true THEN 1 END) as n_risk_related,
    COUNT(CASE WHEN is_recent = true THEN 1 END) as n_recent
FROM sample_1m_finrag;


-- ──────────────────────────────────────────────────────────────────────────
-- V7: Retrieval signal score distribution -- Removed this ! 
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '7. SIGNAL SCORE DISTRIBUTION' as validation_check,
    retrieval_signal_score as score,
    COUNT(*) as n_sentences,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct_of_sample
FROM sample_1m_finrag
GROUP BY retrieval_signal_score
ORDER BY retrieval_signal_score DESC;




-- ──────────────────────────────────────────────────────────────────────────
-- V9: Data quality checks (nulls, invalid values)
-- ──────────────────────────────────────────────────────────────────────────

SELECT 
    '9. DATA QUALITY CHECKS' as validation_check,
    COUNT(CASE WHEN cik IS NULL THEN 1 END) as null_ciks,
    COUNT(CASE WHEN sentence IS NULL THEN 1 END) as null_sentences,
    COUNT(CASE WHEN section_ID IS NULL THEN 1 END) as null_section_IDs,
    COUNT(CASE WHEN temporal_bin IS NULL THEN 1 END) as null_bins,
    COUNT(CASE WHEN sample_id IS NULL THEN 1 END) as null_ids,
    COUNT(CASE WHEN row_hash IS NULL THEN 1 END) as null_hashes,
    CASE 
        WHEN COUNT(CASE WHEN cik IS NULL THEN 1 END) = 0 
         AND COUNT(CASE WHEN sentence IS NULL THEN 1 END) = 0
        THEN '✓ No nulls in critical fields'
        ELSE '⚠️ Nulls detected'
    END as quality_status
FROM sample_1m_finrag;


-- ──────────────────────────────────────────────────────────────────────────
-- V10: Per-company balance check
-- ──────────────────────────────────────────────────────────────────────────

WITH company_stats AS (
    SELECT 
        cik_int,
        name as company_name,
        COUNT(*) as n_sentences
    FROM sample_1m_finrag
    GROUP BY cik_int, name
)
SELECT 
    '10. COMPANY DISTRIBUTION' as validation_check,
    MIN(n_sentences) as min_per_company,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY n_sentences) as median_per_company,
    MAX(n_sentences) as max_per_company,
    ROUND(AVG(n_sentences), 0) as avg_per_company,
    ROUND(MAX(n_sentences) * 1.0 / NULLIF(MIN(n_sentences), 0), 2) as imbalance_ratio,
    CASE 
        WHEN MAX(n_sentences) * 1.0 / NULLIF(MIN(n_sentences), 0) < 10 
        THEN '✓ Balanced distribution'
        ELSE '○ Some imbalance (expected)'
    END as balance_status
FROM company_stats;





-- ══════════════════════════════════════════════════════════════════════════
-- V11: SECTION METADATA INTEGRITY & MAPPING VALIDATION
-- Verifies dimension table join worked correctly and checks for anomalies
-- ══════════════════════════════════════════════════════════════════════════

WITH section_mapping_check AS (
    SELECT 
        section_ID,
        section_name,
        section_desc,
        section_category,
        sec_dim_priority,
        COUNT(*) as n_sentences,
        COUNT(DISTINCT cik_int) as n_companies,
        COUNT(DISTINCT temporal_bin) as n_bins,
        
        -- Check for NULL mappings (join failures)
        COUNT(CASE WHEN section_name IS NULL THEN 1 END) as null_section_names,
        COUNT(CASE WHEN section_desc IS NULL THEN 1 END) as null_section_descs,
        
        -- Check for priority distribution
        COUNT(CASE WHEN sec_dim_priority = 'P0' THEN 1 END) as n_critical,
        COUNT(CASE WHEN sec_dim_priority = 'P1' THEN 1 END) as n_high,
        COUNT(CASE WHEN sec_dim_priority = 'P2' THEN 1 END) as n_medium,
        COUNT(CASE WHEN sec_dim_priority = 'P3' THEN 1 END) as n_low,
        
        -- Verify canonical naming convention
        CASE 
            WHEN section_name LIKE 'ITEM_%' THEN '✓'
            ELSE '⚠️ Non-standard format'
        END as canonical_format_check
        
    FROM sample_1m_finrag
    GROUP BY section_ID, section_name, section_desc, section_category, sec_dim_priority
)

SELECT 
    '═══ SECTION METADATA VALIDATION ═══' as validation_type,
    section_ID,
    section_name,
    SUBSTR(section_desc, 1, 40) as section_desc_preview,
    section_category,
    sec_dim_priority as priority,
    n_sentences,
    n_companies,
    
    -- Quality flags
    CASE 
        WHEN null_section_names > 0 THEN '❌ JOIN FAILED: ' || null_section_names || ' unmapped'
        WHEN canonical_format_check != '✓' THEN '⚠️ Non-canonical naming'
        WHEN n_sentences < 100 THEN '⚠️ Sparse section (<100 sentences)'
        ELSE '✓ Valid'
    END as mapping_status,
    
    ROUND(n_sentences * 100.0 / SUM(n_sentences) OVER (), 2) as pct_of_corpus
    
FROM section_mapping_check
ORDER BY section_ID;


/*
 * all valid !
 * 
#,validation_type,section_ID,section_name,section_desc_preview,section_category,priority,n_sentences,n_companies,mapping_status,pct_of_corpus
1,═══ SECTION METADATA VALIDATION ═══,0,ITEM_1,Item 1: Business,P1_BUSINESS,P1,"103,525",75,✓ Valid,10.32
2,═══ SECTION METADATA VALIDATION ═══,1,ITEM_1A,Item 1A: Risk Factors,P1_RISK,P1,"147,094",75,✓ Valid,14.66
3,═══ SECTION METADATA VALIDATION ═══,2,ITEM_1B,Item 1B: Unresolved Staff Comments,P1_SEC_COMMENTS,P3,"1,255",75,✓ Valid,0.13
4,═══ SECTION METADATA VALIDATION ═══,3,ITEM_2,Item 2: Properties,P1_PROPERTIES,P2,"7,328",75,✓ Valid,0.73
5,═══ SECTION METADATA VALIDATION ═══,4,ITEM_3,Item 3: Legal Proceedings,P1_LEGAL,P2,"10,242",75,✓ Valid,1.02
6,═══ SECTION METADATA VALIDATION ═══,5,ITEM_4,Item 4: Mine Safety Disclosures,P1_MINE_SAFETY,P3,"5,175",75,✓ Valid,0.52
7,═══ SECTION METADATA VALIDATION ═══,6,ITEM_5,Item 5: Market for Registrant Common Equ,P2_MARKET,P2,"8,348",75,✓ Valid,0.83
8,═══ SECTION METADATA VALIDATION ═══,7,ITEM_6,Item 6: [Reserved] / Selected Financial ,P2_SELECTED_FIN,P2,"3,718",75,✓ Valid,0.37
9,═══ SECTION METADATA VALIDATION ═══,8,ITEM_7,Item 7: Management Discussion & Analysis,P2_MDNA,P0,"262,406",75,✓ Valid,26.15
10,═══ SECTION METADATA VALIDATION ═══,9,ITEM_7A,Item 7A: Quantitative and Qualitative Di,P2_MARKET_RISK,P1,"14,926",75,✓ Valid,1.49
11,═══ SECTION METADATA VALIDATION ═══,10,ITEM_8,Item 8: Financial Statements and Supplem,P2_FINANCIALS,P0,"328,412",75,✓ Valid,32.73
12,═══ SECTION METADATA VALIDATION ═══,11,ITEM_9,Item 9: Changes in and Disagreements wit,P2_ACCT_DISAGREE,P3,"1,064",75,✓ Valid,0.11
13,═══ SECTION METADATA VALIDATION ═══,12,ITEM_9A,Item 9A: Controls and Procedures,P2_CONTROLS,P2,"7,933",75,✓ Valid,0.79
14,═══ SECTION METADATA VALIDATION ═══,13,ITEM_9B,Item 9B: Other Information,P2_OTHER_INFO,P3,"1,727",75,✓ Valid,0.17
15,═══ SECTION METADATA VALIDATION ═══,14,ITEM_10,"Item 10: Directors, Executive Officers a",P3_DIRECTORS,P2,"6,850",74,✓ Valid,0.68
16,═══ SECTION METADATA VALIDATION ═══,15,ITEM_11,Item 11: Executive Compensation,P3_COMPENSATION,P2,"3,583",73,✓ Valid,0.36
17,═══ SECTION METADATA VALIDATION ═══,16,ITEM_12,Item 12: Security Ownership of Certain B,P3_OWNERSHIP,P2,"3,199",74,✓ Valid,0.32
18,═══ SECTION METADATA VALIDATION ═══,17,ITEM_13,Item 13: Certain Relationships and Relat,P3_RELATED_TX,P3,"2,731",74,✓ Valid,0.27
19,═══ SECTION METADATA VALIDATION ═══,18,ITEM_14,Item 14: Principal Accountant Fees and S,P3_AUDITOR_FEES,P3,"6,304",75,✓ Valid,0.63
20,═══ SECTION METADATA VALIDATION ═══,19,ITEM_15,Item 15: Exhibits and Financial Statemen,P4_EXHIBITS,P3,"77,714",75,✓ Valid,7.74
 */
-- Summary statistics




-- ══════════════════════════════════════════════════════════════════════════
-- V12: 
-- ══════════════════════════════════════════════════════════════════════════


WITH section_mapping_check AS (
    SELECT 
        section_ID,
        section_name,
        section_desc,
        section_category,
        sec_dim_priority,
        COUNT(*) as n_sentences,
        COUNT(DISTINCT cik_int) as n_companies,
        COUNT(DISTINCT temporal_bin) as n_bins,
        
        -- Check for NULL mappings (join failures)
        COUNT(CASE WHEN section_name IS NULL THEN 1 END) as null_section_names,
        COUNT(CASE WHEN section_desc IS NULL THEN 1 END) as null_section_descs,
        
        -- Check for priority distribution
        COUNT(CASE WHEN sec_dim_priority = 'P0' THEN 1 END) as n_critical,
        COUNT(CASE WHEN sec_dim_priority = 'P1' THEN 1 END) as n_high,
        COUNT(CASE WHEN sec_dim_priority = 'P2' THEN 1 END) as n_medium,
        COUNT(CASE WHEN sec_dim_priority = 'P3' THEN 1 END) as n_low,
        
        -- Verify canonical naming convention
        CASE 
            WHEN section_name LIKE 'ITEM_%' THEN '✓'
            ELSE '⚠️ Non-standard format'
        END as canonical_format_check
        
    FROM sample_1m_finrag
    GROUP BY section_ID, section_name, section_desc, section_category, sec_dim_priority
)
SELECT 
    '═══ VALIDATION SUMMARY ═══' as summary_section,
    COUNT(DISTINCT section_ID) as total_sections_mapped,
    SUM(CASE WHEN section_name IS NULL THEN 1 ELSE 0 END) as unmapped_sections,
    SUM(CASE WHEN section_name LIKE 'ITEM_%' THEN 1 ELSE 0 END) as canonical_format_count,
    SUM(CASE WHEN sec_dim_priority IN ('P0', 'P1') THEN n_sentences END) as critical_high_sentences,
    ROUND(SUM(CASE WHEN sec_dim_priority IN ('P0', 'P1') THEN n_sentences END) * 100.0 / SUM(n_sentences), 2) as pct_critical_high,
    CASE 
        WHEN SUM(CASE WHEN section_name IS NULL THEN 1 END) = 0 THEN '✓✓ All sections mapped successfully'
        ELSE '❌ CRITICAL: ' || SUM(CASE WHEN section_name IS NULL THEN 1 END) || ' sections failed to map'
    END as overall_status
FROM section_mapping_check;

--#,summary_section,total_sections_mapped,unmapped_sections,canonical_format_count,critical_high_sentences,pct_critical_high,overall_status
--1,═══ VALIDATION SUMMARY ═══,20,0,20,"856,363",85.33,[NULL]


-- ══════════════════════════════════════════════════════════════════════════
-- ══════════════════════════════════════════════════════════════════════════


/*
 * 
-- ══════════════════════════════════════════════════════════════════════════
-- PRE-STAGING DIAGNOSTIC: Dimension Table Join Quality Check
-- Verifies all GOOGL section_names can join to dim_sec_sections
-- ══════════════════════════════════════════════════════════════════════════

WITH join_test AS (
    SELECT 
        src.section_ID,
        src.section_name as src_section_name,
        src.section_item as src_section_item,
        dim.sec_item_canonical as dim_matched_canonical,
        dim.section_name as dim_matched_desc,
        dim.section_category as dim_matched_category,
        dim.priority as dim_matched_priority,
        
        -- Join success indicator
        CASE 
            WHEN dim.sec_item_canonical IS NOT NULL THEN '✅ JOIN SUCCESS'
            ELSE '❌ JOIN FAILED'
        END as join_status
        
    FROM read_parquet(getvariable('incremental_data_path')) src
    LEFT JOIN sampler.main.dim_sec_sections dim
        ON TRIM(UPPER(src.section_item)) = TRIM(UPPER(dim.sec_item_canonical))
)
SELECT 
    '🔍 DIMENSION JOIN ANALYSIS' as diagnostic,
    section_ID,
    src_section_name,
    src_section_item,
    dim_matched_canonical,
    SUBSTR(dim_matched_desc, 1, 40) as dim_desc_preview,
    dim_matched_category,
    dim_matched_priority,
    join_status,
    COUNT(*) as n_rows_affected
FROM join_test
GROUP BY section_ID, src_section_name, src_section_item, 
         dim_matched_canonical, dim_matched_desc, 
         dim_matched_category, dim_matched_priority, join_status
ORDER BY section_ID, join_status;
 * 
 */

