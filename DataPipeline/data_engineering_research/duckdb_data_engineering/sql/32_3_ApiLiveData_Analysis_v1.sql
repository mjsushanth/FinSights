-- ============================================================================
-- LIVE API DATA VALIDATION: 4-Year Modern Era (2021-2024)
-- financial/regulatory compliance checks
-- ============================================================================

SET VARIABLE api_parquet_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/sec_finrag_liveApiData_4Y_merged_1024_v1.parquet';

SET VARIABLE histbins_path = 'D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/exports/finrag_21companies_allbins_v2.0.parquet';


SELECT * FROM read_parquet(getvariable('api_parquet_path'));

SELECT * FROM read_parquet(getvariable('histbins_path'));



--Do both datasets have the same core columns?
--Are data types compatible (VARCHAR vs INTEGER can break joins)?
--Are audit columns present (for incremental loads)?


-- ══════════════════════════════════════════════════════════════════════════
-- QUERY 1: COLUMN NAME COMPARISON (Side-by-Side Schema Diff)
-- ══════════════════════════════════════════════════════════════════════════

WITH api_schema AS (
    SELECT 
        column_name,
        column_type,
        ROW_NUMBER() OVER () as position
    FROM (DESCRIBE SELECT * FROM read_parquet(getvariable('api_parquet_path')))
),
hist_schema AS (
    SELECT 
        column_name,
        column_type,
        ROW_NUMBER() OVER () as position
    FROM (DESCRIBE SELECT * FROM read_parquet(getvariable('histbins_path')))
)
SELECT 
    COALESCE(a.column_name, h.column_name) as column_name,
    a.column_type as api_data_type,
    h.column_type as hist_data_type,
    a.position as api_position,
    h.position as hist_position,
    CASE 
        WHEN a.column_name IS NOT NULL AND h.column_name IS NOT NULL THEN '✓ Both'
        WHEN a.column_name IS NOT NULL AND h.column_name IS NULL THEN '⚠️ API Only'
        WHEN a.column_name IS NULL AND h.column_name IS NOT NULL THEN '⚠️ Hist Only'
    END as presence,
    CASE 
        WHEN a.column_type = h.column_type THEN '✓ Match'
        WHEN a.column_type IS NULL OR h.column_type IS NULL THEN 'N/A'
        ELSE '✗ TYPE MISMATCH'
    END as type_compatibility
FROM api_schema a
FULL OUTER JOIN hist_schema h ON a.column_name = h.column_name
ORDER BY 
    CASE presence
        WHEN '✓ Both' THEN 1
        WHEN '⚠️ API Only' THEN 2
        WHEN '⚠️ Hist Only' THEN 3
    END,
    COALESCE(a.position, h.position);


-- 21DEC;


--#,column_name,api_data_type,hist_data_type,api_position,hist_position,presence,type_compatibility
--1,cik,VARCHAR,VARCHAR,1,1,✓ Both,✓ Match
--2,name,VARCHAR,VARCHAR,2,3,✓ Both,✓ Match
--3,report_year,BIGINT,BIGINT,3,12,✓ Both,✓ Match
--4,docID,VARCHAR,VARCHAR,4,5,✓ Both,✓ Match
--5,sentenceID,VARCHAR,VARCHAR,5,6,✓ Both,✓ Match
--6,section_name,VARCHAR,VARCHAR,6,8,✓ Both,✓ Match
--7,form,VARCHAR,VARCHAR,8,9,✓ Both,✓ Match
--8,sentence,VARCHAR,VARCHAR,10,11,✓ Both,✓ Match
--9,temporal_bin,VARCHAR,VARCHAR,11,14,✓ Both,✓ Match
--10,sample_created_at,TIMESTAMP_NS,TIMESTAMP WITH TIME ZONE,12,19,✓ Both,✗ TYPE MISMATCH
--11,last_modified_date,TIMESTAMP_NS,TIMESTAMP WITH TIME ZONE,13,20,✓ Both,✗ TYPE MISMATCH
--12,sample_version,VARCHAR,VARCHAR,14,21,✓ Both,✓ Match
--13,source_file_path,VARCHAR,VARCHAR,15,22,✓ Both,✓ Match
--14,load_method,VARCHAR,VARCHAR,16,23,✓ Both,✓ Match
--15,section_ID,BIGINT,[NULL],7,[NULL],⚠️ API Only,N/A
--16,sentence_index,BIGINT,[NULL],9,[NULL],⚠️ API Only,N/A
--17,record_status,VARCHAR,[NULL],17,[NULL],⚠️ API Only,N/A
--18,cik_int,[NULL],INTEGER,[NULL],2,⚠️ Hist Only,N/A
--19,tickers,[NULL],VARCHAR[],[NULL],4,⚠️ Hist Only,N/A
--20,section,[NULL],BIGINT,[NULL],7,⚠️ Hist Only,N/A
--21,sic,[NULL],VARCHAR,[NULL],10,⚠️ Hist Only,N/A
--22,reportDate,[NULL],VARCHAR,[NULL],13,⚠️ Hist Only,N/A
--23,likely_kpi,[NULL],BOOLEAN,[NULL],15,⚠️ Hist Only,N/A
--24,has_numbers,[NULL],BOOLEAN,[NULL],16,⚠️ Hist Only,N/A
--25,has_comparison,[NULL],BOOLEAN,[NULL],17,⚠️ Hist Only,N/A
--26,section_priority,[NULL],VARCHAR,[NULL],18,⚠️ Hist Only,N/A
--27,row_hash,[NULL],VARCHAR,[NULL],24,⚠️ Hist Only,N/A


-- ══════════════════════════════════════════════════════════════════════════
-- QUERY 2: SCHEMA SUMMARY (Quick Stats)
-- ══════════════════════════════════════════════════════════════════════════

WITH api_schema AS (
    SELECT column_name, column_type
    FROM (DESCRIBE SELECT * FROM read_parquet(getvariable('api_parquet_path')))
),
hist_schema AS (
    SELECT column_name, column_type
    FROM (DESCRIBE SELECT * FROM read_parquet(getvariable('histbins_path')))
),
comparison AS (
    SELECT 
        a.column_name,
        a.column_type as api_type,
        h.column_type as hist_type,
        CASE 
            WHEN a.column_name IS NOT NULL AND h.column_name IS NOT NULL THEN 'shared'
            WHEN a.column_name IS NOT NULL THEN 'api_only'
            ELSE 'hist_only'
        END as presence_category
    FROM api_schema a
    FULL OUTER JOIN hist_schema h ON a.column_name = h.column_name
)
SELECT 
    '═══ SCHEMA COMPARISON SUMMARY ═══' as report,
    (SELECT COUNT(*) FROM api_schema) as api_total_columns,
    (SELECT COUNT(*) FROM hist_schema) as hist_total_columns,
    COUNT(CASE WHEN presence_category = 'shared' THEN 1 END) as shared_columns,
    COUNT(CASE WHEN presence_category = 'api_only' THEN 1 END) as api_only_columns,
    COUNT(CASE WHEN presence_category = 'hist_only' THEN 1 END) as hist_only_columns,
    COUNT(CASE WHEN presence_category = 'shared' AND api_type != hist_type THEN 1 END) as type_mismatches,
    CASE 
        WHEN COUNT(CASE WHEN presence_category = 'api_only' THEN 1 END) = 0 
         AND COUNT(CASE WHEN presence_category = 'hist_only' THEN 1 END) = 0
        THEN '✓ Perfect schema match'
        ELSE '⚠️ Schema differences detected'
    END as compatibility_status
FROM comparison;

--
--#,report,api_total_columns,hist_total_columns,shared_columns,api_only_columns,hist_only_columns,type_mismatches,compatibility_status
--1,═══ SCHEMA COMPARISON SUMMARY ═══,17,24,14,3,10,2,⚠️ Schema differences detected

-- ══════════════════════════════════════════════════════════════════════════
-- QUERY 3: CRITICAL COLUMN VALIDATION
-- ══════════════════════════════════════════════════════════════════════════

WITH required_columns AS (
    SELECT column_name FROM (VALUES
        ('cik'),
        ('name'),
        ('sentence'),
        ('sentenceID'),
        ('docID'),
        ('section'),
        ('reportDate'),
        ('report_year'),
        ('form')
    ) AS t(column_name)
),
api_columns AS (
    SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet(getvariable('api_parquet_path')))
),
hist_columns AS (
    SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet(getvariable('histbins_path')))
)
SELECT 
    '═══ CRITICAL COLUMN CHECK ═══' as validation,
    r.column_name,
    CASE WHEN a.column_name IS NOT NULL THEN '✓' ELSE '✗ MISSING' END as in_api,
    CASE WHEN h.column_name IS NOT NULL THEN '✓' ELSE '✗ MISSING' END as in_hist,
    CASE 
        WHEN a.column_name IS NOT NULL AND h.column_name IS NOT NULL THEN '✓ Present in both'
        WHEN a.column_name IS NULL AND h.column_name IS NULL THEN '✗✗ MISSING FROM BOTH'
        ELSE '⚠️ Present in only one dataset'
    END as status
FROM required_columns r
LEFT JOIN api_columns a ON r.column_name = a.column_name
LEFT JOIN hist_columns h ON r.column_name = h.column_name
ORDER BY 
    CASE status
        WHEN '✓ Present in both' THEN 1
        WHEN '⚠️ Present in only one dataset' THEN 2
        ELSE 3
    END;


--#,validation,column_name,in_api,in_hist,status
--1,═══ CRITICAL COLUMN CHECK ═══,cik,✓,✓,✓ Present in both
--2,═══ CRITICAL COLUMN CHECK ═══,name,✓,✓,✓ Present in both
--3,═══ CRITICAL COLUMN CHECK ═══,sentence,✓,✓,✓ Present in both
--4,═══ CRITICAL COLUMN CHECK ═══,sentenceID,✓,✓,✓ Present in both
--5,═══ CRITICAL COLUMN CHECK ═══,docID,✓,✓,✓ Present in both
--6,═══ CRITICAL COLUMN CHECK ═══,report_year,✓,✓,✓ Present in both
--7,═══ CRITICAL COLUMN CHECK ═══,form,✓,✓,✓ Present in both
--8,═══ CRITICAL COLUMN CHECK ═══,section,✗ MISSING,✓,⚠️ Present in only one dataset
--9,═══ CRITICAL COLUMN CHECK ═══,reportDate,✗ MISSING,✓,⚠️ Present in only one dataset


select * from sampler.main.finrag_tgt_comps_21;


select * from sampler.main.finrag_21companies_allbins;

-- b2124

SELECT * FROM sampler.main.dim_sec_sections;

