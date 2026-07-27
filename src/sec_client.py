import time
from typing import Dict, List, Tuple

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


def fetch_10k_filings(ticker: str, limit: int = 5) -> List[Dict[str, str]]:
    """Return historical 10-K filing metadata for a company."""
    cik = COMPANIES[ticker]
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    response = requests.get(submissions_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()

    recent = data["filings"]["recent"]
    filings: List[Dict[str, str]] = []

    for idx, form in enumerate(recent["form"]):
        if form != "10-K":
            continue

        accession = recent["accessionNumber"][idx]
        primary_doc = recent["primaryDocument"][idx]
        filing_date = recent["filingDate"][idx]
        report_date = recent["reportDate"][idx]
        filing_year = report_date[:4] if report_date else filing_date[:4]
        accession_no_dashes = accession.replace("-", "")

        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{accession_no_dashes}/{primary_doc}"
        )

        filings.append(
            {
                "ticker": ticker,
                "cik": cik,
                "accession": accession,
                "primary_doc": primary_doc,
                "filing_date": filing_date,
                "report_date": report_date,
                "filing_year": filing_year,
                "source_url": filing_url,
            }
        )

        if len(filings) >= limit:
            break

    if not filings:
        raise ValueError(f"No 10-K filings found for {ticker}.")

    return filings


def fetch_latest_10k_metadata(ticker: str) -> Tuple[str, str, str, str]:
    """Return accession number, primary document, filing date, and filing URL."""
    latest_filing = fetch_10k_filings(ticker, limit=1)[0]

    return (
        latest_filing["accession"],
        latest_filing["primary_doc"],
        latest_filing["filing_date"],
        latest_filing["source_url"],
    )


def download_filing_by_accession(
    ticker: str,
    accession: str,
) -> Dict[str, str]:
    """Download a selected historical 10-K filing."""
    filings = fetch_10k_filings(ticker, limit=10)

    selected_filing = next(
        (
            filing
            for filing in filings
            if filing["accession"] == accession
        ),
        None,
    )

    if selected_filing is None:
        raise ValueError(
            f"10-K accession {accession} was not found for {ticker}."
        )

    time.sleep(0.2)

    response = requests.get(
        selected_filing["source_url"],
        headers=ARCHIVES_HEADERS,
        timeout=60,
    )
    response.raise_for_status()

    return {
        **selected_filing,
        "html": response.text,
    }


def download_filing_html(ticker: str) -> Dict[str, str]:
    """Download the latest 10-K filing and preserve the existing workflow."""
    latest_filing = fetch_10k_filings(ticker, limit=1)[0]
    return download_filing_by_accession(
        ticker,
        latest_filing["accession"],
    )