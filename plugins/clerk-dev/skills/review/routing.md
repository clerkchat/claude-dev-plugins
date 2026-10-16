# Routing table

Maps change categories to lenses. The scope step classifies every changed file
into one or more categories, using the repo review-context globs when present
and the path heuristics below otherwise. A lens runs when any changed file hits
one of its categories, or when it is listed under "always".

## Categories and path heuristics

| Category    | Heuristic when no review-context                                                                                 | Meaning                              |
| ----------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| `schema`    | `migration`, `migrations`, `entities`, `entity`, `schema`, `drizzle`, `reviewa`, `.sql`                          | Persistent data shape                |
| `domain`    | `service`, `services`, `domain`, `lib`, `core`, `utils`                                                          | Business logic                       |
| `interface` | `controller`, `routes`, `router`, `handlers`, `dto`, `api`, `public`, `graphql`, `openapi`                       | Inbound request surface              |
| `async`     | `queue`, `queues`, `processor`, `worker`, `consumer`, `cron`, `scheduler`, `jobs`, `events`                      | Background or event-driven execution |
| `llm`       | `prompt`, `prompts`, `tools`, `agent`, `agents`, `pipeline`, `llm`, `sandbox`                                    | Model calls, tool schemas, prompts   |
| `ui`        | `.tsx`, `.jsx`, `.vue`, `.svelte`, `components`, `pages`, `app/`                                                 | Rendered interface                   |
| `config`    | `Dockerfile`, `docker-compose`, `.github/`, `tasks/`, `deploy`, `*.config.*`, `.env*`, `package.json`, lockfiles | Build, deploy, dependencies          |
| `auth`      | `guard`, `guards`, `auth`, `permission`, `policy`, `middleware`                                                  | Access control                       |
| `tests`     | `.test.`, `.spec.`, `__tests__`, `e2e`, `fixtures`, `seed`                                                       | Tests and factories                  |
| `text`      | any file whose diff adds user-visible strings, i18n files, templates, email or message bodies                    | User-facing copy                     |

A file can hit several categories. `.github/workflows` is `config`; a migration
is `schema` and often `config` for deploy ordering.

## Plain names

What the user reads in place of a lens identifier. `Say it as` is the phrase;
`Described as` is the one-line description used in the plan.

| Lens                 | Say it as                | Described as                                                       |
| -------------------- | ------------------------ | ------------------------------------------------------------------ |
| `security`           | security                 | injection, unsafe input, secrets, sandbox escapes                  |
| `side-effects`       | real-world side effects  | messages, calls, charges, or external writes triggered by accident |
| `tenancy`            | tenant isolation         | every lookup scoped to the calling tenant                          |
| `rollout`            | rollout and rollback     | migrations, in-flight jobs, old and new code side by side          |
| `edge-cases`         | edge cases               | empty, null, boundary, and legacy-data inputs                      |
| `concurrency`        | concurrency              | races, retries, duplicate processing                               |
| `capacity`           | resource limits          | memory, timeouts, pool and quota exhaustion                        |
| `scaling`            | behavior at scale        | per-row work, N+1 queries, hot spots                               |
| `sql`                | database queries         | indexes, ordering, migration locks                                 |
| `error-handling`     | error handling           | swallowed errors and silent fallbacks                              |
| `contracts`          | agreements between parts | request and response shapes, payloads, the seams between parts     |
| `completeness`       | completeness             | loose ends, missing wiring, open items in the specs                |
| `spec-conformance`   | spec conformance         | does the change do what the specs and description say              |
| `naming-concepts`    | naming                   | names that fit the codebase's vocabulary                           |
| `design`             | design and reuse         | duplication, pattern fit, dead code                                |
| `tests`              | test quality             | do the tests catch the regressions that matter                     |
| `performance`        | performance              | work that is slower than it needs to be                            |
| `user-facing-text`   | user-facing text         | labels, messages, templates people read                            |
| `data-privacy`       | data privacy             | personal data in logs, telemetry, third parties                    |
| `observability-cost` | observability            | failures visible, telemetry affordable                             |
| `llm-agent`          | LLM integration          | prompts, tool schemas, model calls, agent loops                    |
| `frontend`           | frontend                 | cache correctness, rendering, accessibility                        |
| `cross-repo`         | cross-repository fit     | contracts and deploy order across repositories                     |
| `tech-debt`          | tech debt                | cleanups, simplifications, and refactors around the changed code   |

## Lens triggers

| Lens                 | Runs on categories                                              | Always                             |
| -------------------- | --------------------------------------------------------------- | ---------------------------------- |
| `security`           | interface, auth, config, llm, async                             | yes in standard and deep           |
| `tenancy`            | interface, domain, schema, auth, async                          |                                    |
| `side-effects`       | interface, async, llm, ui, config                               |                                    |
| `rollout`            | schema, async, config, interface, llm                           |                                    |
| `edge-cases`         | domain, interface, async, llm, ui                               | yes in standard and deep           |
| `concurrency`        | async, domain, schema                                           |                                    |
| `error-handling`     | domain, async, interface, llm                                   |                                    |
| `contracts`          | interface, schema, async, llm                                   |                                    |
| `capacity`           | async, domain, interface, llm                                   |                                    |
| `scaling`            | async, schema, domain                                           |                                    |
| `observability-cost` | async, domain, interface                                        |                                    |
| `sql`                | schema, domain                                                  |                                    |
| `data-privacy`       | domain, async, llm, interface                                   |                                    |
| `naming-concepts`    | any non-test, non-config                                        | yes in standard and deep           |
| `design`             | any non-test, non-config                                        | yes in standard and deep           |
| `tests`              | tests, or any domain/interface/async change with no test change |                                    |
| `spec-conformance`   | any                                                             | when a PR body or Spec file exists |
| `performance`        | domain, async, ui                                               |                                    |
| `user-facing-text`   | text, ui, interface                                             |                                    |
| `llm-agent`          | llm                                                             |                                    |
| `frontend`           | ui                                                              |                                    |
| `completeness`       | any                                                             | yes in standard and deep           |
| `cross-repo`         | any                                                             | only in feature mode               |
| `tech-debt`          | any non-test, non-config                                        | yes in standard and deep           |

Lenses not yet implemented are skipped silently; the report header lists which
lenses ran.

## Lens priority order

When a cap leaves room for fewer lenses than were triggered, keep them in this
order: security, tenancy, side-effects, rollout, edge-cases, concurrency, sql,
contracts, then the rest in table order.

## Quick mode

Quick mode keeps only the lenses triggered by categories, drops the "always"
rule, caps the set at four by the lens priority order, and runs them all on
sonnet with effort medium regardless of the agent's own frontmatter.

## Explicit selection

`--lenses a,b,c` replaces the table entirely. Unknown names are reported and
skipped. `--lenses +a` adds to the routed set instead of replacing it, and
`--lenses -a` removes a lens from it: `--lenses -tech-debt` reviews without
the tech debt focus, and `--lenses tech-debt` runs it on its own. A final pass
never runs the tech debt focus.

## Design checks

The `design-check` skill picks lenses for feature records, not diffs: at most
six, of which at most three come from the record's type and the rest from its
risks.

1. By record type, at most three, in this order of preference:
   - a record that touches existing code: `tech-debt` (refactor first, and
     what to reuse);
   - a spec: `completeness`, `spec-conformance`;
   - records spanning repositories (see the `design-check` skill): `contracts`,
     `cross-repo`;
   - a record that introduces new concepts or modules: `design`,
     `naming-concepts`.
2. By risk, the rest: classify what the records describe building into the
   categories above (an endpoint is `interface`, a table `schema`, a worker
   `async`, prompts or tools `llm`, screens `ui`, copy `text`, access rules
   `auth`), take the lenses those categories trigger, ignoring the "always"
   column, and keep the ones whose questions the records most plausibly leave
   open: a record about a tenant-facing endpoint keeps `tenancy`, one about
   plugin prompts keeps `llm-agent` and does not keep `security` just because
   `llm` triggers it. Break ties by the lens priority order.

The skill announces each risk lens with the category behind it, so a missing
lens is visible and `--lenses +x` adds it. With `--lenses`, the explicit rules
above apply instead.

## Triage questions

Asked per slice by a haiku agent that reads the slice patch once. Each answer is
yes or no with a one-line pointer (file and hunk). Lenses in parentheses are
dropped for a slice when the answer is no, unless a path category or an explicit
`--lenses` keeps them.

1. New or changed database query, query builder chain, raw SQL, index, or
   migration? (sql, scaling, performance)
2. New or changed inbound route, handler, DTO, or public type? (contracts,
   tenancy, user-facing-text for error bodies)
3. New or changed job, consumer, scheduled task, or event handler? (concurrency,
   capacity, rollout, performance)
4. New or changed outbound call to a network service, provider SDK, or model?
   (capacity, security, llm-agent, data-privacy, side-effects)
5. New or changed prompt, tool schema, or agent loop logic? (llm-agent)
6. New or changed user-visible string, template, or i18n entry?
   (user-facing-text)
7. New or changed feature gate, environment variable, or deploy configuration?
   (rollout)
8. New or changed UI component, hook, query key, or effect? (frontend,
   performance) 8b. Loop over a collection that comes from a query, payload, or
   file, or a handler on a per-message or per-event path? (performance, scaling)
9. Lookup, mutation, or listing keyed by an identifier that arrives from the
   caller or a payload? (tenancy)
10. Logging, metrics, or tracing added or changed? (observability-cost)
11. Personal data fields (names, phone numbers, emails, message content,
    recordings) read, stored, or sent somewhere new? (data-privacy)
12. Try/catch, fallback, default-on-failure, or retry logic added or changed?
    (error-handling)
13. Tests added, changed, or deleted? (tests; a no here with any yes on 1 to 5
    is itself a tests finding) 14b. A path users would consider safe (test,
    preview, replay, retry, seed, backfill, sample data) that runs workflow,
    messaging, calling, billing, or connected-system code? (side-effects)
14. Markers of unfinished work: TODO, FIXME, XXX, placeholder values, stubbed
    returns, commented-out code, "not yet", "later"? (completeness)

Lenses never dropped by triage: security, edge-cases, naming-concepts, design,
tech-debt, completeness, spec-conformance (when documents exist).
