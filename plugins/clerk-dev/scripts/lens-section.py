#!/usr/bin/env python3
"""Print one section of a lens agent, so a skill can use a lens's Design mode or
Pass mode text without reading the whole agent prompt into its session.

Usage:
  lens-section.py LENS [SECTION]     SECTION defaults to "Pass mode"
  lens-section.py --list [SECTION]   lenses that have the section

LENS is the lens name (edge-cases), not the agent name. Exits 1 when the lens or
the section does not exist.
"""
import os, re, sys

AGENTS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "agents")

def section(lens, name):
    p = os.path.join(AGENTS, f"lens-{lens}.md")
    if not os.path.exists(p): return None
    m = re.search(rf"^## {re.escape(name)}\n(.*?)(?=^## |\Z)", open(p, encoding="utf-8").read(), re.S | re.M)
    return m.group(1).strip() if m else None

def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    if args[0] == "--list":
        name = args[1] if len(args) > 1 else "Pass mode"
        for f in sorted(os.listdir(AGENTS)):
            m = re.fullmatch(r"lens-(.+)\.md", f)
            if m and section(m.group(1), name): print(m.group(1))
        return
    lens, name = args[0], (args[1] if len(args) > 1 else "Pass mode")
    s = section(lens, name)
    if s is None: sys.exit(f"no '## {name}' section for lens {lens}")
    print(f"## {lens}: {name}\n\n{s}")

if __name__ == "__main__": main()
