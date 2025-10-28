# Sampling Strategy - S&P 500 Data + Weighted Multi-Objective Sampling Score.
#### Author: Joel Markapudi.

## Data Sources Acquired

**1. S&P 500 Holdings Data**
- Source: State Street SPDR SPY ETF Daily Holdings (as of Oct 15, 2025)
- File: `SNP_15OCT_SPY_DAILYHOLD.xlsx`
- URL: State Street SPDR website (official fund holdings)
- Records: 503 holdings, 99.94% weight coverage
- Format: Excel with metadata rows (Fund Name, Ticker Symbol, Holdings date in rows 1-3)

**2. SEC Company Identifier Mapping**
- Source: SEC EDGAR official company tickers JSON
- File: `sec_company_tickers.json`
- URL: `https://www.sec.gov/files/company_tickers.json`
- Records: 10,142 companies with CIK-to-ticker mappings

- Quick Read: Please read `## Argument 1: Recency Bias is Actually Good, ## Argument 2: Temporal, Sentence, Section Imbalances shouldnt be corrected in the dataset.` from the `DuckDB_EDA_LargeData.md` file for context on strategy rationale.

**3. To-Choose 200 extra high-value Companies**
- Source: Custom selection based on sector diversity, underrepresented industries, etc.
- Purpose: Enhance dataset representativeness beyond S&P 500

**4. Strategy Explanation - Company Selection**
- Combine S&P 500 companies and 50-200 specially selected firms. (Ideally, non S&P but overlap happens.)
- They are chosen on weighted multi-objective sampling score ( `quality_score` ), potential risky companies and over-bloated text filing companies might be excluded, a curated list of hidden gem-companies are added.
- Revised Target: ~550 companies.
- Choosing 650 or 600 companies still resulted in a sentence-count sample over 6.5 million. So we wish to refine it.
- As of Oct 16, 2025, Total distinct companies chosen: 540
- As of Oct 17, 2025, companies chosen were 75: Eventually, I intentionally merged two selection criteria: market capitalization (S&P 500) and disclosure quality (notable companies). 73 overlapping companies represented high-value entities that meet BOTH criteria. This overlap validates the **quality scoring model.** The final deduplication step - was used to remove duplicates, standard practice in master data management to ensure uniqueness.

- As of Oct 20, 2025, companies chosen were 21: Further refined to top 21 companies. We included a **new data ingestion** pipeline and concept for dynamic N-company selection (can be reused). 
- The justification: we wanted to include latest era bin (2021-2024) and we aim for an estimation of 600k-800k sentences. We realize that the cost of expensive chunking and embedding generation is so high, even for 50k sentences - our local GPUs couldnt handle it. We hope to reduce dataset potentially (and need-based).

------------------------------------------------------------------------------------------------------------------------

## Temporal Sampling Strategy

**Analysis Framework**: Evaluated corpus across three regulatory/economic eras
- **2006-2009 (SOX Era)**: Pre-financial crisis, Sarbanes-Oxley compliance period
- **2010-2015 (Post-Crisis)**: Post-Dodd-Frank implementation, new disclosure regimes
- **2016-2020 (Modern Era)**: Current disclosure standards, most user-relevant period

**Potential Sampling Weights** (A/B/C split):
- Example:
    - 2006-2009: 15% of sample (includes 2008 financial crisis event coverage)
    - 2010-2015: 20% of sample (regulatory transition period)
    - 2016-2020: 65% of sample (recency bias for product relevance)

**Finalized Logic - adapts based on data reality**:
- Take Took 100% of modern bin (2016-2020) → 654K sentences (rough estimate for N companies).
- Split Leftover = 346K, Split 60/40 → bin2, bin1. 
- Instead of clean target percentages we use an Total/60/40 split for older bins and adaptive allocation of budget.


**Rationale**: 
- Targets recent financial queries (user interest skewed to 2016-2020)
- Retained pre-2016 data for potential temporal analysis capabilities in the future("how has X evolved since 2010?")
- 14-year window (2006-2020) balances coverage vs computational efficiency.
- Real-world analog: Bloomberg Terminal doesn't index every public company equally. (Need - High market cap, High trading volume, Historical Importance, Recent Importance, User, Analyst, Company Interests, Third Party Interests, Foreign Interests, Financial Analyst Coverage.)
- **Strong companies write better 10-Ks.** 
- Tier 3: "Recent IPOs with Momentum", Tier 2: "Industry Diversity" ( Biotech, Energy, Real Estate, Transport, Retail). 
- Tier 1: ( Tech, Finance, Consumer, etc.)

------------------------------------------------------------------------------------------------------------------------

### Weighted Multi-Objective Sampling Score Explanation:
- The explanation for the formula, it depends on these chosen elements or stable flags:
    - 80% coverage of sections, Diversity in talk, Substantive content, 'Not minimum compliance',
    - Substance Filter - Raw content volume across all filings, 
    - Recency Relevance Filter - Active in Modern Era, Priority section sentences - giving **intentional information density bias.**


### Scoring Formula (With potential relaxing limits):

`quality_score = (filing_years * 5) + (section_coverage * 10) + (recent_sentences / 100) + (priority_section_sentences / 50)`

```
And, the chained-CTE query also includes these filters:

HAVING 
    filing_years >= 5           -- Temporal consistency
    AND section_coverage >= 16  -- Disclosure comprehensiveness
    AND total_sentences >= 8000 -- Content volume
    AND latest_filing_year >= 2018  -- Recency relevance
    AND priority_section_sentences >= 3000  -- Information density
```
- These filters determine WHO is in the dataset, not WHAT gets sampled.

### Initial Results of Scoring:
- Elite: 1,783 → 1,050 points, companies are Elite 50.
    - ( Heavily regulated industries → verbose 10-Ks → rich disclosure, Recognizable Brands.. )
- Balanced Middle: 1,050 → 875 points.
    - Tech and Software, Healthcare, Pharma, Consumer, Retail, Industrial, Materials, etc. Has good brand recognition value across the world and also strong diversity. For example, FMC, Humana, United Therapeutics, Adobe, Intuit, Electronic Arts, etc.
- 150-300 Comps: 875 → 796 points
    - Regional banks and representation of small cap banks, declining struggling companies, companies with long history but very low sentences, subprime mortgage, controversial companies, Reputational risk companies, messy disclosure companies, gambling industry, etc.

------------------------------------------------------------------------------------------------------------------------

### Post-Sampling:
- Each stratum's allocation is rounded to nearest integer.
- Example: Stratum with 8 sentences, 25.47% rate → 8 × 0.2547 = 2.04 → rounds to 2
- Accumulated across 15,000 strata: +2,000-2,500 sentences.
    ```sql
    GREATEST(1, CAST(ROUND(stratum_size * rate) AS INTEGER))
    ```
- ~0.35% or 1% overage. Total sentences will be 1.003 or 1.005M instead of 1M. Negligible impact. 

