# StockTradeBot Release Process

Phase 8 defines the repository release checklist for the local-first operator build.

## Release Goal

Every release must verify the supported install flow:

```bash
pipx install stocktradebot
stocktradebot init
stocktradebot doctor
stocktradebot
```

## Required Steps

1. update the package version in `pyproject.toml` and `src/stocktradebot/__init__.py`
2. build the frontend bundle from `frontend/`
3. run `make check`
4. run `make package-check`
5. confirm the package smoke test installs the built artifact in isolation and serves the bundled UI
6. update `README.md`, `docs/current-state.md`, and any operator-facing docs changed by the release
7. create a tag only after the verification results are complete and recorded

## Package Smoke Expectations

The package verification step is only complete when all of the following hold:

- the wheel builds successfully
- the installed CLI can run `init`, `doctor`, and `status`
- the installed runtime can serve `/` without falling back to the placeholder page

## Release Notes Minimum Content

Every release note should state:

- supported install flow
- major subsystem changes
- operator-visible safety or workflow changes
- known gaps that still remain intentionally blocked

## Rollback Rule

Do not publish a release that fails the packaged runtime smoke test. Fix the packaging or asset-bundling issue first.