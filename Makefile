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
	rm -f .coverage .coverage.*
	COVERAGE_PROCESS_START=$(CURDIR)/pyproject.toml COVERAGE_RCFILE=$(CURDIR)/pyproject.toml $(PYTEST) tests

frontend-check:
	cd frontend && npm run lint
	cd frontend && npm run test
	cd frontend && npm run build

frontend-e2e:
	cd frontend && npm run build
	cd frontend && npx playwright install chromium
	cd frontend && npm run e2e

package-check:
	cd frontend && npm run build
	$(PYTHON) -m build
	TMPDIR=$$(mktemp -d) && \
	$(PYTHON) -m venv $$TMPDIR/venv && \
	$$TMPDIR/venv/bin/python -m pip install --upgrade pip && \
	$$TMPDIR/venv/bin/python -m pip install dist/*.whl httpx && \
	$$TMPDIR/venv/bin/stocktradebot init --app-home $$TMPDIR/app && \
	$$TMPDIR/venv/bin/stocktradebot doctor --app-home $$TMPDIR/app && \
	$$TMPDIR/venv/bin/stocktradebot status --app-home $$TMPDIR/app >/dev/null && \
	$$TMPDIR/venv/bin/stocktradebot --app-home $$TMPDIR/app --check-only --no-browser && \
	APP_HOME=$$TMPDIR/app $$TMPDIR/venv/bin/python -c "import os; from pathlib import Path; from fastapi.testclient import TestClient; from stocktradebot.api import create_app; from stocktradebot.config import initialize_config; config = initialize_config(Path(os.environ['APP_HOME'])); client = TestClient(create_app(config)); html = client.get('/').text; assert 'Frontend Build Missing' not in html; assert 'id=\"root\"' in html" && \
	rm -rf $$TMPDIR

check:
	$(MAKE) backend-quality
	$(MAKE) backend-tests
	$(MAKE) frontend-check
	$(MAKE) frontend-e2e
	$(MAKE) package-check
