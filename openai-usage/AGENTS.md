# Repository Guidelines

## Project Structure & Module Organization

This directory contains the `openai-usage` Python CLI package inside the
larger `scripts` mono-repo. Project-specific maintainer notes live in
`CLAUDE.md`; treat that file as the first source for architecture details.

- `src/openai_usage/`: package source code.
- `src/openai_usage/cli.py`: argparse entry point and orchestration.
- `src/openai_usage/api.py`: OpenAI Admin API calls and pagination.
- `src/openai_usage/pricing.py`: pricing cache fetch, conversion, and fallback.
- `src/openai_usage/display.py`: terminal table rendering.
- `docs/`: design notes and implementation plans.
- `Dockerfile`, `pyproject.toml`, `README.md`: packaging and runtime metadata.

There is currently no dedicated test directory for this package.

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

No automated test suite exists yet. When adding tests, place them under
`tests/`, use `pytest`, and name files `test_<module>.py`. Test names should
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
