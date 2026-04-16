#!/usr/bin/env python3
"""
Extract wordforms that disappear between adjacent SAOL editions.

This ports the useful adjacent-edition diff logic from the sibling
`saol_search` project, but keeps the scope small:

- no external dependencies
- no generic `wordfreq` scoring
- one output TSV per adjacent edition pair with unique removed wordforms
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_DATA_FILE = Path("data/shlex-sslg-v01_0.txt")
DEFAULT_OUTPUT_DIR = Path("data/removed_words")


def edition_sort_key(edition: str) -> int:
    left = edition.split("-")[0]
    letter = left[0]
    number = int(left[1:])
    letter_value = {"a": 18, "n": 19, "t": 20}[letter]
    return letter_value * 100 + number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write unique removed wordforms for each adjacent SAOL edition pair."
    )
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def load_rows_by_edition(data_file: Path) -> Dict[str, List[dict[str, str]]]:
    rows_by_edition: Dict[str, List[dict[str, str]]] = defaultdict(list)
    with data_file.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows_by_edition[row["#dictionary"]].append(row)
    return dict(rows_by_edition)


def unique_words(rows: Iterable[dict[str, str]]) -> set[str]:
    return {row["entry"] for row in rows if row.get("entry")}


def row_count_by_word(rows: Iterable[dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        word = row.get("entry", "")
        if word:
            counts[word] += 1
    return dict(counts)


def write_removed_words_tsv(
    output_path: Path,
    prev_edition: str,
    curr_edition: str,
    removed_words: List[str],
    prev_row_counts: Dict[str, int],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(
            [
                "wordform",
                "row_count_in_present_edition",
                "present_in",
                "missing_in",
            ]
        )
        for word in removed_words:
            writer.writerow(
                [
                    word,
                    prev_row_counts.get(word, 0),
                    prev_edition,
                    curr_edition,
                ]
            )


def main() -> int:
    args = parse_args()
    rows_by_edition = load_rows_by_edition(args.data_file)
    editions = sorted(rows_by_edition, key=edition_sort_key)

    for i in range(1, len(editions)):
        prev_edition = editions[i - 1]
        curr_edition = editions[i]
        prev_rows = rows_by_edition[prev_edition]
        curr_rows = rows_by_edition[curr_edition]

        prev_words = unique_words(prev_rows)
        curr_words = unique_words(curr_rows)
        removed_words = sorted(prev_words - curr_words)
        prev_row_counts = row_count_by_word(prev_rows)

        output_path = (
            args.output_dir / f"removed_{prev_edition}__{curr_edition}__n={len(removed_words)}.tsv"
        )
        write_removed_words_tsv(
            output_path=output_path,
            prev_edition=prev_edition,
            curr_edition=curr_edition,
            removed_words=removed_words,
            prev_row_counts=prev_row_counts,
        )
        print(f"{prev_edition} -> {curr_edition}: {len(removed_words)} removed words")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
