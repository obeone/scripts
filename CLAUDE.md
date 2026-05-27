# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository shape

Mono-repo of small, self-contained CLI utilities. **Each sub-project owns its own `pyproject.toml`, dependencies, and Python version range** — there is no shared root package. Treat each directory as an independent project: install / lint / test from that directory's contract, not from the root.

The root only ships a `.pre-commit-config.yaml` (shared formatters + mypy) and top-level `AGENTS.md` / `README.md`.

| Path | Lang | Python | Tests |
|------|------|--------|-------|
| `slideshow/` | Python (Tkinter) | 3.9–3.11 | ✅ `pytest` suite under `slideshow/tests/` |
| `openai-usage/` | Python | ≥3.10 | ✅ `openai-usage/tests/` — also has its own `CLAUDE.md` |
| `kdbg/` | Python | ≥3.8 | ❌ |
| `ks/` | Python | — | ❌ (`src/ks/cli.py`) |
| `proxmox/migration-watcher/` | Python | ≥3.7 | ❌ (single-module `watcher.py` at the project root, not under `src/`) |
| `proxmox/restore-watcher/` | Python | ≥3.8 | ❌ (single-module `restore_watcher.py`) |
| `docker-kubernetes/` | Bash | — | ❌ |
| `transfer.sh/` | Bash | — | ❌ |

`mcp/` and `docs/` are unversioned working dirs — confirm scope before editing.

## Per-project quickstart

All Python projects use `uv` for envs (per `~/.claude/CLAUDE.md` user policy). Install editable from the **project subdir**, not the root:

```bash
cd <project>
uv venv && source .venv/bin/activate
uv pip install -e .            # add [dev,test] where the project defines extras (slideshow)
```

Console entrypoints declared in each `pyproject.toml`:

| Project | Command | Module form |
|---------|---------|-------------|
| `slideshow` | `slideshow` | `slideshow.__main__:main` |
| `openai-usage` | `openai-usage` | `python -m openai_usage` |
| `kdbg` | `kdbg` | `kdbg.cli:main` |
| `ks` | — | `python -m ks.cli` |
| `proxmox/migration-watcher` | — | `python proxmox/migration-watcher/watcher.py` |

### Tests

Only `slideshow/` and `openai-usage/` have suites. Preferred granularity (smallest first):

```bash
pytest slideshow/tests/test_<module>.py::<test_name> -q
pytest slideshow/tests/test_<module>.py -q
pytest slideshow/tests -k "<expr>" -q
pytest slideshow/tests -q
```

`slideshow` enforces `mypy --strict`; keep that intact. Other projects ship `ruff` + `mypy` only via the root pre-commit hooks.

### Repo-wide hooks

```bash
pre-commit install
pre-commit run --all-files     # black, isort (black profile), ruff --fix, mypy, whitespace/yaml/large-files
```

Line length is **88** across the repo (black/isort/ruff agree). `slideshow.mypy.strict = true` — do not relax.

## Architecture notes (multi-file)

### `slideshow/` — Tkinter slideshow app

Source under `slideshow/src/slideshow/` is organized by responsibility, not by feature:

- `cli.py` → `__main__.py` → `app.py` (top-level orchestrator)
- `display.py`, `hud.py`, `controls.py` — rendering / overlay / input
- `image_loader.py`, `exif_utils.py`, `favorites.py`, `yoink.py` — image-side concerns
- `config.py`, `models/`, `services/`, `gui/`, `utils/`, `exceptions/` — supporting layers

Test entry conventions in `slideshow/tests/test_app.py` (e.g. `test_toggle_timer`) — match those names for new tests.

### `openai-usage/` — OpenAI cost inspector

Has its own `CLAUDE.md` (read it before editing). Four-module pipeline: `cli` → `pricing` (XDG-cached litellm pricing) → `api` (paginated OpenAI usage) → `display` (prettytable + termcolor). All prices are USD per 1M tokens. Requires `OPENAI_ADMIN_API_KEY` (admin-tier key, not a standard API key).

### `kdbg/` — Kubernetes debug-container launcher

`src/kdbg/`: `cli.py`, `k8s.py`, `helpers.py`, `completion.py`. Wraps `kubectl debug` with `fzf` selection; external `kubectl` + `fzf` must be on `PATH` (not declared as Python deps on purpose).

### `proxmox/migration-watcher/` and `restore-watcher/`

Single-script projects — `watcher.py` and `restore_watcher.py` live at the project root, **not** in `src/`. Don't restructure into a package without reason. `plotext` drives the text graph in `migration-watcher`.

## CodeGraph is indexed

`.codegraph/` exists at the repo root, so the `codegraph_*` MCP tools are live. Per user policy (see `~/.claude/CLAUDE.md`), prefer them over grep+read for **structural** questions (callers, callees, impact, where-defined, trace). Watch for the staleness banner when a file was just edited — re-read those files directly.

## Conventions worth knowing before editing

- `.gitignore` already excludes `.worktrees/`, `*.env`, all `*.egg-info/`, build artifacts, and `.venv/`. Don't recommit them.
- `transfer.sh/transfer-orig.sh` is git-ignored on purpose (upstream reference copy) — don't add it.
- Bash scripts use `#!/usr/bin/env bash` + `set -e`; keep variable expansions quoted (see `AGENTS.md` Bash section).
- New Python projects in this repo should follow the same layout: `src/<package>/`, `pyproject.toml` at the project root, `coloredlogs` for module-level loggers.

## Cursor / Copilot rules

`.cursor/rules/codegraph.mdc` mirrors the global CodeGraph policy. No `.cursorrules` or `.github/copilot-instructions.md` are present — if they appear later, treat them as higher-priority local policy (per `AGENTS.md`).
