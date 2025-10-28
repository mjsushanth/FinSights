-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


SELECT version();
PRAGMA version;

SELECT 1 + 1;


-- show schemas/tables via information_schema
SELECT table_schema, table_name
FROM information_schema.tables
ORDER BY 1,2
LIMIT 20;






-- ============================================================================
-- MERGE KEY DEMONSTRATION: Why sentenceID is Critical
-- Purpose: Prove that year+company filtering causes data loss
-- Demo Company: Apple (CIK 320193)
-- ============================================================================

-- ══════════════════════════════════════════════════════════════════════════
-- SCENARIO SETUP: Simulating a Partial Rerun
-- ══════════════════════════════════════════════════════════════════════════

-- Imagine: You need to re-ingest Apple's 2018 10-K because it had errors
-- Question: What's the correct way to replace it?

WITH apple_data AS (
    -- Current data in database (what we have)
    SELECT 
        cik_int,
        name,
        report_year,
        docID,
        section_name,
        COUNT(*) as n_sentences,
        MIN(sentenceID) as first_sentenceID,
        MAX(sentenceID) as last_sentenceID
    FROM sample_1m_finrag
    WHERE cik_int = 320193  -- Apple
      AND report_year = 2018
    GROUP BY cik_int, name, report_year, docID, section_name
)
SELECT 
    '📊 APPLE 2018 CURRENT DATA' as scenario,
    report_year,
    COUNT(*) as n_sections,
    SUM(n_sentences) as total_sentences,
    'We have ' || SUM(n_sentences) || ' sentences from Apple 2018' as current_state
FROM apple_data
GROUP BY report_year;


--#,scenario,report_year,n_sections,total_sentences,current_state
--1,📊 APPLE 2018 CURRENT DATA,"2,018",20,"1,152",We have 1152 sentences from Apple 2018


-- ══════════════════════════════════════════════════════════════════════════
-- APPROACH 1: "Year + Company" Deletion (WRONG! ❌)
-- ══════════════════════════════════════════════════════════════════════════

SELECT '❌ APPROACH 1: Delete by Year + Company (DANGEROUS)' as approach;

-- Simulate: DELETE WHERE cik_int = 320193 AND report_year = 2018
WITH would_be_deleted AS (
    SELECT 
        cik_int,
        name,
        report_year,
        docID,
        section_name,
        sentenceID,
        SUBSTR(sentence, 1, 100) as sentence_preview
    FROM sample_1m_finrag
    WHERE cik_int = 320193 
      AND report_year = 2018
)
SELECT 
    '🚨 ROWS THAT WOULD BE DELETED' as warning,
    COUNT(*) as n_rows_deleted,
    COUNT(DISTINCT docID) as n_filings_deleted,
    COUNT(DISTINCT section_name) as n_sections_deleted,
    '⚠️ Deletes ALL Apple 2018 data!' as problem
FROM would_be_deleted;




-- Show sample of what gets deleted
SELECT 
    'Sample deleted rows:' as detail,
    report_year,
    section_name,
    sentenceID,
    sentence_preview
FROM (
    SELECT 
        report_year,
        section_name,
        sentenceID,
        SUBSTR(sentence, 1, 80) as sentence_preview,
        ROW_NUMBER() OVER (ORDER BY sentenceID) as rn
    FROM sample_1m_finrag
    WHERE cik_int = 320193 AND report_year = 2018
)
WHERE rn <= 5;


-- ══════════════════════════════════════════════════════════════════════════
-- THE CRITICAL PROBLEM: Partial Re-ingestion
-- ══════════════════════════════════════════════════════════════════════════



WITH simulated_partial_reingestion AS (
    -- Pretend we only re-fetched 3 sections for Apple 2018
    SELECT sentenceID
    FROM sample_1m_finrag
    WHERE cik_int = 320193 
      AND report_year = 2018
      AND section_name IN ('ITEM_1', 'ITEM_7', 'ITEM_8')  -- Only 3 sections!
),
data_loss_calculation AS (
    SELECT 
        COUNT(CASE WHEN section_name IN ('ITEM_1', 'ITEM_7', 'ITEM_8') THEN 1 END) as sections_we_have,
        COUNT(CASE WHEN section_name NOT IN ('ITEM_1', 'ITEM_7', 'ITEM_8') THEN 1 END) as sections_we_DONT_have,
        COUNT(*) as total_sentences
    FROM sample_1m_finrag
    WHERE cik_int = 320193 AND report_year = 2018
)

SELECT 
    'DATA LOSS CALCULATION' as analysis,
    sections_we_have as new_data_sentences,
    sections_we_DONT_have as LOST_FOREVER,
    total_sentences as original_total,
    ROUND(sections_we_DONT_have * 100.0 / total_sentences, 1) as pct_data_lost,
    '❌ Approach 1 deletes ALL, inserts PARTIAL = DATA LOSS!' as verdict
FROM data_loss_calculation;




-- ══════════════════════════════════════════════════════════════════════════
-- APPROACH 2: sentenceID-Based Deletion (CORRECT! ✅)
-- Industry standard for ETL merges
-- ══════════════════════════════════════════════════════════════════════════

SELECT '═══════════════════════════════════════════════════════' as separator;
SELECT '✅ APPROACH 2: Delete by sentenceID (SAFE)' as approach;

-- Simulate: DELETE WHERE sentenceID IN (SELECT sentenceID FROM new_data)
WITH simulated_partial_reingestion AS (
    -- Same scenario: Only 3 sections in new data
    SELECT sentenceID
    FROM sample_1m_finrag
    WHERE cik_int = 320193 
      AND report_year = 2018
      AND section_name IN ('ITEM_1', 'ITEM_7', 'ITEM_8')
),
smart_deletion AS (
    SELECT 
        s.sentenceID,
        s.section_name,
        CASE 
            WHEN s.sentenceID IN (SELECT sentenceID FROM simulated_partial_reingestion)
            THEN 'WILL BE DELETED (and replaced with new version)'
            ELSE 'WILL BE KEPT (not in new data)'
        END as action
    FROM sample_1m_finrag s
    WHERE cik_int = 320193 AND report_year = 2018
)
SELECT 
    '✅ SMART MERGE BEHAVIOR' as analysis,
    action,
    COUNT(*) as n_sentences,
    COUNT(DISTINCT section_name) as n_sections,
    CASE 
        WHEN action LIKE '%DELETED%' THEN 'Only updated sentences removed'
        ELSE 'Untouched sections preserved!'
    END as result
FROM smart_deletion
GROUP BY action;











