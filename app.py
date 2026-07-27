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

from src.database import get_filing_summary, get_section_summary
from src.config import OPENAI_API_KEY
from src.ingestion import (
    batch_ingest_10k,
    ingest_10k,
    ingest_10k_by_accession,
)
from src.parser import SECTION_OPTIONS
from src.rag import (
    generate_answer,
    generate_comparison_answer,
    generate_multi_year_comparison_answer,
)
from src.sec_client import COMPANIES, fetch_10k_filings
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
    st.markdown("### Batch Ingestion")
    batch_tickers = st.multiselect(
        "Select companies to batch index",
        list(COMPANIES.keys()),
        default=["AAPL", "MSFT"] if "AAPL" in COMPANIES and "MSFT" in COMPANIES else [],
    )

    if st.button("Batch index selected companies"):
        if not batch_tickers:
            st.warning("Please select at least one company.")
        else:
            with st.spinner("Batch indexing selected companies..."):
                batch_results = batch_ingest_10k(batch_tickers)

            st.markdown("#### Batch Results")
            for ticker, result in batch_results.items():
                if result["status"] == "completed":
                    st.success(
                        f"{ticker}: completed with {result['chunk_count']} chunks"
                    )
                else:
                    st.error(
                        f"{ticker}: failed - {result['error']}"
                    )
    st.divider()
    st.header("2. Search Settings")
    selected_section = st.selectbox("Section filter", SECTION_OPTIONS)
    top_k = st.slider("Retrieved chunks per company", min_value=3, max_value=10, value=5)

single_tab, comparison_tab, multi_year_tab, metadata_tab = st.tabs(
    [
        "Single Company Q&A",
        "Company Comparison",
        "Multi-Year Comparison",
        "Metadata Dashboard",
    ]
)

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

with multi_year_tab:
    st.subheader("Compare one company's 10-K filings across two years")

    historical_ticker = st.selectbox(
        "Company",
        list(COMPANIES.keys()),
        key="historical_ticker",
    )

    try:
        historical_filings = fetch_10k_filings(
            historical_ticker,
            limit=5,
        )

        filings_by_year = {
            filing["filing_year"]: filing
            for filing in historical_filings
        }

        available_years = sorted(filings_by_year.keys())

        if len(available_years) < 2:
            st.warning(
                "At least two historical 10-K filings are required."
            )
        else:
            year_col_a, year_col_b = st.columns(2)

            with year_col_a:
                earlier_year = st.selectbox(
                    "Earlier filing year",
                    available_years,
                    index=len(available_years) - 2,
                    key="earlier_year",
                )

            with year_col_b:
                later_year = st.selectbox(
                    "Later filing year",
                    available_years,
                    index=len(available_years) - 1,
                    key="later_year",
                )

            earlier_filing = filings_by_year[earlier_year]
            later_filing = filings_by_year[later_year]

            if int(earlier_year) >= int(later_year):
                st.info(
                    "Choose an earlier year on the left and a later year on the right."
                )

            if st.button(
                "Download & index selected years",
                key="index_selected_years",
            ):
                if earlier_year == later_year:
                    st.warning("Please select two different filing years.")
                else:
                    try:
                        with st.spinner(
                            f"Indexing {historical_ticker} {earlier_year} 10-K..."
                        ):
                            earlier_count = ingest_10k_by_accession(
                                historical_ticker,
                                earlier_filing["accession"],
                            )

                        with st.spinner(
                            f"Indexing {historical_ticker} {later_year} 10-K..."
                        ):
                            later_count = ingest_10k_by_accession(
                                historical_ticker,
                                later_filing["accession"],
                            )

                        st.success(
                            f"Indexed {earlier_count} chunks for {earlier_year} "
                            f"and {later_count} chunks for {later_year}."
                        )
                    except Exception as exc:
                        st.error(f"Historical ingestion failed: {exc}")

            multi_year_question = st.text_input(
                "Multi-year comparison question",
                placeholder=(
                    "Example: What risk factors were added, removed, "
                    "or expanded between these filings?"
                ),
                key="multi_year_question",
            )

            if st.button(
                "Compare filing years",
                key="compare_filing_years",
            ) and multi_year_question:
                if int(earlier_year) >= int(later_year):
                    st.warning(
                        "Select an earlier year and a later year."
                    )
                else:
                    with st.spinner(
                        "Retrieving both filings and analyzing changes..."
                    ):
                        try:
                            earlier_contexts = retrieve_context(
                                question=multi_year_question,
                                ticker=historical_ticker,
                                selected_section=selected_section,
                                top_k=top_k,
                                accession=earlier_filing["accession"],
                            )

                            later_contexts = retrieve_context(
                                question=multi_year_question,
                                ticker=historical_ticker,
                                selected_section=selected_section,
                                top_k=top_k,
                                accession=later_filing["accession"],
                            )

                            if not earlier_contexts or not later_contexts:
                                st.warning(
                                    "Missing chunks for one or both years. "
                                    "Click 'Download & index selected years' first."
                                )
                            else:
                                multi_year_answer = (
                                    generate_multi_year_comparison_answer(
                                        question=multi_year_question,
                                        ticker=historical_ticker,
                                        year_a=earlier_year,
                                        contexts_a=earlier_contexts,
                                        year_b=later_year,
                                        contexts_b=later_contexts,
                                        selected_section=selected_section,
                                    )
                                )

                                st.markdown("### Multi-Year Comparison")
                                st.write(multi_year_answer)

                                earlier_col, later_col = st.columns(2)

                                with earlier_col:
                                    st.markdown(
                                        f"### {earlier_year} Sources"
                                    )

                                    for i, ctx in enumerate(
                                        earlier_contexts,
                                        start=1,
                                    ):
                                        meta = ctx["metadata"]
                                        section = meta.get(
                                            "section_name",
                                            "General",
                                        )

                                        with st.expander(
                                            f"{earlier_year} Source {i} | "
                                            f"{section} | "
                                            f"Chunk {meta['chunk_number']}"
                                        ):
                                            st.write(ctx["text"][:2500])
                                            st.markdown(
                                                f"[Open SEC filing]"
                                                f"({meta['source_url']})"
                                            )
                                            st.caption(
                                                f"Distance: {ctx['distance']}"
                                            )

                                with later_col:
                                    st.markdown(
                                        f"### {later_year} Sources"
                                    )

                                    for i, ctx in enumerate(
                                        later_contexts,
                                        start=1,
                                    ):
                                        meta = ctx["metadata"]
                                        section = meta.get(
                                            "section_name",
                                            "General",
                                        )

                                        with st.expander(
                                            f"{later_year} Source {i} | "
                                            f"{section} | "
                                            f"Chunk {meta['chunk_number']}"
                                        ):
                                            st.write(ctx["text"][:2500])
                                            st.markdown(
                                                f"[Open SEC filing]"
                                                f"({meta['source_url']})"
                                            )
                                            st.caption(
                                                f"Distance: {ctx['distance']}"
                                            )

                        except Exception as exc:
                            st.error(
                                f"Multi-year comparison failed: {exc}"
                            )

    except Exception as exc:
        st.error(f"Unable to retrieve historical filings: {exc}")

with metadata_tab:
    st.subheader("PostgreSQL Metadata Dashboard")

    try:
        filing_summary = get_filing_summary()
        section_summary = get_section_summary()

        st.markdown("### Indexed Filings")
        if filing_summary:
            st.dataframe(filing_summary, use_container_width=True)
        else:
            st.info("No filing metadata found yet. Index a filing first.")

        st.markdown("### Section-Level Chunk Counts")
        if section_summary:
            st.dataframe(section_summary, use_container_width=True)
        else:
            st.info("No section metadata found yet. Index a filing first.")

    except Exception as exc:
        st.error(f"Unable to load PostgreSQL metadata: {exc}")

st.divider()

st.markdown(
    """
### Platform Features Included

- Downloads latest public SEC 10-K filings from SEC EDGAR
- Performs formal SEC item parsing for official 10-K sections
- Extracts Item 1, Item 1A, Item 1C, Item 3, Item 7, Item 7A, and Item 8
- Creates searchable chunks and OpenAI embeddings
- Stores chunks and embeddings in ChromaDB for semantic search
- Stores structured filing and chunk metadata in PostgreSQL
- Applies metadata-filtered retrieval by official SEC section
- Generates source-grounded answers with retrieved sources
- Compares two companies across selected SEC filing sections
- Provides a PostgreSQL Metadata Dashboard
- Supports Docker, Docker Compose, and GitHub Actions validation

### Current Version

Version 7 completed with formal SEC item parsing, company comparison, retrieval evaluation, GitHub Actions CI, PostgreSQL metadata storage, and a Streamlit Metadata Dashboard.

### Next Version

Version 8 will add batch ingestion for multiple companies.
"""
)