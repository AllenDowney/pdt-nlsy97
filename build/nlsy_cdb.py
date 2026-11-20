"""Parse NLS Investigator codebook text (.cdb) into entries, one per reference number.

    R03206.00    [YHEA-100]                                     Survey Year: 1997
      PRIMARY VARIABLE
                 HOW IS RS GENERAL HEALTH?                      the title
    Now, I'd like to ask you some questions ...                 question text and comments
    UNIVERSE: All
        3477       1 Excellent                                  count, code, label
         599       0
           0       30000 TO 59999: 300.00-599.99                count, range, label
      -------
    Refusal(-1)            0                                    NLS's reserved codes, with counts
    Don't Know(-2)         3
    Invalid Skip(-3)       2
    TOTAL =========>    8984   VALID SKIP(-4)       0     NON-INTERVIEW(-5)       0
    Min:              1        Max:              5        Mean:                1.94
    Lead In: ...
    Default Next Question: R03207.00
    --------------------------------------------------------------------------------

entries(path) yields {rnum, column, name, year, title, text, universe, rows, reserved, min, max};
`column` is the CSV's column name (R03206.00 -> R0320600), rows are [(count, code or (lo, hi), label)],
reserved is {code: (label, count)}.
"""

import re
from pathlib import Path

HEAD = re.compile(r"^([A-Z]\d{5})\.(\d{2}) +\[([^\]]+)\] +Survey Year: (\S+)\s*$")
ROW = re.compile(r"^\s+(\d+)\s+(-?\d+(?:\.\d+)?)(?:\s+TO\s+(-?\d+(?:\.\d+)?))?(?::)?\s*(.*)$")
RESERVED = re.compile(r"(Refusal|Don't Know|Invalid Skip|VALID SKIP|NON-INTERVIEW)\((-\d)\)\s+(\d+)", re.I)
MINMAX = re.compile(r"Min:\s+(-?[\d.]+)\s+Max:\s+(-?[\d.]+)")


def number(text):
    x = float(text)
    return int(x) if x.is_integer() and "." not in text else x


def entries(path):
    cur = None
    state = None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = HEAD.match(line)
        if m:
            if cur:
                yield finish(cur)
            year = m.group(4)
            cur = {"rnum": f"{m.group(1)}.{m.group(2)}", "column": m.group(1) + m.group(2), "name": m.group(3),
                   "year": int(year) if year.isdigit() else year, "title": "", "text": [], "universe": "",
                   "rows": [], "reserved": {}, "min": None, "max": None}
            state = "head"
            continue
        if cur is None:
            continue
        s = line.strip()
        if line.startswith("-" * 40):
            yield finish(cur)
            cur, state = None, None
            continue
        if state == "head":
            if s in ("PRIMARY VARIABLE", "") or s.startswith("SECONDARY"):
                continue
            cur["title"], state = s, "text"
            continue
        if state == "universe":
            if s:
                cur["universe"] += " " + s  # a wrapped universe
                continue
            state = "text"
            continue
        if state == "text":
            if s.startswith("UNIVERSE:"):
                cur["universe"] = s[len("UNIVERSE:"):].strip()
                state = "universe"
                continue
            r = ROW.match(line)
            if r and line.startswith("    ") and re.match(r"^\s{2,}\d+\s{2,}", line):
                state = "rows"
            elif s.startswith("Refusal(") or s.startswith("TOTAL"):
                state = "tail"
            else:
                cur["text"].append(s)
                continue
        if state == "rows":
            if s.startswith("-------"):
                state = "tail"
                continue
            r = ROW.match(line)
            if r:
                code = number(r.group(2)) if r.group(3) is None else (number(r.group(2)), number(r.group(3)))
                cur["rows"].append((int(r.group(1)), code, r.group(4).strip()))
            elif s and cur["rows"]:
                n, code, label = cur["rows"][-1]
                cur["rows"][-1] = (n, code, (label + " " + s).strip())
            continue
        if state == "tail":
            for label, code, n in RESERVED.findall(line):
                cur["reserved"][int(code)] = (label, int(n))
            mm = MINMAX.search(line)
            if mm:
                cur["min"], cur["max"] = number(mm.group(1)), number(mm.group(2))
    if cur:
        yield finish(cur)


def finish(e):
    text = "\n".join(e["text"]).strip()
    e["text"] = re.sub(r"\n{3,}", "\n\n", text)
    return e
