#!/usr/bin/env python3

import requests
from datetime import datetime, timezone, timedelta
from prettytable import PrettyTable
from termcolor import colored
import os
import argparse
import sys  # For sys.stderr

# API Configuration
API_BASE_URL_PROJECTS = "https://api.openai.com/v1/organization/projects"
API_BASE_URL_PROJECT_API_KEYS = f"{API_BASE_URL_PROJECTS}/{{project_id}}/api_keys"
API_BASE_URL_USAGE_COMPLETIONS = "https://api.openai.com/v1/organization/usage/completions"

# Define pricing centrally for easy updates
# (PRICING dictionary remains the same as in the previous version)
PRICING = {
    # ==== Latest models ====
    "gpt-4.1": {
        "input": 0.2,       # $2.00 per 1M tokens => 0.2¢/1k
        "cached_input": 0.05,  # $0.50 per 1M tokens => 0.05¢/1k
        "output": 0.8,      # $8.00 per 1M tokens => 0.8¢/1k
    },
    "gpt-4.1-2025-04-14": {
        "input": 0.2,
        "cached_input": 0.05,
        "output": 0.8,
    },
    "gpt-4.1-mini": {
        "input": 0.04,      # $0.40/1M = 0.04¢/1k
        "cached_input": 0.01,  # $0.10/1M = 0.01¢/1k
        "output": 0.16,     # $1.60/1M = 0.16¢/1k
    },
    "gpt-4.1-mini-2025-04-14": {
        "input": 0.04,
        "cached_input": 0.01,
        "output": 0.16,
    },
    "gpt-4.1-nano": {
        "input": 0.01,      # $0.10/1M = 0.01¢/1k
        "cached_input": 0.0025,  # $0.025/1M = 0.0025¢/1k
        "output": 0.04,     # $0.40/1M = 0.04¢/1k
    },
    "gpt-4.1-nano-2025-04-14": {
        "input": 0.01,
        "cached_input": 0.0025,
        "output": 0.04,
    },

    # ==== GPT-4.5 Preview ====
    "gpt-4.5-preview": {
        "input": 7.5,         # $75.00/1M = 7.5¢/1k
        "cached_input": 3.75,  # $37.50/1M = 3.75¢/1k
        "output": 15.0,       # $150.00/1M = 15¢/1k
    },
    "gpt-4.5-preview-2025-02-27": {
        "input": 7.5,
        "cached_input": 3.75,
        "output": 15.0,
    },

    # ==== GPT-4o and variants ====
    "gpt-4o": {
        "input": 0.25,
        "cached_input": 0.125,
        "output": 1.0,
    },
    "gpt-4o-2024-08-06": {
        "input": 0.25,        # $2.50/1M = 0.25¢/1k
        "cached_input": 0.125,
        "output": 1.0,
    },
    "gpt-4o-2024-11-20": {
        "input": 0.25,
        "cached_input": 0.125,
        "output": 1.0,
    },
    "gpt-4o-2024-05-13": {
        "input": 0.5,
        "cached_input": 0.5,
        "output": 1.5,
    },
    "gpt-4o-realtime-preview-2024-12-17": {
        "input": 0.5,         # $5.00/1M = 0.5¢/1k
        "cached_input": 0.25,
        "output": 2.0,        # $20.00/1M = 2¢/1k
    },
    "gpt-4o-mini-2024-07-18": {
        "input": 0.015,       # $0.15/1M = 0.015¢/1k
        "cached_input": 0.0075,
        "output": 0.06,
    },
    "gpt-4o-mini": {
        "input": 0.015,
        "cached_input": 0.0075,
        "output": 0.06,
    },
    "gpt-4o-mini-realtime-preview-2024-12-17": {
        "input": 0.06,        # $0.60/1M = 0.06¢/1k
        "cached_input": 0.03,
        "output": 0.24,
    },
    "gpt-4o-search-preview-2025-03-11": {
        "input": 0.25,        # $2.50/1M = 0.25¢/1k
        "output": 1.0,
    },
    "gpt-4o-mini-search-preview-2025-03-11": {
        "input": 0.015,       # $0.15/1M = 0.015¢/1k
        "output": 0.06,
    },

    # ==== Other recent models ====
    "o1-2024-12-17": {
        "input": 1.5,         # $15.00/1M = 1.5¢/1k
        "cached_input": 0.75,
        "output": 6.0,
    },
    "o1-pro-2025-03-19": {
        "input": 15.0,        # $150.00/1M = 15¢/1k
        "output": 60.0,
    },
    "o3-2025-04-16": {
        "input": 1.0,         # $10.00/1M = 1¢/1k
        "cached_input": 0.25,
        "output": 4.0,
    },
    "o3": {
        "input": 0.5,         # $5.00/1M = 0.5¢/1k
        "cached_input": 0.125,
        "output": 2.0,
    },
    "o3-mini-2025-01-31": {
        "input": 0.11,        # $1.10/1M = 0.11¢/1k
        "cached_input": 0.055,
        "output": 0.44,
    },
    "o1-mini-2024-09-12": {
        "input": 0.11,
        "cached_input": 0.055,
        "output": 0.44,
    },
    "o4-mini-2025-04-16": {
        "input": 0.25,
        "cached_input": 0.0275,
        "output": 0.44,
    },

    # ==== Historical GPT models ====
    "gpt-4-turbo-2024-04-09": {
        "input": 1.0,         # $10.00/1M = 1¢/1k
        "output": 3.0,
    },
    "gpt-4-0613": {
        "input": 3.0,         # $30.00/1M = 3¢/1k
        "output": 6.0,
    },
    "gpt-4-32k": {
        "input": 6.0,         # $60.00/1M = 6¢/1k
        "output": 12.0,
    },
    "gpt-3.5-turbo-0125": {
        "input": 0.05,        # $0.50/1M = 0.05¢/1k
        "output": 0.15,
    },
    "gpt-3.5-turbo-instruct": {
        "input": 0.15,        # $1.50/1M = 0.15¢/1k
        "output": 0.2,        # $2.00/1M = 0.2¢/1k
    },
    "gpt-3.5-turbo-16k-0613": {
        "input": 0.3,         # $3.00/1M = 0.3¢/1k
        "output": 0.4,
    },

    # ==== Codex, computer-use, others ====
    "codex-mini-latest": {
        "input": 0.15,        # $1.50/1M = 0.15¢/1k
        "cached_input": 0.0375,
        "output": 0.6,
    },
    "computer-use-preview-2025-03-11": {
        "input": 0.3,         # $3.00/1M = 0.3¢/1k
        "output": 1.2,
    },

    # ==== Embeddings ====
    "text-embedding-3-small": {
        "input": 0.002,  # $0.02/1M tokens => 0.002¢/1k.
    },
    "text-embedding-3-large": {
        "input": 0.013,       # $0.13/1M tokens => 0.013¢/1k
    },
    "text-embedding-ada-002": {
        "input": 0.01,        # $0.10/1M tokens => 0.01¢/1k
    },

    # ==== Audio and TTS ====
    "whisper-1": {
        "minute": 0.006,      # $0.006 per minute audio
    },
    "gpt-4o-transcribe": {
        "input": 0.25,
        "output": 1.0,
        "minute": 0.006,      # $0.006/minute (cost in dollars)
    },
    "gpt-4o-mini-transcribe": {
        "input": 0.125,
        "output": 0.5,
        "minute": 0.003,      # $0.003/minute (cost in dollars)
    },
    "gpt-4o-mini-tts": {
        # Assuming 1.2 cents per 1k characters ($12.00/1M chars)
        "output": 1.2,
        "minute": 0.015,      # $0.015/minute (cost in dollars)
    },

    # ==== Image ====
    "gpt-image-1": {
        "input": 1.0,
        "output": 4.0,
    },
    "dall-e-3": {
        "standard": 4.0,      # 4.0¢/image
        "hd": 8.0,            # 8.0¢/image
    },
    "dall-e-2": {
        "standard": 1.6,      # 1.6¢/image (1024x1024)
        "512": 1.8,           # Assuming 1.8¢/image (512x512)
        "256": 1.6,           # Assuming 1.6¢/image (256x256)
    },

    # ==== Moderation ====
    "omni-moderation-latest": {
        "input": 0.0,
    },
    "text-moderation-latest": {
        "input": 0.0,
    },
}


def fetch_all_api_keys(project_id: str, api_key: str) -> dict:
    '''
    Fetch all API keys for the project, handling pagination.

    Args:
        project_id (str): The project ID to query.
        api_key (str): The API key for authentication.

    Returns:
        dict: A dictionary mapping API key IDs to their names.

    Raises:
        Exception: If the API request fails or JSON decoding fails.
    '''
    url = API_BASE_URL_PROJECT_API_KEYS.format(project_id=project_id)
    headers = {"Authorization": f"Bearer {api_key}"}
    api_keys_map = {}
    params = {"limit": 100}
    current_request_url = url  # Start with the base URL

    # Loop as long as there's a URL to call (handles full next URLs too)
    while current_request_url:
        try:
            # If current_request_url is the base, params are used.
            # If current_request_url is a full next_page URL, params might be embedded or empty.
            active_params = params if current_request_url == url else None
            response = requests.get(
                current_request_url, headers=headers, params=active_params)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as http_err:
            error_message = f"HTTP error fetching API keys: {http_err} - Response: {response.text}"
            print(f"DEBUG: Failed URL: {response.url}", file=sys.stderr)
            print(f"DEBUG: Failed PARAMS: {active_params}", file=sys.stderr)
            raise Exception(error_message) from http_err
        except requests.exceptions.JSONDecodeError as json_err:
            raise Exception(
                f"Failed to decode JSON response for API keys: {response.text}") from json_err
        except requests.exceptions.RequestException as req_err:
            raise Exception(
                f"Request failed while fetching API keys: {req_err}") from req_err

        for key_data in data.get('data', []):
            api_keys_map[key_data['id']] = key_data.get(
                'name', f"Unnamed Key ({key_data['id'][:4]}...)")

        next_cursor = data.get('pagination', {}).get('next_cursor')
        if not next_cursor:
            break

        # Prepare for next iteration: always use the base URL with the cursor
        current_request_url = url
        params = {"limit": 100, "cursor": next_cursor}

    return api_keys_map


def calculate_costs(usage: dict, model_name: str) -> dict:
    '''
    Calculate the cost based on usage and pricing for a specific model.
    Assumes PRICING contains token prices in cents per 1k tokens,
    and minute prices (key 'minute') in dollars per minute.

    Args:
        usage (dict): Dictionary containing usage data (e.g., input_tokens, output_tokens, minute).
        model_name (str): Name of the model for pricing reference.

    Returns:
        dict: A dictionary with calculated costs for input, output, cached input tokens,
              and minutes in cents. Returns an empty dict if model_name is not found in PRICING.
    '''
    model_pricing = PRICING.get(model_name)
    if not model_pricing:
        if model_name and model_name.lower() != "unknown":
            print(
                f"Warning: Pricing for model '{model_name}' not found. Costs will be $0.", file=sys.stderr)
        return {}

    costs = {}
    if 'input_tokens' in usage and 'input' in model_pricing:
        costs['input_cost'] = (usage['input_tokens'] /
                               1000.0) * model_pricing['input']
    if 'output_tokens' in usage and 'output' in model_pricing:
        costs['output_cost'] = (
            usage['output_tokens'] / 1000.0) * model_pricing['output']
    if 'cached_input_tokens' in usage and 'cached_input' in model_pricing:
        costs['cached_input_cost'] = (
            usage['cached_input_tokens'] / 1000.0) * model_pricing['cached_input']
    if 'minute' in usage and 'minute' in model_pricing:
        costs['minute_cost'] = usage['minute'] * \
            model_pricing['minute'] * 100.0  # Convert dollars to cents
    return costs


def fetch_usage_details(project_id: str, api_key: str, api_keys_map: dict,
                        start_date_str: str | None = None,
                        end_date_str: str | None = None) -> dict:
    '''
    Fetch usage details for a given project and date range, including API key names, handling pagination.

    Args:
        project_id (str): The project ID to query usage for.
        api_key (str): The API key for authentication.
        api_keys_map (dict): A dictionary mapping API key IDs to their names.
        start_date_str (str | None): Optional start date in YYYY-MM-DD format.
                                     Defaults to the start of the current month.
        end_date_str (str | None): Optional end date in YYYY-MM-DD format.
                                   Defaults to the end of the current month.

    Returns:
        dict: A dictionary mapping dates (YYYY-MM-DD) to lists of usage details.

    Raises:
        Exception: If the API request fails, JSON decoding fails, or date parsing fails.
        ValueError: If start_date is after end_date.
    '''
    headers = {"Authorization": f"Bearer {api_key}"}
    now = datetime.now(timezone.utc)

    # If start_date_str is None, use the first day of the current month
    if not start_date_str:
        start_time_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        try:
            start_time_dt = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError as ve:
            raise Exception(f"Invalid start date format: {ve}") from ve

    # If end_date_str is None, use the last day and last second of the current month
    if not end_date_str:
        # Find the last day of the month
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_of_month = (next_month - timedelta(seconds=1)).replace(tzinfo=timezone.utc)
        end_time_dt = last_day_of_month
    else:
        try:
            end_time_dt = datetime.strptime(end_date_str, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
            )
        except ValueError as ve:
            raise Exception(f"Invalid end date format: {ve}") from ve

    if start_time_dt > end_time_dt:
        raise ValueError("Start date cannot be after end date.")

    start_time_ts = int(start_time_dt.timestamp())
    end_time_ts = int(end_time_dt.timestamp())

    usages_by_date = {}
    # Initial params for the first request
    current_params = {
        "project_id": project_id,
        "start_time": start_time_ts,
        "end_time": end_time_ts,
        "group_by": "api_key_id,model",
        "bucket_width": "1d"
    }
    # Note: The original logic for start_time_dt and end_time_dt from lines 355-370
    # has been consolidated and corrected above.
    # The timestamp calculations (original lines 372-373 and 408-409) are now correctly placed
    # after the final determination of start_time_dt and end_time_dt.










    current_url = API_BASE_URL_USAGE_COMPLETIONS

    while current_url:
        try:
            response = requests.get(
                current_url, headers=headers, params=current_params)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as http_err:
            error_message = f"HTTP error fetching usage data: {http_err} - Response: {response.text}\nURL: {response.url}\nParams: {current_params}"
            raise Exception(error_message) from http_err
        except requests.exceptions.JSONDecodeError as json_err:
            raise Exception(
                f"Failed to decode JSON response for usage data: {response.text}") from json_err
        except requests.exceptions.RequestException as req_err:
            raise Exception(
                f"Request failed while fetching usage data: {req_err}") from req_err

        for bucket in data.get('data', []):
            bucket_start_time_str = datetime.fromtimestamp(
                bucket.get('start_time'), timezone.utc).strftime('%Y-%m-%d')
            if bucket_start_time_str not in usages_by_date:
                usages_by_date[bucket_start_time_str] = []

            for result in bucket.get('results', []):
                key_id = result.get('api_key_id')
                if key_id not in api_keys_map:
                    continue
                result['api_key_name'] = api_keys_map[key_id]
                model_name = result.get('model', "unknown")
                result['costs'] = calculate_costs(result, model_name)
                usages_by_date[bucket_start_time_str].append(result)

        next_page_info = data.get('next_page')
        if not next_page_info:
            break  # No more pages

        if next_page_info.startswith("http"):
            current_url = next_page_info
            current_params = None  # Params are included in the full URL
        else:
            # Assuming it's a token for the 'page' parameter (OpenAI specific pagination)
            # Preserve original parameters and add/update the page token
            current_params = {
                "project_id": project_id,
                "start_time": start_time_ts,
                "end_time": end_time_ts,
                "group_by": "api_key_id,model",
                "bucket_width": "1d",
                "page": next_page_info  # Add or update the page token
            }
            current_url = API_BASE_URL_USAGE_COMPLETIONS  # Reset to base URL with new params

    return usages_by_date


def fetch_project_usage(project_id: str, api_key: str,
                        start_date_str: str | None = None,
                        end_date_str: str | None = None) -> dict:
    '''
    Fetch usage details for a given project for a specified date range.

    Args:
        project_id (str): The project ID to query usage for.
        api_key (str): The API key for authentication.
        start_date_str (str | None): Optional start date in YYYY-MM-DD format.
        end_date_str (str | None): Optional end date in YYYY-MM-DD format.

    Returns:
        dict: A dictionary mapping dates to usage details.
    '''
    api_keys_map = fetch_all_api_keys(project_id, api_key)
    return fetch_usage_details(project_id, api_key, api_keys_map, start_date_str, end_date_str)


def list_projects(api_key: str, return_list: bool = False) -> list | None:
    '''
    Fetch and display a list of available OpenAI projects.

    Args:
        api_key (str): The API key for authentication.
        return_list (bool, optional): If True, returns the list of projects
                                      instead of printing. Defaults to False.

    Returns:
        list | None: A list of project dictionaries if return_list is True, otherwise None.

    Raises:
        Exception: If the API request fails or JSON decoding fails.
    '''
    all_projects = []
    # Initial params for the first request
    current_params = {"limit": 100}
    headers = {"Authorization": f"Bearer {api_key}"}
    current_url = API_BASE_URL_PROJECTS

    try:
        while current_url:
            response = requests.get(
                current_url, headers=headers, params=current_params)
            response.raise_for_status()
            data = response.json()

            projects_page = data.get('data', [])
            all_projects.extend(projects_page)

            # Pagination for projects uses 'has_more' and 'after' with the last ID
            if data.get('has_more') and projects_page:
                last_id = projects_page[-1].get('id')
                if not last_id:
                    break
                current_params = {'limit': 100, 'after': last_id}
                current_url = API_BASE_URL_PROJECTS  # Stay on base URL, update params
            else:
                break  # No more pages

        if return_list:
            return all_projects
        else:
            if not all_projects:
                print("No projects found.")
                return None
            print("Available Projects:")
            for project in all_projects:
                print(
                    f"- ID: {project.get('id')}, Name: {project.get('name')}")
            return None
    except requests.exceptions.HTTPError as http_err:
        error_message = f"HTTP error fetching projects: {http_err} - Response: {response.text}"
        raise Exception(error_message) from http_err
    except requests.exceptions.JSONDecodeError as json_err:
        raise Exception(
            f"Failed to decode JSON response for projects: {response.text}") from json_err
    except requests.exceptions.RequestException as req_err:
        raise Exception(
            f"Request failed while fetching projects: {req_err}") from req_err


def get_sort_key_tuple(usage_item: dict, criteria_list: list[str], project_names_map: dict) -> tuple:
    '''
    Generate a sort key tuple for a usage item based on a list of criteria.
    Secondary sort criteria are added automatically for stability.

    Args:
        usage_item (dict): The usage data item.
        criteria_list (list[str]): User-specified sort criteria (e.g., ['project', 'day']).
        project_names_map (dict): Mapping of project IDs to names.

    Returns:
        tuple: A tuple of values to be used for sorting.
    '''
    key_parts = []

    # Define all possible values from the usage_item once
    project_id_val = usage_item.get('project_id', '')
    project_name_val = project_names_map.get(
        project_id_val, project_id_val)  # Use name for sorting if available
    date_val = usage_item.get('date', '')
    key_name_val = usage_item.get('api_key_name', '')
    model_val = usage_item.get('model', '')

    # Map criterion string to its corresponding value
    criteria_to_value_map = {
        'project': project_name_val,
        'day': date_val,
        'key': key_name_val,
        'model': model_val
    }

    # Add parts based on user-specified criteria order
    for criterion in criteria_list:
        key_parts.append(criteria_to_value_map.get(
            criterion.lower(), ''))  # .lower() for safety

    # Add remaining criteria (not specified by user) in a fixed order for stable sort
    # This ensures that if user groups by e.g. 'project', items within the same project are then sorted by day, then key, etc.
    all_possible_criteria_in_stable_order = ['project', 'day', 'key', 'model']
    for crit in all_possible_criteria_in_stable_order:
        if crit not in criteria_list:  # Only add if not already added by user's primary criteria
            # Check if the value itself needs to be added, not the criterion string
            if crit == 'project' and 'project' not in criteria_list:
                key_parts.append(project_name_val)
            elif crit == 'day' and 'day' not in criteria_list:
                key_parts.append(date_val)
            elif crit == 'key' and 'key' not in criteria_list:
                key_parts.append(key_name_val)
            elif crit == 'model' and 'model' not in criteria_list:
                key_parts.append(model_val)

    return tuple(key_parts)


def display_results(all_usage_details: list, project_names: dict, group_by_criteria: list[str]) -> None:
    '''
    Display usage data in a formatted table, grouped and sorted as specified.
    Subtotals are displayed for the first criterion in group_by_criteria.

    Args:
        all_usage_details (list): A list of dictionaries, where each dictionary contains
                                  usage details for a specific model/API key combination
                                  on a given date, including 'date' and 'project_id'.
        project_names (dict): A dictionary mapping project IDs to project names.
        group_by_criteria (list[str]): The criteria for grouping and sorting results 
                                     (e.g., ['project', 'day']).
    '''
    table = PrettyTable()
    table.field_names = ["Date", "Project", "Model", "API Key",
                         "Input (¢)", "Output (¢)", "Cached (¢)", "Total (¢)"]
    table.align["Input (¢)"] = "r"
    table.align["Output (¢)"] = "r"
    table.align["Cached (¢)"] = "r"
    table.align["Total (¢)"] = "r"

    grand_total_cost = 0.0

    if not all_usage_details:
        print("No usage data to display.")
        return

    # Sort details based on the full criteria list for detailed row order
    # The get_sort_key_tuple function handles creating a comprehensive sort key
    sorted_usage_details = sorted(all_usage_details, key=lambda x: get_sort_key_tuple(
        x, group_by_criteria, project_names))

    # Determine the primary grouping criterion for subtotals
    # Default to day if empty, though argparse default helps
    primary_group_criterion = group_by_criteria[0] if group_by_criteria else "day"

    group_label_prefix_map = {
        "project": "Total for Project",
        "day": "Total for day",
        "key": "Total for API Key",
        "model": "Total for Model"
    }
    group_label_prefix = group_label_prefix_map.get(
        primary_group_criterion, f"Total for {primary_group_criterion}")

    current_primary_group_id_val = None
    current_primary_group_display_name = ""
    current_group_total_cost = 0.0

    for usage in sorted_usage_details:
        item_primary_group_id_val = None
        item_primary_group_display_name = ""

        # Determine the ID and display name for the current item's *primary* group
        if primary_group_criterion == 'project':
            project_id = usage.get('project_id', 'unknown_project')
            item_primary_group_id_val = project_id
            item_primary_group_display_name = project_names.get(
                project_id, project_id)
        elif primary_group_criterion == 'key':
            api_key_name = usage.get('api_key_name', 'Unknown')
            item_primary_group_id_val = api_key_name
            item_primary_group_display_name = api_key_name
        elif primary_group_criterion == 'model':
            model_name = usage.get('model', 'Unknown Model')
            item_primary_group_id_val = model_name
            item_primary_group_display_name = model_name
        else:  # 'day' or default
            date_str_group = usage.get('date', 'unknown_date')
            item_primary_group_id_val = date_str_group
            item_primary_group_display_name = date_str_group

        if current_primary_group_id_val is None:  # First item
            current_primary_group_id_val = item_primary_group_id_val
            current_primary_group_display_name = item_primary_group_display_name

        if item_primary_group_id_val != current_primary_group_id_val:  # Primary group has changed
            table.add_row([
                colored(f"{group_label_prefix} {current_primary_group_display_name}",
                        'magenta', attrs=['bold']),
                "", "", "", "", "", "",  # Span across other columns
                colored(f"{current_group_total_cost:.4f} ¢",
                        'magenta', attrs=["bold"])
            ])
            table.add_divider()
            current_group_total_cost = 0.0  # Reset for new group
            current_primary_group_id_val = item_primary_group_id_val
            current_primary_group_display_name = item_primary_group_display_name

        # Extract details for the current row
        date_str_row = usage.get('date', 'unknown_date')
        project_id_row = usage.get('project_id', 'unknown_project')
        project_name_disp_row = project_names.get(
            project_id_row, project_id_row)
        model_row = usage.get('model', 'unknown_model')
        api_key_name_disp_row = usage.get('api_key_name', 'Unknown Key')

        costs = usage.get('costs', {})
        input_cost = costs.get('input_cost', 0.0)
        output_cost = costs.get('output_cost', 0.0)
        cached_cost = costs.get('cached_input_cost', 0.0)
        minute_cost = costs.get('minute_cost', 0.0)

        current_row_total = input_cost + output_cost + cached_cost + minute_cost
        current_group_total_cost += current_row_total
        grand_total_cost += current_row_total

        table.add_row([
            colored(date_str_row, 'cyan'),
            colored(project_name_disp_row, 'blue'),
            colored(model_row, 'green'),
            colored(api_key_name_disp_row, 'yellow'),
            colored(f"{input_cost:.4f}", 'red'),
            colored(f"{output_cost:.4f}", 'red'),
            colored(f"{cached_cost:.4f}", 'red'),
            colored(f"{current_row_total:.4f}", color="red", attrs=["bold"])
        ])

    # After the loop, add the total for the very last processed primary group
    if sorted_usage_details:
        table.add_row([
            colored(f"{group_label_prefix} {current_primary_group_display_name}",
                    'magenta', attrs=['bold']),
            "", "", "", "", "", "",
            colored(f"{current_group_total_cost:.4f} ¢",
                    'magenta', attrs=["bold"])
        ])
        table.add_divider()

    # Grand total row
    table.add_row([
        colored("GRAND TOTAL", 'blue', attrs=['bold']),
        "", "", "", "", "", "",
        colored(f"{grand_total_cost:.4f} ¢", 'blue', attrs=["bold"])
    ])
    print(table)


def main() -> None:
    '''
    Main function to fetch and display OpenAI API usage data for specific projects
    based on command-line arguments, date range, and grouping preference.
    '''
    parser = argparse.ArgumentParser(
        description="Fetch and display OpenAI API usage data per project.",
        # Shows default values in help
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-l", "--list-projects", action="store_true", help="List available projects."
    )
    parser.add_argument(
        "-p", "--projects", nargs="+",
        help="Specify one or more project IDs to display usage for. "
        "If not specified, usage for all available projects will be displayed."
    )
    parser.add_argument(
        "-sd", "--start-date",
        type=str,
        help="Start date for usage data (YYYY-MM-DD).",
        default=None  # Default handled in fetch_usage_details to be start of current month
    )
    parser.add_argument(
        "-ed", "--end-date",
        type=str,
        help="End date for usage data (YYYY-MM-DD).",
        default=None  # Default handled in fetch_usage_details to be end of current month
    )
    parser.add_argument(
        "-gb", "--group-by",
        type=str,
        nargs='+',
        choices=["day", "project", "key", "model"],
        default=["day"],
        help="Criteria to group and sort results (e.g., project day). Order matters for sorting. "
             "Subtotals are shown for the first criterion. "
             "Choices: 'day', 'project', 'key', 'model'.",
    )

    args = parser.parse_args()

    api_key = os.getenv("OPENAI_ADMIN_API_KEY")
    if not api_key:
        print("Error: OPENAI_ADMIN_API_KEY environment variable not set.",
              file=sys.stderr)
        return

    if args.list_projects:
        try:
            list_projects(api_key)
        except Exception as e:
            print(f"Error listing projects: {e}", file=sys.stderr)
        return

    # Date validation
    parsed_start_date = args.start_date
    if parsed_start_date:
        try:
            datetime.strptime(parsed_start_date, '%Y-%m-%d')
        except ValueError:
            print(
                "Error: Invalid start-date format. Please use YYYY-MM-DD.", file=sys.stderr)
            return

    parsed_end_date = args.end_date
    if parsed_end_date:
        try:
            datetime.strptime(parsed_end_date, '%Y-%m-%d')
        except ValueError:
            print("Error: Invalid end-date format. Please use YYYY-MM-DD.",
                  file=sys.stderr)
            return

    if parsed_start_date and parsed_end_date:
        if datetime.strptime(parsed_start_date, '%Y-%m-%d') > datetime.strptime(parsed_end_date, '%Y-%m-%d'):
            print("Error: Start date cannot be after end date.", file=sys.stderr)
            return

    project_ids_to_fetch = []
    if args.projects:
        project_ids_to_fetch = args.projects
    else:
        # If no projects are specified, fetch all available project IDs
        print("No projects specified with -p/--projects. Fetching usage for all available projects...")
        try:
            all_available_projects = list_projects(api_key, return_list=True)
            if all_available_projects:
                project_ids_to_fetch = [p['id'] for p in all_available_projects if p.get('id')]
                if not project_ids_to_fetch:
                    print("No project IDs found after listing all projects.", file=sys.stderr)
                    return
                print(f"Found {len(project_ids_to_fetch)} projects to process.")
            else:
                print("No projects found to process.", file=sys.stderr)
                return
        except Exception as e:
            print(f"Error fetching list of all projects: {e}", file=sys.stderr)
            return

    if not project_ids_to_fetch:  # Check if the list is empty after logic
        print("Error: No project IDs to process. Please specify projects with -p/--projects or ensure projects are available.", file=sys.stderr)
        # parser.print_help() # Avoid printing help here as it might be confusing if it was an API error
        return

    all_projects_usage_details = []
    project_names_map = {}

    try:
        projects_list_data = list_projects(
            api_key, return_list=True)  # Renamed to avoid conflict
        if projects_list_data:
            for project_info in projects_list_data:
                project_names_map[project_info.get('id')] = project_info.get(
                    'name', 'Unknown Project')
    except Exception as e:
        print(
            f"Warning: Could not fetch project names: {e}. Project IDs will be used.", file=sys.stderr)

    for project_id in project_ids_to_fetch:
        if projects_list_data and project_id not in project_names_map:
            print(
                f"Warning: Project ID '{project_id}' not found in your list of available projects. Attempting to fetch anyway.", file=sys.stderr)
        # elif not projects_list_data and project_id != DEFAULT_PROJECT_ID and DEFAULT_PROJECT_ID is not None:
        #     print(
        #         f"Warning: Cannot verify Project ID '{project_id}' as project list could not be fetched. Attempting to fetch anyway.", file=sys.stderr)
        # The above warning might be less relevant now if we are iterating through fetched project_ids or user-provided ones.
        # The check for project_id in project_names_map already covers if it was found.

        print(
            f"\nFetching usage for project: {project_names_map.get(project_id, project_id)} ({project_id})")
        try:
            usage_data = fetch_project_usage(
                project_id, api_key, parsed_start_date, parsed_end_date)
            for date_str, usages_on_date in usage_data.items():
                for usage_detail in usages_on_date:
                    # Ensure date is at the top level for sorting
                    usage_detail['date'] = date_str
                    # Ensure project_id is at the top level
                    usage_detail['project_id'] = project_id
                    all_projects_usage_details.append(usage_detail)
        except ValueError as ve:
            print(
                f"Configuration error for project {project_id}: {ve}", file=sys.stderr)
        except Exception as e:
            print(
                f"Error fetching usage for project {project_id}: {e}", file=sys.stderr)

    if all_projects_usage_details:
        display_results(all_projects_usage_details,
                        project_names_map, args.group_by)
    else:
        print("No usage data fetched for the specified projects, or an error occurred for all of them.")


if __name__ == "__main__":
    main()
