import pandas as pd
import numpy as np
from utils.helpers import safe_div
from scripts import config
from utils.helpers import setup_logger
logger = setup_logger()

def process_company_data(ticker, facts):
    """Extract metrics and derived KPIs for one company."""
    data = []
    for label, tag_info in config.XBRL_TAGS.items():
        tag = tag_info.get("tag")
        if not tag:
            continue
        val_list = facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
        for v in val_list:
            if v.get("form") == "10-K" and v.get("fp") == "FY":
                entry = {
                    "company": ticker,
                    "ticker": ticker,
                    "year": int(v.get("fy")),
                    "metric": label,
                    "value": v.get("val"),
                    "unit": tag_info.get("unit", "USD"),
                    "description": tag_info.get("description", "")
                }
                data.append(entry)
    df = pd.DataFrame(data)
    if df.empty:
        return []

    # Derived metrics
    df_pivot = df.pivot_table(index="year", columns="metric", values="value", aggfunc="last").reset_index()
    df_pivot["Return on Assets (ROA) %"] = safe_div(df_pivot["income_stmt_Net Income"], df_pivot["balance_sheet_Total Assets"]) * 100
    df_pivot["Gross Profit Margin %"] = safe_div(df_pivot["income_stmt_Gross Profit"], df_pivot["income_stmt_Revenue"]) * 100

    processed_data = df_pivot.melt(id_vars=["year"], var_name="metric", value_name="value")
    processed_data["ticker"] = ticker
    return processed_data.to_dict(orient="records")
