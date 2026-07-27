from typing import Dict, List

from openai import OpenAI

from src.config import CHAT_MODEL, OPENAI_API_KEY


client = OpenAI(api_key=OPENAI_API_KEY)


def build_context_block(contexts: List[Dict]) -> str:
    """Build a readable context block from retrieved filing chunks."""
    return "\n\n".join(
        [
            f"Source {i + 1} | Ticker: {ctx['metadata']['ticker']} | "
            f"Filing Date: {ctx['metadata']['filing_date']} | "
            f"Section: {ctx['metadata'].get('section_name', 'General')} | "
            f"Chunk: {ctx['metadata']['chunk_number']}\n{ctx['text']}"
            for i, ctx in enumerate(contexts)
        ]
    )


def generate_answer(
    question: str,
    contexts: List[Dict],
    selected_section: str,
) -> str:
    """Generate a source-grounded answer from retrieved filing chunks."""
    context_block = build_context_block(contexts)

    prompt = f"""
You are a careful financial document assistant. Answer the user's
question using only the provided SEC 10-K context.

Selected section filter: {selected_section}

Rules:
- Do not invent facts.
- If the answer is unavailable, say the provided filing context does
  not contain enough information.
- Keep the answer business-friendly and concise.
- Cite supporting chunks as [Source 1], [Source 2], and so on.
- Focus on the selected section when a section filter is active.

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


def generate_comparison_answer(
    question: str,
    ticker_a: str,
    contexts_a: List[Dict],
    ticker_b: str,
    contexts_b: List[Dict],
    selected_section: str,
) -> str:
    """Generate a source-grounded comparison between two companies."""
    context_block_a = build_context_block(contexts_a)
    context_block_b = build_context_block(contexts_b)

    prompt = f"""
You are a careful financial document assistant. Compare two companies
using only the provided SEC 10-K context.

Selected section filter: {selected_section}
Company A: {ticker_a}
Company B: {ticker_b}

Rules:
- Do not invent facts.
- If the provided context is not enough, clearly say so.
- Keep the answer business-friendly and concise.
- Compare the companies directly.
- Cite supporting chunks using Company A sources as [A Source 1],
  [A Source 2], etc. and Company B sources as [B Source 1],
  [B Source 2], etc.
- Focus on the selected section when a section filter is active.

User question:
{question}

Use this answer structure:
1. {ticker_a} summary
2. {ticker_b} summary
3. Similarities
4. Key differences
5. Bottom-line comparison

Company A SEC 10-K context:
{context_block_a}

Company B SEC 10-K context:
{context_block_b}
"""

    response = client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
    )
    return response.output_text

def generate_multi_year_comparison_answer(
    question: str,
    ticker: str,
    year_a: str,
    contexts_a: List[Dict],
    year_b: str,
    contexts_b: List[Dict],
    selected_section: str,
) -> str:
    """Compare the same company's SEC 10-K filings across two years."""

    context_block_a = build_context_block(contexts_a)
    context_block_b = build_context_block(contexts_b)

    prompt = f"""
You are a careful financial document assistant. Compare two annual
SEC 10-K filings for the same company using only the provided context.

Company: {ticker}
Earlier filing year: {year_a}
Later filing year: {year_b}
Selected section filter: {selected_section}

Rules:
- Do not invent facts.
- Clearly identify disclosures that were added, removed, expanded,
  reduced, or materially changed.
- Do not describe wording as changed unless the supplied context
  supports that conclusion.
- If the context is insufficient, clearly say so.
- Keep the answer business-friendly and concise.
- Cite {year_a} evidence as [{year_a} Source 1],
  [{year_a} Source 2], and so on.
- Cite {year_b} evidence as [{year_b} Source 1],
  [{year_b} Source 2], and so on.
- Focus on the selected section when a section filter is active.

User question:
{question}

Use this answer structure:
1. {year_a} disclosure summary
2. {year_b} disclosure summary
3. New or expanded disclosures
4. Removed or reduced disclosures
5. Bottom-line change

{ticker} {year_a} SEC 10-K context:
{context_block_a}

{ticker} {year_b} SEC 10-K context:
{context_block_b}
"""

    response = client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
    )

    return response.output_text