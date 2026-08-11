# Repository Guidelines

## Project Structure & Module Organization

This directory contains the `openai-usage-report` Python CLI package inside the
larger `scripts` mono-repo.

## Packaging: two different names

The distribution name and the command name deliberately differ. Do not
"fix" one to match the other.

| What | Value | Where it comes from |
|------|-------|---------------------|
| PyPI distribution | `openai-usage-report` | `[project].name` |
| Console command | `openai-usage` | `[project.scripts]` |
| Import package | `openai_usage` | `src/openai_usage/` |
| Docker image | `obeoneorg/openai-usage-report` | `docker-openai-usage.yaml` |

`openai-usage` on PyPI is an unrelated project owned by someone else, so
publishing under that name fails with `403 Forbidden`. Renaming
`[project].name` to `openai-usage` breaks the release workflow; it happened
once already and silently blocked publishing for months.

Passing the command name where uv expects the distribution name is what
produces `Package name (openai-usage-report) provided --from does not match
request (openai-usage)`. Install from the path instead:

```bash
uv tool install .          # correct
uv tool install openai-usage --from .   # wrong, this is the error above
```

- `src/openai_usage/`: package source code.
- `src/openai_usage/cli.py`: argparse entry point and orchestration.
- `src/openai_usage/api.py`: OpenAI Admin API calls and pagination.
- `src/openai_usage/pricing.py`: pricing cache fetch, conversion, and fallback.
- `src/openai_usage/display.py`: terminal table rendering.
- `docs/`: design notes and implementation plans.
- `Dockerfile`, `pyproject.toml`, `README.md`: packaging and runtime metadata.

- `tests/`: `pytest` suite.

## Build, Test, and Development Commands

Run commands from `openai-usage/` unless noted.

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

Create a local environment and install the package in editable mode.

```bash
python -m openai_usage --help
openai-usage --help
```

Verify both module execution and the console script.

```bash
ruff check src
docker build -t openai-usage .
```

Run lint checks and build the container image.

## Coding Style & Naming Conventions

Use Python 3.10+ syntax, type hints on public signatures, and standard Black
formatting with 4-space indentation. Keep module names and functions in
`snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`.
Prefer small functions with explicit error handling and actionable CLI
messages. Keep comments sparse; add them only where behavior is not obvious.

## Testing Guidelines

Run the suite with `uv run --with pytest pytest -q` from `openai-usage/`.
Place new tests under `tests/`, use `pytest`, and name files
`test_<module>.py`. Test names should
describe expected behavior, for example
`test_fetch_project_usage_handles_paginated_results`. For bug fixes, add a
regression test that fails before the fix and passes after it.

## Commit & Pull Request Guidelines

The git history uses Conventional Commits, such as
`fix(openai-usage): correct package metadata name`. Keep commits atomic and
scope them to this package when possible. Do not mix dependency bumps with
feature or fix work.

Pull requests should include a short problem statement, the implemented
change, verification commands run, and any user-visible CLI behavior changes.
Never include secrets or real API keys in commits, logs, screenshots, or PR
descriptions.

## Security & Configuration Tips

Runtime access requires `OPENAI_ADMIN_API_KEY` in the environment. Do not store
it in tracked files. Pricing data is cached under the user cache directory,
usually `~/.cache/openai-usage/pricing.json`.
