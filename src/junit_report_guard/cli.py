"""Console interface; exit 1 is an integrity finding, exit 2 a usage error."""

from __future__ import annotations

import argparse
import json

from . import __version__
from .core import audit


def positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a positive integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check JUnit report integrity without copying logs"
    )
    parser.add_argument(
        "reports", nargs="+", help="Explicit XML paths (expand globs in your shell)"
    )
    parser.add_argument("--version", action="version", version=f"junit-report-guard {__version__}")
    parser.add_argument("--json", action="store_true", help="Write a machine-readable report")
    parser.add_argument("--require-files", type=positive, help="Expected number of report files")
    parser.add_argument("--require-success", action="store_true", help="Also fail on failed tests")
    parser.add_argument(
        "--max-bytes", type=positive, default=30_000_000, help="Per-file byte limit"
    )
    parser.add_argument(
        "--max-findings", type=positive, default=1000, help="Maximum stored findings"
    )
    args = parser.parse_args(argv)
    result = audit(
        args.reports,
        require_files=args.require_files,
        require_success=args.require_success,
        max_bytes=args.max_bytes,
        max_findings=args.max_findings,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print(
            f"{'OK' if result['ok'] else 'FAIL'}: {result['totals']['tests']} test cases; "
            f"{result['finding_count']} integrity findings"
        )
        for item in result["findings"]:
            print(
                f"{item['code']}: {item['message']} "
                f"{json.dumps({k: v for k, v in item.items() if k not in ('code', 'message')})}"
            )
        if result["findings_truncated"]:
            print("Additional findings omitted; increase --max-findings to store more")
    return 0 if result["ok"] else 1
