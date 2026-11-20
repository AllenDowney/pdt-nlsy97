#!/usr/bin/env python3
"""Cross-check pdt.panel against scripts/measure_spread.py (PublicDataToolkit Task 69).

For YSAQ-360C (smoked since the last interview; past twelve months in 2013 and 2015), count the
people with at least one valid answer whose period overlaps a year, and with two or more, using
pdt.panel.answers on the common-format data; measure_spread.py counts the same from the wide file.
Run under the memory cap: `make data` first.
"""

import collections
import sys
from pathlib import Path

from pdt.panel import Answer, Panel

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {2005: (8377, 5075), 2010: (7784, 4653), 2012: (1752, 33)}   # measure_spread.py: >=1, >=2


def main():
    p = Panel(ROOT)   # month 0 from dataset.yaml panel.month_zero (NLS: January 1980 = 1)
    people = sorted(p._by_person)
    ok = True
    for year, (want1, want2) in EXPECTED.items():
        counts = collections.Counter()
        for person in people:
            n = sum(1 for a in p.answers("YSAQ-360C", person, year=year) if isinstance(a, Answer) and a.value >= 0)
            counts[min(n, 2)] += 1
        got1, got2 = counts[1] + counts[2], counts[2]
        ok &= (got1, got2) == (want1, want2)
        print(f"{year}: >=1 answer {got1:,} (measure_spread {want1:,}); >=2 {got2:,} ({want2:,})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
