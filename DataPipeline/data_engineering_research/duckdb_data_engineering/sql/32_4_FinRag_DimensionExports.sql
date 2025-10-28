
-- ============================================================================
-- EXPORT DIMENSION TABLES TO PARQUET
-- Naming Convention: finrag_dim_{table_purpose}_v{version}.parquet 
-- if needed, add version. else, auto replace files.
-- ============================================================================

/*
 *  ## Tables Explained. ==========================================================================================================
	1. dim_sec_sections       - Maps HF section codes (0-19) to canonical SEC item names (ITEM_1A, ITEM_7), 
								includes section descriptions, categories, and priorities for RAG routing
	
	2. finrag_tgt_comps_21    - Curated list of 21 high-value companies (CIK, name, ticker) for subset table generation.
	3. finrag_tgt_comps_75    - Target companies for 1M stratified sample (CIK, name, ticker, quality_score), 
								CRITICAL dependency for 31_1_StratifiedSamplingScript
	
	4. finrag_tgt_comps_150   - Extended company set of 150 firms for larger-scale experiments, 
								includes quality metrics and selection method tracking
	5. finrag_tgt_comps_540   - Complete company universe (S&P 500 + Notable firms), 
								master reference for all company selection decisions
	
	6. sp500_with_ciks        - S&P 500 constituent mapping (ticker, company_name, CIK, weight_pct) from State Street SPY holdings, 
								used for market-cap-weighted company selection
								

	## parquet to table name mapping:						
	finrag_dim_sec_sections.parquet       → dim_sec_sections
	finrag_dim_companies_21.parquet       → finrag_tgt_comps_21
	finrag_dim_companies_75.parquet       → finrag_tgt_comps_75
	finrag_dim_companies_150.parquet      → finrag_tgt_comps_150
	finrag_dim_companies_540.parquet      → finrag_tgt_comps_540
	finrag_dim_sp500_holdings.parquet     → sp500_with_ciks

	## Import pattern examples !
	CREATE TABLE dim_sec_sections AS SELECT * FROM read_parquet('finrag_dim_sec_sections.parquet');
	CREATE TABLE finrag_tgt_comps_21 AS SELECT * FROM read_parquet('finrag_dim_companies_21.parquet');
	-- etc.Retry
	================================================================================================================================
 * 
 *  
 */

SET VARIABLE export_base_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports';


-- ══════════════════════════════════════════════════════════════════════════
-- EXPORT 1: Section Dimension (SEC 10-K Section Mapping)
-- ══════════════════════════════════════════════════════════════════════════

SET VARIABLE dim_sections_export = (
    getvariable('export_base_path') || '/finrag_dim_sec_sections.parquet'
);

SELECT 'Exporting section dimension...' as status, getvariable('dim_sections_export') as destination;

PREPARE export_dim_sections AS
    COPY sampler.main.dim_sec_sections 
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

-- DuckDB automatically overwrites if file exists (no manual delete needed)
EXECUTE export_dim_sections(getvariable('dim_sections_export'));

SELECT 
    '✓ DIMENSION 1 EXPORTED' as status,
    'finrag_dim_sec_sections.parquet' as filename,
    COUNT(*) as rows_exported
FROM sampler.main.dim_sec_sections;


-- ══════════════════════════════════════════════════════════════════════════
-- EXPORT 2: Company Dimension (21 Curated Companies)
-- ══════════════════════════════════════════════════════════════════════════

SET VARIABLE dim_companies_export = (
    getvariable('export_base_path') || '/finrag_dim_companies_21.parquet'
);

SELECT 'Exporting company dimension...' as status, getvariable('dim_companies_export') as destination;

PREPARE export_dim_companies AS
    COPY sampler.main.finrag_tgt_comps_21 
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

-- DuckDB automatically overwrites if file exists (no manual delete needed)
EXECUTE export_dim_companies(getvariable('dim_companies_export'));

SELECT 
    '✓ DIMENSION 2 EXPORTED' as status,
    'finrag_dim_companies_21.parquet' as filename,
    COUNT(*) as rows_exported
FROM sampler.main.finrag_tgt_comps_21;




-- ══════════════════════════════════════════════════════════════════════════
-- EXPORT 3: Company Dimension (75 Target Companies - CRITICAL)
-- ══════════════════════════════════════════════════════════════════════════

SET VARIABLE dim_companies_75_export = (
    getvariable('export_base_path') || '/finrag_dim_companies_75.parquet'
);

SELECT 'Exporting 75 companies dimension...' as status, getvariable('dim_companies_75_export') as destination;

PREPARE export_dim_companies_75 AS
    COPY sampler.main.finrag_tgt_comps_75 
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

EXECUTE export_dim_companies_75(getvariable('dim_companies_75_export'));

SELECT 
    '✓ DIMENSION 3 EXPORTED' as status,
    'finrag_dim_companies_75.parquet' as filename,
    COUNT(*) as rows_exported,
    'CRITICAL: Required by 31_1_StratifiedSamplingScript' as note
FROM sampler.main.finrag_tgt_comps_75;


-- ══════════════════════════════════════════════════════════════════════════
-- EXPORT 4: Company Dimension (150 Extended Set)
-- ══════════════════════════════════════════════════════════════════════════

SET VARIABLE dim_companies_150_export = (
    getvariable('export_base_path') || '/finrag_dim_companies_150.parquet'
);

SELECT 'Exporting 150 companies dimension...' as status, getvariable('dim_companies_150_export') as destination;

PREPARE export_dim_companies_150 AS
    COPY sampler.main.finrag_tgt_comps_150 
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

EXECUTE export_dim_companies_150(getvariable('dim_companies_150_export'));

SELECT 
    '✓ DIMENSION 4 EXPORTED' as status,
    'finrag_dim_companies_150.parquet' as filename,
    COUNT(*) as rows_exported
FROM sampler.main.finrag_tgt_comps_150;


-- ══════════════════════════════════════════════════════════════════════════
-- EXPORT 5: Company Dimension (540 Complete Universe)
-- ══════════════════════════════════════════════════════════════════════════

SET VARIABLE dim_companies_540_export = (
    getvariable('export_base_path') || '/finrag_dim_companies_540.parquet'
);

SELECT 'Exporting 540 companies dimension...' as status, getvariable('dim_companies_540_export') as destination;

PREPARE export_dim_companies_540 AS
    COPY sampler.main.finrag_tgt_comps_540 
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

EXECUTE export_dim_companies_540(getvariable('dim_companies_540_export'));

SELECT 
    '✓ DIMENSION 5 EXPORTED' as status,
    'finrag_dim_companies_540.parquet' as filename,
    COUNT(*) as rows_exported
FROM sampler.main.finrag_tgt_comps_540;


-- ══════════════════════════════════════════════════════════════════════════
-- EXPORT 6: S&P 500 Reference Data (Market-Cap Weighted)
-- ══════════════════════════════════════════════════════════════════════════

SET VARIABLE sp500_export = (
    getvariable('export_base_path') || '/finrag_dim_sp500_holdings.parquet'
);

SELECT 'Exporting S&P 500 reference data...' as status, getvariable('sp500_export') as destination;

PREPARE export_sp500 AS
    COPY sampler.main.sp500_with_ciks 
    TO ?
    (FORMAT PARQUET, COMPRESSION 'ZSTD');

EXECUTE export_sp500(getvariable('sp500_export'));

SELECT 
    '✓ DIMENSION 6 EXPORTED' as status,
    'finrag_dim_sp500_holdings.parquet' as filename,
    COUNT(*) as rows_exported
FROM sampler.main.sp500_with_ciks;















-- ══════════════════════════════════════════════════════════════════════════
-- EXPORT SUMMARY
-- ══════════════════════════════════════════════════════════════════════════

SELECT 
    '═════════════════════════════════════════════════════════════════' as separator,
    '             ✓✓✓ ALL DIMENSION TABLES EXPORTED ✓✓✓                ' as status,
    '═════════════════════════════════════════════════════════════════' as separator2;

SELECT 
    'Export Complete' as summary,
    '6 dimension tables exported to: ' || getvariable('export_base_path') as location;


-- Display manifest
SELECT 
    ROW_NUMBER() OVER (ORDER BY table_type) as seq,
    table_type,
    filename,
    purpose,
    dependencies
FROM (
    SELECT 
        'Section Mapping' as table_type,
        'finrag_dim_sec_sections.parquet' as filename,
        'Maps section codes (0-19) to canonical SEC items (ITEM_1A, ITEM_7)' as purpose,
        '31_1, 32_3, Python ETL' as dependencies
    UNION ALL SELECT 
        'Companies (21)',
        'finrag_dim_companies_21.parquet',
        'Curated 21 high-value companies for focused RAG development',
        '32_3 (subset creation)'
    UNION ALL SELECT 
        'Companies (75)',
        'finrag_dim_companies_75.parquet',
        'Target companies for 1M stratified sample [CRITICAL]',
        '31_1 (main sampling)'
    UNION ALL SELECT 
        'Companies (150)',
        'finrag_dim_companies_150.parquet',
        'Extended company set for larger experiments',
        'Future expansion'
    UNION ALL SELECT 
        'Companies (540)',
        'finrag_dim_companies_540.parquet',
        'Complete universe (S&P 500 + Notable firms)',
        'Company selection reference'
    UNION ALL SELECT 
        'S&P 500 Reference',
        'finrag_dim_sp500_holdings.parquet',
        'S&P 500 constituents with CIK mappings and market weights',
        'Company curation, validation'
) AS manifest;





-- ══════════════════════════════════════════════════════════════════════════
-- VALIDATION: Files Ready for Python Import
-- ══════════════════════════════════════════════════════════════════════════

SELECT 
    '═══ PYTHON IMPORT PATHS ═══' as info,
    'Use these paths in your standardization script:' as instruction;

SELECT 
    'dim_sections' as dimension,
    getvariable('export_base_path') || '/finrag_dim_sec_sections.parquet' as python_path
UNION ALL
SELECT 
    'dim_companies',
    getvariable('export_base_path') || '/finrag_dim_companies_21.parquet';



