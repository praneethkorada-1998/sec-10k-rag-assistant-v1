"""
SEC 10-K Intelligence Assistant — MVP Version
Stack: Streamlit + ChromaDB + OpenAI Embeddings + SEC EDGAR public filings

Run:
  pip install streamlit openai chromadb requests beautifulsoup4 python-dotenv
  export OPENAI_API_KEY="your_key_here"
  export SEC_USER_AGENT="Your Name your.email@example.com"
  streamlit run app.py

Notes:
- Uses public SEC EDGAR 10-K filings only.
- Set a real SEC_USER_AGENT. SEC asks automated tools to identify themselves.
- This MVP keeps everything local in ./chroma_db.
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

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "SEC 10-K RAG Demo contact@example.com")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")

if not OPENAI_API_KEY:
    st.warning("Please set OPENAI_API_KEY in your environment or .env file.")

client = OpenAI(api_key=OPENAI_API_KEY)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="sec_10k_filings")

HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}
ARCHIVES_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}

# Starter companies. Add more later.
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


def clean_text(raw_html: str) -> str:
    """Convert filing HTML into readable text."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "table"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


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
    time.sleep(0.2)  # polite delay for SEC servers

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
    """Download, chunk, embed, and store a company's latest 10-K."""
    filing = download_filing_text(ticker)
    chunks = chunk_text(filing["text"])

    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        chunk_id = f"{ticker}_{filing['accession']}_{i}"
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
            }
        )

    # Batch embeddings to reduce API calls.
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


def retrieve_context(question: str, ticker: str, top_k: int = 5) -> List[Dict]:
    question_embedding = get_embedding(question)
    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=top_k,
        where={"ticker": ticker},
    )

    contexts = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc, meta, distance in zip(docs, metas, distances):
        contexts.append({"text": doc, "metadata": meta, "distance": distance})

    return contexts


def generate_answer(question: str, contexts: List[Dict]) -> str:
    context_block = "\n\n".join(
        [
            f"Source {i + 1} | Ticker: {ctx['metadata']['ticker']} | "
            f"Filing Date: {ctx['metadata']['filing_date']} | "
            f"Chunk: {ctx['metadata']['chunk_number']}\n{ctx['text']}"
            for i, ctx in enumerate(contexts)
        ]
    )

    prompt = f"""
You are a careful financial document assistant. Answer the user's question using only the provided SEC 10-K context.

Rules:
- Do not invent facts.
- If the answer is not in the context, say that the filing context provided does not contain enough information.
- Keep the answer business-friendly and concise.
- Include source references like [Source 1], [Source 2] when supporting claims.

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


st.set_page_config(page_title="SEC 10-K Intelligence Assistant", layout="wide")

st.title("SEC 10-K Intelligence Assistant")
st.caption("MVP: public SEC filings + OpenAI embeddings + ChromaDB + Streamlit")

with st.sidebar:
    st.header("1. Ingest Filing")
    selected_ticker = st.selectbox("Select company", list(COMPANIES.keys()))

    if st.button("Download & index latest 10-K"):
        with st.spinner(f"Downloading and indexing latest 10-K for {selected_ticker}..."):
            try:
                chunk_count = ingest_10k(selected_ticker)
                st.success(f"Indexed {chunk_count} chunks for {selected_ticker}.")
            except Exception as exc:
                st.error(f"Ingestion failed: {exc}")

    st.divider()
    st.header("2. Search Settings")
    top_k = st.slider("Retrieved chunks", min_value=3, max_value=10, value=5)

st.subheader("Ask a question about the selected 10-K")
question = st.text_input(
    "Question",
    placeholder="Example: What are the company's main risk factors?",
)

if st.button("Ask") and question:
    with st.spinner("Retrieving relevant filing sections and generating answer..."):
        try:
            contexts = retrieve_context(question, selected_ticker, top_k=top_k)
            if not contexts:
                st.warning("No indexed chunks found. Please ingest the filing first.")
            else:
                answer = generate_answer(question, contexts)
                st.markdown("### Answer")
                st.write(answer)

                st.markdown("### Retrieved Sources")
                for i, ctx in enumerate(contexts, start=1):
                    meta = ctx["metadata"]
                    with st.expander(f"Source {i} — {meta['ticker']} | Chunk {meta['chunk_number']}"):
                        st.write(ctx["text"][:3000])
                        st.markdown(f"[Open SEC filing]({meta['source_url']})")
                        st.caption(f"Distance: {ctx['distance']}")
        except Exception as exc:
            st.error(f"Question answering failed: {exc}")

st.divider()
st.markdown(
    """
### MVP Features Included
- Downloads latest public 10-K filing from SEC EDGAR
- Parses filing HTML into text
- Splits text into chunks
- Creates OpenAI embeddings
- Stores chunks in local ChromaDB
- Retrieves relevant chunks by semantic similarity
- Generates source-grounded answers

### Next Version Ideas
- Add company comparison mode
- Add section detection: Business, Risk Factors, MD&A, Cybersecurity
- Add PostgreSQL metadata storage
- Add Docker deployment
- Add AWS S3 for raw filing storage
- Add evaluation questions and retrieval accuracy checks
"""
)
