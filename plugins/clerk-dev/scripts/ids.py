import re
from typing import NamedTuple

RECORD, REF, CHECK = "record", "ref", "check"
IDEA, PASS, BUILD, MILESTONE, DEFERRED, QUESTION, FOLLOWUP = "idea", "pass", "build", "milestone", "deferred", "question", "followup"

RECORD_PREFIX = "R"
ITEM_PREFIXES = {IDEA: "I", PASS: "P", BUILD: "B", MILESTONE: "M", DEFERRED: "D", QUESTION: "Q", FOLLOWUP: "F"}
ITEMS = tuple(ITEM_PREFIXES)
RECORD_KINDS = (CHECK, REF, RECORD)
ORDER = RECORD_KINDS + ITEMS

class Id(NamedTuple):
    kind: str
    n: int
    sub: int | None = None
    q: int | None = None
    record: str | None = None

def record(n, rtype=None): return f"{RECORD_PREFIX}{n}"
def item(kind, n): return f"{ITEM_PREFIXES[kind]}{n}"
def ref_prefix(record_id): return f"{record_id}."
def ref(record_id, n): return f"{ref_prefix(record_id)}{n}"
def check(record_id, n): return f"{record_id}-{n}"
def in_check(check_name, question_id): return f"{check_name}.{question_id}"

def record_file(n, rtype, slug): return f"{n:03d}-{rtype}-{slug}.md"
def check_file(check_name): return f"{check_name}.md"
def check_from_file(filename): return filename[:-3] if filename.endswith(".md") else None

def _written(kind): return RECORD_PREFIX if kind in RECORD_KINDS else ITEM_PREFIXES[kind]
def _prefixes(kind): return [_written(kind)]

def _alternatives(prefixes):
    return "(?:" + "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True)) + ")"

def _shape(kind, named):
    def group(name, body): return f"(?P<{name}>{body})" if named else body
    number = group("n", r"\d+")
    if kind in ITEM_PREFIXES: return _alternatives(_prefixes(kind)) + number
    rec = group("record", _alternatives(_prefixes(RECORD)) + number)
    if kind == RECORD: return rec
    if kind == REF: return rec + r"\." + group("sub", r"\d+")
    return rec + "-" + group("sub", r"\d+") + r"(?:\." + _alternatives(_prefixes(QUESTION)) + group("q", r"\d+") + ")?"

def pattern(*kinds): return "(?:" + "|".join(_shape(k, False) for k in ORDER if k in kinds) + ")"

PARSERS = [(k, re.compile(_shape(k, True))) for k in ORDER]

def _int(text): return int(text) if text is not None else None

def parse(text):
    for kind, rx in PARSERS:
        m = rx.fullmatch(text)
        if m:
            got = m.groupdict()
            return Id(kind, int(got["n"]), _int(got.get("sub")), _int(got.get("q")), got.get("record"))
    return None

def kind_of(text):
    p = parse(text)
    return p.kind if p else None

def number(text):
    p = parse(text)
    if p is None: raise ValueError(f"{text!r} is not an id")
    return p.n

def key(text):
    p = parse(text)
    return tuple(p[:4]) if p else None

def same(a, b):
    k = key(a)
    return k is not None and k == key(b)

def sort_key(text):
    p = parse(text)
    return (p.n,) if p.sub is None else (p.n, p.sub)

def next_number(texts, kind):
    return max([p.n for p in map(parse, texts) if p and p.kind == kind] or [0]) + 1

def complete(text, kind, *also):
    up = text.upper()
    return up if up.startswith(tuple(p for k in (kind, *also) for p in _prefixes(k))) else _written(kind) + text

def records_in(text, refs=True):
    return re.findall(rf"\b{pattern(RECORD)}\b" + ("" if refs else r"(?!\.\d)"), text)
