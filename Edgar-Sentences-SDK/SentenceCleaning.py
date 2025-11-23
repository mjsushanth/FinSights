import pandas as pd
import re
import unicodedata
import ftfy

# -----------------------------
# Files
# -----------------------------
INPUT_FILE = "scripts/sentence/sec_rag_data/10k_sentences_extracted.csv"
OUTPUT_FILE = "scripts/sentence/sec_rag_data/10k_sentences_cleaned.csv"
OUTPUT_FILE_PARQUET = "scripts/sentence/sec_rag_data/10k_sentences_cleaned.parquet"

# -----------------------------
# Mojibake triggers and replacements
# -----------------------------
MOJIBAKE_TRIGGERS = [
    "â", "‚Ä", "Â", "ñ", "™", 
    "¬Æ",
    "Äî"
]

UTF8_REPLACEMENTS = {
    "‚Ä¢": "•",
    "‚Äî": "—",
    "‚Äì": "-",
    "‚Äú": "\"",
    "‚Äù": "\"",
    "â€™": "'",
    "â€œ": "\"",
    "â€\x9d": "\"",
    "â€˜": "'",
    "â€¦": "...",
    "Â": "",
    "¬Æ": "",
    "Äî": "—",
    "ñ™": "",
    "ñ": "n",
    "™": "",
}

# -----------------------------
# Cleaning function
# -----------------------------
def clean_text(s):
    if pd.isna(s):
        return ""

    s = str(s)

    # 1) Detect mojibake and fix encoding (latin1 -> utf-8)
    if any(t in s for t in MOJIBAKE_TRIGGERS):
        try:
            # This attempts to reverse the common Latin-1 mis-decoding
            s = s.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
        except:
            pass

    # 2) Automatic unicode fix (ftfy is excellent at this)
    s = ftfy.fix_text(s)

    # 3) Manual replacements
    for bad, good in UTF8_REPLACEMENTS.items():
        s = s.replace(bad, good)

    # 4) Remove separators
    s = re.sub(r"[-_=]{4,}", " ", s)

    # 5) Normalize unicode
    s = unicodedata.normalize("NFKC", s)

    # 6) Remove control characters
    s = re.sub(r"[\x00-\x1F\x7F]", " ", s)

    # 7) Replace newlines with space
    s = s.replace("\n", " ").replace("\r", " ")

    # 8) Collapse multiple spaces
    s = re.sub(r"\s{2,}", " ", s)

    return s.strip()

# -----------------------------
# Main logic
# -----------------------------
def main():
    print(f"📂 Loading {INPUT_FILE} ...")
    df = pd.read_csv(INPUT_FILE, encoding="utf-8")
    
    print(f"✅ Loaded {len(df)} rows")
    print(f"📊 Columns: {list(df.columns)}")

    # Section name mapping (Item 1 -> Business, etc.)
    SECTION_NAME_MAPPING = {
        "Item 1": "Business",
        "Item 1A": "Risk Factors",
        "Item 2": "Properties",
        "Item 3": "Legal Proceedings",
        "Item 4": "Mine Safety Disclosures",
        "Item 5": "Market for Stock",
        "Item 7": "Management Discussion and Analysis (MD&A)",
        "Item 7A": "Quantitative and Qualitative Disclosures About Market Risk",
        "Item 8": "Financial Statements and Supplementary Data",
        "Item 9": "Changes in and Disagreements With Accountants",
        "Item 9A": "Controls and Procedures",
        "Item 9B": "Other Information",
        "Item 10": "Directors, Officers & Governance",
        "Item 11": "Executive Compensation",
        "Item 12": "Security Ownership",
        "Item 13": "Certain Relationships and Related Transactions",
        "Item 14": "Principal Accounting Fees and Services",
        "Item 15": "Exhibits List"
    }

    # Check which column exists and use it
    if "section_name" in df.columns:
        print("🏷️  Mapping section names...")
        # Create a new column with descriptive names
        df["section_description"] = df["section_name"].map(SECTION_NAME_MAPPING)
        # Fill any unmapped values with the original section_name
        df["section_description"] = df["section_description"].fillna(df["section_name"])
        print(f"   Section distribution:\n{df['section_name'].value_counts()}")
    elif "section_item" in df.columns:
        print("🏷️  Found 'section_item' column, using that...")
        df["section_description"] = df["section_item"].map(SECTION_NAME_MAPPING)
        df["section_description"] = df["section_description"].fillna(df["section_item"])
    else:
        print("⚠️  No section column found - skipping section mapping")

    # Clean sentences
    print("🧼 Cleaning sentences... (vectorized)")
    initial_count = len(df)
    df["sentence"] = df["sentence"].apply(clean_text)
    
    # Remove empty sentences after cleaning
    df = df[df["sentence"].str.len() > 0].copy()
    print(f"   Removed {initial_count - len(df)} empty sentences after cleaning")

    # Drop duplicates
    print("🔍 Removing duplicates...")
    before_dedup = len(df)
    df.drop_duplicates(subset=["sentence", "cik", "section_name"], inplace=True)
    print(f"   Removed {before_dedup - len(df)} duplicate rows")

    # Save to CSV
    print(f"\n💾 Saving to CSV: {OUTPUT_FILE}")
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"   ✅ Saved {len(df)} rows")

    # Save to Parquet
    print(f"\n💾 Saving to Parquet: {OUTPUT_FILE_PARQUET}")
    df.to_parquet(OUTPUT_FILE_PARQUET, index=False)
    print(f"   ✅ Saved {len(df)} rows")

    # Summary statistics
    print("\n📊 Summary Statistics:")
    print(f"   Total sentences: {len(df)}")
    print(f"   Total companies: {df['cik'].nunique() if 'cik' in df.columns else 'N/A'}")
    print(f"   Average sentence length: {df['sentence'].str.len().mean():.1f} chars")
    
    if "section_name" in df.columns:
        print(f"\n📋 Sections extracted:")
        print(df["section_name"].value_counts())


if __name__ == "__main__":
    main()