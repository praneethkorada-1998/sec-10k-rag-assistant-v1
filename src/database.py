import os
from datetime import datetime
from typing import Dict, List

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv


load_dotenv()


DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB", "sec_filings"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}


def get_connection():
    """Create a PostgreSQL connection."""
    return psycopg2.connect(**DB_CONFIG)


def initialize_database() -> None:
    """Create metadata tables if they do not already exist."""
    create_filings_table = """
    CREATE TABLE IF NOT EXISTS filings (
        id SERIAL PRIMARY KEY,
        ticker VARCHAR(20) NOT NULL,
        cik VARCHAR(20) NOT NULL,
        accession VARCHAR(100) NOT NULL UNIQUE,
        filing_date DATE,
        source_url TEXT,
        chunk_count INTEGER,
        ingestion_status VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_chunks_table = """
    CREATE TABLE IF NOT EXISTS filing_chunks (
        id SERIAL PRIMARY KEY,
        ticker VARCHAR(20) NOT NULL,
        accession VARCHAR(100) NOT NULL,
        chunk_number INTEGER NOT NULL,
        section_name VARCHAR(255),
        sec_item VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(accession, chunk_number)
    );
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(create_filings_table)
            cur.execute(create_chunks_table)
        conn.commit()


def upsert_filing_metadata(
    filing: Dict,
    ticker: str,
    chunk_count: int,
    ingestion_status: str = "completed",
) -> None:
    """Insert or update filing-level metadata."""
    query = """
    INSERT INTO filings (
        ticker,
        cik,
        accession,
        filing_date,
        source_url,
        chunk_count,
        ingestion_status
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (accession)
    DO UPDATE SET
        ticker = EXCLUDED.ticker,
        cik = EXCLUDED.cik,
        filing_date = EXCLUDED.filing_date,
        source_url = EXCLUDED.source_url,
        chunk_count = EXCLUDED.chunk_count,
        ingestion_status = EXCLUDED.ingestion_status;
    """

    values = (
        ticker,
        filing["cik"],
        filing["accession"],
        filing["filing_date"],
        filing["source_url"],
        chunk_count,
        ingestion_status,
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
        conn.commit()


def upsert_chunk_metadata(metadatas: List[Dict]) -> None:
    """Insert or update chunk-level metadata."""
    query = """
    INSERT INTO filing_chunks (
        ticker,
        accession,
        chunk_number,
        section_name,
        sec_item
    )
    VALUES %s
    ON CONFLICT (accession, chunk_number)
    DO UPDATE SET
        ticker = EXCLUDED.ticker,
        section_name = EXCLUDED.section_name,
        sec_item = EXCLUDED.sec_item;
    """

    values = [
        (
            meta["ticker"],
            meta["accession"],
            meta["chunk_number"],
            meta.get("section_name"),
            meta.get("sec_item"),
        )
        for meta in metadatas
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, query, values)
        conn.commit()


def get_filing_summary() -> List[Dict]:
    """Return filing metadata for dashboard display."""
    query = """
    SELECT
        ticker,
        cik,
        accession,
        filing_date,
        chunk_count,
        ingestion_status,
        created_at
    FROM filings
    ORDER BY created_at DESC;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    return [
        {
            "ticker": row[0],
            "cik": row[1],
            "accession": row[2],
            "filing_date": row[3],
            "chunk_count": row[4],
            "ingestion_status": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


def get_section_summary() -> List[Dict]:
    """Return section-level chunk counts."""
    query = """
    SELECT
        ticker,
        section_name,
        sec_item,
        COUNT(*) AS chunk_count
    FROM filing_chunks
    GROUP BY ticker, section_name, sec_item
    ORDER BY ticker, sec_item;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    return [
        {
            "ticker": row[0],
            "section_name": row[1],
            "sec_item": row[2],
            "chunk_count": row[3],
        }
        for row in rows
    ]