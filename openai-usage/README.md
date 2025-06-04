# openai-usage 📊

CLI to inspect token usage and estimated cost for your OpenAI projects.

## Highlights

- Lists projects available to your admin API key
- Fetches usage details by day and model
- Calculates cost using a built‑in price table
- Output presented in colorful tables

## Installation

```bash
pipx install ./openai-usage
```

Set the `OPENAI_ADMIN_API_KEY` environment variable before running.

## Basic Usage

List usage for all projects grouped by day:

```bash
openai-usage
```

Show usage for specific projects and date range:

```bash
openai-usage -p proj_A proj_B -sd 2024-01-01 -ed 2024-01-31
```

Use `openai-usage --help` for more options.
