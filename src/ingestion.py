from src.embeddings import get_embeddings_batch
from src.parser import chunk_text, clean_text, detect_section
from src.sec_client import download_filing_html
from src.vector_store import upsert_chunks


def ingest_10k(ticker: str) -> int:
    """Download, process, embed, and store the latest 10-K."""
    filing = download_filing_html(ticker)
    filing["text"] = clean_text(filing["html"])
    chunks = chunk_text(filing["text"])

    ids = []
    documents = []
    metadatas = []

    for index, chunk in enumerate(chunks):
        section_name = detect_section(chunk)
        chunk_id = f"v2_{ticker}_{filing['accession']}_{index}"

        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append(
            {
                "ticker": ticker,
                "cik": filing["cik"],
                "accession": filing["accession"],
                "filing_date": filing["filing_date"],
                "source_url": filing["source_url"],
                "chunk_number": index,
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