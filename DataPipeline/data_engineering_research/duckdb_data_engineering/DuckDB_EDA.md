# FinRAG EDA Results and Narrative from DuckDB - on 71M data sample.

#### Course Project (MLOps IE7374)
#### Author: Joel Markapudi.

1. The 71.8M sentence corpus exhibits **moderate filing-level variance** (p95/median = 1.89x) with **extreme section-level imbalance** (top 3 sections = 52% of corpus). 
2. Temporal coverage shows **strong recency bias** (2020 = 9.4% vs 1993 = 0.13%), suggesting a **stratified sampling strategy with proportional allocation by `CIK × Year × Section`**.
3. We can however choose the concept of year-bins or we can actually obey the recency bias! and choose recent data, because we believe that data from the modern era is quite reliable and strong.


### D2. Grain Cardinalities: Understanding the Stratification Space
```
n_companies: 4,674
n_filings: 55,096  
n_filing_sections: 1,021,030
n_years: 28
n_sentences: 71,866,962

avg_sentences_per_filing: 1,304.4
avg_sentences_per_section: 70.4
avg_sections_per_filing: 18.53
```

**1. Filing-to-Company Ratio: 11.8 filings per company**
- Most companies file annually over the 28-year span (1993-2020)
- 4,674 companies × 28 years = 130,872 theoretical filings
- Actual: 55,096 filings → **42% coverage**
- **Interpretation**: Not all companies exist for full period; IPOs, bankruptcies, mergers create temporal gaps
- **Sampling implication**: Simple random sampling would oversample surviving/mature firms
- Is that too much of a problem? Or is that a true data feature which shows - that strong companies survived?


**2. Section Grain: 1.02M Strata at `CIK × Year × Section`**
- 18.53 sections per filing (out of ~20 possible 10-K sections)
- Not all sections appear in all filings (older filings pre-2007 have different disclosure requirements)
- **1M+ strata is IDEAL for stratified sampling** - granular enough to capture heterogeneity, not so fine-grained that strata become single observations
- Alternatives:
  - `CIK × Year` → 55K strata (too coarse, loses section diversity)
  - `CIK × Year × SentenceID` → 71M strata (absurd, defeats purpose)

**Picking the “grain” (what to balance across)**:
- Business axes to actually evaluate, or which provides the most meaningful insights.
- We use `Company × Year × Filing` → best when we plan to compare across time & issuers.
- Primary grain: company, year (or company, filing_id if available).
- Caps: per-company/year cap so giants don’t dominate.
- Determinism: either hash-based or a fixed seed; log parameters in a small manifest JSON.


**3. Average Section Size: 70.4 sentences**
- **Small** - typical paragraph-level granularity
- RAG chunking implications: ~70 sentences ≈ 1,800 tokens (at 25.8 tokens/sentence from Polars analysis)
- Sections are natural semantic boundaries; breaking them risks losing context
- **Design decision confirmed**: Keep sections intact during sampling, don't fragment !

---

### D3. Filing Size Distribution: Variance Analysis
```
min: 2 sentences
p25: 845 | median: 1,271 | p75: 1,684
p90: 2,112 | p95: 2,402 | max: 8,286
mean: 1,304.4 | stddev: 648.7
p95_to_median_ratio: 1.89x
```

### Distributional Characteristics

**1. Moderate Right Skew (Not Extreme)**
- p95/median = 1.89x indicates **manageable variance** (p95/median > 5x would signal extreme outliers.)
- The 8,286-sentence max filing is only 6.5× median (outlier but not absurd)
- **Interpretation**: Some companies are verbose (complex multinationals, diversified holdings), but not wildly.

**2. Lower Quartile Concern: 845 sentences**
- 25% of filings have <845 sentences (65% of median)
- These are likely:
  - Small-cap firms with simpler operations
  - Shell companies / SPACs
  - Early-stage filers (pre-2000) when disclosure requirements were lighter
- **Risk**: Uniform sampling at filing level over-represents brief, low-information filings
- **Mitigation**: Stratify by section to ensure even small filings contribute proportionally from each disclosure area

**3. Standard Deviation: 649 sentences (50% of mean)**
- Coefficient of variation: 0.50 → **moderate heterogeneity**
- This validates the need for stratification over simple random sampling
- **Statistical note**: With 55K filings, even modest variance compounds across samples

**4. The "Missing Minimum" Problem**
- Min = 2 sentences → likely data quality issue (incomplete scraping, corrupted file)
- **QC checkpoint**: Before sampling, filter filings with <100 sentences as likely incomplete
- Should be <0.1% of filings based on p25, so minimal data loss

---

## S1. Section Distribution: Imbalance 

```
Top 5 sections (52% of corpus):
Section 8:  14.6M sentences (20.4%) - Financial Statements & Supplementary Data
Section 10: 14.2M sentences (19.7%) - Directors, Executive Officers, Governance  
Section 0:  12.2M sentences (17.0%) - Document Header/Metadata
Section 1:  10.9M sentences (15.1%) - Business Description
Section 19:  9.8M sentences (13.6%) - Exhibits

Bottom tier (0.3-1.5% each):
Sections 2,5,7,11,13,16,17: <500K sentences each
```

### Strategic Implications

**1. The "Big 3" Domination: Sections 8, 10, 0**
- **52% of corpus in 3 sections** out of 20 total sections
- Section 8 (Financial Statements): Pure tables, highly structured
  - Likely rich in KPIs but low in semantic narrative
  - Your RAG system needs to handle tabular data extraction here
- Section 0 (Metadata): Document headers, cover pages
  - **Low information density** for business intelligence queries
  - Consider downweighting in sample or filtering entirely
- Section 10 (Governance): Director biographies, compensation tables
  - Moderate relevance for ESG/governance queries, less for financial analysis

**2. The "Narrative Goldmines" - Sections 1, 7, 1A (not in top-5 here)**
- Section 1 (Business): 15.1% - company strategy, products, competitive landscape
- Section 7 (MD&A): **Missing from this top-tier output** → implies it's in the "minor" sections
  - Wait, S2 shows Section 7 avg=8.1 sentences per filing → it's in the bottom tier!
  - **MD&A in bottom tier is ALARMING** - this section contains forward-looking statements, management commentary, and KPI context
  - Likely mislabeled or parsed incorrectly in the dataset
- **Action item**: Verify section numbering against SEC EDGAR documentation

**3. Coverage Uniformity: 42K-54K filings per section**
- Most sections appear in ~95-98% of filings (52-54K out of 55K)
- Exceptions:
  - Section 1: 42,729 filings (77.5%) - older filings may lack Item 1
  - Section 2: 41,605 filings (75.5%) - properties section (optional for non-RE firms)
- **Sampling design**: Can't assume all sections present in all filings; stratification must handle sparse strata

**4. Avg Sentences Per Filing (rightmost column)**
- Section 8: 269.7 avg → massive tabular blocks
- Section 10: 260.7 avg → lengthy governance disclosures
- Sections 2, 5, 11, 13: 4-5 sentences avg → **trivial content**
- **Implication**: Proportional allocation will give you **tons** of financial tables and governance text, **minimal** representation of properties, legal proceedings, etc.
- **Decision point**: Accept this imbalance (reflects actual 10-K structure) OR apply ceiling caps per section to force minor section representation

---

## S2. Section × Filing Size Distribution: Variance Within Sections

```
Top variance sections:
Section 10: avg=260.7, median=197, p90=653, max=4,431, stddev=296
Section 19: avg=201.0, median=42,  p90=580, max=4,140, stddev=275
Section 8:  avg=269.7, median=250, p90=508, max=4,539, stddev=196

Low variance sections:
Section 12: avg=19.0, median=16, p90=32, max=794, stddev=15
Section 16: avg=8.5,  median=4,  p90=20, max=1,287, stddev=14
```

### Deep Dive: Section-Specific Behaviors

**1. Section 10 (Governance): Bimodal Distribution Alert**
- Median=197 but avg=260.7 → **right skew within section**
- p90=653 (3.3× median) vs corpus-wide p90/median=1.9×
- **Explanation**: Proxy statement incorporation by reference
  - Some companies include full governance details (lengthy)
  - Others reference separate DEF-14A filings (brief)
- **Sampling risk**: Simple proportional allocation gives disproportionate weight to governance-heavy filers
- **Mitigation**: Apply **within-section caps** during sampling (e.g., no single filing-section contributes >0.05% of section stratum)

**2. Section 19 (Exhibits): The Median-Mean Divergence**
- **Median=42 but avg=201** → extreme right skew (5× ratio!)
- Most filings have brief exhibit indices
- A few filings attach full exhibit text (contracts, agreements)
- **Outlier**: max=4,140 sentences (20× average)
- **Interpretation**: Exhibit inclusion varies widely by filing agent and company policy
- **Sampling strategy**: This section needs **log-transform or quantile-based sampling** to avoid outlier dominance

**3. Sections 12, 16, 17: Consistent Brevity**
- Stddev < mean → low variance
- Section 12 (Security Ownership): avg=19, median=16 → stable table size
- Section 16 (Form 10-K Summary): avg=8.5, median=4 → optional section, usually minimal
- **Implication**: These sections contribute stable, predictable amounts to sample; no special handling needed

**4. Section 8 (Financial Statements): Surprisingly Stable**
- Despite being largest section, stddev=196 (73% of mean) is **lower than Section 10's CV**
- Financial tables have standardized formats (GAAP requirements)
- Variance driven by:
  - Number of subsidiaries (consolidated vs standalone)
  - Footnote detail (complex instruments, leases, pensions)
- **Design note**: Financial statement sections are good "anchors" for stratified sampling due to consistency

---

## D4. Temporal Distribution: The Recency Bias

```
1993: 96K sentences   (0.13%) | 171 companies
2002: 1.3M sentences  (1.87%) | 1,392 companies  [Sarbanes-Oxley inflection]
2010: 3.2M sentences  (4.41%) | 2,463 companies
2020: 6.7M sentences  (9.36%) | 4,259 companies  [Peak year]

Growth pattern:
1993-2001: Slow growth (0.13% → 1.01% per year)
2002-2010: Accelerating (1.87% → 4.41%)
2010-2020: Linear growth (4.41% → 9.36%)
```

### Temporal Dynamics

**1. The 2002 Inflection: Sarbanes-Oxley Act**
- 2001: 727K sentences (1.01%)
- 2002: 1.35M sentences (1.87%) → **85% jump**
- Post-Enron regulatory response:
  - Enhanced MD&A disclosure requirements (Section 7)
  - Internal controls narrative (Section 9A)
  - Executive certification boilerplate (Section 13)
- **Data archaeology note**: Pre-2002 filings are structurally different; may need separate treatment in LLM fine-tuning

**2. Recency Bias: 2020 is 72× Larger Than 1993**
- Latest year contributes **9.4%** of entire corpus vs earliest year's **0.13%**
- Simple random sampling → 72:1 overrepresentation of recent filings
- **Why this matters for FinRAG**:
  - User queries span all periods: "Tesla's 2015 revenue" shouldn't be harder to answer than "Tesla's 2020 revenue"
  - Macroeconomic context varies: dot-com era vs 2008 crisis vs COVID → model needs temporal diversity
- **Mitigation**: Stratify by **year bins** with forced representation
  - 1993-2001: "early" (4.5% of corpus)
  - 2002-2009: "SOX era" (22.0%)
  - 2010-2015: "post-crisis" (31.5%)
  - 2016-2020: "modern" (42.0%)
  - Sample proportionally within bins, but ensure each bin meets a **minimum threshold** (e.g., ≥10% of final sample)

**3. Company Coverage Growth: 171 → 4,259 (25× increase)**
- Not all companies in 1993 still exist in 2020 (survivorship bias)
- New entrants (tech IPOs, SPACs) skew toward recent years
- **Sampling challenge**: Stratifying by `CIK × Year` produces sparse strata for early years
  - Many CIKs have only 1-3 filings in 1993-2000
  - Risk of **singleton strata** (stratum with n=1) → can't sample fractions
- **Possible Solution**: **Collapse rare CIKs** into "other" category for early periods, OR use **minimum stratum size threshold** (e.g., strata with <10 sentences get pooled)
- (This wont be implemented. Collapsing multiple-company CIKs into "other" is not good for a narrative finQA system.)


---

### Temporary Analysis
### Stratification Grain: `CIK × Year-Bin × Section`
- Balances temporal diversity (4 bins) with stratum size (avg 255K strata per bin)
- Aligns with regulatory regime changes (2002 SOX, 2010 Dodd-Frank)

**Bins** for years:
1. `1993-2001`: Pre-SOX (9 years, ~4.5% corpus)
2. `2002-2009`: SOX Era (8 years, ~22% corpus)  
3. `2010-2015`: Post-Crisis (6 years, ~31.5% corpus)
4. `2016-2020`: Modern (5 years, ~42% corpus)
**Resulting strata**: 4,674 CIKs × 4 bins × ~18 sections = **~337K strata** 

---

### Section Study:
- Section 8 (20.4% of corpus) → 20.4% of 1M sample = 204K sentences
- Sections with <1% corpus share (e.g., Section 11, 0.35%) get **floor of 0.5%** (5K sentences)
- Ensures non-zero representation for all 20 sections
- No single `docID-section` contributes >0.1% of sample (1K sentences for 1M sample) ?? - Is this idea good?

---

## Critical Open Questions
1. **Section 7 (MD&A) Mislabeling**: This section should be high-volume but appears in bottom tier. Verify against SEC EDGAR's section numbering.
2. **Section 0 (Metadata) Inclusion**: Does Section 0 add value for RAG, or should it be excluded as boilerplate?


### Important EDA about khainhernlow/financial-reports-sec dataset:

The khaihernlow/financial-reports-sec dataset, derived from the EDGAR-CORPUS project (Loukas et al., 2021), contains 4,674 companies with 71.8M sentences spanning 1993-2020. While the source paper claims coverage of "all publicly traded companies," empirical analysis reveals selective coverage:

  Confirmed present: Microsoft, Apple, Amazon, NVIDIA, Meta/Facebook
  Confirmed absent: Alphabet/Google (CIK 1652044), Verizon Communications (CIK 732712), and 87 other S&P 500 constituents
  For example, a few missing companies represent ~13% of the current S&P 500 index (89 of 503 constituents as of October 2025) - based on SPDR daily holdings.


## Argument 1: Recency Bias is Actually Good
## Argument 2: Temporal, Sentence, Section Imbalances shouldnt be corrected in the dataset.

- Temporal relevance: Users care about recent data (2016-2020), not 1993 data
- Section imbalance is fine: RAG should be robust to varying document lengths naturally
- Sentence density shouldn't matter: The retrieval system should fetch relevant chunks regardless of how many chunks a company has
- Variations in densities of time, sentences, filings etc. - these are real world reflections of how a company or entity decides to disclose information.
- We must not try to "correct" these real world distributions, but rather make the algorithm robust. 

1. Product is a RAG system, not a time-series model
    - If someone asks "What was Apple's revenue in 1995?", they'll:
        - Get the closest available (2016 data) with a caveat.
        - Get no results (acceptable for a demo - "Data not available for that period")

2. 80/20 rule
    - 80% of queries will be about recent years (2016-2020)
    - Strategy: Possibly sample 90% from 2016-2020, 10% from 2010-2015 for edge cases
    - Spending budget on expensive chunking and embedding for pre-2010 data is wasteful? 

3. Compute economics
    - 2016-2020: 35M sentences (based on D4: 2016-2020 = 27.6M + 2010-2015 = 27M total)
    - HALF the corpus
    - Better representation of the period users actually care about.

4. Structured + Narrative RAG Point. 
    - Metadata-first filtering (CIK, year, section) → then semantic search
    - NOT pure vector search across undifferentiated corpus
    - Section Density becomes irrelevant.

**Firmly, excessive fixes on statistical rigor distorts true reality.**
If Company A writes 5 paragraphs on supply chain risks and Company B writes 1 sentence, it means Company A is more transparent, more detailed, and more likely to be result of queries. Despite the EDA, Query scope is pre-filtered, LLM context window is fixed, Retrieval is similarity-based. Vector DBs don’t “prefer” bigger issuers; they retrieve highest-similarity chunks. Bias might appear when many similar chunks from one source crowd the top-k.


### Quick Insights:
Array of objects [{...}, {...}] → read_json() with format='auto' works directly
Object of objects {"0": {...}, "1": {...}} → Need json_each() to iterate over keys
read_json(): Auto-parses JSON → DuckDB STRUCT (can't be re-fed to JSON functions)
read_text(): Keeps raw string → Can pass to json_each(), json_extract(), etc.
-> : Returns JSON object (for chaining)
->> : Returns text/string (for final extraction)

```
WITH raw_json AS (SELECT content FROM read_text('file.json'))
SELECT 
    kv.value->>'field1' as col1,
    kv.value->>'field2' as col2
FROM raw_json, json_each(raw_json.content) as kv;
```
Don't fight DuckDB's auto-parsing - work with raw strings. !!


### Initialization and Connection Details:
1. Connection name: This is only a label in DBeaver.
2. Username / Password: leave blank. (no server, no auth).
3. Connection type: optional. 
4. Read-only connection: leave unchecked unless we want to prevent any writes from the UI.
5. Navigator view / Connection folder: optional—organizes how it appears in DBeaver.

### DuckDB Schemas:
**main** → default, persistent schema.
    Create tables/views/macros here unless you choose otherwise.
**temp** → session-temporary objects (disappear when you disconnect).
    Good for scratch tables, staging results, etc.
**system** → read-only internal catalog (functions, types, pragma views).
    don’t create objects here.
can create new schema if needed, to keep things organized.
