-- ============================================================================
-- SECTION DIMENSION TABLE: SEC 10-K Filing Structure
-- ============================================================================

-- CANONICAL DIMENSION TABLE: SEC 10-K Section Mapping v2.0
-- Purpose: Multi-source mapping for historical (HF) and live (API) data
-- ============================================================================


DROP TABLE IF EXISTS sampler.main.dim_sec_sections;


CREATE TABLE sampler.main.dim_sec_sections AS
SELECT * FROM (VALUES
    -- ═══════════════════════════════════════════════════════════════════════
    -- Column Legend:
    -- ═══════════════════════════════════════════════════════════════════════
    -- sec_item_canonical:   PRIMARY KEY - Universal join column (ITEM_1, ITEM_1A, etc.)
    -- hf_section_code:      Hugging Face dataset encoding (0-19)
    -- api_section_code:     SEC EDGAR API / Official Item number ('1', '1A', '7')
    -- section_code:         Machine-readable code (PART_I_ITEM_1)
    -- section_name:         Human-readable name ('Item 1: Business')
    -- section_description:  What this section contains
    -- section_category:     Grouped taxonomy (P1_BUSINESS, P2_MDNA, etc.)
    -- part_number:          Which Part of 10-K (1-4)
    -- priority:             P0/P1/P2/P3/P4 for importance ranking
    -- has_sub_items:        TRUE if contains sub-sections (1A, 1B, etc.)
    -- ═══════════════════════════════════════════════════════════════════════
    
    -- PART I: Business and Risk Information
    -- ═══════════════════════════════════════════════════════════════════════
    (
        'ITEM_1',                           -- sec_item_canonical
        0,                                  -- hf_section_code
        '1',                                -- api_section_code
        'PART_I_ITEM_1',                    -- section_code
        'Item 1: Business',                 -- section_name
        'Business description, products, services, strategy, competition, market segments', -- section_description
        'P1_BUSINESS',                      -- section_category
        1,                                  -- part_number
        'P1',                               -- priority
        TRUE                                -- has_sub_items
    ),
    
    (
        'ITEM_1A',
        1,
        '1A',
        'PART_I_ITEM_1A',
        'Item 1A: Risk Factors',
        'Risk factors, uncertainties, forward-looking statement risks',
        'P1_RISK',
        1,
        'P1',
        FALSE
    ),
    
    (
        'ITEM_1B',
        2,
        '1B',
        'PART_I_ITEM_1B',
        'Item 1B: Unresolved Staff Comments',
        'Outstanding SEC staff comments (typically "None")',
        'P1_SEC_COMMENTS',
        1,
        'P3',
        FALSE
    ),
    
    (
        'ITEM_2',
        3,
        '2',
        'PART_I_ITEM_2',
        'Item 2: Properties',
        'Physical properties, facilities, real estate holdings',
        'P1_PROPERTIES',
        1,
        'P2',
        FALSE
    ),
    
    (
        'ITEM_3',
        4,
        '3',
        'PART_I_ITEM_3',
        'Item 3: Legal Proceedings',
        'Litigation, legal matters, material legal proceedings',
        'P1_LEGAL',
        1,
        'P2',
        FALSE
    ),
    
    (
        'ITEM_4',
        5,
        '4',
        'PART_I_ITEM_4',
        'Item 4: Mine Safety Disclosures',
        'Mine safety statistics (only for mining companies)',
        'P1_MINE_SAFETY',
        1,
        'P3',
        FALSE
    ),
    
    -- ═══════════════════════════════════════════════════════════════════════
    -- PART II: Financial Information and Management Analysis
    -- ═══════════════════════════════════════════════════════════════════════
    
    (
        'ITEM_5',
        6,
        '5',
        'PART_II_ITEM_5',
        'Item 5: Market for Registrant Common Equity',
        'Stock market data, dividends, share repurchases, stock performance',
        'P2_MARKET',
        2,
        'P2',
        FALSE
    ),
    
    (
        'ITEM_6',
        7,
        '6',
        'PART_II_ITEM_6',
        'Item 6: [Reserved] / Selected Financial Data',
        'Multi-year financial summary (deprecated after 2020 for smaller filers)',
        'P2_SELECTED_FIN',
        2,
        'P2',
        FALSE
    ),
    
    (
        'ITEM_7',
        8,
        '7',
        'PART_II_ITEM_7',
        'Item 7: Management Discussion & Analysis (MD&A)',
        'Revenue trends, operating results, liquidity, capital resources, outlook - CRITICAL',
        'P2_MDNA',
        2,
        'P0',                               -- CRITICAL priority
        TRUE                                -- Has Item 7A sub-item
    ),
    
    (
        'ITEM_7A',
        9,
        '7A',
        'PART_II_ITEM_7A',
        'Item 7A: Quantitative and Qualitative Disclosures About Market Risk',
        'Interest rate risk, foreign currency risk, commodity risk exposures',
        'P2_MARKET_RISK',
        2,
        'P1',
        FALSE
    ),
    
    (
        'ITEM_8',
        10,
        '8',
        'PART_II_ITEM_8',
        'Item 8: Financial Statements and Supplementary Data',
        'Audited financial statements, balance sheet, income statement, cash flow, notes - CRITICAL',
        'P2_FINANCIALS',
        2,
        'P0',                               -- CRITICAL priority
        FALSE
    ),
    
    (
        'ITEM_9',
        11,
        '9',
        'PART_II_ITEM_9',
        'Item 9: Changes in and Disagreements with Accountants',
        'Accounting disagreements with auditors (rare, usually "None")',
        'P2_ACCT_DISAGREE',
        2,
        'P3',
        TRUE                                -- Has 9A, 9B sub-items
    ),
    
    (
        'ITEM_9A',
        12,
        '9A',
        'PART_II_ITEM_9A',
        'Item 9A: Controls and Procedures',
        'Internal controls, SOX 404 disclosures, ICFR effectiveness',
        'P2_CONTROLS',
        2,
        'P2',
        FALSE
    ),
    
    (
        'ITEM_9B',
        13,
        '9B',
        'PART_II_ITEM_9B',
        'Item 9B: Other Information',
        'Material information not previously disclosed',
        'P2_OTHER_INFO',
        2,
        'P3',
        FALSE
    ),
    
    -- ═══════════════════════════════════════════════════════════════════════
    -- PART III: Directors, Officers, Corporate Governance
    -- ═══════════════════════════════════════════════════════════════════════
    
    (
        'ITEM_10',
        14,
        '10',
        'PART_III_ITEM_10',
        'Item 10: Directors, Executive Officers and Corporate Governance',
        'Board of directors, executive officers, governance structure',
        'P3_DIRECTORS',
        3,
        'P2',
        FALSE
    ),
    
    (
        'ITEM_11',
        15,
        '11',
        'PART_III_ITEM_11',
        'Item 11: Executive Compensation',
        'Executive pay, equity grants, compensation discussion and analysis',
        'P3_COMPENSATION',
        3,
        'P2',
        FALSE
    ),
    
    (
        'ITEM_12',
        16,
        '12',
        'PART_III_ITEM_12',
        'Item 12: Security Ownership of Certain Beneficial Owners and Management',
        'Share ownership by directors, officers, major shareholders, equity plans',
        'P3_OWNERSHIP',
        3,
        'P2',
        FALSE
    ),
    
    (
        'ITEM_13',
        17,
        '13',
        'PART_III_ITEM_13',
        'Item 13: Certain Relationships and Related Transactions',
        'Related party transactions, director independence',
        'P3_RELATED_TX',
        3,
        'P3',
        FALSE
    ),
    
    (
        'ITEM_14',
        18,
        '14',
        'PART_III_ITEM_14',
        'Item 14: Principal Accountant Fees and Services',
        'Auditor fees, audit and non-audit services',
        'P3_AUDITOR_FEES',
        3,
        'P3',
        FALSE
    ),
    
    -- ═══════════════════════════════════════════════════════════════════════
    -- PART IV: Exhibits and Signatures
    -- ═══════════════════════════════════════════════════════════════════════
    
    (
        'ITEM_15',
        19,
        '15',
        'PART_IV_ITEM_15',
        'Item 15: Exhibits and Financial Statement Schedules',
        'List of exhibits, financial schedules, exhibit index',
        'P4_EXHIBITS',
        4,
        'P3',
        TRUE                                -- Has Item 16 as optional extension
    ),
    
    (
        'ITEM_16',
        NULL,                               -- Not in HF dataset (optional, rarely used)
        '16',
        'PART_IV_ITEM_16',
        'Item 16: Form 10-K Summary',
        'Optional summary of 10-K (rarely used)',
        'P4_SUMMARY',
        4,
        'P3',
        FALSE
    )

) AS t(
    sec_item_canonical,
    hf_section_code,
    api_section_code,
    section_code,
    section_name,
    section_description,
    section_category,
    part_number,
    priority,
    has_sub_items
);


select * from sampler.main.dim_sec_sections dss ;




-- ============================================================================
-- EXPORT dim_sec_sections to Parquet
-- Replaces existing file in exports directory
-- ============================================================================

SET VARIABLE export_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports';
SET VARIABLE export_filename = 'finrag_dim_sec_sections.parquet';

-- Build full path
SET VARIABLE export_full_path = (
    getvariable('export_path') || '/' || getvariable('export_filename')
);

-- Display export path for confirmation
SELECT 
    'Exporting dimension table...' as status,
    getvariable('export_full_path') as destination,
    COUNT(*) as n_sections
FROM sampler.main.dim_sec_sections;

-- Prepare export statement
PREPARE export_dim_sections AS
    COPY sampler.main.dim_sec_sections
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

-- Execute export
EXECUTE export_dim_sections(getvariable('export_full_path'));

-- Confirmation
SELECT 
    '✓ EXPORT COMPLETE' as status,
    getvariable('export_filename') as filename,
    COUNT(*) as rows_exported,
    COUNT(DISTINCT sec_item_canonical) as unique_items
FROM sampler.main.dim_sec_sections;

































































