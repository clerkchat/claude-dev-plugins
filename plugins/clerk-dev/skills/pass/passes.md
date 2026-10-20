# Pass catalogue

A pass is a bounded stretch of writing with one focus on one piece of work,
ending in commits and a narrow check with only the pass's lenses over only the
pass's commits. Each pass below names its lenses; the writing follows each
lens's `## Pass mode` section (`scripts/lens-section.py <lens>`), and the check
runs the same lenses in review. `cross-repo` has no pass; it reviews and checks
designs only.

| Pass          | Lenses                                       | When it is due                                                          |
| ------------- | -------------------------------------------- | ----------------------------------------------------------------------- |
| prep          | tech-debt, design, naming-concepts           | always considered first, for any piece that touches existing code       |
| happy-path    | spec-conformance, completeness               | first, for a piece with a spec; builds the main flow                    |
| dry           | design, tech-debt                            | after the happy path, when it added more than a few functions           |
| edge-cases    | edge-cases, error-handling                   | after the happy path, for any piece with inputs or external calls       |
| concurrency   | concurrency                                  | jobs, consumers, retries, or state shared between requests              |
| observability | observability-cost                           | new operations, jobs, or failure paths                                  |
| security      | security, tenancy, data-privacy, side-effects | new routes, inputs, stores, providers, or real-world actions            |
| performance   | performance, scaling, capacity, sql          | hot paths, per-row work, new queries, or outbound calls at volume       |
| tests         | tests                                        | after the behavior settles; before the full review                      |
| rollout       | rollout, contracts                           | schema changes, payload changes, gates, or clients in other repositories |
| text          | user-facing-text                             | new labels, messages, errors, or templates                              |
| frontend      | frontend                                     | UI state, effects, real-time updates                                    |
| llm           | llm-agent                                    | prompts, tool schemas, model calls, agent loops                         |

Within a pass, only the lenses whose categories the piece touches apply
(`routing.md`); a security pass on a piece with no new store skips
`data-privacy`.

## Order within a milestone

A milestone (a step of the feature's plan) runs its passes in this order:

1. prep;
2. happy-path: the draft;
3. dry, when suggested: it reshapes code, so it goes before the passes that
   check that code;
4. security, when any of its lenses is triggered: **required**, it cannot be
   skipped, and its findings must be triaged before the milestone is ready;
5. the rest in the catalogue table's order;
6. tests and rollout last.

## Suggesting passes

A piece is a spec record, or the paths the engineer names. Classify its files,
or, before any code exists, what its spec's Approach and Contracts describe,
into the `routing.md` categories:

| Category    | Passes it suggests                    |
| ----------- | ------------------------------------- |
| `schema`    | performance, rollout, concurrency     |
| `domain`    | edge-cases, dry                       |
| `interface` | security, edge-cases, rollout         |
| `async`     | concurrency, observability, rollout   |
| `llm`       | llm, security                         |
| `ui`        | frontend, text                        |
| `auth`      | security                              |
| `text`      | text                                  |
| `config`    | rollout                               |

Always start with prep for a piece that touches existing code, however small:
a refactor that makes the change smaller is checked for before any writing, at
the scale of a feature and of a one-function fix alike. When prep's item list
comes out empty (the baseline is already clean), the pass ends with a line
saying so and no commits. Then happy-path for a piece with a spec. Then scale by size, counting
the piece's changed lines, or the spec's requirements before code exists:

- Small (under about 150 lines, or one or two requirements): prep, happy-path,
  and the one pass its riskiest category suggests.
- Medium (up to about 800 lines, or a handful of requirements): prep,
  happy-path, dry, and one or two more by the table's order, ending with
  tests.
- Large, or touching `schema`, `async`, or another repository: every suggested
  pass, with rollout and tests last.

Order the list as the catalogue table does. The suggestion is a list the
engineer edits, not a plan to run unattended.
