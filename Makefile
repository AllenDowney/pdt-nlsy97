PYTHON ?= python
# A PublicDataToolkit checkout. Or `pip install -e $(PDT)` and run `pdt check`.
PDT ?= ../PublicDataToolkit

# Data jobs run under a memory cap (CLAUDE.md); the cohort CSV is 8.1 GB.
CAP ?= systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 --quiet

.PHONY: download extract data build views check

## Fetch the sources into data/raw. Read the publisher's terms first, then: make download ARGS=--accept-terms
download:
	PYTHONPATH=$(PDT)/lib $(PYTHON) scripts/download.py $(ARGS)

## Copy the slice's columns out of the cohort CSV into data/interim (after the codebook step of make build)
extract:
	$(CAP) $(PYTHON) scripts/extract_slice.py

## Write the common-format parquet files in data/processed (STANDARD.md §8)
data:
	$(CAP) env PYTHONPATH=$(PDT)/lib $(PYTHON) scripts/build_data.py

## Build metadata records from data/raw (build/build_records.py writes build/report.md)
build:
	$(CAP) $(PYTHON) build/build_records.py

## Generate agent/, docs/ and export/ from the records (pdt views)
views:
	PYTHONPATH=$(PDT)/lib $(PYTHON) -m pdt views .

## Check the repo against the PublicDataToolkit standard (pdt check)
check:
	$(CAP) env PYTHONPATH=$(PDT)/lib $(PYTHON) -m pdt check .
