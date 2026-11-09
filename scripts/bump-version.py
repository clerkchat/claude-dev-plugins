#!/usr/bin/env python3
"""Bump the clerk-dev plugin version: bump-version.py <patch|minor|major>"""
import os, re, sys

PLUGIN_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "plugins", "clerk-dev", ".claude-plugin", "plugin.json")
VERSION_FIELD = re.compile(r'("version"\s*:\s*")([^"]*)(")')
PARTS = ("major", "minor", "patch")

def parse(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version): sys.exit(f"version {version!r} is not X.Y.Z")
    return tuple(map(int, version.split(".")))

def version_in(text):
    m = VERSION_FIELD.search(text)
    if not m: sys.exit("plugin.json has no version field")
    return m.group(2)

def bumped(version, part):
    major, minor, patch = parse(version)
    return ".".join(map(str, {"major": (major + 1, 0, 0), "minor": (major, minor + 1, 0), "patch": (major, minor, patch + 1)}[part]))

def main(argv):
    if len(argv) != 1 or argv[0] not in PARTS: sys.exit("usage: bump-version.py <patch|minor|major>")
    with open(PLUGIN_JSON, encoding="utf-8") as fh: text = fh.read()
    old = version_in(text)
    new = bumped(old, argv[0])
    with open(PLUGIN_JSON, "w", encoding="utf-8") as fh: fh.write(VERSION_FIELD.sub(lambda m: m.group(1) + new + m.group(3), text, count=1))
    print(f"{old} -> {new}")

if __name__ == "__main__": main(sys.argv[1:])
