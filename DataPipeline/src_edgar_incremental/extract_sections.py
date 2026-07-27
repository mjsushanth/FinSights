"""
Stage 2: extract_sections.py

Reads the Stage 1 manifest, re-fetches each filing by accession number, and
extracts raw section text for every item present in
finrag_dim_sec_sections.parquet (the confirmed section_ID/section_name
ground truth - see PLAN.md decision 1).

Output: one row per (docID, item) with raw section text. Filings/items that
fail to parse are logged and skipped, never crashed on (Gotcha 2 - 10-K/A
amendments and other edge cases can have partial item coverage even after
excluding amendments outright).
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
from edgar import get_by_accession_number, set_identity

EDGAR_IDENTITY = os.getenv("EDGAR_IDENTITY", "your-email@example.com")

MODULE_DIR = Path(__file__).parent
DIM_SECTIONS_PATH = MODULE_DIR.parent / "data_cache" / "dimensions" / "finrag_dim_sec_sections.parquet"
SECTIONS_DIR = MODULE_DIR / "manifests"


def load_section_map() -> dict[str, tuple[int, str]]:
    """Build {edgartools_section_key: (section_ID, section_name)} from the
    existing dimension table. edgartools' tenk.sections dict keys are
    lowercase (e.g. 'part_i_item_1a'); the dim table's section_code column
    is the same string uppercase ('PART_I_ITEM_1A') - confirmed match this
    session. Rows with a null hf_section_code (ITEM_16) are excluded, same
    as the real production fact table."""
    dim = pl.read_parquet(DIM_SECTIONS_PATH).filter(pl.col("hf_section_code").is_not_null())
    return {
        row["section_code"].lower(): (row["hf_section_code"], row["sec_item_canonical"])
        for row in dim.iter_rows(named=True)
    }


def extract_filing_sections(accession_no: str, section_map: dict[str, tuple[int, str]]) -> list[dict]:
    """Returns a list of {section_ID, section_name, raw_text} for every
    known item found in this filing. Logs (does not raise) on any failure
    to parse the filing or a given section."""
    rows = []
    try:
        filing = get_by_accession_number(accession_no)
        tenk = filing.obj()
    except Exception as e:
        print(f"  ERROR parsing filing {accession_no}: {e}")
        return rows

    for key, (section_id, section_name) in section_map.items():
        section = tenk.sections.get(key)
        if section is None:
            continue
        try:
            text = section.text()
        except Exception as e:
            print(f"  ERROR extracting {key} from {accession_no}: {e}")
            continue
        if not text or not text.strip():
            continue
        rows.append({"section_ID": section_id, "section_name": section_name, "raw_text": text})

    return rows


def run(manifest: pl.DataFrame, out_name: str) -> pl.DataFrame:
    set_identity(EDGAR_IDENTITY)
    section_map = load_section_map()

    manifest = manifest.filter(pl.col("found"))
    all_rows = []

    for row in manifest.iter_rows(named=True):
        doc_id = f"{row['cik']}_{row['form']}_{row['target_report_year']}"
        sections = extract_filing_sections(row["accession_no"], section_map)

        coverage = f"{len(sections)}/{len(section_map)}"
        print(f"  {doc_id}: {coverage} sections extracted")

        for sec in sections:
            all_rows.append({
                "docID": doc_id,
                "cik": row["cik"],
                "cik_int": row["cik_int"],
                "name": row["name"],
                "tickers": row["tickers"],
                "sic": row["sic"],
                "form": row["form"],
                "filing_date": row["filing_date"],
                "report_date": row["report_date"],
                "report_year": row["target_report_year"],
                "filing_url": row["filing_url"],
                **sec,
            })

    out_df = pl.DataFrame(all_rows) if all_rows else pl.DataFrame(
        schema={"docID": pl.String, "cik": pl.String, "cik_int": pl.Int64, "name": pl.String,
                "tickers": pl.List(pl.String), "sic": pl.String,
                "form": pl.String, "filing_date": pl.String, "report_date": pl.String,
                "report_year": pl.Int64, "filing_url": pl.String, "section_ID": pl.Int32,
                "section_name": pl.String, "raw_text": pl.String}
    )

    SECTIONS_DIR.mkdir(exist_ok=True)
    out_path = SECTIONS_DIR / out_name
    out_df.write_parquet(out_path)
    print(f"\nExtracted {len(out_df)} sections across {manifest.height} filings. Written to {out_path}")
    return out_df


if __name__ == "__main__":
    manifest_path = SECTIONS_DIR / "fy2025_manifest.parquet"
    manifest = pl.read_parquet(manifest_path)
    run(manifest, "fy2025_sections.parquet")
