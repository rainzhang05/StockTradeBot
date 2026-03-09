PYTHON ?= python3

.PHONY: install frontend-install fmt lint typecheck test frontend-lint frontend-test frontend-build check

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

check:
	ruff format --check src tests
	ruff check src tests
	mypy src
	pytest
	cd frontend && npm run lint
	cd frontend && npm run test
	cd frontend && npm run build
