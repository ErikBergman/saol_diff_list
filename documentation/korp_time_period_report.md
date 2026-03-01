# Korp Time-Period Frequency Analysis Report (1850-2026)

Date of measurement: March 1, 2026  
API base: `https://ws.spraakbanken.gu.se/ws/korp/v8`

## Purpose

This document explains:

1. What was measured in Korp for time-sliced word frequencies.
2. How large the API downloads are for decade-based queries from 1850 to today.
3. How to discover relevant corpora and run reproducible comparisons of word frequencies across time periods.

## Executive Summary

- Public, time-annotated corpora usable in `mode=default` for 1850-2026: **249 corpora**.
- Decade windows used: `1850-1859`, `1860-1869`, ..., `2020-2026` (18 windows total).
- Estimated payload size (API response body) for one word across all decades:
  - Rare/no-hit word: about **3 KB** total.
  - Common word (`och`): about **10 KB** total.
- Practical scaling:
  - **1,000 words**: roughly **3-10 MB** (if using `combined=true&per_corpus=false`).

Most important parameter for data volume:

- `per_corpus=false`: small payloads (recommended for temporal trend analysis).
- `per_corpus=true`: much larger payloads.

Example measured for 2000-2009:

- `per_corpus=false`: **171 bytes**
- `per_corpus=true`: **20,770 bytes**

## What “obtain corpora” means in Korp

Korp API is typically used to obtain:

1. Corpus metadata (names, dates, attributes, access status).
2. Aggregated counts and time-series frequency data.

It is not typically a direct “bulk raw corpus dump” interface. For frequency comparison tasks, you generally do not need raw corpus download; you query counts over selected corpora/time ranges.

## Endpoints used

- `GET /info`  
  Lists available corpora and protected corpora.
- `GET /corpus_config?mode=default`  
  Lists corpora included in a mode.
- `GET /corpus_info?corpus=...`  
  Returns metadata per corpus (`FirstDate`, `LastDate`, structural attrs, etc.).
- `POST /timespan`  
  Returns token totals over time windows (useful denominator / sanity checks).
- `POST /count_time`  
  Returns per-time-bucket counts for a CQP query (word frequency over time).

## Access and corpus filtering strategy

### Step 1: Start from the default Swedish mode

`mode=default` had 290 corpora in this measurement.

### Step 2: Remove inaccessible corpora

Korp returned authorization errors for some corpora in public calls. The blocked set encountered:

- `ASU`, `GDC`, `IVIP`, `LAWLINE`, `MEPAC`, `SOEXEMPEL`
- `SPIN-SOURCE`, `SPINV1`, `SPRAKFRAGOR`
- `SW1203`, `SW1203V1`, `SW1203V2`
- `SWELL-ORIGINAL`, `SWELL-TARGET`
- `SWELLV1-ORIGINAL`, `SWELLV1-TARGET`
- `TISUS`, `TISUSV2`

### Step 3: Keep corpora that overlap your period and have time metadata

Filter corpora to:

- overlap requested date interval (e.g., 1850-2026), and
- contain at least one time-bearing structural attribute:
  - `text_datefrom`, `text_dateto`, `text_timefrom`, `text_timeto`, or `text_year`.

After filtering, usable corpora for this report: **249**.

## Measured data-size findings

### 1) Baseline size for decade token totals (`timespan`)

Using decade-specific corpus subsets, `combined=true`, `per_corpus=false`:

- Total for all 18 decades: **3913 bytes**
- Average per decade: **217 bytes**

This is the approximate minimum payload class for time metadata only.

### 2) Frequency query size (`count_time`) for a rare/no-hit word

Query pattern: `[word = "zzzxxyyqqq"]` (effectively no matches).

- Total for all 18 decades: **3101 bytes**
- Average per decade: **172 bytes**

### 3) Frequency query size (`count_time`) for a common word

Query pattern: `[word = "och"]`.

Measured exactly for 1850-1999 (15 decades): **8528 bytes**.

Using observed ratio vs `timespan`, estimated full 1850-2026 total:

- **~10,317 bytes** (~10.1 KB) per word.

## Recommended query shape for scalable analysis

For decade-level word frequency comparison:

- `granularity=y`
- `from=<decade-start>`
- `to=<decade-end>`
- `combined=true`
- `per_corpus=false`

Then aggregate yearly values into decade totals client-side if needed.

This keeps payloads small and stable.

## Reproducible workflow (Python, no external dependencies)

Create `scripts/korp_decade_frequency.py` (or run inline):

```python
#!/usr/bin/env python3
import json
import urllib.parse
import urllib.request

BASE = "https://ws.spraakbanken.gu.se/ws/korp/v8"
START_YEAR = 1850
END_YEAR = 2026

BLOCKED = {
    "ASU", "GDC", "IVIP", "LAWLINE", "MEPAC", "SOEXEMPEL",
    "SPIN-SOURCE", "SPINV1", "SPRAKFRAGOR",
    "SW1203", "SW1203V1", "SW1203V2",
    "SWELL-ORIGINAL", "SWELL-TARGET",
    "SWELLV1-ORIGINAL", "SWELLV1-TARGET",
    "TISUS", "TISUSV2",
}

def api(path, params=None, method="GET", timeout=120):
    params = params or {}
    if method == "GET":
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{BASE}/{path}" + (f"?{q}" if q else ""))
    else:
        body = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(f"{BASE}/{path}", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw.decode("utf-8")), len(raw)

def get_usable_corpora():
    cfg, _ = api("corpus_config", {"mode": "default"})
    corpora = sorted(cfg.get("corpora", {}).keys())

    meta = {}
    for i in range(0, len(corpora), 80):
        batch = corpora[i:i+80]
        obj, _ = api("corpus_info", {"corpus": ",".join(batch)})
        meta.update(obj.get("corpora", {}))

    usable = []
    for c, cobj in meta.items():
        if c in BLOCKED:
            continue
        inf = cobj.get("info", {})
        s_attrs = set(cobj.get("attrs", {}).get("s", []))
        fd = inf.get("FirstDate")
        ld = inf.get("LastDate")
        if not fd or not ld:
            continue
        fy = int(fd[:4])
        ly = int(ld[:4])
        if ly < START_YEAR or fy > END_YEAR:
            continue
        has_time = any(a in s_attrs for a in (
            "text_datefrom", "text_dateto", "text_timefrom", "text_timeto", "text_year"
        ))
        if not has_time:
            continue
        usable.append((c, fy, ly))
    return sorted(usable)

def decade_ranges():
    y = START_YEAR
    while y <= END_YEAR:
        y2 = min(y + 9, END_YEAR)
        yield y, y2
        y += 10

def compare_word(word):
    corpora = get_usable_corpora()
    out = []
    for y, y2 in decade_ranges():
        decade_corpora = [c for c, fy, ly in corpora if not (ly < y or fy > y2)]
        obj, nbytes = api(
            "count_time",
            {
                "corpus": ",".join(decade_corpora),
                "cqp": f'[word = "{word}"]',
                "granularity": "y",
                "from": f"{y:04d}0101000000",
                "to": f"{y2:04d}1231235959",
                "combined": "true",
                "per_corpus": "false",
            },
            method="POST",
            timeout=180,
        )
        yearly_abs = obj.get("combined", {}).get("absolute", {})
        decade_abs = sum(v for v in yearly_abs.values() if isinstance(v, int))
        out.append((f"{y}-{y2}", decade_abs, nbytes))
    return out

if __name__ == "__main__":
    word = "och"
    rows = compare_word(word)
    total_bytes = sum(b for _, _, b in rows)
    print("decade,absolute_count,response_bytes")
    for d, c, b in rows:
        print(f"{d},{c},{b}")
    print(f"TOTAL_BYTES,{total_bytes}")
```

Run:

```bash
python3 scripts/korp_decade_frequency.py
```

## How to compare multiple words across periods

1. Build a candidate word list (for example, removed SAOL words).
2. For each word, run `count_time` decade windows (or one full range call).
3. Store:
   - decade
   - absolute count
   - response size bytes
4. Optionally normalize by decade token totals from `timespan`.
5. Compare trends:
   - rise/fall over decades
   - rank shifts between periods
   - disappearance/reappearance patterns.

## Suggested output schema

Use CSV columns:

- `word`
- `period` (e.g. `1850-1859`)
- `abs_count`
- `rel_per_million` (optional, if normalized)
- `n_corpora`
- `response_bytes`

This makes it straightforward to compute download cost and quality checks.

## Pitfalls and mitigations

- Authorization errors: remove blocked corpora or authenticate if you have access.
- Slow decades (often modern decades with many corpora):
  - Use decade-specific corpus subsets.
  - Retry with backoff.
  - Keep `per_corpus=false` unless required.
- Query syntax sensitivity:
  - Escape quotes.
  - Prefer exact token queries first (`[word = "..."]`).
- Time coverage heterogeneity:
  - Different corpora activate in different decades.
  - Track `n_corpora` per decade and report it.

## Suggested Korp corpora per SAOL edition (practical shortlist)

These suggestions are based on:

1. Year overlap with each edition year.
2. Publicly queryable corpora (excluding protected corpora from `/info`).
3. Preference for broad language material (newspapers, periodicals, mixed prose), with legal/parliamentary corpora as optional volume boosters.

Note: In your dataset, `a55-dln` predates SAOL edition 1 (1874), but is included here because it appears in your comparison chain.

### Edition mapping used

- `a55-dln` (1855)
- `a74-s01` (1874)
- `a89-s06` (1889)
- `n00-s07` (1900)
- `n23-s08` (1923)
- `n30-bng` (1930)
- `n50-s09` (1950)
- `n73-s10` (1973)
- `n86-s11` (1986)
- `n98-s12` (1998)
- `t06-s13` (2006)

### Recommended bundles

#### `a55-dln` (1855)
- `KUBHIST2-AFTONBLADET-1850`
- `KUBHIST2-STOCKHOLMSDAGBLAD-1850`
- `KUBHIST2-POST-OCHINRIKESTIDNINGAR-1850`
- `KUBHIST2-GHOST-1850`
- `KUBHIST2-NORRKOPINGSTIDNINGAR-1850`

#### `a74-s01` (1874)
- `KUBHIST2-AFTONBLADET-1870`
- `KUBHIST2-STOCKHOLMSDAGBLAD-1870`
- `KUBHIST2-GOTEBORGSPOSTEN-1870`
- `KUBHIST2-POST-OCHINRIKESTIDNINGAR-1870`
- `KUBHIST2-NORRKOPINGSTIDNINGAR-1870`

#### `a89-s06` (1889)
- `KUBHIST2-AFTONBLADET-1880`
- `KUBHIST2-STOCKHOLMSDAGBLAD-1880`
- `KUBHIST2-GOTEBORGSPOSTEN-1880`
- `KUBHIST2-POST-OCHINRIKESTIDNINGAR-1880`
- `KUBHIST2-NORRKOPINGSTIDNINGAR-1880`

#### `n00-s07` (1900)
- `KUBHIST2-AFTONBLADET-1900`
- `KUBHIST2-KALMAR-1900`
- `KUBHIST2-OSTGOTAPOSTEN-1900`
- `UB-KVT-IDUN`
- `UB-KVT-DAGNY`

#### `n23-s08` (1923)
- `KUBHIST-DALPILEN-1920`
- `UB-KVT-KVT`
- `UB-KVT-TIDEVARVET`
- `UB-KVT-HERTHA`
- `RUNEBERG-TIDEN`
- `ORDAT`

#### `n30-bng` (1930)
- `UB-KVT-TIDEVARVET`
- `RUNEBERG-TIDEN`
- `RUNEBERG-BIBLBLAD`
- `ORDAT`
- `FSBSKONLIT1900-1959`

#### `n50-s09` (1950)
- `FRAGELISTOR`
- `SBS-FOLKE`
- `ORDAT`
- `SAOB-BOCKER`
- `VIVILL`

#### `n73-s10` (1973)
- `ASTRA1960-1979`
- `FSBSKONLIT1960-1999`
- `FSBESSAISTIK`
- `SALTNLD-SV`
- `SAOB-BOCKER`

#### `n86-s11` (1986)
- `PAROLE`
- `FSBSKONLIT1960-1999`
- `FSBESSAISTIK`
- `SALTNLD-SV`
- `SAOB-BOCKER`

#### `n98-s12` (1998)
- `PRESS98`
- `HBL1998`
- `LT1998`
- `SWEACHUM`
- `LASBART`
- `BLOGGMIX1998` (optional, internet/register style)

#### `t06-s13` (2006)
- `WEBBNYHETER2006`
- `GP2006`
- `SVT-2006`
- `BLOGGMIX2006`
- `FSBSKONLIT2000TAL`
- `SWEACSAM`

### Optional “volume boost” corpora (all modern editions)

These provide very large token volumes but more institutional language:

- `SOU`
- `SFS`
- `RD-PROP`
- `RD-PROT`
- `RD-BET`
- `RD-MOT`

Use them as a second pass when you want robust counts, not as the only source for colloquial/general vocabulary trends.

## Minimal curl examples

List default-mode corpora config:

```bash
curl -sS 'https://ws.spraakbanken.gu.se/ws/korp/v8/corpus_config?mode=default'
```

Get corpus metadata:

```bash
curl -sS 'https://ws.spraakbanken.gu.se/ws/korp/v8/corpus_info?corpus=ROMI,SEKELSKIFTE'
```

Count yearly frequency for one word in one decade:

```bash
curl -sS 'https://ws.spraakbanken.gu.se/ws/korp/v8/count_time' \
  --data-urlencode 'corpus=ROMI,SEKELSKIFTE' \
  --data-urlencode 'cqp=[word = "och"]' \
  --data-urlencode 'granularity=y' \
  --data-urlencode 'from=19000101000000' \
  --data-urlencode 'to=19091231235959' \
  --data-urlencode 'combined=true' \
  --data-urlencode 'per_corpus=false'
```

Get token totals for normalization:

```bash
curl -sS 'https://ws.spraakbanken.gu.se/ws/korp/v8/timespan' \
  --data-urlencode 'corpus=ROMI,SEKELSKIFTE' \
  --data-urlencode 'granularity=y' \
  --data-urlencode 'from=19000101000000' \
  --data-urlencode 'to=19091231235959' \
  --data-urlencode 'combined=true' \
  --data-urlencode 'per_corpus=false'
```

## References

- Korp API root/info:  
  `https://ws.spraakbanken.gu.se/ws/korp/v8/info`
- Corpus config endpoint:  
  `https://ws.spraakbanken.gu.se/ws/korp/v8/corpus_config`
- Corpus metadata endpoint:  
  `https://ws.spraakbanken.gu.se/ws/korp/v8/corpus_info`
- Time series count endpoint:  
  `https://ws.spraakbanken.gu.se/ws/korp/v8/count_time`
- Time span totals endpoint:  
  `https://ws.spraakbanken.gu.se/ws/korp/v8/timespan`
