#!/usr/bin/env python3
"""Command-line helper to run LightGBM batch predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app_lightgbm_service import predict_with_models


def configure_windows_encoding() -> None:
    """Ensure UTF-8 streams on Windows consoles."""
    if sys.platform.startswith("win"):
        import codecs  # noqa: PLC0415

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run every LightGBM model on the given CSV/Excel file."
    )
    parser.add_argument("file_path", type=Path, help="Path to an input CSV/XLS/XLSX file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for prediction artifacts (default: same as the input file).",
    )
    args = parser.parse_args()

    if not args.file_path.exists():
        parser.error(f"Input file {args.file_path} does not exist.")

    target_dir = args.output_dir or args.file_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    result_path, summary = predict_with_models(
        filepath=str(args.file_path),
        user_dir=str(target_dir),
    )
    print(json.dumps({"resultPath": result_path, "summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    configure_windows_encoding()
    sys.exit(main())
