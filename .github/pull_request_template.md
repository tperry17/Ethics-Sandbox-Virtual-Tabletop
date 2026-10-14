## What this does

<!-- One short paragraph: what changed and why. Name the build-plan step
(docs/BUILD-PLAN.md) if this PR completes or advances one. -->

## Questions for the author

<!-- Required on every PR. List each open question, each assumption made
where the request, the plan or the content was unclear, and anything the
author should double-check before merging. Number them so they can be
answered by number. If there is genuinely nothing, write "None" and say
why. -->

1.

## Checks

- [ ] `uv run ruff check .`
- [ ] `uv run mypy sandbox tests`
- [ ] `uv run pytest`
- [ ] `npm run test:e2e` (if the table client or a page changed)
- [ ] `docs/BUILD-PLAN.md` status updated (if a plan step moved)
