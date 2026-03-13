# StockTradeBot Release Process

This document defines the repository release checklist for the current local-first operator build.

## Release Goal

Every release must verify the supported install flow:

```bash
pipx install stocktradebot
stocktradebot init
stocktradebot doctor
stocktradebot
```

Published releases are uploaded to PyPI by the dedicated GitHub Actions workflow [publish-pypi.yml](/Users/rainzhang/StockTradeBot/.github/workflows/publish-pypi.yml), which is separate from the existing package-verification workflow.

## Trusted Publisher Setup

Before the first PyPI release, register this repository as a PyPI Trusted Publisher with these exact values:

- PyPI project: `stocktradebot`
- repository owner: `rainzhang05`
- repository name: `StockTradeBot`
- workflow filename: `.github/workflows/publish-pypi.yml`
- GitHub environment: `pypi`

If the project does not exist on PyPI yet, create it through PyPI's pending Trusted Publisher flow first. After that registration exists, the workflow can publish without a long-lived API token.

## Required Steps

1. update the package version in `pyproject.toml` and `src/stocktradebot/__init__.py`
2. build the frontend bundle from `frontend/`
3. run `make check`
4. run `make package-check`
5. confirm the PyPI Trusted Publisher exists for `.github/workflows/publish-pypi.yml` and the `pypi` environment
6. create and push a version tag matching the package version, for example `v0.1.0`; that tag triggers the PyPI publish workflow
7. confirm the publish workflow built the frontend, built the distributions, ran `twine check`, passed the installed-wheel smoke path, and uploaded the release to PyPI
8. update `README.md`, `docs/current-state.md`, and any operator-facing docs changed by the release

When a release changes the available research surface, update the root README examples so CLI workflows match the current supported daily and intraday commands.

## Package Smoke Expectations

The package verification step is only complete when all of the following hold:

- the wheel builds successfully
- the installed CLI can run `init`, `doctor`, `status`, and `stocktradebot --check-only --no-browser`
- the installed runtime can serve `/` without falling back to the placeholder page
- the version tag matches `pyproject.toml`

## Release Notes Minimum Content

Every release note should state:

- supported install flow
- major subsystem changes
- operator-visible safety or workflow changes
- known gaps that still remain intentionally blocked

## Rollback Rule

Do not publish a release that fails the packaged runtime smoke test. Fix the packaging or asset-bundling issue first.
