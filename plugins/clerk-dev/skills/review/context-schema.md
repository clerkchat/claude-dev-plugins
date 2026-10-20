# review-context schema

A repo may provide `.claude/skills/review-context/SKILL.md`. The orchestrator
reads it when present and passes its path to every lens agent as `CONTEXT`.
Everything in it is instance knowledge: the names this repo gives to the
categories the generic lenses reason about. Keep the generic lens prompts free
of these names.

Frontmatter:

```yaml
---
name: review-context
description: Repo-specific slice vocabulary, hotspots, and cross-repo contracts for the /clerk-dev:review orchestrator. Not meant to be invoked directly.
user-invocable: false
---
```

Body sections, in this order. All are optional, but keep the headings exact so
the orchestrator and agents can find them.

## Slices

A table of slice names with their layer, default execution context, and file
globs. The partition step uses these globs before falling back to path
heuristics.

| Slice | Layer | Context | Globs |
| ----- | ----- | ------- | ----- |

## Execution contexts

How to tell which execution context a file runs in when the slice default is not
enough (for example, a service called from both a request handler and a job).

## Instances

One subsection per generic category, naming the repo's concrete instances. Use
the headings below so lens agents can jump to the one they need:

- `### Tenancy`: what the tenant is, the scope helpers, the guards, how to spot
  an unscoped lookup.
- `### Async handlers`: queue or event system, where processors live, delivery
  guarantees, retry behavior, how job payloads are versioned.
- `### Replication`: tables or topics replicated elsewhere and what must change
  when a column is added.
- `### Feature gates`: the flag mechanism, how to check one, how to test both
  paths.
- `### Deploy`: deployable units, which ones share code, ordering constraints,
  how migrations run relative to code.
- `### Observability`: logging and metrics conventions, known cost traps.
- `### Data stores`: each store, its engine specifics, migration tooling.
- `### LLM surface`: where prompts, tool schemas, and model clients live.
- `### Security boundaries`: webhooks and their signature checks, sandboxes,
  secrets handling.
- `### Side effects`: the operations that act on the real world (sending
  messages, placing calls, billing, outbound webhooks, writes to connected
  systems), where they live, and the paths meant to be safe (test, preview,
  replay, seed) with the guard each one relies on.
- `### Shared libraries`: the project's own libraries and shared packages,
  each with its path, import name, and what it covers (for example
  "`libs/common`, `@acme/common`: date handling, retries, pagination
  helpers"), so lenses can check new and touched code against them.

## Hazards by focus

Concrete, repo-specific things each lens should check, one `###` subsection per
lens using the lens name (`### edge-cases`, `### design`, `### tests`, ...).
Each item is one line: the hazard and where it shows up. Distill these from the
repo's review standards and past review comments; this is the section that turns
"the team always flags X" into something every run checks. A lens reads its own
subsection in full before reviewing.

## Provides

What other repos consume from this one, each with where it is defined and who
consumes it. Used by the cross-repo lens.

| Contract | Defined in | Consumers |
| -------- | ---------- | --------- |

## Consumes

What this repo depends on from other repos.

| Contract | Provided by | Used in |
| -------- | ----------- | ------- |

## Deploy order

Constraints when this repo ships together with others.

## Excluded from review

Globs for files that change often, carry no reviewable logic, and inflate the
patch: lockfiles, build output, generated code, snapshots, large fixtures. Globs
match the full repo-relative path, so prefix with `**/` to match at any depth.
Added to the orchestrator defaults (`**/*.lock`, `**/*-lock.json`,
`**/yarn.lock`, `**/dist/**`, `**/build/**`, `**/*.generated.*`,
`**/__snapshots__/**`, `**/*.snap`, `**/*.min.*`, any file over 10,000 bytes
averaging more than 300 bytes per changed line, and data files over 500 changed
lines or 40,000 bytes). Excluded files are still listed in the scope table and
the report header.

## Work tracking

Where this repo keeps specifications, plans, and checklists for in-progress
work, as globs, with a line on which ones are authoritative. The orchestrator
selects documents from these globs for the spec-conformance and completeness
lenses, only among files tracked in git; untracked files are never read. Default
when absent: `TODO*.md`, `docs/plans/**`.

## Existing review material

Pointers to repo skills or docs that lens agents should read for judgment calls
(for example a coding-standards skill). Agents read these; do not restate them.

## Known noise

Patterns that look wrong but are intentional here, so lenses do not re-report
them. `records.py guidance --context` copies this section into the guidance
file as Repository noise, which is where lenses read it.

# Drafting a review context

When the user agrees to have one drafted (First runs in a repository, in the
review skill), run one `general-purpose` subagent with `model: sonnet`, effort
`medium`, that writes only `.claude/skills/review-context/SKILL.md` and reads
the rest. It fills in what it can find and leaves out any section it cannot;
an empty heading is worse than none, since lenses trust what is there.

1. Orientation: `AGENTS.md`, `CLAUDE.md`, the README, the top-level layout,
   and the package manifests. Note the languages, frameworks, and deployable
   units.
2. Slices: map the main directories to layers and execution contexts, as
   globs.
3. Instances: search for what each subsection names, and record the concrete
   names with their paths: the tenant entity and its scope helpers and guards;
   the queue or event system and where handlers live; the migration tool; the
   feature flag mechanism; model clients, prompts, and tool schemas; webhook
   signature checks; the code that sends messages, places calls, or charges
   money, and the guards on its test and preview paths; the shared libraries
   and packages, from the workspace configuration and path aliases, with a
   line each on what they cover.
4. Excluded from review: generated code, build output, snapshots, and large
   fixtures that exist in this repository, beyond the defaults.
5. Hazards by focus: the repository's own coding standards, and, when `gh`
   works, the review comments on up to twenty recently merged pull requests
   (`gh pr list --state merged --limit 20`, then `gh pr view <n> --comments`).
   Keep only what recurs or what the standards insist on, one line each,
   under the lens it belongs to.
6. Existing review material: pointers to standards documents or skills the
   lenses should read.

The file starts with the frontmatter above and a line saying it was drafted on
that date and is the user's to edit and commit. Keep it to about 150 lines.
Never commit it.
