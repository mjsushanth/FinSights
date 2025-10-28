-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


-- Absolute paths
CREATE OR REPLACE MACRO parquet_path()   AS 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_filings_large_full.parquet';

-- Output roots 
CREATE OR REPLACE MACRO out_uniform()    AS 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/duckdb-finsight-data/artifacts/sample_uniform/';

CREATE OR REPLACE MACRO out_strat_1m()   AS 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/duckdb-finsight-data/artifacts/sample_strat_1m/';
CREATE OR REPLACE MACRO out_hash_approx()AS 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/duckdb-finsight-data/artifacts/sample_hash_approx1m/';


-- Tuning knobs
CREATE OR REPLACE MACRO sample_pct_approx() AS 2.0;      -- ~2% uniform block sample

CREATE OR REPLACE MACRO target_rows_1m()     AS 1000000;  
CREATE OR REPLACE MACRO target_rows_2m()     AS 2000000;  
CREATE OR REPLACE MACRO target_rows_35k()     AS 35000;  

CREATE OR REPLACE MACRO hash_modulus()       AS 100;      -- deterministic hash denom
CREATE OR REPLACE MACRO hash_keep_lt()       AS 14;       -- keep ~14%
