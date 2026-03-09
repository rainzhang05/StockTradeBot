VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
RUFF ?= $(VENV)/bin/ruff
MYPY ?= $(VENV)/bin/mypy
PYTEST ?= $(VENV)/bin/pytest

.PHONY: install frontend-install fmt lint typecheck test frontend-lint frontend-test frontend-build frontend-e2e backend-quality backend-tests frontend-check package-check check

install:
	$(PYTHON) -m pip install -e ".[dev]"

frontend-install:
	cd frontend && npm install

fmt:
	$(RUFF) format src tests alembic/versions

lint:
	$(RUFF) check src tests alembic/versions

typecheck:
	$(MYPY) src

test:
	$(PYTEST) tests

frontend-lint:
	cd frontend && npm run lint

frontend-test:
	cd frontend && npm run test

frontend-build:
	cd frontend && npm run build

backend-quality:
	$(RUFF) format --check src tests alembic/versions
	$(RUFF) check src tests alembic/versions
	$(MYPY) src

backend-tests:
	$(PYTEST) tests

frontend-check:
	cd frontend && npm run lint
	cd frontend && npm run test
	cd frontend && npm run build

frontend-e2e:
	cd frontend && npm run build
	cd frontend && npx playwright install chromium
	cd frontend && npm run e2e

package-check:
	$(PYTHON) -m build

check:
	$(MAKE) backend-quality
	$(MAKE) backend-tests
	$(MAKE) frontend-check
	$(MAKE) frontend-e2e
	$(MAKE) package-check
