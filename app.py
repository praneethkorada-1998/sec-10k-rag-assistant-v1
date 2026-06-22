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

import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from src.parser import SECTION_OPTIONS, chunk_text, clean_text, detect_section
from src.embeddings import get_embedding, get_embeddings_batch
from src.vector_store import retrieve_context, upsert_chunks
from src.rag import generate_answer
from src.config import OPENAI_API_KEY

from src.config import (
    OPENAI_API_KEY,
    SEC_USER_AGENT,
    EMBEDDING_MODEL,
    CHAT_MODEL,
)

from src.sec_client import COMPANIES, download_filing_html

if not OPENAI_API_KEY:
    st.warning("Please set OPENAI_API_KEY in your environment or .env file.")

def ingest_10k(ticker: str) -> int:
    """Download, chunk, classify, embed, and store a company's latest 10-K."""
    filing = download_filing_html(ticker)
    filing["text"] = clean_text(filing["html"])
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

    upsert_chunks(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return len(chunks)

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
