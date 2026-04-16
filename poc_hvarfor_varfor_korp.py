#!/usr/bin/env python3
"""
POC: Compare yearly relative frequencies of "hvarför" vs "varför" in Korp.

Data source:
  https://ws.spraakbanken.gu.se/ws/korp/v8

The corpus set is the union of all corpora listed under "Recommended bundles"
in documentation/korp_time_period_report.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

API_BASE = "https://ws.spraakbanken.gu.se/ws/korp/v8"

# Union of corpora from "Recommended bundles" in the project documentation.
RECOMMENDED_BUNDLE_CORPORA = sorted(
    {
        "KUBHIST2-AFTONBLADET-1850",
        "KUBHIST2-STOCKHOLMSDAGBLAD-1850",
        "KUBHIST2-POST-OCHINRIKESTIDNINGAR-1850",
        "KUBHIST2-GHOST-1850",
        "KUBHIST2-NORRKOPINGSTIDNINGAR-1850",
        "KUBHIST2-AFTONBLADET-1870",
        "KUBHIST2-STOCKHOLMSDAGBLAD-1870",
        "KUBHIST2-GOTEBORGSPOSTEN-1870",
        "KUBHIST2-POST-OCHINRIKESTIDNINGAR-1870",
        "KUBHIST2-NORRKOPINGSTIDNINGAR-1870",
        "KUBHIST2-AFTONBLADET-1880",
        "KUBHIST2-STOCKHOLMSDAGBLAD-1880",
        "KUBHIST2-GOTEBORGSPOSTEN-1880",
        "KUBHIST2-POST-OCHINRIKESTIDNINGAR-1880",
        "KUBHIST2-NORRKOPINGSTIDNINGAR-1880",
        "KUBHIST2-AFTONBLADET-1900",
        "KUBHIST2-KALMAR-1900",
        "KUBHIST2-OSTGOTAPOSTEN-1900",
        "UB-KVT-IDUN",
        "UB-KVT-DAGNY",
        "KUBHIST-DALPILEN-1920",
        "UB-KVT-KVT",
        "UB-KVT-TIDEVARVET",
        "UB-KVT-HERTHA",
        "RUNEBERG-TIDEN",
        "ORDAT",
        "RUNEBERG-BIBLBLAD",
        "FSBSKONLIT1900-1959",
        "FRAGELISTOR",
        "SBS-FOLKE",
        "SAOB-BOCKER",
        "VIVILL",
        "ASTRA1960-1979",
        "FSBSKONLIT1960-1999",
        "FSBESSAISTIK",
        "SALTNLD-SV",
        "PAROLE",
        "PRESS98",
        "HBL1998",
        "LT1998",
        "SWEACHUM",
        "LASBART",
        "BLOGGMIX1998",
        "WEBBNYHETER2006",
        "GP2006",
        "SVT-2006",
        "BLOGGMIX2006",
        "FSBSKONLIT2000TAL",
        "SWEACSAM",
    }
)

# Group all known spelling variants except modern "varför" in one series.
SERIES_QUERIES = {
    # Historical/alternate spellings (excluding "varför")
    "varfor_variants_excl_varfor": (
        '[word = "[Hh]varför|[Hh]varföre|[Hh]warför|[Hh]warföre|'
        '[Vv]arföre|[Hh]varfor|[Hh]warfor|[Vv]arfor"]'
    ),
    # Modern spelling
    "varför": '[word = "[Vv]arför"]',
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot yearly relative frequency of hvarför vs varför using Korp."
    )
    parser.add_argument("--from-year", type=int, default=1850)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument(
        "--output-png",
        default="documentation/figures/hvarfor_varfor_relative_frequency.png",
    )
    parser.add_argument(
        "--output-csv",
        default="documentation/figures/hvarfor_varfor_relative_frequency.csv",
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--chunk-years",
        type=int,
        default=10,
        help="Split API requests into N-year chunks to avoid long blocking calls.",
    )
    parser.add_argument(
        "--min-total-tokens",
        type=int,
        default=500_000,
        help="Exclude years below this total token count from plotted frequencies.",
    )
    return parser.parse_args()


def api_request(
    endpoint: str,
    params: Dict[str, str],
    timeout: int,
    retries: int,
) -> Tuple[dict, int]:
    url = f"{API_BASE}/{endpoint}"
    body = urllib.parse.urlencode(params).encode("utf-8")
    last_exc: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, data=body, method="POST")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            data = json.loads(raw.decode("utf-8"))
            return data, len(raw)
        except Exception as exc:  # pragma: no cover - network variability
            last_exc = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)

    raise RuntimeError(f"API request failed for {endpoint}: {last_exc}") from last_exc


def year_chunks(from_year: int, to_year: int, chunk_years: int) -> List[Tuple[int, int]]:
    if chunk_years <= 0:
        raise ValueError("--chunk-years must be > 0")
    chunks: List[Tuple[int, int]] = []
    start = from_year
    while start <= to_year:
        end = min(start + chunk_years - 1, to_year)
        chunks.append((start, end))
        start = end + 1
    return chunks


def merge_year_maps(target: Dict[int, Optional[int]], incoming: Dict[int, Optional[int]]) -> None:
    for year, value in incoming.items():
        target[year] = value


def fetch_yearly_series_chunked(
    endpoint: str,
    base_params: Dict[str, str],
    from_year: int,
    to_year: int,
    chunk_years: int,
    timeout: int,
    retries: int,
    label: str,
) -> Tuple[Dict[int, Optional[int]], int]:
    merged: Dict[int, Optional[int]] = {}
    total_bytes = 0
    chunks = year_chunks(from_year, to_year, chunk_years)

    for i, (start, end) in enumerate(chunks, start=1):
        print(f"[{label}] chunk {i}/{len(chunks)}: {start}-{end}")
        params = {
            **base_params,
            "from": f"{start:04d}0101000000",
            "to": f"{end:04d}1231235959",
        }
        obj, nbytes = api_request(endpoint, params, timeout=timeout, retries=retries)
        total_bytes += nbytes
        if "ERROR" in obj:
            raise RuntimeError(f"{endpoint} ERROR for {label} {start}-{end}: {obj['ERROR']}")

        if endpoint == "timespan":
            combined = obj.get("combined", {})
        else:
            combined = obj.get("combined", {}).get("absolute", {})
            if isinstance(combined, int):
                # Korp can return a scalar in sparse chunks; no year mapping to merge.
                combined = {}
        merge_year_maps(merged, to_year_dict(combined))

    return merged, total_bytes


def get_public_corpora() -> set[str]:
    with urllib.request.urlopen(f"{API_BASE}/info", timeout=120) as response:
        info = json.load(response)
    all_corpora = {c.upper() for c in info.get("corpora", [])}
    protected = {c.upper() for c in info.get("protected_corpora", [])}
    return all_corpora - protected


def filter_available(corpora: Iterable[str], public: set[str]) -> List[str]:
    return [c for c in corpora if c.upper() in public]


def to_year_dict(value: object) -> Dict[int, Optional[int]]:
    out: Dict[int, Optional[int]] = {}
    if not isinstance(value, dict):
        return out
    for k, v in value.items():
        try:
            year = int(k)
        except Exception:
            continue
        out[year] = v
    return out


def compute_relative_per_million(
    counts: Dict[int, Optional[int]],
    totals: Dict[int, Optional[int]],
    from_year: int,
    to_year: int,
) -> Dict[int, Optional[float]]:
    rel: Dict[int, Optional[float]] = {}
    for year in range(from_year, to_year + 1):
        c = counts.get(year)
        t = totals.get(year)
        if c is None or t in (None, 0):
            rel[year] = None
        else:
            rel[year] = (float(c) / float(t)) * 1_000_000.0
    return rel


def apply_min_token_filter(
    rel: Dict[int, Optional[float]],
    totals: Dict[int, Optional[int]],
    years: List[int],
    min_total_tokens: int,
) -> Tuple[Dict[int, Optional[float]], Dict[int, bool]]:
    filtered: Dict[int, Optional[float]] = {}
    included: Dict[int, bool] = {}
    for year in years:
        value = rel.get(year)
        total = totals.get(year)
        ok = isinstance(total, int) and total >= min_total_tokens
        included[year] = bool(ok)
        if value is None or not ok:
            filtered[year] = None
        else:
            filtered[year] = value
    return filtered, included


def write_csv(
    path: Path,
    years: List[int],
    totals: Dict[int, Optional[int]],
    variants_abs: Dict[int, Optional[int]],
    varfor_abs: Dict[int, Optional[int]],
    variants_rel_raw: Dict[int, Optional[float]],
    varfor_rel_raw: Dict[int, Optional[float]],
    variants_rel_filtered: Dict[int, Optional[float]],
    varfor_rel_filtered: Dict[int, Optional[float]],
    included_by_filter: Dict[int, bool],
    min_total_tokens: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "year",
                "total_tokens",
                "varfor_variants_excl_varfor_abs",
                "varfor_abs",
                "varfor_variants_excl_varfor_per_million_raw",
                "varfor_per_million_raw",
                "min_total_tokens_filter",
                "included_by_min_tokens_filter",
                "varfor_variants_excl_varfor_per_million_filtered",
                "varfor_per_million_filtered",
            ]
        )
        for year in years:
            writer.writerow(
                [
                    year,
                    totals.get(year),
                    variants_abs.get(year),
                    varfor_abs.get(year),
                    variants_rel_raw.get(year),
                    varfor_rel_raw.get(year),
                    min_total_tokens,
                    int(included_by_filter.get(year, False)),
                    variants_rel_filtered.get(year),
                    varfor_rel_filtered.get(year),
                ]
            )


def make_plot(
    path: Path,
    years: List[int],
    variants_rel: Dict[int, Optional[float]],
    varfor_rel: Dict[int, Optional[float]],
    min_total_tokens: int,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(
            "matplotlib is required for plotting. Install with: pip install matplotlib"
        ) from exc

    variant_points = [(y, variants_rel.get(y)) for y in years if variants_rel.get(y) is not None]
    varfor_points = [(y, varfor_rel.get(y)) for y in years if varfor_rel.get(y) is not None]
    variant_x = [p[0] for p in variant_points]
    variant_y = [p[1] for p in variant_points]
    varfor_x = [p[0] for p in varfor_points]
    varfor_y = [p[1] for p in varfor_points]

    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(12, 6))
    plt.scatter(
        variant_x,
        variant_y,
        label='Variants of "varför" (excluding "varför")',
        s=16,
        color="tab:blue",
    )
    plt.scatter(varfor_x, varfor_y, label='Modern "varför"', s=16, color="tab:orange")
    plt.title(
        'Relative Frequency in Korp Bundles: '
        'Why-word variants vs modern "varför"\n'
        f"(filtered: total_tokens >= {min_total_tokens})"
    )
    plt.xlabel("Year")
    plt.ylabel("Frequency per million tokens")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> int:
    args = parse_args()

    public_corpora = get_public_corpora()
    selected = filter_available(RECOMMENDED_BUNDLE_CORPORA, public_corpora)
    if not selected:
        print("No selected corpora are available/public in Korp.", file=sys.stderr)
        return 1

    missing = sorted(set(RECOMMENDED_BUNDLE_CORPORA) - set(selected))
    if missing:
        print(f"Skipping {len(missing)} unavailable/protected corpora.")

    corpus_param = ",".join(sorted(selected))
    base_params = {
        "corpus": corpus_param,
        "granularity": "y",
        "combined": "true",
        "per_corpus": "false",
    }

    print(f"Using {len(selected)} corpora.")

    try:
        totals, totals_bytes = fetch_yearly_series_chunked(
            "timespan",
            base_params,
            from_year=args.from_year,
            to_year=args.to_year,
            chunk_years=args.chunk_years,
            timeout=args.timeout,
            retries=args.retries,
            label="timespan",
        )
    except Exception as exc:
        print(f"Failed to fetch timespan data: {exc}", file=sys.stderr)
        return 1

    series_abs: Dict[str, Dict[int, Optional[int]]] = {}
    total_downloaded = totals_bytes
    for series_name, cqp in SERIES_QUERIES.items():
        try:
            counts, nbytes = fetch_yearly_series_chunked(
                "count_time",
                {**base_params, "cqp": cqp},
                from_year=args.from_year,
                to_year=args.to_year,
                chunk_years=args.chunk_years,
                timeout=args.timeout,
                retries=args.retries,
                label=f"count_time:{series_name}",
            )
        except Exception as exc:
            print(f"Failed to fetch count_time for {series_name}: {exc}", file=sys.stderr)
            return 1
        total_downloaded += nbytes
        series_abs[series_name] = counts

    years = list(range(args.from_year, args.to_year + 1))
    variants_rel_raw = compute_relative_per_million(
        series_abs["varfor_variants_excl_varfor"], totals, args.from_year, args.to_year
    )
    varfor_rel_raw = compute_relative_per_million(
        series_abs["varför"], totals, args.from_year, args.to_year
    )
    variants_rel_filtered, included_by_filter = apply_min_token_filter(
        variants_rel_raw, totals, years, args.min_total_tokens
    )
    varfor_rel_filtered, _ = apply_min_token_filter(
        varfor_rel_raw, totals, years, args.min_total_tokens
    )

    csv_path = Path(args.output_csv)
    png_path = Path(args.output_png)
    write_csv(
        csv_path,
        years,
        totals,
        series_abs["varfor_variants_excl_varfor"],
        series_abs["varför"],
        variants_rel_raw,
        varfor_rel_raw,
        variants_rel_filtered,
        varfor_rel_filtered,
        included_by_filter,
        args.min_total_tokens,
    )
    make_plot(
        png_path,
        years,
        variants_rel_filtered,
        varfor_rel_filtered,
        args.min_total_tokens,
    )

    excluded_years = [
        y
        for y in years
        if totals.get(y) is not None
        and isinstance(totals.get(y), int)
        and totals.get(y) < args.min_total_tokens
    ]

    print(f"Saved CSV: {csv_path}")
    print(f"Saved plot: {png_path}")
    print(
        f"Filtered out {len(excluded_years)} years with "
        f"total_tokens < {args.min_total_tokens}."
    )
    print(f"Downloaded response payload (bytes): {total_downloaded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
