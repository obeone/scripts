# openai-usage 📊

A command-line tool to inspect token usage and estimated cost for your OpenAI projects.

## Features

- **List Projects**: See all projects accessible with your admin API key.
- **Detailed Usage**: Fetch usage data broken down by day, model, and API key.
- **Auto-Updated Pricing**: Pricing data is automatically fetched from [litellm](https://github.com/BerriAI/litellm)'s community-maintained database and cached locally. Update anytime with `--update-pricing`.
- **Flexible Grouping**: Group and sort results by day, project, key, or model to analyze data from different perspectives.
- **Custom Date Ranges**: Specify start and end dates to focus on a particular period.
- **Colorful Output**: Presents data in a clear, color-coded table for easy reading.

## Installation

1. **Install with `uv`** (recommended), `pipx`, or `pip`:

    ```bash
    # With uv (recommended)
    uv pip install git+https://github.com/obeone/scripts#subdirectory=openai-usage

    # With pipx
    git clone https://github.com/obeone/scripts
    cd scripts
    pipx install ./openai-usage
    ```

2. **Set the Environment Variable**:
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

### Manage Pricing Data

Pricing is automatically fetched from litellm on first run and cached locally (`~/.cache/openai-usage/pricing.json`). To update it manually:

```bash
openai-usage --update-pricing
```

To check the cache status:

```bash
openai-usage --pricing-info
```

A warning is displayed if the cache is older than 30 days.

## Docker Usage

You can also run this tool using Docker, which isolates the environment and handles dependencies automatically.

1. **Build the Docker Image**:
    From the root of the project, run the following command to build the image:

    ```bash
    docker build -t openai-usage .
    ```

2. **Run the Container**:
    When running the container, you must pass your `OPENAI_ADMIN_API_KEY` as an environment variable.

    **Example: View Usage for All Projects**

    To get a complete usage report for all projects, grouped by day:

    ```bash
    docker run --rm -e OPENAI_ADMIN_API_KEY="your_admin_api_key_here" openai-usage
    ```

    **Example: List all projects**

    ```bash
    docker run --rm -e OPENAI_ADMIN_API_KEY="your_admin_api_key_here" openai-usage --list-projects
    ```

    **Example: Get usage for specific projects**

    ```bash
    docker run --rm -e OPENAI_ADMIN_API_KEY="your_admin_api_key_here" openai-usage -p proj_xxxxxxxxxxxx
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
| `--update-pricing` | | Fetch latest pricing from litellm and update local cache. | |
| `--pricing-info` | | Show pricing cache path, last update date, and model count. | |

**Available Grouping Criteria**: `day`, `project`, `key`, `model`.
