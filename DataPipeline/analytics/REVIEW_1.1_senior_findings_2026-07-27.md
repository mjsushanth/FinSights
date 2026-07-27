# Senior Review 1.1 — src_metrics / edgartools KPI rebuild

**Date:** 2026-07-27
**Scope:** Senior review of the src_metrics rebuild and the edgartools sentence/KPI
expansion work (roster 21 -> 25 companies). Focus per request: how complex logic was
translated/re-executed, how data behavior was studied, how the analytics were done, and
how the plans were translated — not a line-by-line audit, not file movement/refactor
noise.

---

## Bottom line
The work is dependable and the heavy lifting is sound — the edgartools port reproduces
the original logic faithfully (margins across companies are realistic: Apple 26.9%,
MSFT 36.1%, Amazon 9.3%), the coverage-guard rewrite is genuinely correct, and the
sentence-side duplicate analysis was rigorous. **One real bug and two concrete data gaps
survived, all clustered in the same spot: KPI statement-label routing.** Nothing
structural is broken.

## 1. Real bug — the `OperatingIncome` alias fix landed in dead code
`derived_kpis.py`: the dict entry `STATEMENT_LABEL_ALIASES["OperatingIncome"]` is
**never read** (grep-confirmed — only Revenue / NetIncome / Assets / Equity /
CurrentAssets / CurrentLiabilities / Inventory / CFO / CapEx are consumed). Operating
income is computed by `compute_operating_income()` (line 169), which uses its own
**hardcoded** tier-1/2/3 lists.

When the domain review found UnitedHealth / Caterpillar missing Operating Margin %,
the fix added `"Earnings from operations"`, `"Operating profit"`,
`"Total income before income taxes"` to the *dict* — a list that function never
consults. So the fix did nothing, and the final output *still showed those two missing* —
which was read as an accepted residual rather than a failed fix.

Data confirms it exactly: Operating Margin % is present for Northrop / T-Mobile
(standard "Operating income" label -> tier-1 match) and **missing for all years** for
UnitedHealth and Caterpillar. The fix is trivial and the right strings were already
written — they just belong in `compute_operating_income`'s tier-1 list
(`"Operating profit"`, `"Earnings from operations"`) and tier-2
(`"Total income before income taxes"`), not the dead dict.

## 2. J&J revenue label — seen during debugging, not fixed
J&J's current filings label revenue `"Sales to customers"`, which isn't aliased. Result:
J&J's **2025 margins silently don't compute** (Net Profit Margin % / Operating Margin %
present only for [2023, 2024]; Current Ratio, which needs no revenue, present for
[2023, 2024, **2025**]). `"Sales to customers"` was actually *seen* in the Run-2
diagnostic but only the UnitedHealth / Caterpillar wordings were added. It's masked from
the guard because 2025 is a new year and 2023/2024 retain stale prior-run values
(see #4).

## 3. Walmart margin looks wrong
Walmart Net Profit Margin % reads 1.20% (2024) / 1.43% (2025) — roughly **half** its
real ~2.5-2.9%, and inconsistent year-to-year (2020 shows a correct 2.84%) in a way real
margins aren't. Leading suspects: the Revenue path uses `_sum_rows_to_year_series` (SUM,
not first-match), so any company with two revenue-like rows both in the alias list
double-counts the denominator; or NetIncome picking a pre-/post-noncontrolling-interest
row inconsistently across the stacked multi-filing frame. Worth a targeted check — the
SUM-semantics on Revenue is the one place a broad alias addition can silently corrupt an
*existing* company's value.

## 4. Process note (how validation translated)
Two design choices let #1-#3 slip: the **parity test checked only Apple** (all-standard
labels, so it couldn't surface label-routing bugs), and the **merge is non-destructive at
metric grain** — a metric that stops resolving keeps its last-known value forever, so the
count-based guard sees "present->present" and never flags a value going stale. Both are
defensible, but together they mean "0 regressions" doesn't imply "every metric recomputed
correctly."

## Correctly parked (don't lose these)
- Sentence side: fused-sentence bug (a bare page-number breaks a split); 3 older filings
  dropped entirely (edgartools Gotcha 5 — CAT 2016/17, NOC 2010); Category-A boilerplate
  headers left in for embedding-stage filtering. All appropriately noted.
- KPI: T-Mobile Free Cash Flow missing (CapEx label has an embedded dollar figure ->
  exact-match fails; correctly diagnosed as needing a matching-strategy change, not
  another alias).

## Checked and genuinely solid
Coverage guard (`find_regressed_keys`) — correct. `metric_key` nulls — 0.2% (14/7,607),
the earlier worry is a non-issue. Merge anti-join grain — correct and non-destructive.
Sentence dedup — 0 adjacent duplicates remain, Category C preserved. dtype/config bugs
found live were real and properly fixed with regression tests.

## Follow-ups (deferred 2026-07-27) — flagged, not yet fixed
Surfaced while fixing items 1-4; both are out of that scope and left for a separate pass.

**F1. Tesla & Alphabet — multi-year extraction only resolves the latest year.**
`MultiFinancials.extract` stacks several 10-Ks and matches statement rows by label. Tesla's
rows (and Alphabet's duplicate `"Revenues"` rows) drift across filings, so a first-match
returns a single partial-year row. Consequence: Operating Margin % / Net Profit Margin %
resolve only for the latest year for these two companies. This is a structural extraction
limitation, not a label gap — a real fix means per-filing extraction + coalesce, or
de-duplicating/merging duplicate label rows in `compute_core_kpis_for_company`. Note the
apostrophe + operating-income fixes *did* land for the years that resolve (Tesla/Alphabet
Debt-to-Equity + ROE now compute across all years via the equity fix).

**F2. Eli Lilly liabilities read ~2x real → Debt ratios inflated.**
`get_total_liabilities_series` returns ~$106B for Eli Lilly FY2023 versus a real ~$53B, so
Debt-to-Assets reads ~1.5-1.66 and Debt-to-Equity ~6.5-9.9 (both overstated). Pre-existing,
unrelated to the 2026-07-27 label work — in the current+noncurrent summation fallback (likely
a double-count or wrong-row pickup for Lilly's balance-sheet layout). Needs a targeted look.

---

*Items 1-4 were fixed as statement-row label additions + an apostrophe-normalizing matcher in
`DataPipeline/src_metrics/derived_kpis.py` on 2026-07-27, verified locally against live EDGAR
data (7 of 9 touched companies fully restored; the other 2 are F1 above). See git history for
that file on/after 2026-07-27.*

*Follow-on (2026-07-27): a ROE guard (`_roe_avg_equity`, suppresses ROE where equity <= 0 in the
metric or prior year) was added to `derived_kpis.py` with unit tests, plus a one-time
`src_metrics/hotfix_negative_equity_roe.py` that scrubbed 5 meaningless negative-equity ROE
values (Oracle 2022/2023, MBIA 2021/2024/2025) from the recomputed table. A full-history recompute
(all 25 companies, 10-year depth) was then pushed to production S3
(`DATA_MERGE_ASSETS/FINRAG_FACT_METRICS/KPI_FACT_DATA_EDGAR.parquet`, 9,260 rows) after archiving
the prior 9,071-row table to `.../ARCHIVE/`; both local mirrors verified byte-identical to S3.*
