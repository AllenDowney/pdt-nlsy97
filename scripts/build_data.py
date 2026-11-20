#!/usr/bin/env python3
"""Write the NLSY97 slice in the common format (STANDARD.md §8): long, one row per respondent
and survey year.

Reads data/interim/slice_wide.csv (the slice's columns of the cohort file, copied as text by
scripts/extract_slice.py) and each record's source_columns, and writes
data/processed/nlsy97-1997-2023-person.parquet and -person_year.parquet.

The reshape is checked both ways before anything is written:
- wide -> long: every publisher cell in the slice's columns lands in exactly one
  (PUBID, survey year, variable) cell, NLS's negative codes included (-5 is a non-interview
  in that year: a code, not a missing row);
- long -> wide: every long cell either came from one publisher cell, which it equals, or has
  no publisher column for that year (the question wasn't in that year's file) and is empty.
pdt.release then checks the parquet file against the long frame, cell by cell.

Run under the memory cap (CLAUDE.md).
"""

import json
import sys
from pathlib import Path

import pandas as pd

try:
    from pdt.release import write_release
except ImportError:
    sys.exit("Needs the PublicDataToolkit library: pip install -e ../PublicDataToolkit, or run through `make data`.")

ROOT = Path(__file__).resolve().parent.parent
RELEASE = "1997-2023"
SOURCE = "nlsy97-all-1997-2023"


def records(table):
    path = ROOT / "metadata/releases" / RELEASE / table / "variables.jsonl"
    return [json.loads(line) for line in path.open()]


def value(token):
    """A cell as the CSV writes it, as a number; '' is empty."""
    if token == "":
        return None
    try:
        return int(token)
    except ValueError:
        return float(token)


def wide():
    return pd.read_csv(ROOT / "data/interim/slice_wide.csv", dtype=str, keep_default_na=False)


def person(w, recs):
    out = pd.DataFrame({r["name"]: w[r["source_columns"][0]["column"]].map(value) for r in recs})
    for r in recs:  # each person variable has one column, in one year
        assert len(r["source_columns"]) == 1, r["name"]
    return out


def person_year(w, recs):
    years = [a["wave"] for a in next(r for r in recs if r["name"] == "SURVEY_YEAR")["availability"]]
    ids = w[next(r for r in recs if r["name"] == "PUBID")["source_columns"][0]["column"]].map(value)
    n = len(w)
    long = pd.DataFrame({"PUBID": ids.repeat(len(years)).reset_index(drop=True),
                         "SURVEY_YEAR": years * n})
    row_of = {(p, y): i for i, (p, y) in enumerate(zip(long["PUBID"], long["SURVEY_YEAR"]))}
    for r in recs:
        if r["name"] in ("PUBID", "SURVEY_YEAR"):
            continue
        col = [None] * len(long)
        for sc in r["source_columns"]:
            for y in sc["waves"]:
                for p, t in zip(ids, w[sc["column"]]):
                    col[row_of[(p, y)]] = value(t)
        long[r["name"]] = col
    long = long[[r["name"] for r in recs]]
    check_both_ways(w, long, recs, ids, years)
    return long


def check_both_ways(w, long, recs, ids, years):
    """Raise unless the reshape is a one-to-one map of cells (see the module docstring)."""
    indexed = long.set_index(["PUBID", "SURVEY_YEAR"])
    for r in recs:
        if r["name"] in ("PUBID", "SURVEY_YEAR"):
            continue
        covered = set()
        for sc in r["source_columns"]:
            for y in sc["waves"]:
                covered.add(y)
                got = indexed.xs(y, level="SURVEY_YEAR")[r["name"]].reindex(ids)
                want = w[sc["column"]].map(value)
                if not all((a is None and pd.isna(b)) or a == b for a, b in zip(want, got)):
                    raise ValueError(f"{r['name']} {y}: the long cells don't match column {sc['column']}")
        for y in set(years) - covered:
            if indexed.xs(y, level="SURVEY_YEAR")[r["name"]].notna().any():
                raise ValueError(f"{r['name']} {y}: cells without a publisher column")
    used = {sc["column"] for r in recs for sc in r.get("source_columns", [])}
    print(f"  reshape checked both ways: {len(used)} publisher columns -> {len(long):,} rows x {len(recs)} variables")


def read(release, table, names):
    w = wide()
    recs = records(table)
    frame = person(w, recs) if table == "person" else person_year(w, recs)
    return frame[names], SOURCE


if __name__ == "__main__":
    write_release(ROOT, read)
