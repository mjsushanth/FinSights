/* 
 * Study Related - RCA notepad based on many issues faced. Esp with dynamic DDL / parameterization.
 * 
 * --------------------------------------------------------------------------------------------------------------------
Layer 1: Client-Side Preprocessing (DBeaver, psql, etc.)
What happens: Client tool does string substitution BEFORE sending SQL to database

@set table_name = 'my_table'
DROP TABLE ${table_name};  -- Client replaces ${table_name} → 'my_table'
❌ No runtime logic (can't compute values in SQL)
❌ Client-specific (DBeaver ${var}, psql :var, different tools vary)
------------------------------------------------------------------------------------------------------------------------
Layer 2: Database Session Variables (DuckDB SET VARIABLE)
What happens: Database stores variable values, can be used in data queries only

SET VARIABLE my_value = 42;
SELECT * FROM table WHERE id = getvariable('my_value');  -- Works in WHERE/SELECT
❌ Cannot use in DDL (table/column names)
❌ Limited to data plane (SELECT, WHERE, etc.)
------------------------------------------------------------------------------------------------------------------------
Layer 3: Prepared Statements (DuckDB PREPARE)
What happens: Database pre-compiles SQL with placeholders for data values only

PREPARE my_query AS
    SELECT * FROM users WHERE id = ?;
EXECUTE my_query(42);  -- Substitutes ? → 42 
✅ SQL injection protection (values are escaped)
✅ Performance (query plan cached)
❌ Only for data values, not identifiers (table/column names)
❌ Cannot use in DDL structure
------------------------------------------------------------------------------------------------------------------------
Layer 4: Dynamic SQL String Execution (Most databases)
What happens: Database executes SQL from a string variable at runtime
No EXECUTE IMMEDIATE or sp_executesql equivalent
------------------------------------------------------------------------------------------------------------------------ */


1. **What SQL can be parameterized vs. what cannot.**
2. **What DuckDB itself supports vs. what DBeaver’s JDBC parser lets through.**

a quick “map” of parameterization styles, then exactly why `DROP …` attempts fail, and three reliable ways to do it going forward.

---

# 1) Parameterization styles — what they’re for

## A) **SQL variables** (DuckDB engine)

* Define: `SET VARIABLE mypath = 'D:/.../file.parquet';`
* Use in expressions: `SELECT getvariable('mypath');`
* **Limit**: variables are **values**, not **identifiers**. You can’t use them where SQL expects a *table name* or *column name*. Many DDL positions (e.g., `COPY … TO`, `DROP TABLE …`) are picky: the parser wants a literal/identifier, not a runtime expression.

## B) **Macros** (DuckDB engine)

* Define: `CREATE OR REPLACE MACRO export_dir() AS 'D:/.../exports';`
* Use inline: `SELECT export_dir() || '/x.parquet';`
* **Limit**: like variables, macros produce **values** that are substituted in expressions. They can’t safely produce **identifiers**. Some DDL positions still require a literal/identifier.

## C) **Prepared statements with placeholders** (DuckDB + JDBC)

* `PREPARE q AS COPY mytab TO ? (FORMAT PARQUET);`
* `EXECUTE q('D:/.../x.parquet');`
* **Use**: great for **data values**; **not** for identifiers (table/column names). Placeholders (`?`) won’t bind identifiers.

## D) **Dynamic SQL** (string → execute)

* **`EXECUTE IMMEDIATE '<sql text>'`**: executes an SQL string.

  * This is the *right* tool for **dynamic identifiers** (e.g., table names).
  * **Caveat**: Some GUI clients (including certain DBeaver/JDBC builds) don’t accept `EXECUTE IMMEDIATE` even though the engine does; they pre-parse and reject it before sending.
* If  client blocks it, the alternative is to run the dynamic step via the **DuckDB CLI** or make the client do **text substitution** before sending SQL.

## E) **Client-side substitution** (DBeaver feature)

* DBeaver can replace `${var}` (or `${schema}.${table}`) **before** SQL is sent to DuckDB.
* **Use**: perfect for identifiers and file paths in picky DDL spots: the server receives a plain literal/identifier.

---

# 2) Why DROP attempts error out

Tried:

```sql
EXECUTE IMMEDIATE ('DROP TABLE IF EXISTS sampler.main.finrag_tgt_comps_' || getvariable('total_companies'));
```

and

```sql
SET VARIABLE drop_table_sql = 'DROP TABLE IF EXISTS sampler.main.' || getvariable('target_table_name');
EXECUTE IMMEDIATE getvariable('drop_table_sql');
```

**Root causes:**

* **Identifiers ≠ values.** `DROP TABLE …` requires an **identifier**; `getvariable(...)` gives a **value** (string). In most SQL engines you need **dynamic SQL** to bridge that (which you tried).
* **Client parser**: DBeaver’s DuckDB JDBC often **does not accept** `EXECUTE IMMEDIATE …` and fails *before* the SQL reaches DuckDB. That’s why it looks like “syntax error at EXECUTE…” or at the expression. (Same story you hit with `COPY … TO (…)`.)

---

# 3) Three reliable fixes (pick one)

## Option 1 — **Use DBeaver variables** (client-side substitution) ✅

Let DBeaver turn  variables into **literal identifiers** before the SQL is sent.

1. Define a DBeaver variable `target_table_name` (via the connection’s Variables UI or `:set` in the editor, depending on  setup).
2. Use it in SQL:

```sql
-- DBeaver will substitute ${target_table_name} -> finrag_tgt_comps_700
DROP TABLE IF EXISTS sampler.main.${target_table_name};
```

**Why it works:** the server sees a plain identifier; no dynamic SQL in-engine, no JDBC quirks.

> Tip: Same trick works for file paths in `COPY … TO`, e.g.,
> `COPY sample_1m_finrag TO '${export_dir}/sec_finrag_1M.parquet' (FORMAT PARQUET);`

## Option 2 — **Use PREPARE for values; avoid dynamic identifiers** ✅

If you can avoid changing the table name dynamically (recommended), keep a **fixed table name** and put run metadata in a **column** (e.g., `run_id = 700`). Then:

```sql
-- Safe: table name is fixed literal; parameterize only values
PREPARE drop_run AS DELETE FROM sampler.main.finrag_tgt_comps WHERE run_id = ?;
EXECUTE drop_run(700);
```

**Why it works:** placeholders are supported for values; you never need dynamic identifiers or `EXECUTE IMMEDIATE`.

## Option 3 — **Run EXECUTE IMMEDIATE in DuckDB CLI** (engine-side dynamic SQL) ✅

If you **must** vary the table name:

```sql
-- In DuckDB CLI (or any client that supports EXECUTE IMMEDIATE):
SET VARIABLE target_table_name = 'finrag_tgt_comps_700';
EXECUTE IMMEDIATE 'DROP TABLE IF EXISTS sampler.main.' || getvariable('target_table_name');
```

**Why it works:** the CLI doesn’t pre-parse; the engine executes the dynamic string. In DBeaver/JDBC, this may still fail due to client-side parsing.

---

# 4) Recommended style & patterns (so you don’t fight the client)

* **Prefer fixed object names**; put run-specific context into **columns** (`run_id`, `era`, `k_companies`, etc.). It makes  pipelines repeatable and removes the need for dynamic DDL.
* When you truly need dynamic names/paths inside **DDL**:

  * In **DBeaver**: use **client variables** `${var}` for identifiers/paths.
  * In pure DuckDB sessions (CLI): use **`EXECUTE IMMEDIATE`** for dynamic strings.
* Use **prepared statements (`?`)** for **data** parameters (filters, values in `INSERT/UPDATE/DELETE`), not identifiers.
* Keep **macros/variables** for **expressions inside SELECTs** and for **logging**, not for DDL identifier slots.


```sql
DROP TABLE IF EXISTS sampler.main.${target_table_name};
SELECT 'Old table dropped (if existed)' AS status;
```

-- ============================================================================
-- ============================================================================

/*
 * NOT FOR EXECUTION.
 * 
 * NOT FOR EXECUTION.
 * 
 * THIS CODE - is just a study sample purpose code, which actually works.
 * 
 * NOT FOR EXECUTION.
 * 
 * NOT FOR EXECUTION.
 */

-- ============================================================================
-- ============================================================================



-- ============================================================================
-- DYNAMIC N-COMPANY TABLE CREATION (DuckDB Variables - One-Shot Execution)
-- pattern with getvariable() approach
-- ============================================================================
-- ──────────────────────────────────────────────────────────────────────────
-- PARAMETERS (User configures ONLY these 3 values)
-- ──────────────────────────────────────────────────────────────────────────

SET VARIABLE n_snp_companies = 25;
SET VARIABLE n_quality_companies = 15;
SET VARIABLE include_google = 1;  -- 1 = true, 0 = false

-- Auto-calculate derived values
SET VARIABLE total_companies = (
    getvariable('n_snp_companies') + 
    getvariable('n_quality_companies') + 
    getvariable('include_google')
);

SET VARIABLE table_suffix = CAST(getvariable('total_companies') AS VARCHAR);
SET VARIABLE version_string = 'v2.0_prod_' || getvariable('table_suffix') || 'companies';

SELECT 
    '═══ CONFIGURATION ═══' as step,
    getvariable('n_snp_companies') as snp_count,
    getvariable('n_quality_companies') as quality_count,
    getvariable('include_google') as google_included,
    getvariable('total_companies') as total_companies,
    'finrag_tgt_comps_' || getvariable('table_suffix') as target_table_name;


-- ──────────────────────────────────────────────────────────────────────────
-- CREATE TABLE (using temp table pattern, then copy to final)
-- ──────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE TEMP TABLE temp_dynamic_companies AS
WITH google_company AS (
    SELECT 
        1652044 as cik_int,
        '0001652044' as cik,
        'Alphabet Inc.' as company_name,
        'GOOGL' as ticker,
        'MANUAL' as source,
        'TIER_PRIORITY' as tier,
        999999.0 as quality_score,
        'GOOGLE_MANDATORY_MANUAL' as selection_source,
        0 as rank_within_group
    WHERE getvariable('include_google') = 1
),

snp_ranked AS (
    SELECT 
        cik_int,
        cik,
        company_name,
        ticker,
        source,
        tier,
        weight_pct * 1000 as quality_score,
        'SNP500_TOP' || CAST(getvariable('n_snp_companies') AS VARCHAR) as selection_source,
        ROW_NUMBER() OVER (ORDER BY weight_pct DESC) as rank_within_group
    FROM sampler.main.finrag_tgt_comps_75
    WHERE TRIM(UPPER(source)) = 'SP500'
      AND cik_int != 1652044
),

quality_ranked AS (
    SELECT 
        cik_int,
        cik,
        company_name,
        ticker,
        source,
        tier,
        quality_score,
        'QUALITY_TOP' || CAST(getvariable('n_quality_companies') AS VARCHAR) as selection_source,
        ROW_NUMBER() OVER (ORDER BY quality_score DESC, cik_int) as rank_within_group
    FROM sampler.main.finrag_tgt_comps_75
    WHERE TRIM(UPPER(source)) != 'SP500'
      AND cik_int != 1652044
)

SELECT 
    ROW_NUMBER() OVER (ORDER BY 
        CASE 
            WHEN selection_source LIKE 'GOOGLE%' THEN 1 
            WHEN selection_source LIKE 'SNP500%' THEN 2 
            WHEN selection_source LIKE 'QUALITY%' THEN 3 
        END,
        rank_within_group
    ) as company_id,
    cik_int,
    cik,
    company_name,
    ticker,
    source,
    tier,
    quality_score,
    selection_source,
    rank_within_group,
    CURRENT_TIMESTAMP as selected_at,
    getvariable('version_string') as version
FROM (
    SELECT * FROM google_company
    UNION ALL
    SELECT * FROM snp_ranked 
    WHERE rank_within_group <= getvariable('n_snp_companies')
    UNION ALL
    SELECT * FROM quality_ranked 
    WHERE rank_within_group <= getvariable('n_quality_companies')
)
ORDER BY company_id;

SELECT '✓ Temp table created with ' || COUNT(*) || ' companies' as status
FROM temp_dynamic_companies;


-- ──────────────────────────────────────────────────────────────────────────
SELECT * FROM temp_dynamic_companies;
-- ──────────────────────────────────────────────────────────────────────────

-- ──────────────────────────────────────────────────────────────────────────
-- COPY TO FINAL TABLE (Manual execution for specific N)
-- User must uncomment the line corresponding to their total_companies value
-- ──────────────────────────────────────────────────────────────────────────

-- For 21 companies (15 SNP + 5 Quality + 1 Google):
-- CREATE OR REPLACE TABLE sampler.main.finrag_tgt_comps_21 AS SELECT * FROM temp_dynamic_companies;


-- For 51 companies (50 SNP + 0 Quality + 1 Google):
-- CREATE OR REPLACE TABLE sampler.main.finrag_tgt_comps_51 AS SELECT * FROM temp_dynamic_companies;

CREATE OR REPLACE TABLE sampler.main.finrag_tgt_comps_51 AS SELECT * FROM temp_dynamic_companies;


-- ============================================================================
-- VALIDATION 1: Count by Selection Source
-- ============================================================================

SELECT 
    '1. SELECTION BREAKDOWN' as check_type,
    selection_source,
    COUNT(*) as n_companies,
    ROUND(AVG(quality_score), 1) as avg_quality
FROM temp_dynamic_companies
GROUP BY selection_source
ORDER BY CASE 
    WHEN selection_source LIKE 'GOOGLE%' THEN 1 
    WHEN selection_source LIKE 'SNP500%' THEN 2 
    ELSE 3 
END;


-- ============================================================================
-- VALIDATION 2: Total Count & Uniqueness Check
-- ============================================================================

SELECT 
    '2. FINAL VERIFICATION' as check_type,
    COUNT(*) as total_companies,
    COUNT(DISTINCT cik_int) as unique_ciks,
    getvariable('total_companies') as expected_count,
    CASE 
        WHEN COUNT(*) = getvariable('total_companies') 
         AND COUNT(DISTINCT cik_int) = getvariable('total_companies')
        THEN '✓ Perfect - All parameters met'
        ELSE '⚠️ Count mismatch'
    END as status
FROM temp_dynamic_companies;



















