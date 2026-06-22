"""
SEC 10-K Intelligence Assistant — Version 2
Stack: Streamlit + ChromaDB + OpenAI Embeddings + SEC EDGAR public filings

New in Version 2:
- Adds section tagging for SEC 10-K chunks
- Adds section filter dropdown in Streamlit
- Allows targeted retrieval for Risk Factors, Business, Cybersecurity, Competition, Legal / Regulatory, and Financial Risks

Run:
  py -m streamlit run app.py

Required .env:
  OPENAI_API_KEY=your_key_here
  SEC_USER_AGENT=Your Name your.email@example.com

Notes:
- Uses public SEC EDGAR 10-K filings only.
- Keep .env private and never upload it to GitHub.
- ChromaDB persists locally in ./chroma_db.
"""

import os
import re
import time
from typing import Dict, List, Tuple

import chromadb
import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

from src.config import (
    OPENAI_API_KEY,
    SEC_USER_AGENT,
    EMBEDDING_MODEL,
    CHAT_MODEL,
)

if not OPENAI_API_KEY:
    st.warning("Please set OPENAI_API_KEY in your environment or .env file.")

client = OpenAI(api_key=OPENAI_API_KEY)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="sec_10k_filings_v2")

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

SECTION_OPTIONS = [
    "All Sections",
    "Business",
    "Risk Factors",
    "Cybersecurity",
    "Competition",
    "Legal / Regulatory",
    "Financial Risks",
]


def clean_text(raw_html: str) -> str:
    """Convert SEC filing HTML into readable text."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "table"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def detect_section(chunk: str) -> str:
    """
    Lightweight section classifier for MVP Version 2.
    This does not perfectly parse formal SEC item boundaries, but it gives useful section metadata for filtering.
    """
    text = chunk.lower()

    risk_terms = [
        "risk factors",
        "risks related",
        "could adversely affect",
        "material adverse effect",
        "uncertainties",
    ]
    cyber_terms = [
        "cybersecurity",
        "cyber security",
        "data security",
        "information security",
        "security breach",
        "ransomware",
        "unauthorized access",
    ]
    competition_terms = [
        "competition",
        "competitive",
        "competitors",
        "compete",
        "market share",
    ]
    legal_terms = [
        "legal proceedings",
        "regulatory",
        "regulation",
        "compliance",
        "laws and regulations",
        "litigation",
        "government investigation",
    ]
    financial_terms = [
        "financial condition",
        "liquidity",
        "cash flows",
        "interest rates",
        "credit risk",
        "market risk",
        "foreign exchange",
        "revenue",
        "operating results",
    ]
    business_terms = [
        "business",
        "products and services",
        "customers",
        "operations",
        "segments",
        "strategy",
    ]

    def has_any(terms: List[str]) -> bool:
        return any(term in text for term in terms)

    # Priority matters. More specific sections first.
    if has_any(cyber_terms):
        return "Cybersecurity"
    if has_any(risk_terms):
        return "Risk Factors"
    if has_any(legal_terms):
        return "Legal / Regulatory"
    if has_any(competition_terms):
        return "Competition"
    if has_any(financial_terms):
        return "Financial Risks"
    if has_any(business_terms):
        return "Business"

    return "General"


def chunk_text(text: str, chunk_size: int = 3500, overlap: int = 500) -> List[str]:
    """Simple character-based chunking for MVP. Later replace with token-aware chunking."""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def get_embedding(text: str) -> List[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


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


def download_filing_text(ticker: str) -> Dict[str, str]:
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
        "text": clean_text(response.text),
    }


def ingest_10k(ticker: str) -> int:
    """Download, chunk, classify, embed, and store a company's latest 10-K."""
    filing = download_filing_text(ticker)
    chunks = chunk_text(filing["text"])

    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        section_name = detect_section(chunk)
        chunk_id = f"v2_{ticker}_{filing['accession']}_{i}"

        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append(
            {
                "ticker": ticker,
                "cik": filing["cik"],
                "accession": filing["accession"],
                "filing_date": filing["filing_date"],
                "source_url": filing["source_url"],
                "chunk_number": i,
                "section_name": section_name,
            }
        )

    embeddings = []
    batch_size = 64
    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]
        embeddings.extend(get_embeddings_batch(batch))

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return len(chunks)


def build_where_filter(ticker: str, selected_section: str) -> Dict:
    """Build ChromaDB metadata filter."""
    if selected_section == "All Sections":
        return {"ticker": ticker}

    return {
        "$and": [
            {"ticker": ticker},
            {"section_name": selected_section},
        ]
    }


def retrieve_context(question: str, ticker: str, selected_section: str, top_k: int = 5) -> List[Dict]:
    question_embedding = get_embedding(question)
    where_filter = build_where_filter(ticker, selected_section)

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=top_k,
        where=where_filter,
    )

    contexts = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc, meta, distance in zip(docs, metas, distances):
        contexts.append({"text": doc, "metadata": meta, "distance": distance})

    return contexts


def generate_answer(question: str, contexts: List[Dict], selected_section: str) -> str:
    context_block = "\n\n".join(
        [
            f"Source {i + 1} | Ticker: {ctx['metadata']['ticker']} | "
            f"Filing Date: {ctx['metadata']['filing_date']} | "
            f"Section: {ctx['metadata'].get('section_name', 'General')} | "
            f"Chunk: {ctx['metadata']['chunk_number']}\n{ctx['text']}"
            for i, ctx in enumerate(contexts)
        ]
    )

    prompt = f"""
You are a careful financial document assistant. Answer the user's question using only the provided SEC 10-K context.

Selected section filter: {selected_section}

Rules:
- Do not invent facts.
- If the answer is not in the context, say that the filing context provided does not contain enough information.
- Keep the answer business-friendly and concise.
- Include source references like [Source 1], [Source 2] when supporting claims.
- If a section filter is selected, focus your answer on that section.

User question:
{question}

SEC 10-K context:
{context_block}
"""

    response = client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
    )
    return response.output_text


st.set_page_config(page_title="SEC 10-K Intelligence Assistant V2", layout="wide")

st.title("SEC 10-K Intelligence Assistant — V2")
st.caption("Public SEC filings + OpenAI embeddings + ChromaDB + Streamlit + section filters")

with st.sidebar:
    st.header("1. Ingest Filing")
    selected_ticker = st.selectbox("Select company", list(COMPANIES.keys()))

    if st.button("Download & index latest 10-K"):
        with st.spinner(f"Downloading and indexing latest 10-K for {selected_ticker}..."):
            try:
                chunk_count = ingest_10k(selected_ticker)
                st.success(f"Indexed {chunk_count} chunks for {selected_ticker} with section metadata.")
            except Exception as exc:
                st.error(f"Ingestion failed: {exc}")

    st.divider()
    st.header("2. Search Settings")
    selected_section = st.selectbox("Section filter", SECTION_OPTIONS)
    top_k = st.slider("Retrieved chunks", min_value=3, max_value=10, value=5)

st.subheader("Ask a question about the selected 10-K")

question = st.text_input(
    "Question",
    placeholder="Example: What are the company's main risk factors?",
)

if st.button("Ask") and question:
    with st.spinner("Retrieving relevant filing sections and generating answer..."):
        try:
            contexts = retrieve_context(
                question=question,
                ticker=selected_ticker,
                selected_section=selected_section,
                top_k=top_k,
            )

            if not contexts:
                st.warning(
                    "No matching chunks found. Try selecting 'All Sections' or re-index the filing for Version 2."
                )
            else:
                answer = generate_answer(question, contexts, selected_section)

                st.markdown("### Answer")
                st.write(answer)

                st.markdown("### Retrieved Sources")
                for i, ctx in enumerate(contexts, start=1):
                    meta = ctx["metadata"]
                    section = meta.get("section_name", "General")
                    with st.expander(
                        f"Source {i} — {meta['ticker']} | Section: {section} | Chunk {meta['chunk_number']}"
                    ):
                        st.write(ctx["text"][:3000])
                        st.markdown(f"[Open SEC filing]({meta['source_url']})")
                        st.caption(f"Distance: {ctx['distance']}")
        except Exception as exc:
            st.error(f"Question answering failed: {exc}")

st.divider()
st.markdown(
    """
### Version 2 Features Included
- Downloads latest public 10-K filing from SEC EDGAR
- Parses filing HTML into text
- Splits text into chunks
- Tags chunks with lightweight section metadata
- Creates OpenAI embeddings
- Stores chunks in local ChromaDB
- Adds section filter dropdown
- Retrieves relevant chunks by semantic similarity and metadata filter
- Generates source-grounded answers

### Section Filters
- All Sections
- Business
- Risk Factors
- Cybersecurity
- Competition
- Legal / Regulatory
- Financial Risks

### Next Version Ideas
- Add formal SEC Item parsing: Item 1, Item 1A, Item 7, Item 7A, Item 8
- Add company comparison mode
- Add PostgreSQL metadata storage
- Add Docker deployment
- Add AWS S3 for raw filing storage
- Add evaluation metrics for retrieval quality
"""
)
