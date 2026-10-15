#!/usr/bin/env python3
"""Split a merged findings file by finding id.

Usage: split-findings.py MERGED --keep 3,7,12 -o KEPT [--rest REST]

Writes the findings whose ids are listed to KEPT, and the others to REST
when given, each as a findings file the other scripts read (the header and
one `findings` block). Ids and entry text are kept as they are. The final
pass uses it to append only the findings that meet the final bar.
"""
import argparse, re

def chunks(text):
    m = re.search(r"^```\s*findings\s*\n(.*?)^```\s*$", text, re.S | re.M)
    header = text[: m.start()] if m else text
    body = m.group(1) if m else ""
    parts = re.split(r"(?m)^(?=- id: \d+)", body)
    out = {}
    for p in parts:
        mm = re.match(r"^- id: (\d+)", p)
        if mm: out[int(mm.group(1))] = p.rstrip("\n")
    return header, out

def write(path, header, entries):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header.rstrip("\n") + "\n\n```findings\n" + "\n\n".join(entries) + "\n```\n")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("merged"); ap.add_argument("--keep", default=""); ap.add_argument("-o", required=True); ap.add_argument("--rest")
    a = ap.parse_args()
    keep = {int(x) for x in re.findall(r"\d+", a.keep)}
    header, byid = chunks(open(a.merged, encoding="utf-8").read())
    write(a.o, header, [byid[i] for i in sorted(byid) if i in keep])
    if a.rest: write(a.rest, header, [byid[i] for i in sorted(byid) if i not in keep])
    print(f"kept {sum(1 for i in byid if i in keep)} of {len(byid)}")

if __name__ == "__main__":
    main()
