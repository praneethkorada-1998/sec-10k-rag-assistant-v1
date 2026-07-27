from typing import Dict, List

import chromadb

from src.embeddings import get_embedding


chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(
    name="sec_10k_filings_v6_items"
)

def upsert_chunks(
    ids: List[str],
    documents: List[str],
    embeddings: List[List[float]],
    metadatas: List[Dict],
) -> None:
    """Store filing chunks and their metadata in ChromaDB."""
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def build_where_filter(
    ticker: str,
    selected_section: str,
    accession: str | None = None,
) -> Dict:
    """Build a ChromaDB filter for company, section, and filing."""
    conditions = [{"ticker": ticker}]

    if selected_section != "All Sections":
        conditions.append({"section_name": selected_section})

    if accession:
        conditions.append({"accession": accession})

    if len(conditions) == 1:
        return conditions[0]

    return {"$and": conditions}

def retrieve_context(
    question: str,
    ticker: str,
    selected_section: str,
    top_k: int = 5,
    accession: str | None = None,
) -> List[Dict]:
    """Retrieve relevant chunks from a specific SEC filing."""
    question_embedding = get_embedding(question)

    where_filter = build_where_filter(
        ticker=ticker,
        selected_section=selected_section,
        accession=accession,
    )

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=top_k,
        where=where_filter,
    )

    contexts = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for document, metadata, distance in zip(
        documents,
        metadatas,
        distances,
    ):
        contexts.append(
            {
                "text": document,
                "metadata": metadata,
                "distance": distance,
            }
        )

    return contexts