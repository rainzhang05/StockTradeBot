# StockTradeBot Agent Operating Contract

This repository is intentionally documentation-first. Every agent must treat the files under `docs/` as the implementation source of truth and must follow this contract before making any modification.

## 1. Mandatory Read-First Rule

Before changing any file in the repository, agents must read every file currently present under `docs/` in full.

Read in this order:

1. `docs/README.md`
2. `docs/current-state.md`
3. `docs/plan.md`
4. `docs/decisions.md`
5. `docs/roadmap.md`
6. all remaining `docs/*.md` files in the repository

No code, config, workflow, or documentation change may begin before that read pass is complete.

## 2. Source-of-Truth and Conflict Rules

Documentation precedence is:

1. `docs/current-state.md` for what is actually implemented now
2. `docs/decisions.md` for accepted architectural decisions and explicit supersessions
3. subsystem specifications such as `docs/architecture.md`, `docs/data-modeling.md`, `docs/trading-system.md`, `docs/product-ui.md`, and `docs/engineering.md`
4. `docs/plan.md` for project charter and non-negotiables
5. `docs/roadmap.md` for sequencing and phase gates

If documents conflict:

- stop implementation work immediately
- resolve the documentation conflict first
- record the resolution in the appropriate doc
- update `docs/current-state.md` if the conflict affected current understanding

Agents must not silently pick one interpretation when the docs disagree.

## 3. Required Working Style

Agents must:

- follow the roadmap phase order unless the task is an urgent bug fix to already-implemented functionality
- keep changes aligned with the documented architecture and locked decisions
- prefer the smallest complete implementation slice that moves the roadmap forward
- update docs when implementation introduces a new decision, interface, dependency, or operational rule
- keep the repository single-user and local-first for v1
- preserve the free-source-only market-data constraint
- preserve the regular-hours-only v1 trading scope unless the docs are intentionally revised

Agents must not:

- bypass risk and validation gates for convenience
- enable live trading silently
- add hosted multi-user behavior to v1 without updating the docs and decisions first
- assume a paid market-data provider is allowed in v1

## 4. Required End-of-Task Checklist

After every completed modification, agents must:

1. verify the implementation against the relevant docs
2. run all relevant tests and checks for the affected area
3. verify repository-wide coverage remains at or above 80%
4. verify local checks cover the same intent as the current GitHub workflows
5. fix any failing check before declaring the work complete
6. update `docs/current-state.md`
7. update any affected spec document if the implementation changed the documented system shape
8. create a small local git commit for the completed logical slice

If the repository does not yet contain the needed tests, workflows, or coverage harness for the changed area, agents must add them as part of the work unless the task is documentation-only.

## 5. Verification Standards

Agents must verify as applicable:

- unit tests
- integration tests
- end-to-end or workflow tests for user-facing behavior
- data quality and reproducibility checks for data/model code
- coverage threshold of `>= 80%`
- linting, type-checking, and build checks
- GitHub Actions parity with local verification steps

“Works on my machine” is not sufficient. “Docs say it should work” is not sufficient. Verification must be concrete.

## 6. Current State Maintenance

`docs/current-state.md` must be updated at the end of every completed task to reflect reality.

At minimum, agents must update:

- what changed
- which roadmap phase or milestone moved
- subsystem implementation status
- known gaps or new risks
- verification results actually run
- the “last updated because” entry

Agents must not leave `docs/current-state.md` describing a state that no longer matches the repository.

## 7. Commit Policy

Agents must commit locally and frequently.

Commit rules:

- make small, atomic commits
- one logical slice per commit
- avoid bundling unrelated docs/code/workflow changes together
- use clear, descriptive commit messages
- complete verification before each commit whenever practical
- do not leave partially documented architectural changes uncommitted

If a task is too large for one safe commit, split it into smaller completed slices.

## 8. Documentation-Only Tasks

For documentation-only tasks, agents still must:

- read all docs first
- keep documentation internally consistent
- update `docs/current-state.md`
- run lightweight validation appropriate to the change, such as link/path checks and contradiction review

Coverage and workflow thresholds apply to implementation work. Documentation-only tasks should report when those checks are not applicable.

## 9. Definition of Done

Work is done only when:

- the implementation matches the docs
- the docs match the implementation
- verification has passed
- `docs/current-state.md` is updated
- the logical slice has been committed locally

Anything short of that is still in progress.
