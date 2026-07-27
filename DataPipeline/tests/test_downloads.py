# tests/test_downloads.py
import io
import os
import zipfile
from pathlib import Path

import pandas as pd
import pytest

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import src_legacy_bs4_scraper.download_filings as dl


# ---------- helpers ----------

# using dummy response instead of real network calls
class DummyResponse:
    def __init__(self, content=b"", text=""):
        self.content = content
        self.text = text


def make_zip_with_master_idx(lines_after_header):
    """Create a zip (bytes) with a master.idx file.
    The code skips first 11 lines, so we pad 11 header lines."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w") as zf:
        content = "\n".join(["hdr"] * 11 + lines_after_header) + "\n"
        zf.writestr("master.idx", content)
    return bio.getvalue()


# ---------- tests ----------

def test_requests_retry_session_mounts_and_retries():
    s = dl.requests_retry_session(retries=7, backoff_factor=0.1)
    # Basic sanity: adapters are mounted and carry a Retry config
    assert "http://" in s.adapters and "https://" in s.adapters
    http_adapter = s.adapters["http://"]
    https_adapter = s.adapters["https://"]
    assert getattr(http_adapter, "max_retries").total == 7
    assert getattr(https_adapter, "max_retries").total == 7


def test_download_success(tmp_path, monkeypatch):
    # Return a "good" response (no rate-limit text) with some bytes
    # Creating a fake session 
    def fake_rrs(**kwargs):
        class Sess:
            def get(self, url, headers=None):
                return DummyResponse(content=b"file-bytes", text="OK")
        return Sess()
    monkeypatch.setattr(dl, "requests_retry_session", fake_rrs)

    ok = dl.download(
        url="https://example.com/file.htm",
        filename="x.htm",
        download_folder=str(tmp_path),
        user_agent="ua",
    )
    assert ok is True
    assert (tmp_path / "x.htm").read_bytes() == b"file-bytes"


def test_download_retries_exceeded(tmp_path, monkeypatch):
    # Always returns the SEC "managed until action" text -> should fail
    def fake_rrs(**kwargs):
        class S:
            def get(self, url, headers=None):
                return DummyResponse(content=b"", text="will be managed until action is taken to declare your traffic.")
        return S()
    monkeypatch.setattr(dl, "requests_retry_session", fake_rrs)

    ok = dl.download(
        url="https://example.com/file.htm",
        filename="x.htm",
        download_folder=str(tmp_path),
        user_agent="ua",
    )
    assert ok is False
    assert not (tmp_path / "x.htm").exists()


def test_download_indices_creates_tsv(tmp_path, monkeypatch, caplog):
    # Prepare a master.idx row (last column .txt; code swaps to -index.html)
    row = "0000000000|COMPANY|10-K|2025-01-01|edgar/data/0/0/0.txt"
    zip_bytes = make_zip_with_master_idx([row])

    def fake_rrs(**kwargs):
        class S:
            def get(self, url, headers=None):
                return DummyResponse(content=zip_bytes, text="OK")
        return S()
    monkeypatch.setattr(dl, "requests_retry_session", fake_rrs)

    indices_dir = tmp_path / "indices"
    indices_dir.mkdir()
    dl.download_indices(
        start_year=2025,
        end_year=2025,
        quarters=[1],
        skip_present_indices=False,
        indices_folder=str(indices_dir),
        user_agent="ua",
    )

    tsv = indices_dir / "2025_QTR1.tsv"
    assert tsv.exists()
    # Check the transformed last column ends with -index.html
    txt = tsv.read_text(encoding="utf-8").strip()
    parts = txt.split("|")
    assert parts[-1].endswith("-index.html")


def test_get_specific_indices_filters_by_type_and_cik(tmp_path, monkeypatch):
    # Create a minimal TSV file like the function expects
    tsv = tmp_path / "2025_QTR1.tsv"
    data = [
        # CIK | Company | Type | Date | complete_text_file_link | html_index | Filing Date | Period of Report | SIC | htm_file_link | State of Inc | State location | Fiscal YE | filename
        "1234|A Co|10-K|2025-01-15|edgar/a.txt|edgar/a-index.html|2025-01-15|2024-12-31|1234|edgar/a.htm|DE|CA|1231|a.htm",
        "5678|B Co|8-K|2025-02-01|edgar/b.txt|edgar/b-index.html|2025-02-01|2025-01-31|5678|edgar/b.htm|DE|NY|1231|b.htm",
        "00001234|A Co|10-K|2025-01-15|edgar/c.txt|edgar/c-index.html|2025-01-15|2024-12-31|1234|edgar/c.htm|DE|CA|1231|c.htm",
    ]
    tsv.write_text("\n".join(data) + "\n", encoding="utf-8")

    # Provide a CSV with CIKs only (so no need to map tickers)
    csv_path = tmp_path / "companies.csv"
    pd.DataFrame({"cik_int": ["1234"]}).to_csv(csv_path, index=False)

    # Stub network call the function would make to fetch ticker map
    def fake_rrs(**kwargs):
        class S:
            def get(self, url, headers=None):
                return DummyResponse(content=b"{}", text="OK")
        return S()
    monkeypatch.setattr(dl, "requests_retry_session", fake_rrs)

    df = dl.get_specific_indices(
        tsv_filenames=[str(tsv)],
        filing_types=["10-K"],
        user_agent="ua",
        cik_tickers=str(csv_path),
    )
    # Should keep only CIK 1234 rows of type 10-K (2 rows above become 2, but one of them
    # normalizes CIK '00001234' -> '1234', so both 10-K rows remain)
    assert not df.empty
    assert set(df["Type"]) == {"10-K"}
    assert set(df["CIK"].astype(str).map(lambda x: str(int(x)))) == {"1234"}


def test_crawl_parses_and_calls_download(tmp_path, monkeypatch):
    # Route module-level DATASET_DIR to tmp
    monkeypatch.setattr(dl, "DATASET_DIR", Path(tmp_path))

    # Ensure companies_info.json exists
    (tmp_path / "companies_info.json").write_text("{}", encoding="utf-8")

    html = """
    <div class="companyInfo">
    <span class="companyName">ACME, INC.</span>
    <p class="identInfo">
        State of Inc <span>DE</span> |
        State location <a href="/cgi-bin/browse-edgar?action=getcompany&State=CA">CA</a> |
        Fiscal Year End 1231
        <a href="/cgi-bin/browse-edgar?action=getcompany&SIC=3630">SIC</a>
    </p>
    </div>

    <div class="infoHead">Filing Date</div> <div class="info">2025-02-01</div>
    <div class="infoHead">Period of Report</div> <div class="info">2024-12-31</div>

    <table summary="Document Format Files">
    <tr><th>H</th></tr>
    <tr><td></td><td></td><td></td><td></td><td></td><td><a href="/ix?doc=/Archives/edgar/data/1/filing.htm">doc</a></td><td></td><td>10-K</td></tr>
    <tr><td></td><td></td><td></td><td>Complete submission text file</td><td></td><td><a href="/Archives/edgar/data/1/filing.txt">txt</a></td><td></td><td>10-K</td></tr>
    </table>
    """

    # Fake session returning the HTML (twice: index page and company page)
    calls = {"n": 0}
    def fake_rrs(**kwargs):
        class S:
            def get(self, url, headers=None):
                calls["n"] += 1
                return DummyResponse(content=html.encode("utf-8"), text="OK")
        return S()
    monkeypatch.setattr(dl, "requests_retry_session", fake_rrs)

    # Stub download() – we just want to see it called with the right filename
    saved = {"args": None}
    def fake_download(url, filename, download_folder, user_agent):
        saved["args"] = (url, filename, download_folder, user_agent)
        return True
    monkeypatch.setattr(dl, "download", fake_download)

    # Prepare inputs
    series = pd.Series({
        "CIK": "1000",
        "Type": "10-K",
        "html_index": "https://example.com/index",
        "complete_text_file_link": "https://www.sec.gov/Archives/edgar/data/1000/000000.txt",
        "SIC": pd.NA,
        "State of Inc": pd.NA,
        "State location": pd.NA,
        "Fiscal Year End": pd.NA,
    })

    out = dl.crawl(
        filing_types=["10-K"],
        series=series.copy(),
        raw_filings_folder=str(tmp_path / "raw"),
        user_agent="ua",
    )

    # It should return an updated series and have constructed a filename
    assert isinstance(out, pd.Series)
    assert out["Filing Date"] == "2025-02-01"
    assert out["Period of Report"] == "2024-12-31"
    # Ensured company info filled from the page and/or cache
    assert out["State of Inc"] == "DE"
    assert out["State location"] == "CA"
    assert out["Fiscal Year End"] == "1231"
    # download() was called with a cleaned filename (ix?doc=/ removed -> .htm)
    assert saved["args"] is not None
    _, fname, folder, _ = saved["args"]
    assert fname.endswith(".htm")
    assert "10K" in fname
