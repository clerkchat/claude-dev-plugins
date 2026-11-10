---
name: writing-code
description: How to shape code: refactor first to a clean baseline, reuse and extend what exists, one source of truth, clean abstractions. Use before writing or changing code of any size, and whenever a session writes an inline change itself. Preloaded by the builder agent; handing work off to builders is the building skill.
---

# Writing code

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, BL-4, Q-3, PASS-3, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

Human reviewers of this team's changes keep asking for more reuse, cleaner
abstractions, and less duplication than agents deliver. Lean hard that way.
This is deliberately strong; the team tunes it down if it goes too far.

## Refactor first

Before writing any change, large or small, read the code it touches and ask
whether reshaping that code first would make the change smaller or plainer:

- a helper to extract, so the change reuses it instead of adding a copy;
- a function to split, so the change edits one step instead of threading
  through all of them;
- a data shape to fix, so the change needs no conversions;
- dead code or a leftover option to drop, so the change has fewer cases.

If so, do that refactor first, in its own commits, with the tests passing and
behavior unchanged, and build the change on it; the change's own commits should
read as small additions. If not, say in one line that the baseline is clean.

When the change is one part of several (a plan's milestones, a feature's
pieces, a brief's handoffs), look ahead too: read what the later parts will
touch, and prefer the refactor that makes this part and those smaller or
plainer. Keep the look short. When nothing is clear yet, say so in one line and
look again at the next part, when more of the shape is known; do not refactor
for a guess.

This holds at every scale: a feature's first piece, a one-function fix, a
follow-up. Refactoring deployed code still follows the branch's scope (Branch
scope in `skills/review/tracking.md`): when the branch's Purpose does not cover
that code, propose the refactor instead of making it.

## Changing live code

An enabling refactor of deployed code, especially on a hot path, keeps the
same values as new code but weighs them differently: what the paths you did
not touch do matters more than how tidy the change is.

- Add to a decision rather than redefine it. When a function, flag, column, or
  predicate already means something to its callers (`hasId()` meaning "this
  row was inserted"), keep that meaning and add an explicit signal for the new
  case. Changing what an existing signal means changes every caller at once,
  including the ones you did not read.
- Make the new condition opt-in, with a default under which every path you did
  not touch behaves exactly as before. The old behavior is the fallback.
- Before changing a branch, find its live callers and say how many take it.

Before calling the clean fix risky and offering a workaround instead, find the
fix's smallest form: the opt-in flag, the added signal, the precedent the
codebase already has. Present that version next to the workaround, with the
argument for its safety. Judged in the abstract, the right fix often looks
riskier than it is.

## Reuse

- Before writing any helper, type, validator, query, or pattern, search the
  codebase and its shared libraries for one that exists. Search by behavior,
  not name: the verbs, the types it takes and returns, the distinctive calls
  inside it. Look first in the shared libraries (`libs/`, `packages/`,
  `shared/`, `common/`, `core/`, `utils/`, the workspace packages and path
  aliases in the manifests).
- Use what exists. When it nearly fits, extend it (the option or case to add)
  rather than write a near-copy. When your code is the more general of the two,
  move it into the shared place and have the old one call it.
- Do things the way the codebase already does them: one way to handle errors,
  wire dependencies, build queries, lay out modules. A second pattern needs a
  reason, even when it is nicer.

## One source of truth

- When a change would repeat logic, extract the shared abstraction instead,
  including logic repeated across files and across the code you are adding.
- No hand-kept lists, enums, schemas, or constants that must stay in sync with
  another; derive one from the other.
- Abstractions at the right level: no framework for one caller, no wrapper
  around one call, no parameter added to a shared type because one function
  needs it.
- Before adding a fallback, find where the value is written. When one source
  already holds the resolved value, read only that source.

## Tests

Agents tend to write a test as one long method that builds everything, runs
several scenarios, and asserts along the way. Write tests the way the rest of
this skill writes code: a shared baseline, then small parts that each add one
thing.

- Group tests by the unit or behavior under test (`describe`, a test class,
  subtests). Put the baseline every test in the group needs (the subject, its
  collaborators, default data) in the framework's setup hook: `beforeEach`,
  `setUp`, a pytest fixture, a helper each subtest calls.
- One scenario per test. A test states only how its scenario differs from the
  baseline, does one thing, and asserts that one thing's outcome.
- When several tests share a condition, give the condition a nested group whose
  setup hook applies it, and name the group after it.
- Name groups and tests so they read as a spec: "when the contact is archived",
  "rejects the update".
- Build test data with the repository's factories or builders, or add one,
  rather than repeating object literals.
- Persist test data with the factory's persisting method (`create()`), not by
  building the object and inserting it by hand.
- Call a helper with its defaults, and pass an argument only when it changes
  the outcome; an argument that only narrows what the default already does is
  noise.
- Put imports at the top of the file; a lazy or dynamic import needs a stated
  reason.
- Keep what matters to a test visible: a reader should see, from the test and
  the nearest setup hook, every input its assertion depends on. Do not hide a
  scenario's deciding input three hooks up.
- When the test file you extend is itself written as long methods, restructure
  the tests your change touches first, as in Refactor first.

The same shape in any framework; in Jest, instead of one test that creates a
contact, updates it, archives it, and updates it again:

```ts
describe('ContactService.update', () => {
  let contact: Contact;

  beforeEach(async () => {
    contact = await contactFactory.create({ name: 'Ada' });
  });

  it('saves the new name', async () => {
    await service.update(contact.id, { name: 'Grace' });
    expect(await repo.findOneBy({ id: contact.id })).toMatchObject({ name: 'Grace' });
  });

  describe('when the contact is archived', () => {
    beforeEach(() => service.archive(contact.id));

    it('rejects the update', async () => {
      await expect(service.update(contact.id, { name: 'Grace' })).rejects.toThrow(ArchivedContactError);
    });
  });
});
```
