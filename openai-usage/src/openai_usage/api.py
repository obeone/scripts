"""
OpenAI API client for fetching projects, API keys, and usage data.
"""

import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

API_BASE_URL_PROJECTS = "https://api.openai.com/v1/organization/projects"
API_BASE_URL_PROJECT_API_KEYS = f"{API_BASE_URL_PROJECTS}/{{project_id}}/api_keys"
API_BASE_URL_USAGE_COMPLETIONS = (
    "https://api.openai.com/v1/organization/usage/completions"
)


def fetch_all_api_keys(project_id: str, api_key: str) -> dict:
    """
    Fetch all API keys for a given project, handling pagination.

    Parameters
    ----------
    project_id : str
        The ID of the project to query.
    api_key : str
        The admin API key for authentication.

    Returns
    -------
    dict
        A dictionary mapping API key IDs to their names.

    Raises
    ------
    Exception
        If the API request fails or the JSON response is invalid.
    """
    url = API_BASE_URL_PROJECT_API_KEYS.format(project_id=project_id)
    headers = {"Authorization": f"Bearer {api_key}"}
    api_keys_map = {}
    params = {"limit": 100}
    current_request_url = url

    while current_request_url:
        try:
            active_params = params if current_request_url == url else None
            response = requests.get(
                current_request_url, headers=headers, params=active_params
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as http_err:
            error_message = (
                f"HTTP error fetching API keys: {http_err} - "
                f"Response: {response.text}"
            )
            logger.debug("Failed URL: %s", response.url)
            logger.debug("Failed PARAMS: %s", active_params)
            raise Exception(error_message) from http_err
        except requests.exceptions.JSONDecodeError as json_err:
            raise Exception(
                f"Failed to decode JSON response for API keys: {response.text}"
            ) from json_err
        except requests.exceptions.RequestException as req_err:
            raise Exception(
                f"Request failed while fetching API keys: {req_err}"
            ) from req_err

        for key_data in data.get("data", []):
            api_keys_map[key_data["id"]] = key_data.get(
                "name", f"Unnamed Key ({key_data['id'][:4]}...)"
            )

        next_cursor = data.get("pagination", {}).get("next_cursor")
        if not next_cursor:
            break

        current_request_url = url
        params = {"limit": 100, "cursor": next_cursor}

    return api_keys_map


def fetch_usage_details(
    project_id: str,
    api_key: str,
    api_keys_map: dict,
    pricing: dict,
    start_date_str: str | None = None,
    end_date_str: str | None = None,
) -> dict:
    """
    Fetch usage details for a project and date range, handling pagination.

    Parameters
    ----------
    project_id : str
        The project ID to query usage for.
    api_key : str
        The admin API key for authentication.
    api_keys_map : dict
        A dictionary mapping API key IDs to their names.
    pricing : dict
        The pricing dictionary (model_name -> price_dict).
    start_date_str : str or None
        Optional start date in 'YYYY-MM-DD' format.
    end_date_str : str or None
        Optional end date in 'YYYY-MM-DD' format.

    Returns
    -------
    dict
        A dictionary mapping dates ('YYYY-MM-DD') to lists of usage details.

    Raises
    ------
    Exception
        If an API request fails or date parsing fails.
    ValueError
        If the start date is after the end date.
    """
    from openai_usage.pricing import calculate_costs

    headers = {"Authorization": f"Bearer {api_key}"}
    now = datetime.now(timezone.utc)

    # Determine start date
    if not start_date_str:
        start_time_dt = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        try:
            start_time_dt = datetime.strptime(
                start_date_str, "%Y-%m-%d"
            ).replace(tzinfo=timezone.utc)
        except ValueError as ve:
            raise Exception(f"Invalid start date format: {ve}") from ve

    # Determine end date
    if not end_date_str:
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1)
        else:
            next_month = now.replace(month=now.month + 1, day=1)
        end_time_dt = (next_month - timedelta(seconds=1)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    else:
        try:
            end_time_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
                hour=23,
                minute=59,
                second=59,
                microsecond=999999,
                tzinfo=timezone.utc,
            )
        except ValueError as ve:
            raise Exception(f"Invalid end date format: {ve}") from ve

    if start_time_dt > end_time_dt:
        raise ValueError("Start date cannot be after end date.")

    start_time_ts = int(start_time_dt.timestamp())
    end_time_ts = int(end_time_dt.timestamp())

    usages_by_date = {}
    current_params = {
        "project_id": project_id,
        "start_time": start_time_ts,
        "end_time": end_time_ts,
        "group_by": "api_key_id,model",
        "bucket_width": "1d",
    }
    current_url = API_BASE_URL_USAGE_COMPLETIONS

    while current_url:
        try:
            response = requests.get(
                current_url, headers=headers, params=current_params
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as http_err:
            error_message = (
                f"HTTP error fetching usage data: {http_err} - "
                f"Response: {response.text}\n"
                f"URL: {response.url}\nParams: {current_params}"
            )
            raise Exception(error_message) from http_err
        except requests.exceptions.JSONDecodeError as json_err:
            raise Exception(
                f"Failed to decode JSON response for usage data: "
                f"{response.text}"
            ) from json_err
        except requests.exceptions.RequestException as req_err:
            raise Exception(
                f"Request failed while fetching usage data: {req_err}"
            ) from req_err

        for bucket in data.get("data", []):
            bucket_start_time_str = datetime.fromtimestamp(
                bucket.get("start_time"), timezone.utc
            ).strftime("%Y-%m-%d")
            if bucket_start_time_str not in usages_by_date:
                usages_by_date[bucket_start_time_str] = []

            for result in bucket.get("results", []):
                key_id = result.get("api_key_id")
                if key_id not in api_keys_map:
                    continue
                result["api_key_name"] = api_keys_map[key_id]
                model_name = result.get("model", "unknown")
                result["costs"] = calculate_costs(result, model_name, pricing)
                usages_by_date[bucket_start_time_str].append(result)

        next_page_info = data.get("next_page")
        if not next_page_info:
            break

        if next_page_info.startswith("http"):
            current_url = next_page_info
            current_params = None
        else:
            current_params = {
                "project_id": project_id,
                "start_time": start_time_ts,
                "end_time": end_time_ts,
                "group_by": "api_key_id,model",
                "bucket_width": "1d",
                "page": next_page_info,
            }
            current_url = API_BASE_URL_USAGE_COMPLETIONS

    return usages_by_date


def fetch_project_usage(
    project_id: str,
    api_key: str,
    pricing: dict,
    start_date_str: str | None = None,
    end_date_str: str | None = None,
) -> dict:
    """
    Fetch all usage details for a single project.

    Parameters
    ----------
    project_id : str
        The project ID to query usage for.
    api_key : str
        The admin API key for authentication.
    pricing : dict
        The pricing dictionary (model_name -> price_dict).
    start_date_str : str or None
        Optional start date in 'YYYY-MM-DD' format.
    end_date_str : str or None
        Optional end date in 'YYYY-MM-DD' format.

    Returns
    -------
    dict
        A dictionary mapping dates to usage details.
    """
    api_keys_map = fetch_all_api_keys(project_id, api_key)
    return fetch_usage_details(
        project_id, api_key, api_keys_map, pricing, start_date_str, end_date_str
    )


def list_projects(api_key: str, return_list: bool = False) -> list | None:
    """
    Fetch and display a list of available OpenAI projects.

    Parameters
    ----------
    api_key : str
        The admin API key for authentication.
    return_list : bool
        If True, returns the list instead of printing. Defaults to False.

    Returns
    -------
    list or None
        A list of project dicts if return_list is True, otherwise None.

    Raises
    ------
    Exception
        If the API request fails or the JSON response is invalid.
    """
    all_projects = []
    current_params = {"limit": 100}
    headers = {"Authorization": f"Bearer {api_key}"}
    current_url = API_BASE_URL_PROJECTS

    try:
        while current_url:
            response = requests.get(
                current_url, headers=headers, params=current_params
            )
            response.raise_for_status()
            data = response.json()

            projects_page = data.get("data", [])
            all_projects.extend(projects_page)

            if data.get("has_more") and projects_page:
                last_id = projects_page[-1].get("id")
                if not last_id:
                    break
                current_params = {"limit": 100, "after": last_id}
                current_url = API_BASE_URL_PROJECTS
            else:
                break

        if return_list:
            return all_projects

        if not all_projects:
            print("No projects found.")
            return None
        print("Available Projects:")
        for project in all_projects:
            print(f"- ID: {project.get('id')}, Name: {project.get('name')}")
        return None
    except requests.exceptions.HTTPError as http_err:
        error_message = (
            f"HTTP error fetching projects: {http_err} - "
            f"Response: {response.text}"
        )
        raise Exception(error_message) from http_err
    except requests.exceptions.JSONDecodeError as json_err:
        raise Exception(
            f"Failed to decode JSON response for projects: {response.text}"
        ) from json_err
    except requests.exceptions.RequestException as req_err:
        raise Exception(
            f"Request failed while fetching projects: {req_err}"
        ) from req_err
