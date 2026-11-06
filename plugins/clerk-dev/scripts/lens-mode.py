#!/usr/bin/env python3
USAGE = """Print one mode's lines of a lens agent's concerns, so a skill can use a lens's
Pass mode text without reading the whole agent prompt into its session.

Usage:
  lens-mode.py LENS [MODE]     MODE is review, design, survey, or pass; defaults to pass
  lens-mode.py --list [MODE]   lenses whose concerns all carry the mode's line, not all n/a

LENS is the lens name (edge-cases), not the agent name. Exits 1 when the lens does
not exist, its concerns do not parse, or they do not all carry the mode's line.
"""
import os, re, sys
from collections import namedtuple
import records

AGENTS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "agents")
OPENERS = {
    "Review": "Checked in a diff (see the review protocol):",
    "Design": "Asked of a design, plan, pieces, or brief record (see Design mode in the review protocol):",
    "Survey": "Asked of existing code before a change is defined (see Survey mode in the review protocol):",
    "Pass": "What the author does in a pass that uses this lens:",
}
LABELS = tuple(OPENERS)
NA = "n/a:"
ITEM = re.compile(r"(\d+)\. \*\*(.+)\*\*")
LABELED = re.compile(r"   - (\w+): ?(.*)")
CONTINUED = re.compile(r"     \S.*")

Concern = namedtuple("Concern", "number title lines")

class ConcernError(Exception): pass

def parse(lens, text):
    found = []
    for line in (l.rstrip() for l in text.split("\n")):
        where = f"lens-{lens}.md" + (f" concern {found[-1].number}" if found else "")
        if not line or line.startswith("### "): continue
        item, labeled = ITEM.fullmatch(line), LABELED.fullmatch(line)
        if item: found.append(Concern(int(item.group(1)), item.group(2), []))
        elif labeled and found:
            if labeled.group(1) not in LABELS: raise ConcernError(f"{where}: unknown label '{labeled.group(1)}', expected one of {', '.join(LABELS)}")
            found[-1].lines.append([labeled.group(1), labeled.group(2)])
        elif CONTINUED.fullmatch(line) and found and found[-1].lines: found[-1].lines[-1][1] += " " + line.strip()
        else: raise ConcernError(f"{where}: cannot read '{line.strip()}'; a concern is 'N. **Title.**' with '   - Label: text' lines under it")
    return [c._replace(lines=[tuple(l) for l in c.lines]) for c in found]

def concerns(lens):
    p = os.path.join(AGENTS, f"lens-{lens}.md")
    if not os.path.exists(p): raise ConcernError(f"no lens {lens}")
    with open(p, encoding="utf-8") as f: return parse(lens, records.section(f.read(), "Concerns"))

def line(concern, label): return next((text for l, text in concern.lines if l == label), None)

def na(text): return text[len(NA):].strip() if text.startswith(NA) else None

def carries(found, label): return bool(found) and all(line(c, label) is not None for c in found)

def applies(found, label): return carries(found, label) and any(na(line(c, label)) is None for c in found)

def lenses(): return sorted(m.group(1) for m in (re.fullmatch(r"lens-(.+)\.md", f) for f in os.listdir(AGENTS)) if m)

def mode_text(lens, label):
    found = concerns(lens)
    if not found: raise ConcernError(f"lens-{lens}.md has no concerns under '## Concerns'")
    if not carries(found, label): raise ConcernError(f"lens-{lens}.md concerns do not all carry a '{label}:' line")
    bullets = [f"- **{c.title}** {line(c, label)}" for c in found if na(line(c, label)) is None]
    return "\n".join([f"## {lens}: {label} mode", "", OPENERS[label], "", *bullets])

def main():
    args = sys.argv[1:]
    if not args: sys.exit(USAGE)
    label = (args[1] if len(args) > 1 else "pass").capitalize()
    if label not in LABELS: sys.exit(f"unknown mode {args[1]}; one of {', '.join(l.lower() for l in LABELS)}")
    try:
        if args[0] != "--list": print(mode_text(args[0], label)); return
        for lens in lenses():
            if applies(concerns(lens), label): print(lens)
    except ConcernError as e: sys.exit(str(e))

if __name__ == "__main__": main()
