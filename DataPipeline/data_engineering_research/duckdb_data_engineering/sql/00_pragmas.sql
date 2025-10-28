-- ============================================================================
-- Author: Joel Markapudi
-- Date: October, 2025
-- ============================================================================


-- Usually works well if you comment out/not use and let db AUTOPICK resources.

--PRAGMA threads=8;                     -- use CPU cores
--PRAGMA memory_limit='16GB';           -- leave headroom 


PRAGMA enable_object_cache=true;      -- speeds repeated scans

-- for HTTPS/S3 later:
-- INSTALL httpfs; LOAD httpfs;
