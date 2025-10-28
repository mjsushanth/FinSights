-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


SELECT * FROM sec_company_tickers
WHERE ticker IN ('GOOGL', 'GOOG', 'GOOGLE')
   OR UPPER(company_name) LIKE '%GOOGLE%'
   OR UPPER(company_name) LIKE '%ALPHABET%'
   OR cik = 1652044;

--#,cik,ticker,company_name
--1,"1,652,044",GOOG,Alphabet Inc.
--2,"1,652,044",GOOGL,Alphabet Inc.

-- ============================================================================
-- SEARCH: Find Google/Alphabet in corpus (all possible representations)
-- ============================================================================

SELECT DISTINCT
    CAST(cik AS INTEGER) as cik_int,
    LPAD(CAST(cik AS VARCHAR), 10, '0') as cik10,
    name as company_name,
    tickers,
    MIN(CAST(reportDate AS DATE)) as earliest_filing,
    MAX(CAST(reportDate AS DATE)) as latest_filing,
    COUNT(DISTINCT docID) as n_filings,
    COUNT(*) as n_sentences
FROM read_parquet(parquet_path())
WHERE 
    -- Search by CIK
    CAST(cik AS INTEGER) = 1652044
    
    -- OR search by company name patterns
    OR UPPER(name) LIKE '%GOOGLE%'
    OR UPPER(name) LIKE '%ALPHABET%'
    
    -- OR search by ticker (if tickers array contains these)
    OR list_contains(tickers, 'GOOGL')
    OR list_contains(tickers, 'GOOG')
    OR list_contains(tickers, 'GOOGLE')
    
GROUP BY cik, name, tickers
ORDER BY latest_filing DESC NULLS LAST;

--# Empty result

-- ============================================================================
-- BROADER SEARCH: Partial matches (relaxed)
-- ============================================================================

SELECT DISTINCT
    CAST(cik AS INTEGER) as cik_int,
    name as company_name,
    tickers,
    MIN(CAST(reportDate AS DATE)) as earliest_filing,
    MAX(CAST(reportDate AS DATE)) as latest_filing,
    COUNT(DISTINCT docID) as n_filings
FROM read_parquet(parquet_path())
WHERE 
    UPPER(name) LIKE '%ALPH%'  -- Catches "Alphabet"
    OR UPPER(name) LIKE '%GOOG%'  -- Catches "Google"
    OR array_to_string(tickers, ',') LIKE '%GOOG%'  -- Search in ticker array
GROUP BY cik, name, tickers
ORDER BY latest_filing DESC NULLS LAST;

--#,cik_int,company_name,tickers,earliest_filing,latest_filing,n_filings
--1,"1,491,829",ALPHA NETWORK ALLIANCE VENTURES INC.,{'ANAV'},2013-12-31 00:00:00.000,2020-12-31 00:00:00.000,7
--2,"855,787",ALPHA ENERGY INC,{'APHE'},2017-12-31 00:00:00.000,2020-12-31 00:00:00.000,4
--3,"884,269",ALPHA PRO TECH LTD,{'APT'},1999-12-31 00:00:00.000,2020-12-31 00:00:00.000,22
--4,"1,818,383","MediaAlpha, Inc.",{'MAX'},2020-12-31 00:00:00.000,2020-12-31 00:00:00.000,1
--5,"1,832,010",Omega Alpha SPAC,{'OMEG'},2020-12-31 00:00:00.000,2020-12-31 00:00:00.000,1
--6,"1,350,653","Alphatec Holdings, Inc.",{'ATEC'},2006-12-31 00:00:00.000,2020-12-31 00:00:00.000,15
--7,"1,398,137","Generation Alpha, Inc.",{'GNAL'},2012-12-31 00:00:00.000,2020-12-31 00:00:00.000,9
--8,"1,387,467",ALPHA & OMEGA SEMICONDUCTOR Ltd,{'AOSL'},2011-06-30 00:00:00.000,2020-06-30 00:00:00.000,10
--9,"1,037,038",RALPH LAUREN CORP,{'RL'},1998-03-28 00:00:00.000,2020-03-28 00:00:00.000,21
--10,"1,616,736",Alpha Investment Inc.,{'ALPC'},2019-12-31 00:00:00.000,2019-12-31 00:00:00.000,1
--11,"1,023,298",alpha-En Corp,{'ALPE'},2008-12-31 00:00:00.000,2018-12-31 00:00:00.000,10





SELECT DISTINCT
    CAST(cik AS INTEGER) as cik_int,
    name as company_name,
    tickers,
    MIN(CAST(reportDate AS DATE)) as earliest_filing,
    MAX(CAST(reportDate AS DATE)) as latest_filing,
    COUNT(DISTINCT docID) as n_filings
FROM read_parquet(parquet_path())
WHERE 
    UPPER(name) LIKE '%APPLE%'  -- Catches "Alphabet"
    OR array_to_string(tickers, ',') LIKE '%AAPL%'  -- Search in ticker array
GROUP BY cik, name, tickers
ORDER BY latest_filing DESC NULLS LAST;



-- ============================================================================
-- CHECK: Is CIK 1652044 in corpus at all?
-- ============================================================================

SELECT 
    COUNT(*) as total_sentences,
    COUNT(DISTINCT docID) as n_filings,
    MIN(YEAR(CAST(reportDate AS DATE))) as earliest_year,
    MAX(YEAR(CAST(reportDate AS DATE))) as latest_year,
    list(DISTINCT YEAR(CAST(reportDate AS DATE)) ORDER BY YEAR(CAST(reportDate AS DATE))) as years_present
FROM read_parquet(parquet_path())
WHERE CAST(cik AS INTEGER) = 1652044;
--
--#,total_sentences,n_filings,earliest_year,latest_year,years_present
--1,0,0,[NULL],[NULL],NULL

-- ============================================================================
-- SANITY CHECK: What are the largest tech companies by sentence count?
-- ============================================================================

SELECT 
    CAST(cik AS INTEGER) as cik_int,
    name as company_name,
    tickers,
    COUNT(*) as n_sentences,
    COUNT(DISTINCT docID) as n_filings
FROM read_parquet(parquet_path())
WHERE 
    UPPER(name) LIKE '%MICROSOFT%'
    OR UPPER(name) LIKE '%APPLE%'
    OR UPPER(name) LIKE '%AMAZON%'
    OR UPPER(name) LIKE '%GOOGLE%'
    OR UPPER(name) LIKE '%ALPHABET%'
    OR UPPER(name) LIKE '%META%'
    OR UPPER(name) LIKE '%FACEBOOK%'
    OR UPPER(name) LIKE '%NVIDIA%'
GROUP BY cik, name, tickers
ORDER BY n_sentences DESC;


--#,cik_int,company_name,tickers,n_sentences,n_filings
--1,"789,019",MICROSOFT CORP,{'MSFT'},"33,445",27
--2,"320,193",Apple Inc.,{'AAPL'},"32,911",25
--3,"1,045,810",NVIDIA CORP,{'NVDA'},"30,983",19
--4,"22,444",COMMERCIAL METALS Co,{'CMC'},"30,867",24
--5,"1,141,240",LIQUIDMETAL TECHNOLOGIES INC,{'LQMT'},"30,453",19
--6,"55,242",KENNAMETAL INC,{'KMT'},"22,241",20
--7,"1,018,724",AMAZON COM INC,{'AMZN'},"20,287",21
--8,"22,701",Pineapple Energy Inc.,{'PEGY'},"20,247",26
--9,"63,330",MAUI LAND & PINEAPPLE CO INC,{'MLP'},"18,371",24
--10,"1,543,418",Trilogy Metals Inc.,{'TMQ'},"16,826",9
--11,"1,383,084",INVESCO DB BASE METALS FUND,{'DBB'},"15,299",14
--12,"1,383,057",Invesco DB Precious Metals Fund,{'DBP'},"15,139",14
--13,"1,326,801","Meta Platforms, Inc.",{'META'},"13,032",9
--14,"1,591,588","A-Mark Precious Metals, Inc.",{'AMRK'},"12,658",7
--15,"1,483,386",abrdn Precious Metals Basket ETF Trust,{'GLTR'},"11,985",11
--16,"1,358,654","RED METAL RESOURCES, LTD.",{'RMESF'},"11,296",12
--17,"1,172,178",LIBERTY STAR URANIUM & METALS CORP.,{'LBSR'},"9,023",8
--18,"1,418,121","Apple Hospitality REIT, Inc.",{'APLE'},"8,464",6
--19,"1,156,784","CarbonMeta Technologies, Inc.",{'COWI'},"7,814",8
--20,"1,621,832","Aqua Metals, Inc.",{'AQMS'},"6,018",6
--21,"924,095","Metavesco, Inc.",{'MVCO'},"3,925",6
--22,"1,754,820","Desktop Metal, Inc.",{'DM'},"3,314",2
--23,"1,654,672","PINEAPPLE, INC.",{'PNPL'},"2,981",2
--24,"1,634,379","Metacrine, Inc.",{'MTCR'},"2,129",1
--25,"1,688,487",Metaurus Equity Component Trust,{'IDIV'},"1,443",3
--26,"1,515,139","METAWORKS PLATFORMS, INC.",{'MWRK'},"1,056",1
--27,"1,488,638",American Metals Recovery & Recycling Inc.,{'AMRR'},"1,008",3

