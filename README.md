# saol_diff_list

Small Python proofs of concept for exploring Swedish lexical data from two angles:

- dictionary data sampled from a tab-separated lexicon export
- time-based word-frequency comparisons from Sprakbanken's Korp API

The repository is not packaged as a library. It is a lightweight working directory for experiments, scripts, and generated analysis artifacts.

## What the repo does

The main workflow in this repo compares historical and alternate spellings of the Swedish "why" word against the modern spelling `varför` over time.

The script:

- queries Sprakbanken Korp year by year, in configurable year chunks
- uses a fixed set of recommended corpora documented in [`documentation/korp_time_period_report.md`](documentation/korp_time_period_report.md)
- groups older and alternate spellings into one series
- keeps modern `varför` as a separate series
- normalizes counts by total yearly token volume
- filters out low-volume years
- writes both a CSV and a plot under [`documentation/figures`](documentation/figures)

There is also a smaller helper script that prints the first ten entries from each dictionary edition in the bundled lexicon file.

## Repository layout

- [`poc_hvarfor_varfor_korp.py`](poc_hvarfor_varfor_korp.py): main Korp frequency-analysis script
- [`poc_first_ten.py`](poc_first_ten.py): quick sampler for the local TSV lexicon data
- [`data/shlex-sslg-v01_0.txt`](data/shlex-sslg-v01_0.txt): bundled tab-separated lexical data
- [`documentation/korp_time_period_report.md`](documentation/korp_time_period_report.md): notes on corpus selection, API behavior, and measurement strategy
- [`documentation/figures/hvarfor_varfor_relative_frequency.csv`](documentation/figures/hvarfor_varfor_relative_frequency.csv): generated yearly output data
- [`documentation/figures/hvarfor_varfor_relative_frequency.png`](documentation/figures/hvarfor_varfor_relative_frequency.png): generated plot

## Requirements

- Python 3
- network access to `https://ws.spraakbanken.gu.se/ws/korp/v8` for the Korp script
- `matplotlib` for plot generation

The scripts use only the Python standard library apart from plotting.

## Usage

Sample the bundled lexicon data:

```bash
python3 poc_first_ten.py
```

Run the Korp comparison:

```bash
python3 poc_hvarfor_varfor_korp.py
```

Example with custom settings:

```bash
python3 poc_hvarfor_varfor_korp.py \
  --from-year 1850 \
  --to-year 2026 \
  --chunk-years 10 \
  --min-total-tokens 500000
```

## Korp script outputs

By default, the main script writes:

- `documentation/figures/hvarfor_varfor_relative_frequency.csv`
- `documentation/figures/hvarfor_varfor_relative_frequency.png`

The CSV includes:

- yearly total token counts
- absolute counts for the historical-variant series
- absolute counts for modern `varför`
- raw relative frequencies per million tokens
- filtered relative frequencies after excluding low-volume years

## Notes

- The corpus list is hard-coded in `poc_hvarfor_varfor_korp.py` and mirrors the "Recommended bundles" section in the report.
- The script skips unavailable or protected Korp corpora when the API reports they are not public.
- The repo currently looks more like a research notebook in script form than a finished application.
- Generated figures in `documentation/figures` are outputs, not source data.
