"""
SEC 10-K Intelligence Assistant - Version 4
Stack: Streamlit + ChromaDB + OpenAI Embeddings + SEC EDGAR public filings

New in Version 4:
- Adds Company Comparison Mode
- Compares two companies using retrieved SEC 10-K chunks
- Supports section-filtered comparison for Risk Factors, Cybersecurity,
  Competition, Legal / Regulatory, Financial Risks, and Business

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
from src.rag import generate_answer, generate_comparison_answer
from src.sec_client import COMPANIES
from src.vector_store import retrieve_context


if not OPENAI_API_KEY:
    st.warning("Please set OPENAI_API_KEY in your environment or .env file.")

st.set_page_config(
    page_title="SEC Filing Intelligence Platform ",
    layout="wide",
)

st.title("SEC Filing Intelligence Platform")
st.caption(
    "Data-engineered SEC filing ingestion, formal item parsing, semantic retrieval, source-grounded answers, and company comparison"
)

with st.sidebar:
    st.header("1. Ingest Filing")
    selected_ticker = st.selectbox("Select company", list(COMPANIES.keys()))

    if st.button("Download & index latest 10-K"):
        with st.spinner(f"Downloading and indexing latest 10-K for {selected_ticker}..."):
            try:
                chunk_count = ingest_10k(selected_ticker)
                st.success(
                    f"Indexed {chunk_count} chunks for {selected_ticker} with section metadata."
                )
            except Exception as exc:
                st.error(f"Ingestion failed: {exc}")

    st.divider()
    st.header("2. Search Settings")
    selected_section = st.selectbox("Section filter", SECTION_OPTIONS)
    top_k = st.slider("Retrieved chunks per company", min_value=3, max_value=10, value=5)

single_tab, comparison_tab = st.tabs(["Single Company Q&A", "Company Comparison"])

with single_tab:
    st.subheader("Ask a question about one company's 10-K")

    question = st.text_input(
        "Question",
        placeholder="Example: What are the company's main risk factors?",
        key="single_question",
    )

    if st.button("Ask", key="single_ask") and question:
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
                        "No matching chunks found. Try selecting 'All Sections' or re-index the filing."
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
                            f"Source {i} - {meta['ticker']} | Section: {section} | Chunk {meta['chunk_number']}"
                        ):
                            st.write(ctx["text"][:3000])
                            st.markdown(f"[Open SEC filing]({meta['source_url']})")
                            st.caption(f"Distance: {ctx['distance']}")
            except Exception as exc:
                st.error(f"Question answering failed: {exc}")

with comparison_tab:
    st.subheader("Compare two companies using their SEC 10-K filings")

    col1, col2 = st.columns(2)

    with col1:
        ticker_a = st.selectbox(
            "Company A",
            list(COMPANIES.keys()),
            index=0,
            key="ticker_a",
        )

    with col2:
        ticker_b = st.selectbox(
            "Company B",
            list(COMPANIES.keys()),
            index=1 if len(COMPANIES) > 1 else 0,
            key="ticker_b",
        )

    if ticker_a == ticker_b:
        st.info("Choose two different companies for comparison.")

    if st.button("Download & index both companies", key="ingest_both"):
        if ticker_a == ticker_b:
            st.warning("Please choose two different companies first.")
        else:
            try:
                with st.spinner(f"Indexing latest 10-K for {ticker_a}..."):
                    count_a = ingest_10k(ticker_a)

                with st.spinner(f"Indexing latest 10-K for {ticker_b}..."):
                    count_b = ingest_10k(ticker_b)

                st.success(
                    f"Indexed {count_a} chunks for {ticker_a} and {count_b} chunks for {ticker_b}."
                )
            except Exception as exc:
                st.error(f"Comparison ingestion failed: {exc}")

    comparison_question = st.text_input(
        "Comparison question",
        placeholder="Example: Compare the main risk factors between these two companies.",
        key="comparison_question",
    )

    if st.button("Compare", key="compare_button") and comparison_question:
        if ticker_a == ticker_b:
            st.warning("Please choose two different companies for comparison.")
        else:
            with st.spinner("Retrieving both filings and generating comparison..."):
                try:
                    contexts_a = retrieve_context(
                        question=comparison_question,
                        ticker=ticker_a,
                        selected_section=selected_section,
                        top_k=top_k,
                    )

                    contexts_b = retrieve_context(
                        question=comparison_question,
                        ticker=ticker_b,
                        selected_section=selected_section,
                        top_k=top_k,
                    )

                    if not contexts_a or not contexts_b:
                        st.warning(
                            "Missing retrieved chunks for one or both companies. Try indexing both companies or selecting 'All Sections'."
                        )
                    else:
                        comparison_answer = generate_comparison_answer(
                            question=comparison_question,
                            ticker_a=ticker_a,
                            contexts_a=contexts_a,
                            ticker_b=ticker_b,
                            contexts_b=contexts_b,
                            selected_section=selected_section,
                        )

                        st.markdown("### Comparison Answer")
                        st.write(comparison_answer)

                        source_col_a, source_col_b = st.columns(2)

                        with source_col_a:
                            st.markdown(f"### {ticker_a} Sources")
                            for i, ctx in enumerate(contexts_a, start=1):
                                meta = ctx["metadata"]
                                section = meta.get("section_name", "General")
                                with st.expander(
                                    f"A Source {i} - {meta['ticker']} | Section: {section} | Chunk {meta['chunk_number']}"
                                ):
                                    st.write(ctx["text"][:2500])
                                    st.markdown(f"[Open SEC filing]({meta['source_url']})")
                                    st.caption(f"Distance: {ctx['distance']}")

                        with source_col_b:
                            st.markdown(f"### {ticker_b} Sources")
                            for i, ctx in enumerate(contexts_b, start=1):
                                meta = ctx["metadata"]
                                section = meta.get("section_name", "General")
                                with st.expander(
                                    f"B Source {i} - {meta['ticker']} | Section: {section} | Chunk {meta['chunk_number']}"
                                ):
                                    st.write(ctx["text"][:2500])
                                    st.markdown(f"[Open SEC filing]({meta['source_url']})")
                                    st.caption(f"Distance: {ctx['distance']}")
                except Exception as exc:
                    st.error(f"Company comparison failed: {exc}")

st.divider()

st.markdown(
    """
### Version 4 Features Included
- Downloads the latest public 10-K filing from SEC EDGAR
- Parses and splits filing content into searchable chunks
- Tags chunks with section metadata
- Creates OpenAI embeddings
- Stores and retrieves chunks using ChromaDB
- Generates source-grounded single-company answers
- Adds company comparison mode
- Compares two companies across selected 10-K sections
- Displays retrieved sources separately for each company
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

### Strong Comparison Examples
- Compare the main risk factors between these two companies.
- How do these companies describe cybersecurity risks differently?
- Compare the competitive pressures discussed by both companies.
- What legal or regulatory risks are similar across both filings?
- Which company appears more exposed to financial risk based on the retrieved sections?

### Next Version Ideas
- Add formal SEC Item parsing
- Add PostgreSQL metadata storage
- Add AWS S3 raw-filing storage
- Add automated retrieval evaluation
- Add cloud deployment
"""
)