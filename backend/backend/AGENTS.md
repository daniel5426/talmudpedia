AGENTS for talmudpedia backend

Last Updated: 2026-02-18

Overview
- This document guides agentic coding agents on how to build, lint, test, and maintain the backend.
- Emphasizes deterministic tests, small, verifiable steps, and clear code style rules.

Environment and Setup
- Create a clean Python virtual environment and install dependencies:
  - python -m venv venv
  - source venv/bin/activate  # macOS/Linux
  - pip install -r backend/requirements.txt
- If using a container, ensure DOCKER_HOST budgets and env vars are set as expected by infra scripts.
- Load local environment variables from backend/.env when running locally; ensure required keys exist for tests.
- For reproducible tests, pin versions where possible and vendor a requirements file for CI.

Common Commands (Build/Lint/Test)
- Database migrations (Alembic):
  - alembic upgrade head
- Run the application (FastAPI):
  - uvicorn backend.main:app --reload --port 8000
- Run all tests (Legacy suite):
  - pytest backend/tests_legacy -q
- Run a single test file:
  - pytest backend/tests_legacy/test_agent_full_system.py -q
- Run a single test function:
  - pytest backend/tests_legacy/test_agent_full_system.py::test_full_execution_flow -q
- Run tests with verbose output for a single function:
  - pytest -vv backend/tests_legacy/test_agent_full_system.py::test_full_execution_flow
- Run tests with a keyword filter (subset):
  - pytest backend/tests_legacy -k "test_full_execution_flow" -q
- Run tests and stop on first failure:
  - pytest -x backend/tests_legacy -q
- Run a quick flake/lint pass:
  - pip install "ruff[all]" black isort flake8
  - ruff check backend
- Auto-format and sort imports:
  - black backend
  - isort backend
- Type checks (optional):
  - pip install mypy
  - mypy backend

Code Style Guidelines (Python)
- Imports
  - Order: standard library, third-party, local; import groups sorted alphabetically.
  - No wildcard imports; prefer explicit module imports.
- Formatting
  - Follow Black formatting (88 char line length by default).
  - Enforce consistent import order with isort.
- Types and Typing
  - Use type hints for public APIs and data models (Optional, List, Dict, etc.).
  - Prefer Pydantic models for data validation in APIs.
- Naming conventions
  - Functions/variables: snake_case; Classes: PascalCase; constants: UPPER_SNAKE.
- Error handling
  - Avoid bare excepts; catch specific exceptions.
  - Raise meaningful exceptions or return structured error payloads.
- Logging
  - Use module-level loggers: logger = logging.getLogger(__name__);
  - Redact secrets in logs; never log credentials.
- Testing
  - Place tests under backend/tests_legacy or backend/tests; use descriptive file names.
  - Use pytest fixtures for DB setup/teardown; keep tests deterministic and isolated.
- Documentation
  - Docstrings for public APIs; docstrings should describe usage, parameters, and return values.
- Security
  - Do not log secrets; redact keys in test outputs and logs.
- Versioning and commits
  - Prefer conventional commits style: feat:, fix:, docs:, perf:, refactor:, test:, chore.

Cursor Rules and Copilot Rules
- Cursor rules: Not found in this repository (.cursor/rules or .cursorrules not present).
- Copilot rules: Not present (.github/copilot-instructions.md not found).

Notes and Best Practices
- For single-test runs, prefer explicit file and function references rather than broad -k searches to reduce flakiness.
- When tests are flaky due to environment, consider adding a focused test to cover the failure mode and mark it to skip in CI when necessary.
- Keep test data minimal and deterministic to minimize side effects and speed up runs.

Testing Methodology
- Use fixtures to isolate DB state; avoid shared mutable globals.
- Name tests clearly; reflect behavior being tested.
- Run tests with -q for quiet, or -vv for verbose function-level detail.

CI and Makefile
- Consider adding a Makefile target set:
  - test-legacy, test-all, lint, format, typecheck
- Add a minimal CI snippet to run the primary commands above.

Optional: Documentation and Arch
- If you maintain architecture docs, keep them in code_architect/ with the tree.
- Update architecture whenever you add/modify critical API surfaces.

Next steps
- If you want, I can add a Makefile and a small CI snippet to standardize the workflow.

Extended Development Workflow
- Pre-commit hooks: install and run locally before commits:
  - pip install pre-commit
  - pre-commit install
  - pre-commit run --all-files
- Subset test strategies:
  - Use -k with descriptive substrings:
    - pytest backend/tests_legacy -k "agent_full_system or database" -q
- Database migrations during development:
  - alembic downgrade head; alembic upgrade head
- Secrets and config:
  - Do not commit secrets; use backend/.env.local or a CI secret store.
- Performance hints:
  - Use pytest -q; run only the slow tests to measure improvements.
- Reporting:
  - Save test outputs to a log file for CI; e.g., pytest -q > tests.log 2>&1

Extended Development Workflow
- Pre-commit hooks: install and run locally before commits:
  - pip install pre-commit
  - pre-commit install
  - pre-commit run --all-files
- Subset test strategies:
  - Use -k with descriptive substrings:
    - pytest backend/tests_legacy -k "agent_full_system or database" -q
- Database migrations during development:
  - alembic downgrade head; alembic upgrade head
- Secrets and config:
  - Do not commit secrets; use backend/.env.local or a CI secret store.
- Performance hints:
  - Use pytest -q; run only the slow tests to measure improvements.
- Reporting:
  - Save test outputs to a log file for CI; e.g., pytest -q > tests.log 2>&1

End
