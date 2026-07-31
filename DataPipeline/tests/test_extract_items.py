# tests/test_extract_and_convert.py
import json
import re
from pathlib import Path
import pandas as pd
import pytest
from bs4 import BeautifulSoup

import src_legacy_bs4_scraper.extract_and_convert as ec


def test_convert_json_to_parquet(tmp_path, monkeypatch):
    # Prepare a minimal JSON with one item and a period_of_report inside the allowed range
    sample = {
        "cik": "1234",
        "company": "ACME Inc",
        "filing_type": "10-K",
        "filing_date": "2025-02-01",
        "period_of_report": "2024-12-31",
        "item_1": "Short line.\nThis is a long sentence that should be split only by the sentence tokenizer. Another end. \nLast one."
    }
    json_path = tmp_path / "one.json"
    json_path.write_text(json.dumps(sample), encoding="utf-8")

    csv_out = tmp_path / "csv"
    pq_out = tmp_path / "pq"

    ok = ec.convert_json_to_parquet(
        json_path=str(json_path),
        csv_output_folder=str(csv_out),
        parquet_output_folder=str(pq_out),
        min_year=2021,
        max_year=2025,
    )

    # Should succeed and write both files
    assert ok is True
    csv_file = csv_out / "one.csv"
    pq_file = pq_out / "one.parquet"
    assert csv_file.exists()
    assert pq_file.exists()

    df = pd.read_csv(csv_file, dtype=str)
    # check a few important columns exist and are populated
    for col in [
        "cik",
        "name",
        "report_year",
        "docID",
        "sentenceID",
        "section_name",
        "section_item",
        "section_ID",
        "form",
        "sentence_index",
        "sentence",
        "filingDate",
        "reportDate",
        "temporal_bin",
        "source_file_path",
        "load_method",
    ]:
        assert col in df.columns

    # cik padded
    assert (df["cik"] == "0000001234").all()
    # form comes through
    assert (df["form"] == "10-K").all()
    # section_name should be mapped from "item_1" -> "Business"
    assert (df["section_name"] == "Business").all()
    # report_year pulled from period_of_report
    assert (df["report_year"] == "2024").all()
    # temporal bin based on 2024
    assert (df["temporal_bin"] == "bin_2021_2025").all()
    # sentenceIDs look reasonable
    assert df["sentenceID"].str.contains(r"0000001234_10-K_2024_section_1_\d+").all()


def test_convert_json_to_parquet_year_out_of_range(tmp_path):
    # period_of_report is 2019, out of [2021,2025] => skip
    sample = {
        "cik": "99",
        "company": "Out Range Co",
        "filing_type": "10-K",
        "filing_date": "2020-02-01",
        "period_of_report": "2019-12-31",
        "item_1": "Something here."
    }
    json_path = tmp_path / "skip.json"
    json_path.write_text(json.dumps(sample), encoding="utf-8")

    csv_out = tmp_path / "csv"
    pq_out = tmp_path / "pq"

    ok = ec.convert_json_to_parquet(
        json_path=str(json_path),
        csv_output_folder=str(csv_out),
        parquet_output_folder=str(pq_out),
        min_year=2021,
        max_year=2025,
    )
    assert ok is False
    assert not (csv_out / "skip.csv").exists()
    assert not (pq_out / "skip.parquet").exists()


# -------------------------
# HtmlStripper + helpers
# -------------------------

def test_html_stripper():
    s = ec.HtmlStripper()
    s.feed("<p>Hello <b>World</b></p>")
    assert s.get_data() == "Hello World"


def test_strip_html_inserts_breaks_then_strips():
    html = "<div>line1</div><p>line2<br/>line3</p><td>x</td><td>y</td>"
    text = ec.ExtractItems.strip_html(html)
    # we expect tags to be gone but content preserved
    assert "line1" in text and "line2" in text and "line3" in text
    # td closing inserts spaces so "x y" appears
    assert "x  y" in text or "x y" in text  # tolerate spacing normalization


def test_remove_multiple_lines_compacts():
    src = "A\n\n\nB\n \nC"
    out = ec.ExtractItems.remove_multiple_lines(src)
    # Multiple newlines collapse to single newline, stray spaces trimmed
    assert out == "A\nB\nC"


def test_clean_text_replacements_and_header_removal():
    src = (
        "A\u00a0B \u2013 dash\n"
        "\nTABLE OF CONTENTS\n"
        "Keep me\n"
        "Page 12\n"
        "F-3\n"
        "INDEX TO FINANCIAL STATEMENTS\n"
        "Hello"
    )
    out = ec.ExtractItems.clean_text(src)
    # non-breaking space becomes space; en-dash normalized to hyphen
    assert "A B - dash" in out
    # header blocks removed
    assert "TABLE OF CONTENTS" not in out
    assert "INDEX TO FINANCIAL STATEMENTS" not in out
    # page numbers removed
    assert "Page 12" not in out
    assert "F-3" not in out
    # the kept parts remain
    assert "Keep me" in out and "Hello" in out


def test_handle_spans_html_and_text(tmp_path):
    # HTML case: spans with text get unwrapped; spans with margin styles get replaced
    soup = BeautifulSoup(
        '<div>before<span>keep</span><span style="margin-left:36pt;"></span>after</div>',
        "html.parser",
    )
    inst = ec.ExtractItems(
        remove_tables=False,
        items_to_extract=[],
        include_signature=False,
        raw_files_folder=".",   # dummy
        extracted_files_folder=".",  # dummy
        skip_extracted_filings=False,
    )
    out = inst.handle_spans(soup, is_html=True)    # After handle_spans, return value is a BeautifulSoup object
    # The first loop unwraps non-empty span -> text "keep" remains
    # Because of current implementation, margin check branch will replace remaining span with a space
    assert "before" in str(out)
    assert "keep" in str(out)
    assert "after" in str(out)
    assert "margin-left" not in str(out)  # style span is gone/replaced

    # Non-HTML (string) case with explicit regex removal
    raw = '<span style="margin-right:12pt;">x</span>mid<span style="margin-top:10pt;">y</span>end'
    out2 = inst.handle_spans(raw, is_html=False)
    # horizontal span -> replaced with space, vertical -> replaced with newline
    assert " mid" in out2  # leading space from first span removal
    assert "\nend" in out2


# -------------------------
# Item patterns + minimal parse
# -------------------------

def test_adjust_item_patterns_examples():
    e = ec.ExtractItems(
        remove_tables=False,
        items_to_extract=["1", "1A", "SIGNATURE"],
        include_signature=False,
        raw_files_folder=".",
        extracted_files_folder=".",
        skip_extracted_filings=False,
    )

    # "1" should match "ITEM 1"
    pat1 = e.adjust_item_patterns("1")
    assert re.search(pat1, "ITEM 1", flags=re.IGNORECASE)

    # "1A" should match "ITEM 1A"
    pat1a = e.adjust_item_patterns("1A")
    assert re.search(pat1a, "ITEM 1A", flags=re.IGNORECASE)

    # "SIGNATURE" should match "SIGNATURES" (your pattern allows optional (s)/(S))
    sig = e.adjust_item_patterns("SIGNATURE")
    assert re.search(sig, "SIGNATURES", flags=re.IGNORECASE)


def test_parse_item_minimal_section():
    # Build a minimal text with newlines before ITEM tokens
    text = (
        "\nITEM 1. Business text line A. Business continues.\n"
        "Some filler until next section.\n"
        "  \n"
        " \n"
        "\nITEM 2 Next section starts here."
    )

    e = ec.ExtractItems(
        remove_tables=False,
        items_to_extract=["1", "2"],
        include_signature=False,
        raw_files_folder=".",
        extracted_files_folder=".",
        skip_extracted_filings=False,
    )
    # Ensure items_list reflects order
    e.items_list = ["1", "2"]
    section, positions = e.parse_item(text, "1", ["2"], positions=[])
    assert "Business text line A" in section
    assert "Next section starts" not in section

def test_extract_items_10k_minimal(tmp_path, monkeypatch):
    # Arrange a fake raw filing: /tmp/.../RAW/10-K/file.htm
    raw_root = tmp_path / "RAW"
    (raw_root / "10-K").mkdir(parents=True)
    filing_file = raw_root / "10-K" / "demo.htm"

    # Minimal EDGAR-like content with <DOCUMENT> wrapper and two items
    filing_file.write_text(
        "<DOCUMENT>\n"
        "<TYPE>10-K\n"
        "ITEM 1. Business\n"
        "We sell things.\n"
        "ITEM 7. Management’s Discussion\n"
        "Lots of analysis.\n"
        "</DOCUMENT>\n",
        encoding="utf-8"
    )

    # Minimal filing metadata row (as your code expects)
    filing_metadata = pd.Series({
        "CIK": "1234567890",
        "Company": "ACME INC.",
        "Type": "10-K",
        "Date": "2025-02-01",
        "Period of Report": "2024-12-31",
        "SIC": "1234",
        "State of Inc": "DE",
        "State location": "CA",
        "Fiscal Year End": "1231",
        "html_index": "http://example.com",
        "htm_file_link": "http://example.com/file.htm",
        "complete_text_file_link": "http://example.com/file.txt",
        "filename": "demo.htm",
    })

    extractor = ec.ExtractItems(
        remove_tables=False,
        items_to_extract=["1", "7"],      # subset that exists in our text
        include_signature=False,
        raw_files_folder=str(raw_root),
        extracted_files_folder=str(tmp_path / "EXTRACTED"),
        skip_extracted_filings=False,
    )

    # this sets the expected items list for 10-K
    extractor.determine_items_to_extract(filing_metadata)

    out = extractor.extract_items(filing_metadata)
    assert out is not None

    # core metadata is present
    for k in ["cik","company","filing_type","filing_date","period_of_report","filename"]:
        assert k in out

    # items you asked to extract exist
    assert "item_1" in out and out["item_1"]
    assert "item_7" in out and out["item_7"]

    # signature should not be included when include_signature=False
    assert "SIGNATURE" not in out
