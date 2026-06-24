import argparse

from src.evaluation import (
    evaluate_retrieval,
    load_evaluation_cases,
    write_reports,
)
from src.sec_client import COMPANIES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate SEC 10-K section retrieval quality."
    )
    parser.add_argument(
        "--ticker",
        required=True,
        choices=sorted(COMPANIES.keys()),
        help="Ticker already indexed in ChromaDB.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks retrieved for each question.",
    )
    parser.add_argument(
        "--cases",
        default="evaluation_cases.json",
        help="Path to the evaluation case JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation_results",
        help="Directory for JSON and Markdown reports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top_k < 1:
        raise ValueError("--top-k must be at least 1.")

    cases = load_evaluation_cases(args.cases)
    report = evaluate_retrieval(
        ticker=args.ticker,
        cases=cases,
        top_k=args.top_k,
    )
    paths = write_reports(report, args.output_dir)

    metric_name = f"hit_rate_at_{args.top_k}"
    print(f"Ticker: {args.ticker}")
    print(f"Cases: {report['case_count']}")
    print(
        f"Hit Rate@{args.top_k}: "
        f"{report['metrics'][metric_name]:.1%}"
    )
    print(
        "Mean Reciprocal Rank: "
        f"{report['metrics']['mean_reciprocal_rank']:.3f}"
    )
    print(f"Markdown report: {paths['markdown']}")
    print(f"JSON report: {paths['json']}")


if __name__ == "__main__":
    main()
