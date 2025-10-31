import requests
import json
import time
from sec_edgar_api import EdgarClient
from datetime import date
from src_metrics import config
from utils.helpers import setup_logger
logger = setup_logger()

def extract_companies(n=None):
    """Fetch company tickers and CIKs from SEC JSON."""
    headers = {'User-Agent': config.USER_AGENT}
    url = 'https://www.sec.gov/files/company_tickers.json'

    res = requests.get(url, headers=headers)
    res.raise_for_status()
    data = res.json()

    companies = {}
    values_list = list(data.values())[:n] if n else data.values()
    for entry in values_list:
        ticker = entry.get("ticker")
        cik = str(entry.get("cik_str")).zfill(10)
        companies[ticker] = cik
    return companies


def fetch_raw_facts(cik, retries=3, sleep_time=2):
    """Fetch raw company facts (unprocessed SEC data)."""
    client = EdgarClient(user_agent=config.USER_AGENT)
    for attempt in range(retries):
        try:
            return client.get_company_facts(cik=cik)
        except Exception as e:
            print(f"Attempt {attempt+1} failed for {cik}: {e}")
            if attempt < retries - 1:
                time.sleep(sleep_time * (attempt + 1))
    return None


def ingest_data(n=2):
    companies = extract_companies(n)
    raw_data = {}

    for ticker, cik in companies.items():
        print(f"Fetching data for {ticker}...")
        facts = fetch_raw_facts(cik)
        if facts:
            raw_data[ticker] = facts
        time.sleep(2)
    return raw_data
