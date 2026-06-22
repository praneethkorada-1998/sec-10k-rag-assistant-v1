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
import streamlit as st

from src.config import OPENAI_API_KEY
from src.ingestion import ingest_10k
from src.parser import SECTION_OPTIONS
from src.rag import generate_answer
from src.sec_client import COMPANIES
from src.vector_store import retrieve_context


if not OPENAI_API_KEY:
    st.warning("Please set OPENAI_API_KEY in your environment or .env file.")

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
### Version 3 Features Included
- Downloads the latest public 10-K filing from SEC EDGAR
- Parses and splits filing content into searchable chunks
- Tags chunks with section metadata
- Creates OpenAI embeddings
- Stores and retrieves chunks using ChromaDB
- Generates source-grounded answers
- Uses modular configuration, SEC client, parsing, embedding, vector-store, RAG, and ingestion components
- Includes Docker preparation and evaluation questions

### Section Filters
- All Sections
- Business
- Risk Factors
- Cybersecurity
- Competition
- Legal / Regulatory
- Financial Risks

### Next Version Ideas
- Add formal SEC Item parsing
- Add company comparison mode
- Add PostgreSQL metadata storage
- Add AWS S3 raw-filing storage
- Add automated retrieval evaluation
"""
)