#!/usr/bin/env python3
"""Print a background subagent's final reply from its task output file.

The Agent tool returns an `output_file` for each background agent: its
transcript as JSON lines. Reading that file into the session would flood it;
this prints only the reply, so a raw file can be written without copying the
reply by hand.

Usage:
  agent-reply.py OUTPUT_FILE [--out PATH] [--header "line" ...]

The reply is the agent's last hand-back message when it made one, else the text
of its last assistant message. With --out, it is written there (directories
created) under the header lines, and the path and size are printed instead.
Exits 1 when the file has no reply yet.
"""
import argparse, json, os, sys

def reply(path):
    last_text, handback = None, None
    for line in open(path, encoding="utf-8"):
        try: o = json.loads(line)
        except ValueError: continue
        if o.get("type") != "assistant": continue
        for c in (o.get("message") or {}).get("content") or []:
            if c.get("type") == "text" and c.get("text", "").strip(): last_text = c["text"]
            elif c.get("type") == "tool_use" and c.get("name") == "SubagentHandback":
                handback = (c.get("input") or {}).get("message") or handback
    return handback or last_text

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output_file"); ap.add_argument("--out"); ap.add_argument("--header", action="append", default=[])
    a = ap.parse_args()
    r = reply(a.output_file)
    if not r: sys.exit(f"no reply in {a.output_file} yet")
    if not a.out:
        print(r); return
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    body = ("\n".join(a.header) + "\n\n" if a.header else "") + r.rstrip("\n") + "\n"
    open(a.out, "w", encoding="utf-8").write(body)
    print(f"{a.out} ({len(body):,} bytes)")

if __name__ == "__main__": main()
