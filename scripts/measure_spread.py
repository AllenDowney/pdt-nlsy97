#!/usr/bin/env python3
"""Measure how a person's answers spread over rounds in the NLSY97 slice (PublicDataToolkit Task 69).

Reads data/interim/slice_wide.csv and the records' source_columns; prints the tables quoted in
PublicDataToolkit/planning/tasks/task-69.md. Describes the data; makes no analysis choices.

1. Gaps between a person's interviews (CV_INTERVIEW_CMONTH, continuous months), and missed rounds.
2. "At age A": how many interviews a person has at age A (CV_AGE_INT_DATE), and if none, how far
   the nearest interview is from their A-th birthday; and whether NLS's monthly array
   (MAR_STATUS) has a status for the month they turned A.
3. "In year Y" for a since-the-last-interview question (YSAQ-360C): how many rounds' reference
   periods overlap year Y: (previous interview, this interview], or the twelve months before the
   interview in the years the record's wording says "within the past twelve months".
4. An "ever" question (YSAQ-359): the round in which a person first gave a substantive answer.
5. Agreement between CV_MARSTAT_COLLAPSED at an interview and MAR_STATUS in that month.
"""

import collections
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "metadata/releases/1997-2023"


def records(table):
    return {r["name"]: r for r in map(json.loads, (REL / table / "variables.jsonl").open())}


def by_year(wide, rec):
    """{year: Series of ints, indexed by row} for a record spanning years."""
    return {y: wide[sc["column"]].astype(int) for sc in rec["source_columns"] for y in sc["waves"]}


def quantiles(xs, qs=(0.5, 0.9, 0.99)):
    s = pd.Series(xs)
    return ", ".join(f"p{int(q * 100)} {s.quantile(q):.0f}" for q in qs) + f", max {s.max():.0f}"


def main():
    wide = pd.read_csv(ROOT / "data/interim/slice_wide.csv", dtype=str, keep_default_na=False)
    py, pe = records("person_year"), records("person")
    n = len(wide)
    cmonth = by_year(wide, py["CV_INTERVIEW_CMONTH"])
    age = by_year(wide, py["CV_AGE_INT_DATE"])
    years = sorted(cmonth)
    bm = wide[pe["KEY!BDATE_M"]["source_columns"][0]["column"]].astype(int)
    by = wide[pe["KEY!BDATE_Y"]["source_columns"][0]["column"]].astype(int)
    birth = (by - 1980) * 12 + bm          # continuous month: January 1980 = 1
    mar = {r["name"][len("MAR_STATUS_"):]: wide[r["source_columns"][0]["column"]].astype(int)
           for name, r in pe.items() if name.startswith("MAR_STATUS_")}

    def mar_at(i, cm):
        y, m = 1980 + (cm - 1) // 12, (cm - 1) % 12 + 1
        col = mar.get(f"{y}.{m:02d}")
        return None if col is None else col.iloc[i]

    # 1. Gaps between interviews
    interviews = [[(y, cmonth[y].iloc[i]) for y in years if cmonth[y].iloc[i] > 0] for i in range(n)]
    gaps = collections.defaultdict(list)
    missed = 0
    persons_missing = 0
    for iv in interviews:
        miss_here = False
        for (y0, c0), (y1, c1) in zip(iv, iv[1:]):
            skipped = years.index(y1) - years.index(y0) - 1
            era = "annual (to 2011)" if y1 <= 2011 else "biennial (2013 on)"
            gaps[era].append(c1 - c0)
            if skipped:
                missed += 1
                miss_here = True
                gaps["after a missed round"].append(c1 - c0)
        persons_missing += miss_here
    pairs = sum(max(len(iv) - 1, 0) for iv in interviews)
    print("## 1. Months between a person's consecutive interviews\n")
    print("| Pairs of interviews | Count | Months between them |\n|---|---|---|")
    for era in ("annual (to 2011)", "biennial (2013 on)", "after a missed round"):
        print(f"| {era} | {len(gaps[era]):,} | {quantiles(gaps[era])} |")
    print(f"\n{pairs:,} pairs of consecutive interviews; {missed:,} ({missed / pairs:.1%}) skip at least one round. "
          f"{persons_missing:,} of {n:,} people ({persons_missing / n:.1%}) missed a round and came back. "
          f"Interviews per person: {quantiles([len(iv) for iv in interviews], (0.1, 0.5))}.\n")

    # 2. At age A
    print("## 2. A person's interviews at age A, and NLS's monthly marital array at that age\n")
    print("| Age | 0 interviews at that age | 1 | 2 or more | Of the 0: nearest interview ≤ 12 months from the birthday | > 12 months | MAR_STATUS has a status the month of the birthday |")
    print("|---|---|---|---|---|---|---|")
    for A in (16, 18, 21, 25, 30, 35):
        counts = collections.Counter()
        near = collections.Counter()
        arr = 0
        for i in range(n):
            k = sum(1 for y in years if age[y].iloc[i] == A)
            counts[min(k, 2)] += 1
            bd = birth.iloc[i] + 12 * A
            if k == 0:
                d = min((abs(c - bd) for _, c in interviews[i]), default=None)
                near["none" if d is None else ("le12" if d <= 12 else "gt12")] += 1
            v = mar_at(i, bd)
            arr += v is not None and v >= 0
        print(f"| {A} | {counts[0]:,} ({counts[0] / n:.0%}) | {counts[1]:,} ({counts[1] / n:.0%}) | "
              f"{counts[2]:,} ({counts[2] / n:.0%}) | {near['le12']:,} | {near['gt12'] + near['none']:,} | "
              f"{arr:,} ({arr / n:.0%}) |")

    # 3. In year Y, for a since-the-last-interview question
    q = by_year(wide, py["YSAQ-360C"])
    # The record's wordings: "since the last interview" through 2011; "within the past twelve months" in 2013, 2015.
    twelve = {y for w in py["YSAQ-360C"]["questions"] if "twelve months" in w["text"] for y in w["waves"]}

    def period(c0, c1, y1):
        return (c1 - 12, c1) if y1 in twelve else (c0, c1)
    print("\n## 3. YSAQ-360C (smoked since the last interview): how many rounds' periods overlap year Y\n")
    print("| Year | People with ≥1 answer whose period overlaps Y | 1 round | 2 rounds | 3 or more | none |\n|---|---|---|---|---|---|")
    for Y in (2000, 2005, 2010, 2012, 2014):
        lo, hi = (Y - 1980) * 12 + 1, (Y - 1980) * 12 + 12
        dist = collections.Counter()
        for i in range(n):
            iv = interviews[i]
            k = 0
            for (y0, c0), (y1, c1) in zip(iv, iv[1:]):
                p0, p1 = period(c0, c1, y1)
                if y1 in q and q[y1].iloc[i] >= 0 and p0 < hi and p1 >= lo:
                    k += 1
            dist[min(k, 3)] += 1
        have = n - dist[0]
        print(f"| {Y} | {have:,} | {dist[1]:,} | {dist[2]:,} | {dist[3]:,} | {dist[0]:,} |")
    lengths = [c1 - c0 for i in range(n) for (y0, c0), (y1, c1) in zip(interviews[i], interviews[i][1:])
               if y1 in q and y1 not in twelve and q[y1].iloc[i] >= 0]
    long_ = sum(1 for x in lengths if x > 18)
    print(f"\nPeriods behind the {len(lengths):,} answers: {quantiles(lengths)} months; "
          f"{long_:,} ({long_ / len(lengths):.1%}) are longer than 18 months. (Since-the-last-interview answers only; "
          f"in {sorted(twelve)} the question asks about the past twelve months.)\n")

    # 4. An ever question
    ever = by_year(wide, py["YSAQ-359"])
    first = collections.Counter()
    for i in range(n):
        f = next((y for y in sorted(ever) if ever[y].iloc[i] >= 0), None)
        first[f or "never answered"] += 1
    print("## 4. YSAQ-359 (ever smoked): the year of a person's first substantive answer\n")
    print("| First answered | People |\n|---|---|")
    for k in sorted(first, key=str):
        print(f"| {k} | {first[k]:,} |")

    # 5. Interview answer vs the monthly array
    ms = by_year(wide, py["CV_MARSTAT_COLLAPSED"])
    agree = total = 0
    for y in years:
        for i in range(n):
            c, v = cmonth[y].iloc[i], ms[y].iloc[i]
            if c > 0 and v >= 0:
                a = mar_at(i, c)
                if a is not None and a >= 0:
                    total += 1
                    agree += (v == 1) == (a == 2)
    print(f"\n## 5. CV_MARSTAT_COLLAPSED at each interview vs MAR_STATUS in the interview month\n\n"
          f"Married or not agrees in {agree:,} of {total:,} person-interviews ({agree / total:.1%}).")


if __name__ == "__main__":
    main()
