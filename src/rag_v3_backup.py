from typing import Dict, List

from openai import OpenAI

from src.config import CHAT_MODEL, OPENAI_API_KEY


client = OpenAI(api_key=OPENAI_API_KEY)


def generate_answer(
    question: str,
    contexts: List[Dict],
    selected_section: str,
) -> str:
    """Generate a source-grounded answer from retrieved filing chunks."""
    context_block = "\n\n".join(
        [
            f"Source {i + 1} | Ticker: {ctx['metadata']['ticker']} | "
            f"Filing Date: {ctx['metadata']['filing_date']} | "
            f"Section: {ctx['metadata'].get('section_name', 'General')} | "
            f"Chunk: {ctx['metadata']['chunk_number']}\n{ctx['text']}"
            for i, ctx in enumerate(contexts)
        ]
    )

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