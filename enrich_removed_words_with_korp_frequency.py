#!/usr/bin/env python3
"""
Append Korp corpus frequencies to removed-word TSV files.

This keeps the workflow small and explicit:

- input: one TSV from data/removed_words/ (or another compatible file)
- mapping: data/saol_edition_to_corpus.toml
- output: same rows, same order, with added corpus/frequency columns

Official Korp endpoint used:
  /count
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import tomllib
import urllib.parse
import urllib.request
from contextlib import nullcontext
from pathlib import Path
from typing import Dict, Iterable, Iterator, List

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        TaskID,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    Console = None
    Progress = None
    TaskID = int
    RICH_AVAILABLE = False


API_BASE = "https://ws.spraakbanken.gu.se/ws/korp/v8"
DEFAULT_INPUT_DIR = Path("data/removed_words")
DEFAULT_OUTPUT_DIR = Path("data/removed_words_frequency")
DEFAULT_MAPPING_FILE = Path("data/saol_edition_to_corpus.toml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add Korp corpus frequencies to removed-word TSV rows."
    )
    parser.add_argument("--input-file", type=Path, help="Single removed-word TSV to enrich.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing removed-word TSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for enriched TSV files.",
    )
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=DEFAULT_MAPPING_FILE,
        help="TOML file mapping SAOL editions to Korp corpora.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only enrich the first N rows of each file; 0 means all rows.",
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Optional delay between API requests.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Number of wordforms to query per Korp count request. Use 1 for reliable single-query counts.",
    )
    parser.add_argument(
        "--no-rich",
        action="store_true",
        help="Disable rich progress output even if rich is installed.",
    )
    return parser.parse_args()


def load_mapping(mapping_file: Path) -> Dict[str, str]:
    raw = tomllib.loads(mapping_file.read_text(encoding="utf-8"))
    return {edition: data["corpus"] for edition, data in raw.items()}


def input_files(args: argparse.Namespace) -> List[Path]:
    if args.input_file:
        return [args.input_file]
    return sorted(args.input_dir.glob("removed_*.tsv"))


def api_request(
    endpoint: str,
    params: Dict[str, str],
    timeout: int,
    retries: int,
) -> dict:
    last_exc: Exception | None = None
    url = f"{API_BASE}/{endpoint}"
    body = urllib.parse.urlencode(params).encode("utf-8")

    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, data=body, method="POST")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network variability
            last_exc = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)

    raise RuntimeError(f"API request failed for {endpoint}: {last_exc}") from last_exc


def cqp_escape(token: str) -> str:
    escaped = re.escape(token)
    escaped = escaped.replace('"', r"\"")
    return escaped


def wordform_to_cqp(wordform: str) -> str:
    tokens = wordform.split()
    if not tokens:
        raise ValueError("Empty wordform")
    return " ".join(f'[word = "{cqp_escape(token)}"]' for token in tokens)


def extract_absolute_frequency(obj: dict, corpus: str) -> int:
    if "ERROR" in obj:
        raise RuntimeError(str(obj["ERROR"]))

    corpora = obj.get("corpora", {})
    corpus_obj = corpora.get(corpus, {})
    sums = corpus_obj.get("sums", {})
    absolute = sums.get("absolute")
    if isinstance(absolute, int):
        return absolute
    if isinstance(absolute, float):
        return int(absolute)

    total = obj.get("total", {})
    total_sums = total.get("sums", {})
    total_absolute = total_sums.get("absolute")
    if isinstance(total_absolute, int):
        return total_absolute
    if isinstance(total_absolute, float):
        return int(total_absolute)

    return 0


def extract_batched_absolute_frequencies(
    obj: dict,
    corpus: str,
    expected: int,
) -> List[int]:
    if "ERROR" in obj:
        raise RuntimeError(str(obj["ERROR"]))

    corpora = obj.get("corpora", {})
    corpus_obj = corpora.get(corpus, [])
    if isinstance(corpus_obj, list):
        values: List[int] = []
        for item in corpus_obj[:expected]:
            sums = item.get("sums", {})
            absolute = sums.get("absolute")
            if isinstance(absolute, int):
                values.append(absolute)
            elif isinstance(absolute, float):
                values.append(int(absolute))
            else:
                values.append(0)
        return values

    return [extract_absolute_frequency(obj, corpus)]


def batched(items: List[str], size: int) -> Iterable[List[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def target_rows_and_words_by_corpus(
    rows: List[dict[str, str]],
    edition_to_corpus: Dict[str, str],
    limit: int,
) -> tuple[List[dict[str, str]], Dict[str, List[str]]]:
    target_rows: List[dict[str, str]] = rows[:limit] if limit > 0 else rows
    words_by_corpus: Dict[str, List[str]] = {}
    seen_by_corpus: Dict[str, set[str]] = {}

    for row in target_rows:
        corpus = edition_to_corpus[row["present_in"]]
        seen = seen_by_corpus.setdefault(corpus, set())
        if corpus not in words_by_corpus:
            words_by_corpus[corpus] = []
        wordform = row["wordform"]
        if wordform not in seen:
            seen.add(wordform)
            words_by_corpus[corpus].append(wordform)

    return target_rows, words_by_corpus


def iter_batch_jobs(words_by_corpus: Dict[str, List[str]], batch_size: int) -> Iterator[tuple[str, List[str]]]:
    for corpus, wordforms in words_by_corpus.items():
        for chunk in batched(wordforms, batch_size):
            yield corpus, chunk


def fetch_batch_frequencies(
    words_by_corpus: Dict[str, List[str]],
    timeout: int,
    retries: int,
    sleep_seconds: float,
    batch_size: int,
    progress: Progress | None = None,
    request_task: TaskID | None = None,
) -> Dict[str, int]:
    frequencies: Dict[str, int] = {}
    batch_index = 0

    for corpus, chunk in iter_batch_jobs(words_by_corpus, batch_size):
        batch_index += 1
        params = {
            "corpus": corpus,
            "cqp": wordform_to_cqp(chunk[0]),
        }
        for i, wordform in enumerate(chunk[1:], start=1):
            params[f"subcqp{i}"] = wordform_to_cqp(wordform)

        obj = api_request("count", params, timeout=timeout, retries=retries)
        values = extract_batched_absolute_frequencies(obj, corpus, expected=len(chunk))
        for wordform, freq in zip(chunk, values):
            frequencies[wordform] = freq

        if progress is not None and request_task is not None:
            progress.update(
                request_task,
                description=f"Querying Korp: {corpus}",
                advance=len(chunk),
            )
        else:
            print(f"  {corpus}: batch {batch_index}, {len(chunk)} wordforms", flush=True)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return frequencies


def enrich_rows(
    rows: List[dict[str, str]],
    edition_to_corpus: Dict[str, str],
    timeout: int,
    retries: int,
    sleep_seconds: float,
    limit: int,
    batch_size: int,
    progress: Progress | None = None,
    request_task: TaskID | None = None,
) -> List[dict[str, str]]:
    out_rows: List[dict[str, str]] = []

    target_rows, words_by_corpus = target_rows_and_words_by_corpus(
        rows=rows,
        edition_to_corpus=edition_to_corpus,
        limit=limit,
    )

    frequency_by_corpus_word: Dict[tuple[str, str], int] = {}
    batch_frequencies = fetch_batch_frequencies(
        words_by_corpus=words_by_corpus,
        timeout=timeout,
        retries=retries,
        sleep_seconds=sleep_seconds,
        batch_size=batch_size,
        progress=progress,
        request_task=request_task,
    )
    for corpus, wordforms in words_by_corpus.items():
        for wordform in wordforms:
            frequency_by_corpus_word[(corpus, wordform)] = batch_frequencies[wordform]

    for row in target_rows:
        corpus = edition_to_corpus[row["present_in"]]
        out_rows.append(
            {
                **row,
                "corpus": corpus,
                "corpus_frequency": str(
                    frequency_by_corpus_word.get((corpus, row["wordform"]), 0)
                ),
            }
        )

    if limit > 0 and limit < len(rows):
        for row in rows[limit:]:
            present_in = row["present_in"]
            out_rows.append(
                {
                    **row,
                    "corpus": edition_to_corpus[present_in],
                    "corpus_frequency": "",
                }
            )

    return out_rows


def read_tsv(path: Path) -> List[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows: List[dict[str, str]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    edition_to_corpus = load_mapping(args.mapping_file)
    files = input_files(args)
    if not files:
        raise SystemExit("No input files found.")

    use_rich = RICH_AVAILABLE and not args.no_rich
    console = Console() if use_rich else None
    progress_context = (
        Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        if use_rich
        else nullcontext(None)
    )

    with progress_context as progress:
        files_task = None
        request_task = None
        if progress is not None:
            files_task = progress.add_task("Files", total=len(files))
            request_task = progress.add_task("Querying Korp", total=1)

        for path in files:
            rows = read_tsv(path)
            target_rows, words_by_corpus = target_rows_and_words_by_corpus(
                rows=rows,
                edition_to_corpus=edition_to_corpus,
                limit=args.limit,
            )
            unique_wordforms = sum(len(wordforms) for wordforms in words_by_corpus.values())

            if progress is not None and request_task is not None:
                progress.update(
                    request_task,
                    total=max(unique_wordforms, 1),
                    completed=0,
                    description=f"Querying Korp: {path.name}",
                )
            else:
                print(
                    f"Processing {path.name} ({len(target_rows)} rows, {unique_wordforms} lookups)",
                    flush=True,
                )

            enriched = enrich_rows(
                rows=rows,
                edition_to_corpus=edition_to_corpus,
                timeout=args.timeout,
                retries=args.retries,
                sleep_seconds=args.sleep_seconds,
                limit=args.limit,
                batch_size=args.batch_size,
                progress=progress,
                request_task=request_task,
            )
            out_path = args.output_dir / path.name.replace(
                "removed_", "removed_with_frequency_"
            )
            write_tsv(out_path, enriched)

            if progress is not None:
                progress.update(
                    request_task,
                    description=f"Wrote {out_path.name}",
                )
                if files_task is not None:
                    progress.advance(files_task)
            else:
                print(f"  wrote {out_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
