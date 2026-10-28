# Commit messages

Every commit a skill writes (review fixes, follow-ups, handoffs, passes) uses
Conventional Commits, `<type>(<area>): <what the change does>`, with the type
saying what kind of change it is, so that pr-draft and reviews can sort
commits by their messages. This holds in every repository, whatever style its
other commits use.

| Type | Kind | Use for |
| --- | --- | --- |
| `refactor` | prep | Reshaping code without changing behavior |
| `feat` | new | Code nothing on the base runs yet, including fixes to code added earlier on the branch |
| `fix` | live | Repairing behavior the base already has |
| `change` | live | Deliberately changing behavior the base already has: a new option on a deployed endpoint, a different default |
| `build` | live | Build setup, dependencies, and packaging, since they change what is deployed |
| `ci` | tooling | CI workflows and checks; nothing deployed changes |
| `chore` | tooling | Housekeeping with no effect on what runs: lint config, scripts |
| `test` | tests | Tests only |
| `docs` | docs | Docs only |

A `!` after the type or area (`change(api)!:`) marks a break: a route, field,
table, or check that callers rely on is removed or changed.

- **Against the base.** "The base already has" means the branch's base, not
  earlier commits on the branch: a fix to code three commits back is `feat`,
  since nothing deployed runs it.
- **One kind per commit.** Commit a refactor apart from the change built on
  it. When a commit cannot be split, it takes the riskiest kind it holds, in
  this order: break, live, new, prep, tooling, tests, docs.
- **A type is a claim.** Readers check it against the diff: a `refactor` or
  `chore` that changes behavior is live, and a commit with no type (the
  user's own) is sorted from its diff.
