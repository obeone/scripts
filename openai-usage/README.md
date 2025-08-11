# openai-usage 📊

A command-line tool to inspect token usage and estimated cost for your OpenAI projects.

## Features

- **List Projects**: See all projects accessible with your admin API key.
- **Detailed Usage**: Fetch usage data broken down by day, model, and API key.
- **Cost Calculation**: Automatically calculate estimated costs using a comprehensive, up-to-date pricing table.
- **Flexible Grouping**: Group and sort results by day, project, key, or model to analyze data from different perspectives.
- **Custom Date Ranges**: Specify start and end dates to focus on a particular period.
- **Colorful Output**: Presents data in a clear, color-coded table for easy reading.

## Installation

1.  **Install with `pipx`** (recommended) or `pip`:
    ```bash
    pipx install ./openai-usage
    ```

2.  **Set the Environment Variable**:
    This tool requires an **admin-level** OpenAI API key to access organization and project data. Set it as an environment variable:
    ```bash
    export OPENAI_ADMIN_API_KEY="your_admin_api_key_here"
    ```

## Usage

### List Available Projects

To see a list of all projects you have access to:
```bash
openai-usage --list-projects
```

### View Usage for All Projects

To get a complete usage report for all projects, grouped by day:
```bash
openai-usage
```

### View Usage for Specific Projects and a Date Range

Focus on one or more projects and specify a time window:
```bash
openai-usage --projects proj_xxxxxxxxxxxx --start-date 2024-01-01 --end-date 2024-01-31
```

### Group and Sort Results

Analyze data by grouping it differently. The following command groups results first by project, then by day:
```bash
openai-usage --group-by project day
```

## Options

| Argument | Short | Description | Default |
|---|---|---|---|
| `--help` | `-h` | Show the help message and exit. | |
| `--list-projects` | `-l` | List available projects and exit. | |
| `--projects [ID ...]` | `-p` | One or more project IDs to analyze. | All projects |
| `--start-date YYYY-MM-DD` | `-sd` | The start date for the usage report. | Start of current month |
| `--end-date YYYY-MM-DD` | `-ed` | The end date for the usage report. | End of current month |
| `--group-by [CRITERIA ...]` | `-gb` | Criteria to group and sort results. Order matters. | `day` |

**Available Grouping Criteria**: `day`, `project`, `key`, `model`.