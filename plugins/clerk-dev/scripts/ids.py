import re
from typing import NamedTuple

RECORD, REF, CHECK, SURVEY = "record", "ref", "check", "survey"
IDEA, PASS, BUILD, MILESTONE, DEFERRED, QUESTION, FOLLOWUP, BACKLOG = "idea", "pass", "build", "milestone", "deferred", "question", "followup", "backlog"

RECORD_LEADS = {"brainstorm": "STORM-", "design": "DESIGN-", "decision": "DEC-", "guidance": "GUIDE-",
                "pieces": "PIECES-", "plan": "PLAN-", "brief": "BRIEF-"}
ITEM_LEADS = {IDEA: "IDEA-", PASS: "PASS-", BUILD: "BUILD-", MILESTONE: "MILE-", DEFERRED: "DEFER-", QUESTION: "Q-", FOLLOWUP: "F", BACKLOG: "BL-"}
ALIASES = {"IDEAS-": RECORD, "R": RECORD, "I": IDEA, "P": PASS, "B": BUILD, "M": MILESTONE, "D": DEFERRED, "Q": QUESTION}
TYPE_ALIASES = {"spec": "brief", "capabilities": "pieces"}
SURVEY_LEAD = "SURVEY-"

RECORD_TYPES = tuple(RECORD_LEADS)
ITEMS = tuple(ITEM_LEADS)
RECORD_KINDS = (CHECK, REF, RECORD)
ORDER = RECORD_KINDS + (SURVEY,) + ITEMS

class Id(NamedTuple):
    kind: str
    n: int
    sub: int | None = None
    q: int | None = None
    record: str | None = None

def record_type(name): return TYPE_ALIASES.get(name, name)

def record(n, rtype):
    if rtype not in RECORD_LEADS: raise ValueError(f"{rtype!r} is not a record type")
    return f"{RECORD_LEADS[rtype]}{n}"

def item(kind, n): return f"{ITEM_LEADS[kind]}{n}"
def ref(record_id, n): return f"{record_id}.{n}"
def check(record_id, n): return f"{record_id}-{n}"
def in_check(check_name, question_id): return f"{check_name}.{question_id}"
def survey(n): return f"{SURVEY_LEAD}{n}"

def record_file(n, rtype, slug): return f"{n:03d}-{rtype}-{slug}.md"
def check_file(check_name): return f"{check_name}.md"
def check_from_file(filename): return filename[:-3] if filename.endswith(".md") else None

def _written(kind):
    if kind == RECORD: return list(RECORD_LEADS.values())
    if kind == SURVEY: return [SURVEY_LEAD]
    return [ITEM_LEADS[kind]]

def _leads(kind): return _written(kind) + [lead for lead, k in ALIASES.items() if k == kind]

def _alternatives(leads):
    return "(?:" + "|".join(re.escape(p) for p in sorted(leads, key=len, reverse=True)) + ")"

def _shape(kind, named):
    def group(name, body): return f"(?P<{name}>{body})" if named else body
    number = group("n", r"\d+")
    question = r"(?:\." + _alternatives(_leads(QUESTION)) + group("q", r"\d+") + ")?"
    if kind == SURVEY: return _alternatives(_leads(kind)) + number + question
    if kind in ITEM_LEADS: return _alternatives(_leads(kind)) + number
    rec = group("record", _alternatives(_leads(RECORD)) + number)
    if kind == RECORD: return rec
    if kind == REF: return rec + r"\." + group("sub", r"\d+")
    return rec + "-" + group("sub", r"\d+") + question

def pattern(*kinds): return "(?:" + "|".join(_shape(k, False) for k in ORDER if k in kinds) + ")"

PARSERS = [(k, re.compile(_shape(k, True))) for k in ORDER]
def _dashless():
    stems = [lead[:-1] for lead in (*RECORD_LEADS.values(), *ITEM_LEADS.values(), SURVEY_LEAD, *ALIASES) if lead.endswith("-")]
    return re.compile("^(" + "|".join(sorted(stems, key=len, reverse=True)) + r")(?=\d)")

DASHLESS = _dashless()
BARE = re.compile(r"(\d+)(?:\.(\d+))?")

def _int(text): return int(text) if text is not None else None

def parse(text):
    if not text: return None
    for kind, rx in PARSERS:
        m = rx.fullmatch(text)
        if m:
            got = m.groupdict()
            return Id(kind, int(got["n"]), _int(got.get("sub")), _int(got.get("q")), got.get("record"))
    return None

def _parsed(text):
    p = parse(text)
    if p is None: raise ValueError(f"{text!r} is not an id")
    return p

def kind_of(text):
    p = parse(text)
    return p.kind if p else None

def number(text): return _parsed(text).n

def key(text):
    p = parse(text)
    return tuple(p[:4]) if p else None

def same(a, b):
    k = key(a)
    return k is not None and k == key(b)

def sort_key(text):
    p = _parsed(text)
    return (p.n,) if p.sub is None else (p.n, p.sub)

def next_number(texts, kind):
    return max([p.n for p in map(parse, texts) if p and p.kind == kind] or [0]) + 1

def normalize(text):
    return DASHLESS.sub(r"\1-", text.strip().upper(), count=1)

def read(text, *kinds):
    up = normalize(text)
    p = parse(up)
    if p: return p if p.kind in kinds else None
    m = BARE.fullmatch(up)
    if not m: return None
    kind = REF if m.group(2) else next((k for k in kinds if k != REF), None)
    return Id(kind, int(m.group(1)), _int(m.group(2))) if kind in kinds else None

def _with_question(name, q): return name if q is None else in_check(name, item(QUESTION, q))

def render(p, rtype=None):
    if p.kind == SURVEY: return _with_question(survey(p.n), p.q)
    if p.kind in ITEM_LEADS: return item(p.kind, p.n)
    rec = record(p.n, rtype)
    if p.kind == RECORD: return rec
    if p.kind == REF: return ref(rec, p.sub)
    return _with_question(check(rec, p.sub), p.q)

def complete(text, kind, *also):
    p = read(text, kind, *also)
    return render(p) if p and p.kind in ITEM_LEADS else normalize(text)

def canonical(text, types):
    p = parse(text)
    if p is None or (p.kind in RECORD_KINDS and p.n not in types): return text
    return render(p, types.get(p.n))

def rewrite(text, types):
    return re.sub(rf"\b{pattern(*ORDER)}\b", lambda m: canonical(m.group(0), types), text)

def mentions(text, *kinds): return re.findall(rf"\b{pattern(*kinds)}\b", text)

def records_in(text, refs=True):
    return re.findall(rf"\b{pattern(RECORD)}\b" + ("" if refs else r"(?!\.\d)"), text)
