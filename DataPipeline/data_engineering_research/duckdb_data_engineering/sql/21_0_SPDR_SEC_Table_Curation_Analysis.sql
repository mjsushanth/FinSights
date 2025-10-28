-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


-- https://www.ssga.com/us/en/individual/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx

--{
--  "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
--  "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
--  ...
--}

-- theres format auto, etc. dont try to auto format for now. 
-- Load SEC company tickers (handles the {"0": {...}, "1": {...}} structure)
-- json_each is a table function and needs to be in the FROM clause.
-- read_json() already parsed it into a DuckDB STRUCT

-- SPDR --> product is the SPDR S&P 500 ETF Trust (SPY), which is an ETF that seeks to track the performance of the S&P 500 index
-- download daily holdings

CREATE OR REPLACE TABLE sec_company_tickers AS
WITH raw_json AS (
    SELECT content FROM read_text('D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/webdata/sec_company_tickers.json')
)
SELECT 
    CAST(kv.value->>'cik_str' AS INTEGER) as cik,
    kv.value->>'ticker' as ticker,
    kv.value->>'title' as company_name
FROM raw_json, json_each(raw_json.content) as kv;


-- Validation
SELECT COUNT(*) FROM sec_company_tickers;
--#,count_star()
--1,10,142

SELECT * FROM sec_company_tickers WHERE ticker IN ('NVDA', 'MSFT', 'AAPL') ORDER BY ticker;
--#,cik,ticker,company_name
--1,"320,193",AAPL,Apple Inc.
--2,"789,019",MSFT,MICROSOFT CORP
--3,"1,045,810",NVDA,NVIDIA CORP


-----------------------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------------------


-- Install and load spatial extension (Excel support)
INSTALL spatial;
LOAD spatial;



-- Load SPY holdings, skipping first 4 rows

DROP TABLE IF EXISTS spy_holdings_raw_15OCT;



-- Drop existing table
DROP TABLE IF EXISTS spy_holdings_raw_15OCT;

-- worked but did not skip rows oddly.
-- st_read('...', layer='holdings', open_options=['HEADERS=YES', 'SKIP=4'] );


CREATE OR REPLACE TABLE spy_holdings_raw_15OCT AS
SELECT * 
FROM st_read('D:/JoelDesktop folds_24/NEU FALL2025/MLops IE7374 Project/finrag-insights-mlops/data/webdata/SNP_15OCT_SPY_DAILYHOLD.xlsx',
    layer='holdings',
    open_options=['HEADERS=NO']  -- Don't let GDAL interpret headers.
);

SELECT * FROM spy_holdings_raw_15OCT LIMIT 10;

-- create the clean table, skipping rows 1-4 and using row 5 as headers
CREATE OR REPLACE TABLE spy_holdings_15OCT AS
SELECT 
    TRIM(Field1) as company_name,
    TRIM(Field2) as ticker,
    TRIM(Field3) as identifier,
    TRIM(Field4) as sedol,
    CAST(REPLACE(TRIM(Field5), ',', '') AS DOUBLE) as weight_pct,
    TRIM(Field6) as sector,
    CAST(REPLACE(TRIM(Field7), ',', '') AS BIGINT) as shares_held,
    TRIM(Field8) as local_currency
FROM spy_holdings_raw_15OCT
WHERE Field1 NOT IN ('Fund Name:', 'Ticker Symbol:', 'Holdings:', 'Name', '[NULL]')  -- Filter header rows
  AND Field2 IS NOT NULL 
  AND Field2 != '-'
  AND Field2 NOT IN ('SPY', 'As of 15-Oct-2025', 'Ticker')  -- Filter metadata rows
ORDER BY weight_pct DESC;


-- One entry was "US dollar" without a ticker, which got filtered out
-- GOOGL (Class A) + GOOG (Class C) = 2 entries
-- hold 502-505 securities
-- Validation
SELECT COUNT(*) as n_holdings, 
       SUM(weight_pct) as total_weight 
FROM spy_holdings_15OCT;  

SELECT * FROM spy_holdings_15OCT LIMIT 10;

SELECT * FROM spy_holdings_raw_15OCT 
WHERE Field2 IS NULL OR Field2 = '-' OR Field2 = 'Ticker';

---------------------------------------------------------------------------------------------------------------------------------------







