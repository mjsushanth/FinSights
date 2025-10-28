import json
import logging
import os
import re
import sys

from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

import click
import cssutils
import numpy as np
import pandas as pd
import polars as pl

from bs4 import BeautifulSoup
from pathos.pools import ProcessPool
from tqdm import tqdm

# from nltk.tokenize import sent_tokenize

import nltk
try:
    from nltk.tokenize import sent_tokenize
    # Test if punkt_tab is available
    sent_tokenize("Test sentence.")
except LookupError:
    print("⚠️  NLTK punkt_tab not found. Downloading...")
    try:
        nltk.download('punkt_tab', quiet=False)
        from nltk.tokenize import sent_tokenize
        print("✅ NLTK punkt_tab downloaded successfully")
    except Exception as e:
        print(f"❌ Failed to download NLTK data: {e}")
        print("⚠️  Falling back to simple regex tokenizer")
        # Fallback tokenizer
        def sent_tokenize(text: str) -> list:
            """Simple fallback sentence tokenizer"""
            sentences = re.split(r'(?<=[.!?])\s+', text)
            return [s.strip() for s in sentences if s.strip()]

# from __init__ import DATASET_DIR
from src import DATASET_DIR
from src.item_lists import item_list_10k
from src.logger import Logger

# Change the default recursion limit of 1000 to 30000
sys.setrecursionlimit(30000)

# Suppress cssutils stupid warnings
cssutils.log.setLevel(logging.CRITICAL)

cli = click.Group()

regex_flags = re.IGNORECASE | re.DOTALL | re.MULTILINE

# This map is needed for 10-Q reports
roman_numeral_map = {
    "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
    "6": "VI", "7": "VII", "8": "VIII", "9": "IX", "10": "X",
    "11": "XI", "12": "XII", "13": "XIII", "14": "XIV", "15": "XV",
    "16": "XVI", "17": "XVII", "18": "XVIII", "19": "XIX", "20": "XX",
}

# Instantiate a logger object
LOGGER = Logger(name="ExtractItems").get_logger()


# ============================================================================
# HELPER FUNCTIONS FOR PARQUET CONVERSION
# ============================================================================

def _is_heading_line(s: str) -> bool:
    """Check if a line is likely a heading."""
    s = s.strip()
    return (
        (len(s.split()) <= 8 and not re.search(r'[.!?]$', s))
        or re.match(r'(?i)^item\s+\d+[a-zA-Z]?\.?$', s)
    )


def _normalize_item_token(s: str) -> str:
    """Normalize 'Item X.' tokens to prevent unwanted sentence splits."""
    return re.sub(r'(?i)\bItem\s+(\d+[A-Za-z]?)\.', r'Item \1', s)


def temporal_bin(y):
    """Assign temporal bin based on year."""
    if 2006 <= y <= 2009:
        return "bin_2006_2009"
    elif 2010 <= y <= 2015:
        return "bin_2010_2015"
    elif 2016 <= y <= 2020:
        return "bin_2016_2020"
    elif 2021 <= y <= 2025:
        return "bin_2021_2025"
    else:
        return "bin_unknown"


def convert_json_to_parquet(json_path: str, csv_output_folder: str, parquet_output_folder: str, min_year: int = None, max_year: int = None) -> bool:
    """
    Convert extracted JSON into sentence-level CSV and Parquet files.
    
    Args:
        json_path: Path to the JSON file
        csv_output_folder: Folder to save CSV files
        parquet_output_folder: Folder to save Parquet files
        min_year: Minimum year to include (None or "current" for current year)
        max_year: Maximum year to include (None or "current" for current year)
        
    Returns:
        bool: True if conversion successful, False otherwise
    """
    p = Path(json_path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        LOGGER.warning(f"Failed to read {p}: {e}")
        return False

    # ---- Metadata Extraction ----
    cik = str(data.get("cik") or data.get("CIK") or "").strip()
    name = data.get("company") or data.get("company_name") or ""
    filing_type = data.get("filing_type") or data.get("filingType") or ""
    filing_date = data.get("filing_date") or data.get("filingDate") or ""
    period_of_report = data.get("period_of_report") or data.get("periodOfReport") or ""

    def parse_year(date_str):
        m = re.search(r"(\d{4})", str(date_str))
        return int(m.group(1)) if m else None

    ####  Updating report_year to pull from period_of_report only
    report_year = parse_year(period_of_report)
    
    current_year = datetime.now().year
    actual_min_year = current_year if min_year in [None, "current", "auto", 0] else min_year
    actual_max_year = current_year if max_year in [None, "current", "auto", 0] else max_year
    
    if not report_year or not (actual_min_year <= report_year <= actual_max_year):
        LOGGER.debug(f"Skipping {p.name} - year {report_year} outside range [{actual_min_year}-{actual_max_year}]")
        return False

    cik_padded = str(cik).zfill(10)
    docID = f"{cik_padded}_{filing_type}_{report_year}"

    # ---- Extract Items ----
    item_keys = [k for k in data.keys() if k.lower().startswith("item_")]
    if not item_keys:
        LOGGER.debug(f"No item sections found in {p.name}")
        return False

    records = []
    section_map = {
        "item_1": 0, "item_1a": 1, "item_1b": 2, "item_2": 3, "item_3": 4,
        "item_4": 5, "item_5": 6, "item_6": 7, "item_7": 8, "item_7a": 9,
        "item_8": 10, "item_9": 11, "item_9a": 12, "item_9b": 13, "item_10": 14,
        "item_11": 15, "item_12": 16, "item_13": 17, "item_14": 18, "item_15": 19
    }

    section_title_map = {
        "item_1": "Business",
        "item_1a": "Risk Factors",
        "item_1b": "Unresolved Staff Comments",
        "item_2": "Properties",
        "item_3": "Legal Proceedings",
        "item_4": "Mine Safety Disclosures",
        "item_5": "Market for Stock",
        "item_6": "Selected Financial Data",
        "item_7": "Management’s Discussion and Analysis (MD&A)",
        "item_7a": "Quantitative and Qualitative Disclosures About Market Risk",
        "item_8": "Financial Statements and Supplementary Data",
        "item_9": "Changes in and Disagreements With Accountants on Accounting and Financial Disclosure",
        "item_9a": "Controls and Procedures",
        "item_9b": "Other Information",
        "item_10": "Directors, Officers & Governance",
        "item_11": "Executive Compensation",
        "item_12": "Security Ownership of Certain Beneficial Owners and Management",
        "item_13": "Certain Relationships and Related Transactions",
        "item_14": "Principal Accounting Fees and Services",
        "item_15": "Exhibits List"
    }

    for sec_idx, sec_key in enumerate(sorted(item_keys, key=str.lower)):
        raw_text = str(data.get(sec_key, "")).strip()
        if not raw_text:
            continue
        
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        paras, header_buf = [], []
        for ln in lines:
            if _is_heading_line(ln):
                header_buf.append(ln)
                continue
            if header_buf:
                combined = " ".join(header_buf + [ln])
                combined = _normalize_item_token(combined)
                paras.append(combined)
                header_buf = []
            else:
                paras.append(ln)
        if header_buf:
            combined = " ".join(header_buf)
            combined = _normalize_item_token(combined)
            paras.append(combined)

        sentences = []
        for para in paras:
            if len(para.split()) < 40:
                sentences.append(para.strip())
            else:
                sentences.extend([s.strip() for s in sent_tokenize(para) if s.strip()])

        for s_idx, sent in enumerate(sentences):
            sent = re.sub(r"\s+", " ", sent).strip()
            if not sent:
                continue

            section_id = section_map.get(sec_key.lower(), None)
            section_token = sec_key.split("_", 1)[-1]
            sentenceID = f"{docID}_section_{section_token}_{s_idx}"
            
            rec = {
                "cik": cik_padded,                
                "name": name,
                "report_year": report_year,
                "docID": docID,
                "sentenceID": sentenceID,
                "section_name": sec_key,          # will update later using map
                "section_item": sec_key.strip().upper(),          # new column
                "section_ID": section_id,
                "form": filing_type,                
                "sentence_index": s_idx,
                "sentence": sent,
                "SIC": data.get("sic") or None,     # new column
                "filingDate": filing_date,         # new column
                "reportDate": period_of_report or None #if period_of_report else f"{current_year}-12-31"  # new column
            }
            records.append(rec)

    if not records:
        LOGGER.debug(f"No sentences generated for {p.name}")
        return False

    df = pd.DataFrame(records)

    # --- Remove record_status if exists ---
    if "record_status" in df.columns:
        df = df.drop(columns=["record_status"])

    # --- Update section_name using section_title_map ---
    df["section_name"] = df["section_item"].map(lambda x: section_title_map.get(x.lower(), x))

    # --- Add Audit Columns ---
    df["temporal_bin"] = df["report_year"].apply(lambda y: temporal_bin(y) if pd.notnull(y) else "bin_unknown")
    now = datetime.now()
    df["sample_created_at"] = now
    df["last_modified_date"] = now
    df["sample_version"] = "v2.1_combined_extraction"
    df["source_file_path"] = str(json_path)
    df["load_method"] = "extract_and_convert"

    # ---- Write CSV + Parquet ----
    os.makedirs(csv_output_folder, exist_ok=True)
    os.makedirs(parquet_output_folder, exist_ok=True)
    
    base_name = p.stem
    csv_path = os.path.join(csv_output_folder, f"{base_name}.csv")
    parquet_path = os.path.join(parquet_output_folder, f"{base_name}.parquet")
    
    df.to_csv(csv_path, index=False, encoding="utf-8")
    try:
        df.to_parquet(parquet_path, index=False)
    except Exception as e:
        LOGGER.warning(f"Failed to write parquet for {p.name}: {e}")
        return False

    LOGGER.debug(f"Exported {len(df)} sentences for {p.name}")
    return True


# ============================================================================
# HTML STRIPPER CLASS 
# ============================================================================

class HtmlStripper(HTMLParser):
    """Class to strip HTML tags from a string."""

    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, data: str) -> None:
        self.fed.append(data)

    def get_data(self) -> str:
        return "".join(self.fed)

    def strip_tags(self, html: str) -> str:
        self.feed(html)
        return self.get_data()


# ============================================================================
# EXTRACT ITEMS CLASS 
# ============================================================================

class ExtractItems:
    """A class used to extract certain items from the raw files."""

    def __init__(
        self,
        remove_tables: bool,
        items_to_extract: List[str],
        include_signature: bool,
        raw_files_folder: str,
        extracted_files_folder: str,
        skip_extracted_filings: bool,
    ) -> None:
        self.remove_tables = remove_tables
        self.items_to_extract = items_to_extract
        self.include_signature = include_signature
        self.raw_files_folder = raw_files_folder
        self.extracted_files_folder = extracted_files_folder
        self.skip_extracted_filings = skip_extracted_filings

    def determine_items_to_extract(self, filing_metadata) -> None:
        """Determine the items to extract based on the filing type."""
        if filing_metadata["Type"] == "10-K":
            items_list = item_list_10k        
        else:
            raise Exception(
                f"Unsupported filing type: {filing_metadata['Type']}. No items_list defined."
            )

        self.items_list = items_list

        if self.items_to_extract:
            overlapping_items_to_extract = [
                item for item in self.items_to_extract if item in items_list
            ]
            if overlapping_items_to_extract:
                self.items_to_extract = overlapping_items_to_extract
            else:
                raise Exception(
                    f"Items defined by user do not match the items for {filing_metadata['Type']} filings."
                )
        else:
            self.items_to_extract = items_list

    @staticmethod
    def strip_html(html_content: str) -> str:
        """Strip the HTML tags from the HTML content."""
        html_content = re.sub(r"(<\s*/\s*(div|tr|p|li|)\s*>)", r"\1\n\n", html_content)
        html_content = re.sub(r"(<br\s*>|<br\s*/>)", r"\1\n\n", html_content)
        html_content = re.sub(r"(<\s*/\s*(th|td)\s*>)", r" \1 ", html_content)
        html_content = HtmlStripper().strip_tags(html_content)
        return html_content

    @staticmethod
    def remove_multiple_lines(text: str) -> str:
        """Replace consecutive new lines and spaces with a single new line or space."""
        text = re.sub(r"(( )*\n( )*){2,}", "#NEWLINE", text)
        text = re.sub(r"\n", " ", text)
        text = re.sub(r"(#NEWLINE)+", "\n", text).strip()
        text = re.sub(r"[ ]{2,}", " ", text)
        return text

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean the text by removing unnecessary blocks of text and substituting special characters."""
        # Replace special characters
        text = re.sub(r"[\xa0]", " ", text)
        text = re.sub(r"[\u200b]", " ", text)
        text = re.sub(r"[\x91]", "'", text)
        text = re.sub(r"[\x92]", "'", text)
        text = re.sub(r"[\x93]", '"', text)
        text = re.sub(r"[\x94]", '"', text)
        text = re.sub(r"[\x95]", "•", text)
        text = re.sub(r"[\x96]", "-", text)
        text = re.sub(r"[\x97]", "-", text)
        text = re.sub(r"[\x98]", "˜", text)
        text = re.sub(r"[\x99]", "™", text)
        text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015]", "-", text)
        text = re.sub(r"[\u2018]", "'", text)
        text = re.sub(r"[\u2019]", "'", text)
        text = re.sub(r"[\u2009]", " ", text)
        text = re.sub(r"[\u00ae]", "®", text)
        text = re.sub(r"[\u201c]", '"', text)
        text = re.sub(r"[\u201d]", '"', text)

        def remove_whitespace(match):
            ws = r"[^\S\r\n]"
            return f'{match[1]}{re.sub(ws, r"", match[2])}{match[3]}{match[4]}'

        def remove_whitespace_signature(match):
            ws = r"[^\S\r\n]"
            return f'{match[1]}{re.sub(ws, r"", match[2])}{match[4]}{match[5]}'

        # Fix broken section headers
        text = re.sub(
            r"(\n[^\S\r\n]*)(P[^\S\r\n]*A[^\S\r\n]*R[^\S\r\n]*T)([^\S\r\n]+)((\d{1,2}|[IV]{1,2})[AB]?)",
            remove_whitespace, text, flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(\n[^\S\r\n]*)(I[^\S\r\n]*T[^\S\r\n]*E[^\S\r\n]*M)([^\S\r\n]+)(\d{1,2}[AB]?)",
            remove_whitespace, text, flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(\n[^\S\r\n]*)(S[^\S\r\n]*I[^\S\r\n]*G[^\S\r\n]*N[^\S\r\n]*A[^\S\r\n]*T[^\S\r\n]*U[^\S\r\n]*R[^\S\r\n]*E[^\S\r\n]*(S|\([^\S\r\n]*s[^\S\r\n]*\))?)([^\S\r\n]+)([^\S\r\n]?)",
            remove_whitespace_signature, text, flags=re.IGNORECASE,
        )

        text = re.sub(
            r"(ITEM|PART)(\s+\d{1,2}[AB]?)([-•])",
            r"\1\2 \3 ", text, flags=re.IGNORECASE,
        )

        # Remove unnecessary headers
        regex_flags = re.IGNORECASE | re.MULTILINE
        text = re.sub(
            r"\n[^\S\r\n]*"
            r"(TABLE\s+OF\s+CONTENTS|INDEX\s+TO\s+FINANCIAL\s+STATEMENTS|BACK\s+TO\s+CONTENTS|QUICKLINKS)"
            r"[^\S\r\n]*\n", "\n", text, flags=regex_flags,
        )

        # Remove page numbers and headers
        text = re.sub(r"\n[^\S\r\n]*[-'""—]*\d+[-'""—]*[^\S\r\n]*\n", "\n", text, flags=regex_flags)
        text = re.sub(r"\n[^\S\r\n]*\d+[^\S\r\n]*\n", "\n", text, flags=regex_flags)
        text = re.sub(r"[\n\s]F[-'""—]*\d+", "", text, flags=regex_flags)
        text = re.sub(r"\n[^\S\r\n]*Page\s[\d*]+[^\S\r\n]*\n", "", text, flags=regex_flags)

        return text

    @staticmethod
    def calculate_table_character_percentages(table_text: str) -> Tuple[float, float]:
        """Calculate character type percentages contained in the table text."""
        digits = sum(c.isdigit() for c in table_text)
        spaces = sum(c.isspace() for c in table_text)

        if len(table_text) - spaces:
            non_blank_digits_percentage = digits / (len(table_text) - spaces)
        else:
            non_blank_digits_percentage = 0

        if len(table_text):
            spaces_percentage = spaces / len(table_text)
        else:
            spaces_percentage = 0

        return non_blank_digits_percentage, spaces_percentage

    def remove_html_tables(self, doc_report: str, is_html: bool) -> str:
        """Remove HTML tables that contain numerical data."""
        if is_html:
            tables = doc_report.find_all("table")
            for tbl in tables:
                tbl_text = ExtractItems.clean_text(ExtractItems.strip_html(str(tbl)))
                item_index_found = False
                for item_index in self.items_list:
                    item_index_pattern = self.adjust_item_patterns(item_index)
                    if len(list(re.finditer(rf"\n[^\S\r\n]*{item_index_pattern}[.*~\-:\s]", tbl_text, flags=regex_flags))) > 0:
                        item_index_found = True
                        break
                if item_index_found:
                    continue

                trs = (
                    tbl.find_all("tr", attrs={"style": True})
                    + tbl.find_all("td", attrs={"style": True})
                    + tbl.find_all("th", attrs={"style": True})
                )

                background_found = False
                for tr in trs:
                    style = cssutils.parseStyle(tr["style"])
                    if (style["background"] and style["background"].lower() not in ["none", "transparent", "#ffffff", "#fff", "white"]) or \
                       (style["background-color"] and style["background-color"].lower() not in ["none", "transparent", "#ffffff", "#fff", "white"]):
                        background_found = True
                        break

                trs = (
                    tbl.find_all("tr", attrs={"bgcolor": True})
                    + tbl.find_all("td", attrs={"bgcolor": True})
                    + tbl.find_all("th", attrs={"bgcolor": True})
                )

                bgcolor_found = False
                for tr in trs:
                    if tr["bgcolor"].lower() not in ["none", "transparent", "#ffffff", "#fff", "white"]:
                        bgcolor_found = True
                        break

                if bgcolor_found or background_found:
                    tbl.decompose()
        else:
            doc_report = re.sub(r"<TABLE>.*?</TABLE>", "", str(doc_report), flags=regex_flags)

        return doc_report

    def handle_spans(self, doc: str, is_html) -> str:
        """Handle span elements depending on their type."""
        if is_html:
            for span in doc.find_all("span"):
                if span.get_text(strip=True):
                    span.unwrap()

            for span in doc.find_all("span"):
                if "margin-left" or "margin-right" in span.attrs.get("style", ""):
                    span.replace_with(" ")
                elif "margin-top" or "margin-bottom" in span.attrs.get("style", ""):
                    span.replace_with("\n")
        else:
            horizontal_margin_pattern = re.compile(
                r'<span[^>]*style="[^"]*(margin-left|margin-right):\s*[\d.]+pt[^"]*"[^>]*>.*?</span>',
                re.IGNORECASE,
            )
            vertical_margin_pattern = re.compile(
                r'<span[^>]*style="[^"]*(margin-top|margin-bottom):\s*[\d.]+pt[^"]*"[^>]*>.*?</span>',
                re.IGNORECASE,
            )
            doc = re.sub(horizontal_margin_pattern, " ", doc)
            doc = re.sub(vertical_margin_pattern, "\n", doc)

        return doc

    def adjust_item_patterns(self, item_index: str) -> str:
        """Adjust the item_pattern for matching in the document text."""
        if "part" in item_index:
            if "__" not in item_index:
                item_index_number = item_index.split("_")[1]
                item_index_pattern = rf"PART\s*(?:{roman_numeral_map[item_index_number]}|{item_index_number})"
                return item_index_pattern
            else:
                item_index = item_index.split("__")[1]

        item_index_pattern = item_index

        if item_index == "9A":
            item_index_pattern = item_index_pattern.replace("A", r"[^\S\r\n]*A(?:\(T\))?")
        elif item_index == "SIGNATURE":
            pass
        elif "A" in item_index:
            item_index_pattern = item_index_pattern.replace("A", r"[^\S\r\n]*A")
        elif "B" in item_index:
            item_index_pattern = item_index_pattern.replace("B", r"[^\S\r\n]*B")
        elif "C" in item_index:
            item_index_pattern = item_index_pattern.replace("C", r"[^\S\r\n]*C")

        if item_index == "SIGNATURE":
            item_index_pattern = rf"{item_index}(s|\(s\))?"
        else:
            if "." in item_index:
                item_index = item_index.replace(".", r"\.")
            if item_index in roman_numeral_map:
                item_index = f"(?:{roman_numeral_map[item_index]}|{item_index})"
            item_index_pattern = rf"ITEMS?\s*{item_index}"

        return item_index_pattern

    def parse_item(self, text: str, item_index: str, next_item_list: List[str], 
                   positions: List[int], ignore_matches: int = 0) -> Tuple[str, List[int]]:
        """Parses the specified item/section in a report text."""
        regex_flags = re.IGNORECASE | re.DOTALL
        item_index_pattern = self.adjust_item_patterns(item_index)

        if "part" in item_index and "PART" not in item_index_pattern:
            item_index_part_number = item_index.split("__")[0]

        possible_sections_list = []
        impossible_match = None
        last_item = True
        
        for next_item_index in next_item_list:
            last_item = False
            if possible_sections_list:
                break
            if next_item_index == next_item_list[-1]:
                last_item = True

            next_item_index_pattern = self.adjust_item_patterns(next_item_index)

            if "part" in next_item_index and "PART" not in next_item_index_pattern:
                next_item_index_part_number = next_item_index.split("__")[0]
                if next_item_index_part_number != item_index_part_number:
                    last_item = True
                    break

            matches = list(re.finditer(rf"\n[^\S\r\n]*{item_index_pattern}[.*~\-:\s\(]", text, flags=regex_flags))
            for i, match in enumerate(matches):
                if i < ignore_matches:
                    continue
                offset = match.start()

                possible = list(re.finditer(
                    rf"\n[^\S\r\n]*{item_index_pattern}[.*~\-:\s\()].+?(\n[^\S\r\n]*{str(next_item_index_pattern)}[.*~\-:\s\(])",
                    text[offset:], flags=re.DOTALL,
                ))

                if not possible:
                    possible = list(re.finditer(
                        rf"\n[^\S\r\n]*{item_index_pattern}[.*~\-:\s\()].+?(\n[^\S\r\n]*{str(next_item_index_pattern)}[.*~\-:\s\(])",
                        text[offset:], flags=regex_flags,
                    ))

                if possible:
                    possible_sections_list += [(offset, possible)]
                elif next_item_index == next_item_list[-1] and not possible_sections_list and match:
                    impossible_match = match

        item_section, positions = ExtractItems.get_item_section(possible_sections_list, text, positions)

        if positions:
            if item_index in self.items_list and item_section == "":
                item_section = self.get_last_item_section(item_index, text, positions)
            if item_index == "SIGNATURE":
                item_section = self.get_last_item_section(item_index, text, positions)
        elif impossible_match or last_item:
            if item_index in self.items_list:
                item_section = self.get_last_item_section(item_index, text, positions)

        return item_section, positions

    @staticmethod
    def get_item_section(possible_sections_list: List[Tuple[int, List[re.Match]]], 
                        text: str, positions: List[int]) -> Tuple[str, List[int]]:
        """Returns the correct section from a list of all possible item sections."""
        item_section: str = ""
        max_match_length: int = 0
        max_match: Optional[re.Match] = None
        max_match_offset: Optional[int] = None

        for offset, matches in possible_sections_list:
            for match in matches:
                match_length = match.end() - match.start()
                if positions:
                    if match_length > max_match_length and offset + match.start() >= positions[-1]:
                        max_match = match
                        max_match_offset = offset
                        max_match_length = match_length
                elif match_length > max_match_length:
                    max_match = match
                    max_match_offset = offset
                    max_match_length = match_length

        if max_match:
            if positions:
                if max_match_offset + max_match.start() >= positions[-1]:
                    item_section = text[max_match_offset + max_match.start() : max_match_offset + max_match.regs[1][0]]
            else:
                item_section = text[max_match_offset + max_match.start() : max_match_offset + max_match.regs[1][0]]
            positions.append(max_match_offset + max_match.end() - len(max_match[1]) - 1)

        return item_section, positions

    def get_last_item_section(self, item_index: str, text: str, positions: List[int]) -> str:
        """Returns the text section starting through a given item."""
        item_index_pattern = self.adjust_item_patterns(item_index)
        item_list = list(re.finditer(rf"\n[^\S\r\n]*{item_index_pattern}[.\-:\s].+?", text, flags=regex_flags))

        item_section = ""
        for item in item_list:
            if "SIGNATURE" in item_index:
                if item != item_list[-1]:
                    continue
            if positions:
                if item.start() >= positions[-1]:
                    item_section = text[item.start():].strip()
                    break
            else:
                item_section = text[item.start():].strip()
                break

        return item_section

    def parse_10q_parts(self, parts: List[str], text: str, ignore_matches: int = 0) -> Tuple[Dict[str, str], List[int]]:
        """Iterate over the different parts and parse their data from the text."""
        texts = {}
        part_positions = []
        for i, part in enumerate(parts):
            next_part = parts[i + 1:]
            part_section, part_positions = self.parse_item(text, part, next_part, part_positions, ignore_matches)
            texts[part] = part_section
        return texts, part_positions

    def check_10q_parts_for_bugs(self, text: str, texts: Dict[str, str], 
                                 part_positions: List[int], filing_metadata: Dict[str, Any]) -> Dict[str, str]:
        """Check for common bugs in 10-Q report part extraction."""
        if not part_positions or not texts:
            LOGGER.debug(f'{filing_metadata["filename"]} - Could not detect positions/texts of parts.')
        elif not texts["part_1"] and part_positions:
            LOGGER.debug(f'{filing_metadata["filename"]} - Detected error in part separation - No PART I found.')
            texts["part_1"] = text[: part_positions[0] - len(texts["part_2"])]
        elif len(part_positions) > 1:
            if part_positions[1] - len(texts["part_2"]) - part_positions[0] > 200:
                separation = part_positions[1] - len(texts["part_2"]) - part_positions[0]
                LOGGER.debug(f'{filing_metadata["filename"]} - Detected error in part separation - End of PART I is {separation} chars from start of PART II.')
                texts["part_1"] = text[part_positions[0] - len(texts["part_1"]) : part_positions[1] - len(texts["part_2"])]
        return texts

    def get_10q_parts(self, text: str, filing_metadata: Dict[str, Any]) -> Dict[str, str]:
        """For 10-Q reports, separate the report text according to different parts."""
        parts = []
        for item in self.items_list:
            part = item.split("__")[0]
            if part not in parts:
                parts.append(part)
        self.items_list = parts

        texts, part_positions = self.parse_10q_parts(parts, text, ignore_matches=0)
        texts = self.check_10q_parts_for_bugs(text, texts, part_positions, filing_metadata)

        ignore_matches = 1
        length_difference = len(texts["part_2"]) - len(texts["part_1"])
        while length_difference > 5000:
            texts, part_positions = self.parse_10q_parts(parts, text, ignore_matches=ignore_matches)
            texts["part_1"] = ""
            texts = self.check_10q_parts_for_bugs(text, texts, part_positions, filing_metadata)
            new_length_difference = len(texts["part_2"]) - len(texts["part_1"])
            if new_length_difference == length_difference:
                texts, part_positions = self.parse_10q_parts(parts, text, ignore_matches=0)
                texts = self.check_10q_parts_for_bugs(text, texts, part_positions, filing_metadata)
                LOGGER.debug(f'{filing_metadata["filename"]} - Could not separate PARTs correctly.')
                break
            length_difference = new_length_difference
            ignore_matches += 1

        self.items_list = item_list_10q
        return texts

    def extract_items(self, filing_metadata: Dict[str, Any]) -> Any:
        """Extracts all items/sections for a file."""
        absolute_filename = os.path.join(self.raw_files_folder, filing_metadata["Type"], filing_metadata["filename"])

        with open(absolute_filename, "r", errors="backslashreplace") as file:
            content = file.read()

        content = re.sub(r"<PDF>.*?</PDF>", "", content, flags=regex_flags)
        documents = re.findall("<DOCUMENT>.*?</DOCUMENT>", content, flags=regex_flags)

        doc_report = None
        found, is_html = False, False

        for doc in documents:
            doc_type = re.search(r"\n[^\S\r\n]*<TYPE>(.*?)\n", doc, flags=regex_flags)
            doc_type = doc_type.group(1) if doc_type else None

            if doc_type.startswith(("10", "8")):
                doc_report = BeautifulSoup(doc, "html.parser")
                is_html = (True if doc_report.find("td") else False) and (True if doc_report.find("tr") else False)
                if not is_html:
                    doc_report = doc
                found = True

        if not found:
            if documents:
                LOGGER.info(f'\nCould not find documents for {filing_metadata["filename"]}')
            doc_report = BeautifulSoup(content, "html.parser")
            is_html = (True if doc_report.find("td") else False) and (True if doc_report.find("tr") else False)
            if not is_html:
                doc_report = content

        if filing_metadata["filename"].endswith("txt") and not documents:
            LOGGER.info(f'\nNo <DOCUMENT> tag for {filing_metadata["filename"]}')

        if self.remove_tables:
            doc_report = self.remove_html_tables(doc_report, is_html=is_html)

        doc_report = self.handle_spans(doc_report, is_html=is_html)

        json_content = {
            "cik": filing_metadata["CIK"],
            "company": filing_metadata["Company"],
            "filing_type": filing_metadata["Type"],
            "filing_date": filing_metadata["Date"],
            "period_of_report": filing_metadata["Period of Report"],
            "sic": filing_metadata["SIC"],
            "state_of_inc": filing_metadata["State of Inc"],
            "state_location": filing_metadata["State location"],
            "fiscal_year_end": filing_metadata["Fiscal Year End"],
            "filing_html_index": filing_metadata["html_index"],
            "htm_filing_link": filing_metadata["htm_file_link"],
            "complete_text_filing_link": filing_metadata["complete_text_file_link"],
            "filename": filing_metadata["filename"],
        }

        text = ExtractItems.strip_html(str(doc_report))
        text = ExtractItems.clean_text(text)

        if filing_metadata["Type"] == "10-Q":
            part_texts = self.get_10q_parts(text, filing_metadata)

        positions = []
        all_items_null = True
        for i, item_index in enumerate(self.items_list):
            next_item_list = self.items_list[i + 1:]

            if "part" in item_index:
                if i != 0:
                    if self.items_list[i - 1].split("__")[0] != item_index.split("__")[0]:
                        positions = []
                text = part_texts[item_index.split("__")[0]]

                if item_index.split("__")[0] not in json_content:
                    parts_text = ExtractItems.remove_multiple_lines(part_texts[item_index.split("__")[0].strip()])
                    json_content[item_index.split("__")[0]] = parts_text

            if "part" in self.items_list[i - 1] and item_index == "SIGNATURE":
                item_section = part_texts[item_index]
            else:
                item_section, positions = self.parse_item(text, item_index, next_item_list, positions)

            item_section = ExtractItems.remove_multiple_lines(item_section.strip())

            if item_index in self.items_to_extract:
                if item_section != "":
                    all_items_null = False

                if item_index == "SIGNATURE":
                    if self.include_signature:
                        json_content[f"{item_index}"] = item_section
                else:
                    if "part" in item_index:
                        json_content[item_index.split("__")[0] + "_item_" + item_index.split("__")[1]] = item_section
                    else:
                        json_content[f"item_{item_index}"] = item_section

        if all_items_null:
            LOGGER.info(f"\nCould not extract any item for {absolute_filename}")
            return None

        return json_content

    def process_filing(self, filing_metadata: Dict[str, Any]) -> int:
        """Process a filing by extracting items/sections and saving the content to a JSON file."""
        json_filename = f'{filing_metadata["filename"].split(".")[0]}.json'
        self.determine_items_to_extract(filing_metadata)
        absolute_json_filename = os.path.join(self.extracted_files_folder, filing_metadata["Type"], json_filename)

        if self.skip_extracted_filings and os.path.exists(absolute_json_filename):
            return 0

        json_content = self.extract_items(filing_metadata)

        if not os.path.isdir(os.path.join(self.extracted_files_folder, filing_metadata["Type"])):
            os.mkdir(os.path.join(self.extracted_files_folder, filing_metadata["Type"]))
            
        if json_content is not None:
            with open(absolute_json_filename, "w", encoding="utf-8") as filepath:
                json.dump(json_content, filepath, indent=4, ensure_ascii=False)

        return 1


# ============================================================================
# MAIN FUNCTION - COMBINES EXTRACTION AND CONVERSION
# ============================================================================

def main() -> None:
    """
    Main function that:
    1. Extracts items from SEC filings and saves as JSON
    2. Converts JSON files to CSV/Parquet format
    """
    with open("./config/config.json") as fin:
        config = json.load(fin)["extract_items"]

    filings_metadata_filepath = os.path.join(DATASET_DIR, config["filings_metadata_file"])

    if os.path.exists(filings_metadata_filepath):
        filings_metadata_df = pd.read_csv(filings_metadata_filepath, dtype=str)
        filings_metadata_df = filings_metadata_df.replace({np.nan: None})
    else:
        LOGGER.info(f'No such file "{filings_metadata_filepath}"')
        return

    if config["filing_types"]:
        filings_metadata_df = filings_metadata_df[filings_metadata_df["Type"].isin(config["filing_types"])]
    
    if len(filings_metadata_df) == 0:
        LOGGER.info(f"No filings to process for filing types {config['filing_types']}.")
        return

    raw_filings_folder = os.path.join(DATASET_DIR, config["raw_filings_folder"])
    if not os.path.isdir(raw_filings_folder):
        LOGGER.info(f'No such directory: "{raw_filings_folder}')
        return

    extracted_filings_folder = os.path.join(DATASET_DIR, config["extracted_filings_folder"])
    if not os.path.isdir(extracted_filings_folder):
        os.mkdir(extracted_filings_folder)

    # Create output folders
    parquet_folder = os.path.join(DATASET_DIR, config["parquet_folder"])
    if not os.path.isdir(parquet_folder):
        os.mkdir(parquet_folder)

    csv_folder = os.path.join(DATASET_DIR, config["csv_folder"])
    if not os.path.isdir(csv_folder):
        os.mkdir(csv_folder)

    merged_folder = os.path.join(DATASET_DIR, config["merged_parquet_file"])
    if not os.path.isdir(merged_folder):
        os.mkdir(merged_folder)

    extraction = ExtractItems(
        remove_tables=config["remove_tables"],
        items_to_extract=config["items_to_extract"],
        include_signature=config["include_signature"],
        raw_files_folder=raw_filings_folder,
        extracted_files_folder=extracted_filings_folder,
        skip_extracted_filings=config["skip_extracted_filings"],
    )

    LOGGER.info(f"Starting the structured JSON extraction from {len(filings_metadata_df)} unstructured EDGAR filings.")

    list_of_series = list(zip(*filings_metadata_df.iterrows()))[1]

    # STEP 1: Extract items and save as JSON
    with ProcessPool(processes=1) as pool:
        processed = list(
            tqdm(
                pool.imap(extraction.process_filing, list_of_series),
                total=len(list_of_series),
                ncols=100,
                desc="Extracting items"
            )
        )

    LOGGER.info("\nItem extraction is completed successfully.")
    LOGGER.info(f"{sum(processed)} files were processed.")
    LOGGER.info(f"Extracted filings are saved to: {extracted_filings_folder}")

    # STEP 2: Convert JSON files to CSV/Parquet
    LOGGER.info("\nStarting conversion of JSON files to CSV/Parquet format...")
    
    # Get all filing types from the extracted filings folder
    json_files = []
    filing_types_found = []
    
    # Check what filing type folders actually exist
    if os.path.exists(extracted_filings_folder):
        for item in os.listdir(extracted_filings_folder):
            item_path = os.path.join(extracted_filings_folder, item)
            if os.path.isdir(item_path):
                filing_types_found.append(item)
                # Get all JSON files in this folder
                for f in os.listdir(item_path):
                    if f.endswith(".json"):
                        json_files.append(os.path.join(item_path, f))
    
    if not json_files:
        LOGGER.info(f"No JSON files found in {extracted_filings_folder}")
        LOGGER.info(f"Filing type folders found: {filing_types_found}")
        return
    
    LOGGER.info(f"Found {len(json_files)} JSON files to convert across {len(filing_types_found)} filing types")

    # Create subfolder for parquet files by filing type
    converted_count = 0
    failed_count = 0
    
    for json_file in tqdm(json_files, desc="Converting to Parquet", ncols=100):
        try:
            #filing_type = Path(json_file).parent.name
            #output_folder = os.path.join(parquet_folder)
            
            if convert_json_to_parquet(
                json_path=json_file,
                csv_output_folder=os.path.join(csv_folder),
                parquet_output_folder=os.path.join(parquet_folder),
                min_year=config.get("min_year", 2021),
                max_year=config.get("max_year", 2025)
            ):
                converted_count += 1
            else:
                failed_count += 1
        except Exception as e:
            LOGGER.warning(f"Error converting {json_file}: {e}")
            failed_count += 1

    LOGGER.info(f"\nConversion completed.")
    LOGGER.info(f"{converted_count} JSON files were converted to CSV/Parquet format.")
    if failed_count > 0:
        LOGGER.info(f"{failed_count} files were skipped or failed conversion.")
    LOGGER.info(f"Parquet files are saved to: {parquet_folder}")

    # STEP 3: Merge all parquet files by filing type
    LOGGER.info("\nStarting to merge parquet files by filing type...")
    
    merge_count = 0
    for filing_type in filing_types_found:
        parquet_type_folder = os.path.join(parquet_folder)
        
        if not os.path.exists(parquet_type_folder):
            continue
            
        # Get all parquet files for this filing type
        parquet_files = [
            os.path.join(parquet_type_folder, f)
            for f in os.listdir(parquet_type_folder)
            if f.endswith(".parquet")
        ]
        
        if not parquet_files:
            LOGGER.info(f"No parquet files found for {filing_type}")
            continue
        
        LOGGER.info(f"Merging {len(parquet_files)} parquet files for {filing_type}...")
        
        try:
            # Use Polars for efficient merging
            dfs = []
            for pf in tqdm(parquet_files, desc=f"Reading {filing_type} parquets", ncols=100):
                try:
                    df = pl.read_parquet(pf)
                    dfs.append(df)
                except Exception as e:
                    LOGGER.warning(f"Failed to read {pf}: {e}")
            
            if dfs:
                # Concatenate all dataframes
                merged_df = pl.concat(dfs, how="vertical")
                
                # Sort by docID and sentence_index for better organization
                merged_df = merged_df.sort(["docID", "section_ID", "sentence_index"])
                
                # Save merged file to merged_folder 
                #output_folder = os.path.join(extracted_filings_folder, filing_type)
                output_folder = merged_folder
                os.makedirs(output_folder, exist_ok=True)
                
                #merged_filename = f"{filing_type}_merged_.parquet"
                merged_filename = "finrag_sec_incremental_stg_data.parquet"
                merged_filepath = os.path.join(output_folder, merged_filename)
                
                # Write using Polars (more efficient than pandas)
                merged_df.write_parquet(merged_filepath, compression="snappy")
                
                # # Also save as CSV for convenience
                # csv_filepath = os.path.join(output_folder, f"{filing_type}_merged.csv")
                # merged_df.write_csv(csv_filepath)
                
                LOGGER.info(f"✓ Merged {filing_type}: {len(merged_df)} total sentences")
                LOGGER.info(f"  Parquet: {merged_filepath}")
                LOGGER.info(f"  CSV: {csv_filepath}")
                
                merge_count += 1
        except Exception as e:
            LOGGER.error(f"Failed to merge {filing_type} files: {e}")
    
    LOGGER.info(f"\n{'='*80}")
    LOGGER.info(f"PIPELINE COMPLETED SUCCESSFULLY")
    LOGGER.info(f"{'='*80}")
    LOGGER.info(f"Extracted: {sum(processed)} filings")
    LOGGER.info(f"Converted: {converted_count} JSON files to parquet")
    LOGGER.info(f"Merged: {merge_count} filing types into single files")
    LOGGER.info(f"\nFinal merged files location: {extracted_filings_folder}")
    LOGGER.info(f"Individual parquet files location: {parquet_folder}")
    LOGGER.info(f"{'='*80}")
    
if __name__ == "__main__":
    main()