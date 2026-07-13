from src.database import initialize_database, upsert_chunk_metadata, upsert_filing_metadata
from src.embeddings import get_embeddings_batch
from src.parser import chunk_text_with_sec_items, clean_text
from src.sec_client import download_filing_html
from src.vector_store import upsert_chunks


def ingest_10k(ticker: str) -> int:
    """Download, process, embed, and store the latest 10-K with SEC item metadata."""
    filing = download_filing_html(ticker)
    filing["text"] = clean_text(filing["html"])

    chunk_records = chunk_text_with_sec_items(filing["text"])

    ids = []
    documents = []
    metadatas = []

    for index, record in enumerate(chunk_records):
        chunk, section_name, item_number = record

        chunk_id = f"v7_{ticker}_{filing['accession']}_{index}"

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
                "sec_item": item_number,
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

    initialize_database()
    upsert_filing_metadata(
        filing=filing,
        ticker=ticker,
        chunk_count=len(documents),
        ingestion_status="completed",
    )
    upsert_chunk_metadata(metadatas)

    return len(documents)