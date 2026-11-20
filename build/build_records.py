"""Build the NLSY97 slice's records from the NLS codebook and the cohort file, 1997-2023.

Usage:
    python build/build_records.py     (make build; run under the memory cap)

Reads build/slice.yaml, the codebook inside data/raw/1997-2023/nlsy97_all_1997-2023.zip (the
slice's entries are copied to data/interim/slice.cdb) and the slice's columns
(data/interim/slice_wide.csv, from scripts/extract_slice.py). Writes
metadata/releases/1997-2023/<table>/variables.jsonl and build/report.md.

A record is a question name; each survey year's entry for it is one codebook entry and one column
(a reference number). Where each field comes from (STANDARD.md §3):
- label: the latest year's codebook title; question text, universe, codes and labels, ranges,
  implied decimals, the reserved codes -1 to -5 and every count: the codebook
- source_columns: the codebook's reference number for each year (R03206.00 is column R0320600)
- availability by year and n: the data (values that aren't negative codes)
- missing types of the reserved codes: rule nlsy_reserved_codes, from NLS's labels
- measure: build/slice.yaml (hand)
- SURVEY_YEAR, the person_year table's year: rule nlsy_reshape
- questions[].reference_period: rule nlsy_reference_period, from explicit phrases in the text
"""

import collections
import json
import re
import zipfile
from pathlib import Path

import pandas as pd
import yaml

import nlsy_cdb

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "data/raw/1997-2023/nlsy97_all_1997-2023.zip"
INTERIM = ROOT / "data/interim"
META = ROOT / "metadata"
DATASET = "nlsy97"
RULE_VERSION = "0.1"
CODEBOOK, DATA = "nlsy97-codebook", "nlsy97-all-1997-2023"
GO_TO = re.compile(r"\s*\(Go To [A-Z]\d{5}\.\d{2}\)\s*$")

# Rule nlsy_reserved_codes: NLS reserves -1 to -5 for every variable and prints each one's count
# under its codebook entry. The types come from the labels.
RESERVED = {-1: ("Refusal", ["refused"], None),
            -2: ("Don't know", ["dk"], None),
            -3: ("Invalid skip", ["no_answer"], "An invalid skip: the respondent wasn't asked a question they should have been."),
            -4: ("Valid skip", ["inap"], None),
            -5: ("Non-interview", ["not_asked"], "The respondent wasn't interviewed in that survey year.")}


def slice_cdb(names):
    """The slice's codebook entries, copied out of the 329 MB codebook once (streamed)."""
    out = INTERIM / "slice.cdb"
    if out.exists():
        return out
    head = re.compile(r"^[A-Z]\d{5}\.\d{2} +\[([^\]]+)\]")
    keep = False
    with zipfile.ZipFile(ZIP) as z, z.open("nlsy97_all_1997-2023.cdb") as f, open(out, "w") as w:
        for raw in f:
            line = raw.decode("latin-1")
            m = head.match(line)
            if m:
                keep = m.group(1) in names or any(
                    n.startswith("__prefix__") and m.group(1).startswith(n[len("__prefix__"):] + "_") for n in names)
            if keep:
                w.write(line)
    return out


GROUPS = []
ARRAY_HEAD = re.compile(r"^([A-Z][A-Z_]*?)_\d{4}\.\d{2}$")


def slice_names(spec):
    """The question names to copy out of the codebook: the tables' names, and for each array prefix,
    every name that starts with it (prefix_YYYY.MM)."""
    names = {n for t in spec["tables"].values() for n in t}
    prefixes = {p for arrays in (spec.get("arrays") or {}).values() for p in arrays}
    return names | {f"__prefix__{p}" for p in prefixes}


def tokens_by_column():
    """{column: Counter(token)} from the slice's columns, cells as written."""
    wide = pd.read_csv(INTERIM / "slice_wide.csv", dtype=str, keep_default_na=False)
    return {c: collections.Counter(wide[c]) for c in wide.columns}, len(wide)


# Rule nlsy_reference_period: the period a wording states, from explicit phrases only. A wording
# with none ("In general, how is your health?") gets no reference_period.
PERIODS = [(re.compile(r"since (the )?last interview", re.I), "since_last_interview", None),
           (re.compile(r"(within|during|in) the past twelve months|past 12 months", re.I), "past_months", 12),
           (re.compile(r"(past|last) 30 days", re.I), "past_30_days", None),
           (re.compile(r"during the (last|past) month", re.I), "past_months", 1),
           (re.compile(r"\bhave you ever\b", re.I), "ever", None),
           (re.compile(r"as of (the )?(survey|interview) date", re.I), "as_of_interview", None),
           (re.compile(r"in the previous year", re.I), "calendar_year", None)]


def reference_period(text):
    for pattern, kind, months in PERIODS:
        if pattern.search(text):
            return kind, months
    return None


def is_valid_token(t):
    """Not empty and not one of NLS's reserved codes -1 to -5 (other negatives, such as a family
    income below -$2,999, are values)."""
    return t not in ("", "-1", "-2", "-3", "-4", "-5")


def years_text(years):
    return ", ".join(map(str, years))


def build_record(name, table, entries, measure, spec, tokens):
    es = sorted(entries, key=lambda e: str(e["year"]))
    last = es[-1]
    hand = {"origin": "hand", "author": spec["author"], "date": spec["date"]}
    fields = {"measure": hand}
    record = {"dataset": DATASET, "release": spec["release"], "table": table, "name": name, "label": last["title"]}
    notes = []
    titles = collections.OrderedDict()
    for e in es:
        titles.setdefault(e["title"], []).append(e["year"])
    if len(titles) > 1:
        fields["label"] = {"origin": "publisher", "source": CODEBOOK, "note": "The latest survey year's title."}
        notes.append("Titles by year: " + "; ".join(f"{t} ({years_text(y)})" for t, y in titles.items()))
    wordings = collections.OrderedDict()
    for e in es:
        if e["text"] and not e["text"].startswith("COMMENT:"):
            wordings.setdefault(" ".join(e["text"].split()), []).append(e["year"])
    if wordings:
        record["questions"] = []
        for t, y in wordings.items():
            q = {"text": t, "waves": y}
            period = reference_period(t)
            if period:
                q["reference_period"] = period[0]
                if period[1]:
                    q["months"] = period[1]
            record["questions"].append(q)
        if any("reference_period" in q for q in record["questions"]):
            fields["questions"] = {"origin": "publisher", "source": CODEBOOK,
                                   "note": "Text from the codebook; reference_period from the text by rule "
                                           f"nlsy_reference_period {RULE_VERSION} (STANDARD.md §4.1)."}
    notes += sorted({" ".join(e["text"][len("COMMENT:"):].split()) for e in es if e["text"].startswith("COMMENT:")})
    universes = collections.OrderedDict()
    for e in es:
        universes.setdefault(e["universe"], []).append(e["year"])
    stated = [(u, y) for u, y in universes.items() if u]
    if len(universes) == 1 and stated:
        record["universe"] = stated[0][0]
    elif stated:  # a universe by wave (STANDARD.md §4.1); years whose entry states none are left out
        record["universe"] = [{"text": u, "waves": y} for u, y in stated]
        if len(stated) < len(universes):
            notes.append("The codebook states no universe for " + years_text(universes.get("", [])) + ".")
    # Codes: the latest year's label; n is the codebook's count summed over the years, which is the
    # count in the long table.
    values, counts, lows, highs, relabeled = {}, collections.Counter(), [], [], []
    by_wave = collections.defaultdict(list)   # code -> [{wave, n}], the codebook's count in each year
    for e in es:
        for code, (_, n) in e["reserved"].items():
            by_wave[code].append({"wave": e["year"], "n": n})
        for n, code, label in e["rows"]:
            if isinstance(code, tuple):
                lows.append(code[0])
                highs.append(code[1])
                continue
            label = GO_TO.sub("", label).strip()
            if not label:
                lows.append(code)
                highs.append(code)
                continue
            if code in values and values[code].lower() != label.lower():
                relabeled.append(f"{code}: '{values[code]}' -> '{label}' ({e['year']})")
            values[code] = label
            counts[code] += n
            by_wave[code].append({"wave": e["year"], "n": n})
    reserved_n = collections.Counter()
    for e in es:
        for code, (_, n) in e["reserved"].items():
            reserved_n[code] += n
    spans = len(es) > 1
    out_values = [dict({"code": c, "label": l, "kind": "valid", "n": counts[c]},
                       **({"counts": by_wave[c]} if spans else {})) for c, l in values.items()]
    for code, (label, types, note) in RESERVED.items():
        if code in reserved_n:
            out_values.append({"code": code, "label": label, "kind": "missing", "missing_types": types,
                               "n": reserved_n[code], **({"counts": by_wave[code]} if spans else {}),
                               "origin": {"origin": "rule", "rule": "nlsy_reserved_codes", "rule_version": RULE_VERSION,
                                          "source": CODEBOOK,
                                          "note": "NLS reserves -1 to -5 and counts them under every entry; the type "
                                                  "is from the label." + (f" {note}" if note else "")}})
    record["values"] = out_values
    fields["values"] = {"origin": "publisher", "source": CODEBOOK,
                        "note": "The codebook's codes and labels (the latest year's label, without routing such as "
                                "'(Go To R21895.00)'); counts are the codebook's count in each year, n their sum."}
    if relabeled:
        notes.append("Labels that differ by year (beyond case): " + "; ".join(relabeled))
    if lows:
        record["valid_range"] = {"min": min(lows), "max": max(highs), "note": "The codebook's code ranges."}
        fields["valid_range"] = {"origin": "publisher", "source": CODEBOOK}
    elif not values and all(e["min"] is not None for e in es):
        record["valid_range"] = {"min": min(e["min"] for e in es), "max": max(e["max"] for e in es),
                                 "note": "The codebook lists no codes; its Min and Max."}
        fields["valid_range"] = {"origin": "publisher", "source": CODEBOOK}
    m = re.search(r"(\d+) IMPLIED DECIMAL", " ".join(e["text"] for e in es), re.I)
    if m:
        record["implied_decimals"] = int(m.group(1))
        fields["implied_decimals"] = {"origin": "publisher", "source": CODEBOOK,
                                      "note": "The entry's note: 'N IMPLIED DECIMAL PLACES'."}
    record["measure"] = measure
    present = [t for e in es for t in tokens[e["column"]] if t != ""]
    record["storage_type"] = "integer" if all(re.fullmatch(r"-?\d+", t) for t in present) else "float"
    fields["storage_type"] = {"origin": "rule", "rule": "storage_type_from_values", "rule_version": RULE_VERSION,
                              "source": DATA}
    record["source_columns"] = [{"waves": [e["year"]], "column": e["column"]} for e in es]
    fields["source_columns"] = {"origin": "publisher", "source": CODEBOOK,
                                "note": "Each year's reference number (R03206.00 is column R0320600)."}
    record["availability"] = [{"wave": e["year"], "n": sum(k for t, k in tokens[e["column"]].items() if is_valid_token(t))}
                              for e in es]
    fields["availability"] = {"origin": "data_file", "source": DATA, "note": "n counts values that aren't empty or NLS's reserved codes -1 to -5."}
    if notes:
        record["notes"] = "\n".join(notes)
    record["source_location"] = {"source": CODEBOOK, "anchor": last["rnum"]}
    record["provenance"] = {"record": {"origin": "publisher", "source": CODEBOOK}, "fields": fields}
    return record


def survey_year_record(spec, years, persons):
    rule = {"origin": "rule", "rule": "nlsy_reshape", "rule_version": RULE_VERSION, "source": DATA,
            "note": "The survey year of the codebook entry each cell came from; person_year has one row per "
                    "respondent and survey year."}
    return {"dataset": DATASET, "release": spec["release"], "table": "person_year", "name": "SURVEY_YEAR",
            "label": "Survey year of the row", "storage_type": "integer", "measure": "categorical",
            "variable_type": "design", "valid_range": {"min": min(years), "max": max(years)},
            "availability": [{"wave": y, "n": persons} for y in years],
            "provenance": {"record": rule, "fields": {}}}


def check_codes(record, entries, tokens):
    """C4: tokens in the data the record doesn't cover."""
    if record["measure"] in ("identifier", "weight"):
        return []
    listed = {v["code"] for v in record.get("values", [])}
    vr = record.get("valid_range")
    out = []
    for e in entries:
        for t, n in tokens[e["column"]].items():
            if t == "":
                continue
            c = float(t)
            c = int(c) if c.is_integer() else c
            if c not in listed and not (vr and vr["min"] <= c <= vr["max"]):
                out.append(f"- `{record['name']}` {e['year']} ({e['column']}): code {t} occurs {n:,} times, not documented")
    return out


def main():
    spec = yaml.safe_load((ROOT / "build" / "slice.yaml").read_text())
    names = slice_names(spec)
    by_name = collections.defaultdict(list)
    for e in nlsy_cdb.entries(slice_cdb(names)):
        by_name[e["name"]].append(e)
    for table, arrays in (spec.get("arrays") or {}).items():
        for prefix, measure in arrays.items():
            members = sorted(n for n in by_name if n.startswith(prefix + "_"))
            spec["tables"][table].update({n: measure for n in members})
            GROUPS.append({"id": f"array-{prefix.lower().replace('_', '-')}", "kind": "other",
                           "label": f"{prefix}: an NLS event history array ({len(members)} monthly variables)",
                           "members": [{"release": spec["release"], "table": table, "name": n} for n in members],
                           "ordered": True,
                           "origin": {"origin": "publisher", "source": CODEBOOK,
                                      "note": "NLSY97 Codebook Supplement, Appendix 6: Event History Creation and "
                                              "Documentation; one variable per month."}})
    tokens, persons = tokens_by_column()
    years = sorted({e["year"] for n in spec["tables"]["person_year"] for e in by_name[n] if isinstance(e["year"], int)})
    problems, report, total = [], [], 0
    for table, variables in spec["tables"].items():
        records = []
        for name, measure in variables.items():
            entries = by_name[name]
            rec = build_record(name, table, entries, measure, spec, tokens)
            if table == "person_year" and name == "PUBID":
                n = rec["availability"][0]["n"]
                rec["source_columns"] = [{"waves": years, "column": entries[0]["column"]}]
                rec["availability"] = [{"wave": y, "n": n} for y in years]
                rec["notes"] = "The respondent's id, repeated on each of their rows (one per survey year)."
            problems += check_codes(rec, entries, tokens)
            records.append(rec)
        if table == "person_year":
            records.insert(1, survey_year_record(spec, years, persons))
        write_jsonl(META / "releases" / spec["release"] / table / "variables.jsonl", records)
        report += [f"## {table}", "", f"- {len(records)} records", ""]
        total += len(records)
    write_jsonl(META / "groups.jsonl", GROUPS)
    lines = [f"# Build report: {DATASET}, release {spec['release']}", "",
             "Generated by `build/build_records.py`. Do not edit.", "", f"- Records: {total}",
             f"- Respondents: {persons:,}; survey years: {years_text(years)}", ""] + report
    lines += ["## Codes in the data the records don't cover", ""] + (problems or ["None."])
    (ROOT / "build" / "report.md").write_text("\n".join(lines) + "\n")
    print(f"{total} records; see build/report.md")


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
