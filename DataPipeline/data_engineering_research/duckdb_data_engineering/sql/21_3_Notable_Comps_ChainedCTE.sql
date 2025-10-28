-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================

-- ============================================================================
-- Exploration/EDA:
-- ============================================================================
-- Task ideal ; 200 More companies, 700 table + 1 mil sample parquet.
-- FROM read_parquet(parquet_path()) -- access pattern so far. 
-- Candidate pool for notable additions
-- Initial Exploration CTE QUERY:





WITH sp500_ciks AS (
  SELECT DISTINCT CAST(cik AS VARCHAR) as cik FROM sp500_with_ciks
),
quality_candidates AS (
  SELECT 
    CAST(cik AS VARCHAR) as cik,
    name,
    COUNT(DISTINCT YEAR(reportDate::DATE)) as filing_years,
    COUNT(DISTINCT section) as section_coverage,
    COUNT(*) as total_sentences,
    -- Recency score (bonus for 2018-2020 activity)
    SUM(CASE WHEN YEAR(reportDate::DATE) >= 2018 THEN 1 ELSE 0 END) as recent_sentences,
    -- Key section density (Sections 1, 8, 10)
    SUM(CASE WHEN section IN (1, 8, 10) THEN 1 ELSE 0 END) as priority_section_sentences,
    MAX(YEAR(reportDate::DATE)) as latest_filing_year
  FROM read_parquet(parquet_path())
  WHERE cik NOT IN (SELECT cik FROM sp500_ciks)
  GROUP BY cik, name
  HAVING 
    filing_years >= 5           -- Consistent filers
    AND section_coverage >= 16  -- Comprehensive sections
    AND total_sentences >= 8000 -- Substantive content (NOT minimal)
    AND latest_filing_year >= 2018  -- Active in modern era
    AND priority_section_sentences >= 3000  -- Rich KPI/risk narrative
)

SELECT *,
  (filing_years * 5) + 
  (section_coverage * 10) + 
  (recent_sentences / 100) + 
  (priority_section_sentences / 50) as quality_score
FROM quality_candidates
ORDER BY quality_score DESC
LIMIT 300;  

---------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------

-- ============================================================================
-- NOTABLE COMPANY SELECTION: S&P 500 Complement (Target: 200 Companies)
-- Strategy: 120 auto-inclusion + 80 curated additions = 200 total
-- ============================================================================


--CTE 1-2: Base filtering (S&P 500 exclusion + quality gates)
--CTE 3: Score calculation
--CTE 4: Hidden gems manual curation 
--CTE 5: Exclusion list (problematic companies) 
--CTE 6: Auto-inclusion pool (top 120 by score, excluding bad actors)
--CTE 7: Final selection (auto + hidden gems, deduplicated, limited to 200)


DROP TABLE IF EXISTS notable_companies_200;


CREATE OR REPLACE TABLE notable_companies_200 AS
WITH sp500_ciks AS (
    SELECT DISTINCT CAST(cik AS VARCHAR) as cik 
    FROM sp500_with_ciks
),

-- CTE 2: Quality candidates with comprehensive filters
-- S&P 500 companies automatically excluded via WHERE clause
quality_candidates AS (
    SELECT 
        CAST(cik AS VARCHAR) as cik,
        name,
        COUNT(DISTINCT YEAR(reportDate::DATE)) as filing_years,
        COUNT(DISTINCT section) as section_coverage,
        COUNT(*) as total_sentences,
        SUM(CASE WHEN YEAR(reportDate::DATE) >= 2018 THEN 1 ELSE 0 END) as recent_sentences,
        SUM(CASE WHEN section IN (1, 8, 10) THEN 1 ELSE 0 END) as priority_section_sentences,
        MAX(YEAR(reportDate::DATE)) as latest_filing_year
    FROM read_parquet(parquet_path())
    WHERE cik NOT IN (SELECT cik FROM sp500_ciks)  -- S&P 500 filter enforced here
    GROUP BY cik, name
    HAVING 
        filing_years >= 5                          -- Temporal consistency
        AND section_coverage >= 16                 -- Disclosure comprehensiveness
        AND total_sentences >= 8000                -- Content volume
        AND latest_filing_year >= 2018             -- Recency relevance
        AND priority_section_sentences >= 3000     -- Information density
),

-- CTE 3: Add quality score calculation (simplified company_type)
scored_candidates AS (
    SELECT 
        *,
        -- Multi-factor quality score
        (filing_years * 5) + 
        (section_coverage * 10) + 
        (recent_sentences / 100) + 
        (priority_section_sentences / 50) as quality_score,
        -- Simplified type classification (removed exhibit_bloat logic)
        CASE 
            WHEN UPPER(name) LIKE '%BANCORP%' 
              OR UPPER(name) LIKE '%BANK%' 
              OR UPPER(name) LIKE '%FINANCIAL CORP%' 
            THEN 'regional_bank'
            ELSE 'normal'
        END as company_type
    FROM quality_candidates
),

-- CTE 4: Hidden gems - manually curated must-includes (brand recognition)
-- NOTE: If any of these are in S&P 500, they'll be auto-excluded by quality_candidates filter
hidden_gems_list AS (
    SELECT cik, 'hidden_gem' as inclusion_reason
    FROM (VALUES
        -- Tier 1: Tech/Software giants (high demo value)
        ('0000796343'),  -- ADOBE INC.
        ('0001141391'),  -- Mastercard Inc
        ('0000896878'),  -- INTUIT INC
        ('0000769397'),  -- Autodesk, Inc.
        ('0000712515'),  -- ELECTRONIC ARTS INC.
        ('0001137789'),  -- Seagate Technology
        ('0000106040'),  -- WESTERN DIGITAL CORP
        ('0001090872'),  -- AGILENT TECHNOLOGIES, INC.
        ('0000070866'),  -- NCR CORP
        
        -- Tier 2: Consumer brands (household names)
        ('0000021344'),  -- COCA COLA CO
        ('0000077476'),  -- PEPSICO INC
        ('0001103982'),  -- Mondelez International, Inc.
        ('0000056873'),  -- KROGER CO
        ('0000046080'),  -- HASBRO, INC.
        ('0000063276'),  -- MATTEL INC /DE/
        ('0000793952'),  -- HARLEY-DAVIDSON, INC.
        
        -- Tier 3: Healthcare/Pharma
        ('0000049071'),  -- HUMANA INC
        ('0000879169'),  -- INCYTE CORP
        ('0001082554'),  -- UNITED THERAPEUTICS Corp
        
        -- Tier 4: Industrial/Materials leaders
        ('0000823768'),  -- WASTE MANAGEMENT INC
        ('0000037785'),  -- FMC CORP
        ('0000026172'),  -- CUMMINS INC
        ('0000022444'),  -- COMMERCIAL METALS Co
        
        -- Tier 5: Financials (major institutions only)
        ('0001059556'),  -- MOODYS CORP /DE/
        ('0001156375'),  -- CME GROUP INC.
        ('0000791963'),  -- OPPENHEIMER HOLDINGS INC
        ('0000062709'),  -- MARSH & MCLENNAN COMPANIES, INC.
        
        -- Tier 6: Specialty/Unique businesses
        ('0001067701'),  -- UNITED RENTALS, INC.
        ('0000921582'),  -- IMAX CORP
        ('0001133421'),  -- NORTHROP GRUMMAN CORP /DE/
        ('0000033185'),  -- EQUIFAX INC
        
        -- Tier 7: Energy/Utilities (selective major players)
        ('0001039684'),  -- ONEOK INC /NEW/
        ('0001002910'),  -- AMEREN CORP
        ('0000072741')   -- EVERSOURCE ENERGY (re-added, bloat filter removed)
    ) AS t(cik)
),

-- CTE 5: Exclusion list - ONLY truly problematic companies (minimal list)
exclusion_list AS (
    SELECT cik, exclusion_reason
    FROM (VALUES
        -- Subprime/regulatory issues
        ('0000873860', 'regulatory_issues'),        -- OCWEN FINANCIAL CORP
        
        -- Obscure companies with very low demo value
        ('0000830122', 'niche_low_activity'),       -- VIDLER WATER RESOURCES, INC.
        ('0001014111', 'obscure')                   -- GlassBridge Enterprises, Inc.
    ) AS t(cik, exclusion_reason)
),

-- CTE 6: Auto-inclusion pool - INCREASED to 180 companies (relaxed filters)
auto_inclusion_pool AS (
    SELECT 
        cik,
        name,
        filing_years,
        section_coverage,
        total_sentences,
        recent_sentences,
        priority_section_sentences,
        latest_filing_year,
        quality_score,
        company_type,
        'auto_top180' as selection_method
    FROM scored_candidates
    WHERE 
        -- Only exclude truly problematic companies (minimal exclusion list)
        cik NOT IN (SELECT cik FROM exclusion_list)
    ORDER BY quality_score DESC
    LIMIT 195 -- INCREASED 
),

-- CTE 7: Final 200 selection - combine auto + hidden gems, deduplicate
final_200 AS (
    -- Start with auto-inclusion pool (180 companies)
    SELECT 
        cik, name, filing_years, section_coverage, total_sentences,
        recent_sentences, priority_section_sentences, latest_filing_year,
        quality_score, company_type, selection_method
    FROM auto_inclusion_pool
    
    UNION
    
    -- Add hidden gems not already in auto-inclusion
    SELECT 
        sc.cik, sc.name, sc.filing_years, sc.section_coverage, sc.total_sentences,
        sc.recent_sentences, sc.priority_section_sentences, sc.latest_filing_year,
        sc.quality_score, sc.company_type, hg.inclusion_reason as selection_method
    FROM scored_candidates sc
    INNER JOIN hidden_gems_list hg ON sc.cik = hg.cik
    WHERE 
        -- Only add if not already in auto-inclusion
        sc.cik NOT IN (SELECT cik FROM auto_inclusion_pool)
        -- And not in exclusion list (minimal)
        AND sc.cik NOT IN (SELECT cik FROM exclusion_list)
    
    ORDER BY quality_score DESC
    LIMIT 200  -- For ensuring exactly 200
)

-- Final SELECT for CREATE TABLE
SELECT 
    ROW_NUMBER() OVER (ORDER BY quality_score DESC) as company_rank,
    cik,
    name as company_name,
    filing_years,
    section_coverage,
    total_sentences,
    recent_sentences,
    priority_section_sentences,
    latest_filing_year,
    ROUND(quality_score, 2) as quality_score,
    company_type,
    selection_method,
    -- Derived metrics for sampling reference
    ROUND(priority_section_sentences * 1.0 / total_sentences, 3) as priority_ratio,
    ROUND(recent_sentences * 1.0 / total_sentences, 3) as recency_ratio,
    ROUND(total_sentences * 1.0 / filing_years, 1) as avg_sentences_per_year
FROM final_200
ORDER BY quality_score DESC;


