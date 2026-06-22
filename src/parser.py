import re
from typing import List

from bs4 import BeautifulSoup


SECTION_OPTIONS = [
    "All Sections",
    "Business",
    "Risk Factors",
    "Cybersecurity",
    "Competition",
    "Legal / Regulatory",
    "Financial Risks",
]


def clean_text(raw_html: str) -> str:
    """Convert SEC filing HTML into readable text."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "table"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def detect_section(chunk: str) -> str:
    """Assign lightweight section metadata to a filing chunk."""
    text = chunk.lower()

    section_terms = [
        (
            "Cybersecurity",
            [
                "cybersecurity",
                "cyber security",
                "data security",
                "information security",
                "security breach",
                "ransomware",
                "unauthorized access",
            ],
        ),
        (
            "Risk Factors",
            [
                "risk factors",
                "risks related",
                "could adversely affect",
                "material adverse effect",
                "uncertainties",
            ],
        ),
        (
            "Legal / Regulatory",
            [
                "legal proceedings",
                "regulatory",
                "regulation",
                "compliance",
                "laws and regulations",
                "litigation",
                "government investigation",
            ],
        ),
        (
            "Competition",
            [
                "competition",
                "competitive",
                "competitors",
                "compete",
                "market share",
            ],
        ),
        (
            "Financial Risks",
            [
                "financial condition",
                "liquidity",
                "cash flows",
                "interest rates",
                "credit risk",
                "market risk",
                "foreign exchange",
                "revenue",
                "operating results",
            ],
        ),
        (
            "Business",
            [
                "business",
                "products and services",
                "customers",
                "operations",
                "segments",
                "strategy",
            ],
        ),
    ]

    for section_name, terms in section_terms:
        if any(term in text for term in terms):
            return section_name

    return "General"


def chunk_text(
    text: str,
    chunk_size: int = 3500,
    overlap: int = 500,
) -> List[str]:
    """Split filing text into overlapping chunks."""
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks