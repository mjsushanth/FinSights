-- ============================================================================
-- QUERY 1: Section Content Fingerprinting via Keyword Presence. 
-- Purpose: Validate HuggingFace section encoding by analyzing actual content
-- Author: Joel Markapudi
-- ============================================================================

SET VARIABLE parquet_source_path = 
'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_filings_large_full.parquet';



-- ============================================================================
-- REGEX based identity confirmation; -- TLDR this doesnt work. Unapproved.
-- ============================================================================


WITH section_samples AS (
    -- Sample 500 sentences per section for analysis
    SELECT 
        section,
        sentence,
        ROW_NUMBER() OVER (PARTITION BY section ORDER BY RANDOM()) as rn
    FROM read_parquet(getvariable('parquet_source_path'))
    WHERE sentence IS NOT NULL
      AND LENGTH(sentence) > 50  -- Substantive sentences only
),

section_keywords AS (
    SELECT 
        section,
        -- Count keyword presence to infer section identity
        COUNT(*) as n_sampled,
        
        -- Business/Overview keywords (Expected: Section 0 = Item 1)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(business|products|services|operations|customers|segment|market)\b') 
            THEN 1 ELSE 0 END) as kw_business,
        
        -- Risk Factor keywords (Expected: Section 1 = Item 1A)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(risk|adverse|uncertainty|may|could|volatility|exposure)\b') 
            THEN 1 ELSE 0 END) as kw_risk,
        
        -- MD&A keywords (Expected: Section 7 or 8 = Item 7)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(management|discussion|analysis|revenue|operating|income|results)\b') 
            THEN 1 ELSE 0 END) as kw_mdna,
        
        -- Financial Statements keywords (Expected: Section 8 or 9 = Item 8)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(financial statements?|consolidated|balance sheet|income statement)\b') 
            THEN 1 ELSE 0 END) as kw_financials,
        
        -- Notes to Financials keywords (Expected: Section 10)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(note [0-9]+|accounting|fair value|depreciation|amortization)\b') 
            THEN 1 ELSE 0 END) as kw_notes,
        
        -- Properties keywords (Expected: Section 2 or 3 = Item 2)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(properties|facilities|real estate|leased|owned)\b') 
            THEN 1 ELSE 0 END) as kw_properties,
        
        -- Legal Proceedings keywords (Expected: Section 3 or 4 = Item 3)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(litigation|legal proceeding|lawsuit|plaintiff|defendant)\b') 
            THEN 1 ELSE 0 END) as kw_legal,
        
        -- Controls/Governance keywords (Expected: Section 12-14)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(internal control|disclosure control|certif|sox|sarbanes)\b') 
            THEN 1 ELSE 0 END) as kw_controls,
        
        -- Exhibits keywords (Expected: Section 15, 19)
        SUM(CASE WHEN REGEXP_MATCHES(LOWER(sentence), 
            '\b(exhibit|filed herewith|incorporated by reference)\b') 
            THEN 1 ELSE 0 END) as kw_exhibits,
        
        -- Extract sample sentences for manual verification
        STRING_AGG(
            CASE WHEN rn <= 3 THEN SUBSTR(sentence, 1, 100) END, 
            ' || '
        ) as sample_text
        
    FROM section_samples
    WHERE rn <= 500  -- 500 sentences per section
    GROUP BY section
)

SELECT 
    section,
    n_sampled,
    
    -- Calculate dominant signal percentage for each keyword category
    ROUND(kw_business * 100.0 / n_sampled, 1) as pct_business,
    ROUND(kw_risk * 100.0 / n_sampled, 1) as pct_risk,
    ROUND(kw_mdna * 100.0 / n_sampled, 1) as pct_mdna,
    ROUND(kw_financials * 100.0 / n_sampled, 1) as pct_financials,
    ROUND(kw_notes * 100.0 / n_sampled, 1) as pct_notes,
    ROUND(kw_properties * 100.0 / n_sampled, 1) as pct_properties,
    ROUND(kw_legal * 100.0 / n_sampled, 1) as pct_legal,
    ROUND(kw_controls * 100.0 / n_sampled, 1) as pct_controls,
    ROUND(kw_exhibits * 100.0 / n_sampled, 1) as pct_exhibits,
    
    -- Infer likely identity based on strongest signal
    CASE 
        WHEN kw_business > GREATEST(kw_risk, kw_mdna, kw_financials, kw_notes) THEN 'LIKELY: Item 1 Business'
        WHEN kw_risk > GREATEST(kw_business, kw_mdna, kw_financials, kw_notes) THEN 'LIKELY: Item 1A Risk Factors'
        WHEN kw_mdna > GREATEST(kw_business, kw_risk, kw_financials, kw_notes) THEN 'LIKELY: Item 7 MD&A'
        WHEN kw_financials > GREATEST(kw_business, kw_risk, kw_mdna, kw_notes) THEN 'LIKELY: Item 8 Financials'
        WHEN kw_notes > GREATEST(kw_business, kw_risk, kw_mdna, kw_financials) THEN 'LIKELY: Notes to Financials'
        WHEN kw_properties > 10 THEN 'LIKELY: Item 2 Properties'
        WHEN kw_legal > 10 THEN 'LIKELY: Item 3 Legal'
        WHEN kw_controls > 10 THEN 'LIKELY: Item 9/12 Controls'
        WHEN kw_exhibits > 10 THEN 'LIKELY: Item 15 Exhibits'
        ELSE 'UNCLEAR - needs manual inspection'
    END as inferred_identity,
    
    sample_text
    
FROM section_keywords
ORDER BY section;



-- ============================================================================
-- MANUAL SECTION INSPECTION QUERY
-- Pick ONE company, ONE year, ONE filing → Review all sections
-- ============================================================================

SET VARIABLE parquet_source_path = 
'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_filings_large_full.parquet';

-- Pick a well-known company for easy verification
-- Example: Apple (CIK 0000320193) for 2020
SET VARIABLE inspection_cik = '0000320193';  -- Apple
SET VARIABLE inspection_year = 2020;




-- First rank the sentences, THEN aggregate
WITH ranked_sentences AS (
    SELECT 
        cik,
        name as company_name,
        reportDate,
        docID,
        section,
        sentence,
        sentenceID,
        ROW_NUMBER() OVER (PARTITION BY section ORDER BY sentenceID) as rn
    FROM read_parquet(getvariable('parquet_source_path'))
    WHERE cik = getvariable('inspection_cik')
      AND YEAR(CAST(reportDate AS DATE)) = getvariable('inspection_year')
      AND sentence IS NOT NULL
)

SELECT 
    section,
    COUNT(*) as sentences_in_section,
    MAX(company_name) as company_name,
    MAX(reportDate) as reportDate,
    MAX(docID) as docID,
    
    -- Show first 3 sentences from each section
    STRING_AGG(
        CASE WHEN rn <= 3 THEN '| ' || sentence END, 
        '\n'
    ) as sample_sentences_preview

FROM ranked_sentences
GROUP BY section
ORDER BY section;




































