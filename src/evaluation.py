import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from src.vector_store import retrieve_context


def load_evaluation_cases(path: str) -> List[Dict]:
    """Load and validate retrieval evaluation cases."""
    with open(path, "r", encoding="utf-8") as file:
        cases = json.load(file)

    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation cases must be a non-empty JSON list.")

    required_fields = {"id", "question", "expected_section"}
    for case in cases:
        missing = required_fields - case.keys()
        if missing:
            raise ValueError(
                f"Evaluation case is missing fields: {sorted(missing)}"
            )

    return cases


def evaluate_retrieval(
    ticker: str,
    cases: List[Dict],
    top_k: int = 5,
) -> Dict:
    """Evaluate unfiltered semantic retrieval against expected sections."""
    results = []
    reciprocal_rank_total = 0.0
    hit_count = 0

    for case in cases:
        contexts = retrieve_context(
            question=case["question"],
            ticker=ticker,
            selected_section="All Sections",
            top_k=top_k,
        )

        retrieved_sections = [
            context["metadata"].get("section_name", "General")
            for context in contexts
        ]
        expected_section = case["expected_section"]

        first_relevant_rank = next(
            (
                rank
                for rank, section in enumerate(retrieved_sections, start=1)
                if section == expected_section
            ),
            None,
        )
        hit = first_relevant_rank is not None

        if hit:
            hit_count += 1
            reciprocal_rank_total += 1 / first_relevant_rank

        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected_section": expected_section,
                "retrieved_sections": retrieved_sections,
                "first_relevant_rank": first_relevant_rank,
                "hit": hit,
            }
        )

    case_count = len(cases)
    return {
        "ticker": ticker,
        "top_k": top_k,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": case_count,
        "metrics": {
            f"hit_rate_at_{top_k}": hit_count / case_count,
            "mean_reciprocal_rank": reciprocal_rank_total / case_count,
        },
        "results": results,
    }


def write_reports(report: Dict, output_dir: str) -> Dict[str, str]:
    """Write machine-readable JSON and a GitHub-friendly Markdown report."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    ticker = report["ticker"].lower()
    json_path = destination / f"{ticker}_retrieval_evaluation.json"
    markdown_path = destination / f"{ticker}_retrieval_evaluation.md"

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    metric_name = f"hit_rate_at_{report['top_k']}"
    hit_rate = report["metrics"][metric_name]
    mrr = report["metrics"]["mean_reciprocal_rank"]

    lines = [
        f"# Retrieval Evaluation: {report['ticker']}",
        "",
        f"- Cases: {report['case_count']}",
        f"- Top K: {report['top_k']}",
        f"- Hit Rate@{report['top_k']}: {hit_rate:.1%}",
        f"- Mean Reciprocal Rank: {mrr:.3f}",
        "",
        "| ID | Expected section | First relevant rank | Result |",
        "|---|---|---:|---|",
    ]

    for result in report["results"]:
        rank = result["first_relevant_rank"] or "-"
        status = "PASS" if result["hit"] else "FAIL"
        lines.append(
            f"| {result['id']} | {result['expected_section']} | "
            f"{rank} | {status} |"
        )

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }
