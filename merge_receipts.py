"""
merge_receipts.py — Ingest receipts from distributed runs, print LLM cost accounting.

Usage:
    python merge_receipts.py --list        # list all receipts
    python merge_receipts.py               # print aggregated summary
    python merge_receipts.py --dir receipts/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from receipt_system import ReceiptSystem


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge and summarize pipeline receipts")
    parser.add_argument("--dir", default="receipts/", help="Receipts directory")
    parser.add_argument("--list", action="store_true", help="List individual receipts")
    args = parser.parse_args()

    rs = ReceiptSystem(args.dir)

    if args.list:
        for r in rs.load_all():
            print(json.dumps(r, indent=2))
    else:
        summary = rs.summarize()
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
