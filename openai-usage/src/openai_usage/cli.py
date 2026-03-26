"""
Command-line interface for the OpenAI usage reporting tool.
"""

import os
import sys
from datetime import datetime

from openai_usage.api import fetch_project_usage, list_projects
from openai_usage.display import display_results
from openai_usage.pricing import get_cache_info, load_pricing, update_pricing


def _build_parser():
    """
    Build and return the argument parser.

    Returns
    -------
    argparse.ArgumentParser
        The configured argument parser.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch and display OpenAI API usage data per project.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-l",
        "--list-projects",
        action="store_true",
        help="List available projects and exit.",
    )
    parser.add_argument(
        "-p",
        "--projects",
        nargs="+",
        help=(
            "One or more project IDs to display usage for. "
            "If omitted, all projects are shown."
        ),
    )
    parser.add_argument(
        "-sd",
        "--start-date",
        type=str,
        help=(
            "Start date for usage data (YYYY-MM-DD). "
            "Defaults to the start of the current month."
        ),
    )
    parser.add_argument(
        "-ed",
        "--end-date",
        type=str,
        help=(
            "End date for usage data (YYYY-MM-DD). "
            "Defaults to the end of the current month."
        ),
    )
    parser.add_argument(
        "-gb",
        "--group-by",
        type=str,
        nargs="+",
        choices=["day", "project", "key", "model"],
        default=["day"],
        help=(
            "Criteria to group and sort results. Order matters for sorting. "
            "Subtotals are shown for the first criterion."
        ),
    )
    parser.add_argument(
        "--update-pricing",
        action="store_true",
        help="Fetch latest pricing from litellm and update local cache.",
    )
    parser.add_argument(
        "--pricing-info",
        action="store_true",
        help="Show pricing cache status and exit.",
    )
    return parser


def main() -> None:
    """
    Main entry point for the OpenAI usage reporting tool.

    Parses command-line arguments, loads pricing, fetches data from the
    OpenAI API, and displays the results.
    """
    parser = _build_parser()
    args = parser.parse_args()

    # Handle pricing commands (no API key needed)
    if args.pricing_info:
        print(get_cache_info())
        return

    if args.update_pricing:
        try:
            update_pricing()
        except Exception as e:
            print(f"Error updating pricing: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # All other commands need an API key
    api_key = os.getenv("OPENAI_ADMIN_API_KEY")
    if not api_key:
        print(
            "Error: OPENAI_ADMIN_API_KEY environment variable not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.list_projects:
        try:
            list_projects(api_key)
        except Exception as e:
            print(f"Error listing projects: {e}", file=sys.stderr)
        return

    # Validate date formats
    try:
        if args.start_date:
            datetime.strptime(args.start_date, "%Y-%m-%d")
        if args.end_date:
            datetime.strptime(args.end_date, "%Y-%m-%d")
        if args.start_date and args.end_date:
            if datetime.strptime(
                args.start_date, "%Y-%m-%d"
            ) > datetime.strptime(args.end_date, "%Y-%m-%d"):
                print(
                    "Error: Start date cannot be after end date.",
                    file=sys.stderr,
                )
                sys.exit(1)
    except ValueError:
        print(
            "Error: Invalid date format. Please use YYYY-MM-DD.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load pricing
    pricing = load_pricing()

    # Determine which project IDs to fetch
    project_ids_to_fetch = []
    if args.projects:
        project_ids_to_fetch = args.projects
    else:
        print(
            "No projects specified with -p/--projects. "
            "Fetching usage for all available projects...",
        )
        try:
            all_available_projects = list_projects(api_key, return_list=True)
            if all_available_projects:
                project_ids_to_fetch = [
                    p["id"]
                    for p in all_available_projects
                    if p.get("id")
                ]
                if not project_ids_to_fetch:
                    print(
                        "No project IDs found after listing all projects.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                print(
                    f"Found {len(project_ids_to_fetch)} projects to process."
                )
            else:
                print("No projects found to process.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(
                f"Error fetching list of all projects: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    if not project_ids_to_fetch:
        print("Error: No project IDs to process.", file=sys.stderr)
        sys.exit(1)

    all_projects_usage_details = []
    project_names_map = {}

    # Fetch project names for display
    try:
        projects_list_data = list_projects(api_key, return_list=True)
        if projects_list_data:
            project_names_map = {
                p.get("id"): p.get("name", "Unknown Project")
                for p in projects_list_data
            }
    except Exception as e:
        print(
            f"Warning: Could not fetch project names: {e}. "
            f"Project IDs will be used.",
            file=sys.stderr,
        )

    # Fetch usage for each project
    for project_id in project_ids_to_fetch:
        print(
            f"Fetching usage for project: "
            f"{project_names_map.get(project_id, project_id)}..."
        )
        try:
            usage_by_date = fetch_project_usage(
                project_id, api_key, pricing, args.start_date, args.end_date
            )
            for date, usage_list in usage_by_date.items():
                for usage_item in usage_list:
                    usage_item["date"] = date
                    usage_item["project_id"] = project_id
                    all_projects_usage_details.append(usage_item)
        except Exception as e:
            print(
                f"Error fetching usage for project {project_id}: {e}",
                file=sys.stderr,
            )

    # Display the consolidated results
    display_results(
        all_projects_usage_details, project_names_map, args.group_by
    )
