#!/usr/bin/env python3
"""Read and write item files: deferred items (DEFER-3) and design-check questions (Q-3).

An item file is a Markdown checkbox list, one item per top-level checkbox with
its fields as a nested bullet list, so a Markdown formatter keeps the layout.
Every item has an Instruction (what to do) and a Status (where it stands), in
the vocabulary of `skills/review/tracking.md` "Items"; the box is ticked
exactly when the status is fixed, wont-fix, or deferred. A box ticked by hand
with no status reads as fixed.

Usage:
  items.py list FILE [--open]
  items.py set FILE ID "Fix as noted" [--note "..."]
  items.py status FILE ID STATUS [--ref "commit, record, or reason"]
  items.py validate FILE

Other scripts import read(), write(), and the constants.
"""
import argparse, datetime, os, re, sys
from records import load_script, write_atomic
import ids

INSTRUCTIONS = ("Fix as recommended", "Fix as noted", "Discuss", "Defer", "Ignore", "Refine")
STATUSES = ("open", "in-progress", "fixed", "wont-fix", "deferred")
DONE = ("fixed", "wont-fix", "deferred")
DESIGN_WEIGHTS = ("settle-first", "worth-settling", "note")
SURVEY_WEIGHTS = ("do-first", "worth-doing", "note")
SURVEY_KINDS = ("refactor", "trap")
ABSOLUTE_WHERE = re.compile(r"^/\S*:\d+$")


def not_done(items): return [i for i in items if not i["done"]]

ITEM_ID = ids.pattern(*ids.ITEMS)
ITEM_RE = re.compile(rf"^[-*+] \[( |x|X)\] ({ITEM_ID})\.\s+(.*)$")

def labels_in(path):
    """Field labels used in a file: every `  - Label:` under an item."""
    if not os.path.exists(path): return []
    seen = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^\s+[-*+]\s+([A-Z][A-Za-z ]{1,24}):\s", line)
        if m and m.group(1) not in seen: seen.append(m.group(1))
    return seen

def read(path, labels=None):
    """Items as {id, done, text, fields, order}. Everything indented under an
    item's checkbox belongs to it; bullet markers are dropped, the text is read
    as one paragraph, and it is split on the field labels, so a file a formatter
    rewrapped or re-indented reads the same. `labels` defaults to those the file
    uses plus Instruction, Status, and Outcome."""
    if not os.path.exists(path): return []
    labels = list(labels or labels_in(path))
    for k in ("Instruction", "Status", "Outcome"):
        if k not in labels: labels.append(k)
    split = re.compile(r"(?:^|\s)(" + "|".join(re.escape(l) for l in sorted(labels, key=len, reverse=True)) + r"):(?=\s|$)")
    items, cur = [], None
    for line in open(path, encoding="utf-8"):
        m = ITEM_RE.match(line.rstrip("\n"))
        if m:
            cur = {"done": m.group(1).lower() == "x", "id": m.group(2), "lines": [m.group(3)]}
            items.append(cur); continue
        if not line.strip(): continue
        if cur and line[0] in " \t": cur["lines"].append(re.sub(r"^[-*+]\s+", "", line.strip()))
        else: cur = None
    for it in items:
        parts = split.split(" ".join(it.pop("lines")))
        it["text"] = parts[0].strip()
        it["fields"] = {k: v.strip() for k, v in zip(parts[1::2], parts[2::2])}
        it["order"] = [k for k in parts[1::2]]
        st = it["fields"].get("Status", "").lower()
        if not st: it["fields"]["Status"] = "fixed" if it["done"] else "open"
        it["done"] = it["fields"]["Status"] in DONE
    return items

def write(path, items, header, order=()):
    """Write items under `header`, fields in `order` first, then as read."""
    out = [header]
    for it in items:
        it["done"] = it["fields"].get("Status", "open") in DONE
        out.append(f"- [{'x' if it['done'] else ' '}] {it['id']}. {it['text']}\n")
        keys = [k for k in order if k in it["fields"]] + [k for k in it.get("order", []) if k not in order and k in it["fields"]]
        keys += [k for k in it["fields"] if k not in keys]
        for k in keys:
            out.append(f"  - {k}:{' ' + it['fields'][k] if it['fields'][k] else ''}\n")
        out.append("\n")
    write_atomic(path, "".join(out).rstrip("\n") + "\n")

def header_of(path):
    """Everything before the first item, kept as it is on rewrite."""
    text = open(path, encoding="utf-8").read()
    m = re.search(rf"^[-*+] \[[ xX]\] {ITEM_ID}\.", text, re.M)
    return text[:m.start()] if m else text.rstrip("\n") + "\n\n"

def instruction(value):
    v = next((i for i in INSTRUCTIONS if i.lower() == value.strip().lower()), None)
    if not v: sys.exit(f"unknown instruction {value!r}; one of: {', '.join(INSTRUCTIONS)}")
    return v

def base(value):
    """The instruction without its note: "Fix as noted: shorter wording" -> "Fix as noted"."""
    return value.split(":", 1)[0].strip()

def set_status(it, status, ref=None):
    if status not in STATUSES: sys.exit(f"unknown status {status!r}; one of: {', '.join(STATUSES)}")
    it["fields"]["Status"] = status
    if ref: it["fields"]["Outcome"] = f"{datetime.date.today().isoformat()} {ref}"
    elif status == "open": it["fields"].pop("Outcome", None)

def find(items, iid):
    it = next((i for i in items if ids.same(i["id"], ids.normalize(iid))), None)
    if not it: sys.exit(f"{iid} not found")
    return it

def first_token(value): return (value.split() or [""])[0]

def check_problems(path, items):
    records = load_script("records.py")
    kind, _ = records.check_header(open(path, encoding="utf-8").read(), ids.check_from_file(os.path.basename(path)) or "")
    survey = kind == records.SURVEY
    weights = SURVEY_WEIGHTS if survey else DESIGN_WEIGHTS
    bad = []
    for i in items:
        f = i["fields"]
        if f.get("Weight") and first_token(f["Weight"]) not in weights: bad.append(f"{i['id']}: weight {f['Weight']!r}")
        if survey and f.get("Kind") and f["Kind"].strip() not in SURVEY_KINDS: bad.append(f"{i['id']}: kind {f['Kind']!r}")
        if survey and f.get("Where") and not ABSOLUTE_WHERE.match(f["Where"].strip()): bad.append(f"{i['id']}: where {f['Where']!r}")
    return bad

def close(it, status, ref=None):
    set_status(it, status, (f"in {ref}" if re.fullmatch(r"[0-9a-f]{7,40}", ref) else ref) if ref else "closed")

def reopen(it): set_status(it, "open")

def set_instruction(it, value, note=None):
    it["fields"]["Instruction"] = instruction(value) + (f": {note}" if note else "")

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    l = sp.add_parser("list"); l.add_argument("file"); l.add_argument("--open", action="store_true")
    s = sp.add_parser("set"); s.add_argument("file"); s.add_argument("iid"); s.add_argument("value"); s.add_argument("--note")
    st = sp.add_parser("status"); st.add_argument("file"); st.add_argument("iid"); st.add_argument("value"); st.add_argument("--ref")
    sp.add_parser("validate").add_argument("file")
    a = ap.parse_args()
    if not os.path.exists(a.file): sys.exit(f"{a.file} does not exist")
    items = read(a.file)
    if a.cmd == "list":
        for i in items:
            if a.open and i["done"]: continue
            f = i["fields"]
            print(f"{'x' if i['done'] else ' '} {i['id']}. {i['text']}  [{f.get('Instruction') or 'no instruction'}; {f['Status']}" + (f"; {f['Outcome']}" if f.get("Outcome") else "") + "]")
    elif a.cmd == "validate":
        bad = [f"{i['id']}: instruction {i['fields']['Instruction']!r}" for i in items if i["fields"].get("Instruction") and base(i["fields"]["Instruction"]) not in INSTRUCTIONS]
        bad += [f"{i['id']}: status {i['fields']['Status']!r}" for i in items if i["fields"]["Status"] not in STATUSES]
        bad += check_problems(a.file, items)
        print("\n".join(bad) or f"{len(items)} items, all valid"); sys.exit(1 if bad else 0)
    else:
        it = find(items, a.iid)
        if a.cmd == "set":
            set_instruction(it, a.value, a.note)
        else:
            set_status(it, a.value, a.ref)
        write(a.file, items, header_of(a.file), order=labels_in(a.file))
        print(f"{it['id']}: {it['fields'].get('Instruction') or 'no instruction'}; {it['fields']['Status']}")

if __name__ == "__main__": main()
