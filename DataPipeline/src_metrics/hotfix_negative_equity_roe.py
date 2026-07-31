"""
hotfix_negative_equity_roe.py - one-time data hotfix that mirrors the ROE
guard now living in derived_kpis._roe_avg_equity(). It removes meaningless
"ROE % (Avg Equity)" rows from an already-computed KPI fact table where
stockholders' equity was negative in the metric year OR the prior year -
average equity is unreliable across a sign change and produces ratios of
thousands of percent or flipped signs (e.g. Oracle 7301% / -403%, MBIA 589%).

Why this exists separately from the guard: the guard prevents such rows on
any FUTURE pipeline run, but a table produced before the guard existed still
contains them. This scrubs those rows without a full 20-40 min re-fetch.

Equity sign is read from the derived "Debt-to-Equity" row for the same
(cik, year): liabilities are always positive, so Debt-to-Equity < 0 iff
equity < 0 - an exact proxy that needs no raw-equity column in the table.

Usage:
    python hotfix_negative_equity_roe.py <in.parquet> [out.parquet]
    (omitting out.parquet writes <in>.cleaned.parquet)
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROE_LABEL = "ROE % (Avg Equity)"
DTE_LABEL = "Debt-to-Equity"


def scrub_negative_equity_roe(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (cleaned_df, dropped_df). Drops derived ROE rows whose (cik,
    year) or (cik, year-1) had negative equity, inferred from Debt-to-Equity < 0."""
    neg = (
        df.filter((pl.col("metric_type") == "derived")
                  & (pl.col("metric_label") == DTE_LABEL)
                  & (pl.col("value") < 0))
          .select("cik", "year").unique()
    )
    neg_this = neg.with_columns(pl.lit(True).alias("_neg_this"))
    # a negative equity at year Y makes ROE at Y+1 (which averages Y and Y+1) unreliable
    neg_prev = neg.with_columns((pl.col("year") + 1).alias("year"),
                                pl.lit(True).alias("_neg_prev"))

    d = (df.join(neg_this, on=["cik", "year"], how="left")
           .join(neg_prev, on=["cik", "year"], how="left")
           .with_columns((pl.col("_neg_this").fill_null(False)
                          | pl.col("_neg_prev").fill_null(False)).alias("_neg_equity")))

    drop_mask = ((pl.col("metric_type") == "derived")
                 & (pl.col("metric_label") == ROE_LABEL)
                 & pl.col("_neg_equity"))

    dropped = d.filter(drop_mask).select(df.columns)
    cleaned = d.filter(~drop_mask).select(df.columns)
    return cleaned, dropped


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else in_path.with_suffix(".cleaned.parquet")

    df = pl.read_parquet(in_path)
    cleaned, dropped = scrub_negative_equity_roe(df)

    print(f"Input : {in_path}  ({df.height:,} rows)")
    print(f"Dropped {dropped.height} negative-equity ROE row(s):")
    for r in dropped.select("cik", "year", "value").iter_rows(named=True):
        print(f"    {r['cik']} {r['year']}  ROE={r['value']:.2f}")
    cleaned.write_parquet(out_path)
    print(f"Output: {out_path}  ({cleaned.height:,} rows)")


if __name__ == "__main__":
    main()
