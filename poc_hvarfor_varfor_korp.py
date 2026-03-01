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

# Case-insensitive-ish by including both initial letter cases.
WORD_QUERIES = {
    "hvarför": '[word = "[Hh]varför"]',
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


def get_public_corpora() -> set[str]:
    with urllib.request.urlopen(f"{API_BASE}/info", timeout=120) as response:
        info = json.load(response)
    all_corpora = {c.upper() for c in info.get("corpora", [])}
    protected = {c.upper() for c in info.get("protected_corpora", [])}
    return all_corpora - protected


def filter_available(corpora: Iterable[str], public: set[str]) -> List[str]:
    return [c for c in corpora if c.upper() in public]


def to_year_dict(value: dict) -> Dict[int, Optional[int]]:
    out: Dict[int, Optional[int]] = {}
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


def write_csv(
    path: Path,
    years: List[int],
    totals: Dict[int, Optional[int]],
    hvarfor_abs: Dict[int, Optional[int]],
    varfor_abs: Dict[int, Optional[int]],
    hvarfor_rel: Dict[int, Optional[float]],
    varfor_rel: Dict[int, Optional[float]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "year",
                "total_tokens",
                "hvarfor_abs",
                "varfor_abs",
                "hvarfor_per_million",
                "varfor_per_million",
            ]
        )
        for year in years:
            writer.writerow(
                [
                    year,
                    totals.get(year),
                    hvarfor_abs.get(year),
                    varfor_abs.get(year),
                    hvarfor_rel.get(year),
                    varfor_rel.get(year),
                ]
            )


def make_plot(
    path: Path,
    years: List[int],
    hvarfor_rel: Dict[int, Optional[float]],
    varfor_rel: Dict[int, Optional[float]],
) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(
            "matplotlib is required for plotting. Install with: pip install matplotlib"
        ) from exc

    hvarfor_points = [(y, hvarfor_rel.get(y)) for y in years if hvarfor_rel.get(y) is not None]
    varfor_points = [(y, varfor_rel.get(y)) for y in years if varfor_rel.get(y) is not None]
    hvarfor_x = [p[0] for p in hvarfor_points]
    hvarfor_y = [p[1] for p in hvarfor_points]
    varfor_x = [p[0] for p in varfor_points]
    varfor_y = [p[1] for p in varfor_points]

    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(12, 6))
    plt.scatter(hvarfor_x, hvarfor_y, label="hvarför", s=16)
    plt.scatter(varfor_x, varfor_y, label="varför", s=16)
    plt.title('Relative Frequency in Korp Bundles: "hvarför" vs "varför"')
    plt.xlabel("Year")
    plt.ylabel("Frequency per million tokens")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> int:
    args = parse_args()
    from_ts = f"{args.from_year:04d}0101000000"
    to_ts = f"{args.to_year:04d}1231235959"

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
        "from": from_ts,
        "to": to_ts,
        "combined": "true",
        "per_corpus": "false",
    }

    print(f"Using {len(selected)} corpora.")

    totals_obj, totals_bytes = api_request(
        "timespan",
        base_params,
        timeout=args.timeout,
        retries=args.retries,
    )
    if "ERROR" in totals_obj:
        print(f"timespan ERROR: {totals_obj['ERROR']}", file=sys.stderr)
        return 1

    totals = to_year_dict(totals_obj.get("combined", {}))

    word_abs: Dict[str, Dict[int, Optional[int]]] = {}
    total_downloaded = totals_bytes
    for word, cqp in WORD_QUERIES.items():
        obj, nbytes = api_request(
            "count_time",
            {**base_params, "cqp": cqp},
            timeout=args.timeout,
            retries=args.retries,
        )
        total_downloaded += nbytes
        if "ERROR" in obj:
            print(f"count_time ERROR for {word}: {obj['ERROR']}", file=sys.stderr)
            return 1
        combined = obj.get("combined", {}).get("absolute", {})
        word_abs[word] = to_year_dict(combined)

    years = list(range(args.from_year, args.to_year + 1))
    hvarfor_rel = compute_relative_per_million(
        word_abs["hvarför"], totals, args.from_year, args.to_year
    )
    varfor_rel = compute_relative_per_million(
        word_abs["varför"], totals, args.from_year, args.to_year
    )

    csv_path = Path(args.output_csv)
    png_path = Path(args.output_png)
    write_csv(
        csv_path,
        years,
        totals,
        word_abs["hvarför"],
        word_abs["varför"],
        hvarfor_rel,
        varfor_rel,
    )
    make_plot(png_path, years, hvarfor_rel, varfor_rel)

    print(f"Saved CSV: {csv_path}")
    print(f"Saved plot: {png_path}")
    print(f"Downloaded response payload (bytes): {total_downloaded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
