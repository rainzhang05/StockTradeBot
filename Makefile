PYTHON ?= python3

.PHONY: install frontend-install fmt lint typecheck test frontend-lint frontend-test frontend-build backend-quality backend-tests frontend-check package-check check

install:
	$(PYTHON) -m pip install -e ".[dev]"

frontend-install:
	cd frontend && npm install

fmt:
	ruff format src tests

lint:
	ruff check src tests

typecheck:
	mypy src

test:
	pytest

frontend-lint:
	cd frontend && npm run lint

frontend-test:
	cd frontend && npm run test

frontend-build:
	cd frontend && npm run build

backend-quality:
	ruff format --check src tests
	ruff check src tests
	mypy src

backend-tests:
	pytest

frontend-check:
	cd frontend && npm run lint
	cd frontend && npm run test
	cd frontend && npm run build

package-check:
	python -m build

check:
	$(MAKE) backend-quality
	$(MAKE) backend-tests
	$(MAKE) frontend-check
	$(MAKE) package-check
