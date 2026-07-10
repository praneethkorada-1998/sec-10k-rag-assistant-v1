import re
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup


SECTION_OPTIONS = [
    "All Sections",
    "Item 1 - Business",
    "Item 1A - Risk Factors",
    "Item 1C - Cybersecurity",
    "Item 3 - Legal Proceedings",
    "Item 7 - MD&A",
    "Item 7A - Market Risk",
    "Item 8 - Financial Statements",
    "Business",
    "Risk Factors",
    "Cybersecurity",
    "Competition",
    "Legal / Regulatory",
    "Financial Risks",
]


SEC_ITEM_MAP = {
    "1": "Item 1 - Business",
    "1A": "Item 1A - Risk Factors",
    "1B": "Item 1B - Unresolved Staff Comments",
    "1C": "Item 1C - Cybersecurity",
    "2": "Item 2 - Properties",
    "3": "Item 3 - Legal Proceedings",
    "7": "Item 7 - MD&A",
    "7A": "Item 7A - Market Risk",
    "8": "Item 8 - Financial Statements",
}


def clean_text(raw_html: str) -> str:
    """Convert SEC filing HTML into readable text."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "table"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def normalize_item_number(item_number: str) -> str:
    """Normalize SEC item numbers such as 1A, 7A, etc."""
    return item_number.upper().replace(".", "").strip()


def extract_sec_items(text: str) -> List[Dict[str, str]]:
    """
    Extract official SEC 10-K item sections.

    This detects headings such as:
    ITEM 1. BUSINESS
    ITEM 1A. RISK FACTORS
    ITEM 1C. CYBERSECURITY
    ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS
    """

    item_pattern = re.compile(
        r"(?im)^\s*item\s+"
        r"(1A|1B|1C|1|2|3|7A|7|8)"
        r"\.?\s+"
        r"([^\n]{0,120})"
    )

    matches = list(item_pattern.finditer(text))
    sections = []

    if not matches:
        return sections

    for index, match in enumerate(matches):
        item_number = normalize_item_number(match.group(1))
        heading_text = match.group(2).strip()
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)

        section_text = text[start:end].strip()

        if len(section_text) < 500:
            continue

        section_name = SEC_ITEM_MAP.get(item_number, f"Item {item_number}")

        sections.append(
            {
                "item_number": item_number,
                "section_name": section_name,
                "heading_text": heading_text,
                "text": section_text,
            }
        )

    return sections


def detect_section(chunk: str) -> str:
    """
    Backward-compatible fallback section detector.

    Used when official SEC item parsing is unavailable.
    """
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


def chunk_text_with_sec_items(
    text: str,
    chunk_size: int = 3500,
    overlap: int = 500,
) -> List[Tuple[str, str, str]]:
    """
    Split SEC filing text into chunks with official SEC item metadata.

    Returns:
        List of tuples:
        (chunk_text, section_name, item_number)
    """

    sec_sections = extract_sec_items(text)
    chunk_records = []

    if sec_sections:
        for section in sec_sections:
            section_chunks = chunk_text(
                section["text"],
                chunk_size=chunk_size,
                overlap=overlap,
            )

            for chunk in section_chunks:
                chunk_records.append(
                    (
                        chunk,
                        section["section_name"],
                        section["item_number"],
                    )
                )

        return chunk_records

    fallback_chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    for chunk in fallback_chunks:
        chunk_records.append(
            (
                chunk,
                detect_section(chunk),
                "N/A",
            )
        )

    return chunk_records