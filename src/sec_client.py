import time
from typing import Dict, Tuple

import requests

from src.config import SEC_USER_AGENT

HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

ARCHIVES_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}

COMPANIES: Dict[str, str] = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "TSLA": "0001318605",
    "JPM": "0000019617",
    "UNH": "0000731766",
    "WMT": "0000104169",
}


def fetch_latest_10k_metadata(ticker: str) -> Tuple[str, str, str, str]:
    """Return accession number, primary document, filing date, and filing URL."""
    cik = COMPANIES[ticker]
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    response = requests.get(submissions_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()

    recent = data["filings"]["recent"]
    forms = recent["form"]

    for idx, form in enumerate(forms):
        if form == "10-K":
            accession = recent["accessionNumber"][idx]
            primary_doc = recent["primaryDocument"][idx]
            filing_date = recent["filingDate"][idx]
            accession_no_dashes = accession.replace("-", "")
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession_no_dashes}/{primary_doc}"
            )
            return accession, primary_doc, filing_date, filing_url

    raise ValueError(f"No 10-K filing found for {ticker}.")


def download_filing_html(ticker: str) -> Dict[str, str]:
    """Download latest 10-K filing HTML and return raw HTML with metadata."""
    accession, primary_doc, filing_date, filing_url = fetch_latest_10k_metadata(ticker)
    time.sleep(0.2)

    response = requests.get(filing_url, headers=ARCHIVES_HEADERS, timeout=60)
    response.raise_for_status()

    return {
        "ticker": ticker,
        "cik": COMPANIES[ticker],
        "accession": accession,
        "primary_doc": primary_doc,
        "filing_date": filing_date,
        "source_url": filing_url,
        "html": response.text,
    }