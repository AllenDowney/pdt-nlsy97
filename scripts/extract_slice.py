#!/usr/bin/env python3
"""Copy the slice's columns out of the 8.1 GB NLSY97 CSV into data/interim/slice_wide.csv.

The columns are the reference numbers of every codebook entry whose question name is in
build/slice.yaml (data/interim/slice.cdb, copied from the codebook first). Cells are kept
as text, exactly as written. Read in row chunks; run under the memory cap (CLAUDE.md).
"""

import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / "data/raw/1997-2023/nlsy97_all_1997-2023.zip"
MEMBER = "nlsy97_all_1997-2023.csv"
OUT = ROOT / "data/interim/slice_wide.csv"


def columns():
    sys.path.insert(0, str(ROOT / "build"))
    import yaml
    from build_records import slice_cdb, slice_names  # copies the slice's codebook entries to data/interim/slice.cdb
    spec = yaml.safe_load((ROOT / "build/slice.yaml").read_text())
    slice_cdb(slice_names(spec))
    heads = re.findall(r"^([A-Z]\d{5})\.(\d{2}) +\[", (ROOT / "data/interim/slice.cdb").read_text(), re.M)
    return [a + b for a, b in heads]


def main():
    cols = columns()
    first = True
    with zipfile.ZipFile(ZIP) as z, z.open(MEMBER) as f:
        reader = pd.read_csv(io.TextIOWrapper(f, encoding="latin-1"), usecols=cols, dtype=str,
                             keep_default_na=False, chunksize=1000)
        for chunk in reader:
            chunk[cols].to_csv(OUT, mode="w" if first else "a", header=first, index=False)
            first = False
    print(f"{OUT.relative_to(ROOT)}: {len(cols)} columns")


if __name__ == "__main__":
    sys.exit(main())
