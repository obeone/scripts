"""
Usage data display with formatted tables.
"""

from prettytable import PrettyTable
from termcolor import colored


def get_sort_key_tuple(
    usage_item: dict,
    criteria_list: list[str],
    project_names_map: dict,
) -> tuple:
    """
    Generate a sort key for a usage item based on specified criteria.

    Parameters
    ----------
    usage_item : dict
        The usage data dictionary.
    criteria_list : list[str]
        User-specified sort criteria (e.g., ['project', 'day']).
    project_names_map : dict
        A mapping of project IDs to names.

    Returns
    -------
    tuple
        A tuple of values suitable for use as a sort key.
    """
    project_id_val = usage_item.get("project_id", "")
    project_name_val = project_names_map.get(project_id_val, project_id_val)
    date_val = usage_item.get("date", "")
    key_name_val = usage_item.get("api_key_name", "")
    model_val = usage_item.get("model", "")

    criteria_to_value_map = {
        "project": project_name_val,
        "day": date_val,
        "key": key_name_val,
        "model": model_val,
    }

    key_parts = []
    for criterion in criteria_list:
        key_parts.append(criteria_to_value_map.get(criterion.lower(), ""))

    all_possible_criteria = ["project", "day", "key", "model"]
    for crit in all_possible_criteria:
        if crit not in criteria_list:
            key_parts.append(criteria_to_value_map[crit])

    return tuple(key_parts)


def display_results(
    all_usage_details: list,
    project_names: dict,
    group_by_criteria: list[str],
) -> None:
    """
    Display usage data in a formatted table, grouped and sorted as specified.

    Parameters
    ----------
    all_usage_details : list
        A list of dictionaries containing usage details.
    project_names : dict
        A dictionary mapping project IDs to project names.
    group_by_criteria : list[str]
        The criteria for grouping and sorting results.
    """
    if not all_usage_details:
        print("No usage data to display.")
        return

    table = PrettyTable()
    table.field_names = [
        "Date",
        "Project",
        "Model",
        "API Key",
        "Input ($)",
        "Output ($)",
        "Cached ($)",
        "Total ($)",
    ]
    for col in ("Input ($)", "Output ($)", "Cached ($)", "Total ($)"):
        table.align[col] = "r"

    grand_total_cost = 0.0

    sorted_usage_details = sorted(
        all_usage_details,
        key=lambda x: get_sort_key_tuple(x, group_by_criteria, project_names),
    )

    primary_group_criterion = (
        group_by_criteria[0] if group_by_criteria else "day"
    )
    group_label_prefix_map = {
        "project": "Total for Project",
        "day": "Total for day",
        "key": "Total for API Key",
        "model": "Total for Model",
    }
    group_label_prefix = group_label_prefix_map.get(
        primary_group_criterion, f"Total for {primary_group_criterion}"
    )

    current_primary_group_id_val = None
    current_primary_group_display_name = ""
    current_group_total_cost = 0.0

    for usage in sorted_usage_details:
        if primary_group_criterion == "project":
            project_id = usage.get("project_id", "unknown_project")
            item_primary_group_id_val = project_id
            item_primary_group_display_name = project_names.get(
                project_id, project_id
            )
        elif primary_group_criterion == "key":
            api_key_name = usage.get("api_key_name", "Unknown")
            item_primary_group_id_val = api_key_name
            item_primary_group_display_name = api_key_name
        elif primary_group_criterion == "model":
            model_name = usage.get("model", "Unknown Model")
            item_primary_group_id_val = model_name
            item_primary_group_display_name = model_name
        else:
            date_str_group = usage.get("date", "unknown_date")
            item_primary_group_id_val = date_str_group
            item_primary_group_display_name = date_str_group

        if current_primary_group_id_val is None:
            current_primary_group_id_val = item_primary_group_id_val
            current_primary_group_display_name = (
                item_primary_group_display_name
            )

        if item_primary_group_id_val != current_primary_group_id_val:
            table.add_row([
                colored(
                    f"{group_label_prefix} "
                    f"{current_primary_group_display_name}",
                    "magenta",
                    attrs=["bold"],
                ),
                "",
                "",
                "",
                "",
                "",
                "",
                colored(
                    f"${current_group_total_cost:.4f}",
                    "magenta",
                    attrs=["bold"],
                ),
            ])
            table.add_divider()
            current_group_total_cost = 0.0
            current_primary_group_id_val = item_primary_group_id_val
            current_primary_group_display_name = (
                item_primary_group_display_name
            )

        date_str_row = usage.get("date", "unknown_date")
        project_id_row = usage.get("project_id", "unknown_project")
        project_name_disp_row = project_names.get(
            project_id_row, project_id_row
        )
        model_row = usage.get("model", "unknown_model")
        api_key_name_disp_row = usage.get("api_key_name", "Unknown Key")

        costs = usage.get("costs", {})
        input_cost = costs.get("input_cost", 0.0)
        output_cost = costs.get("output_cost", 0.0)
        cached_cost = costs.get("cached_input_cost", 0.0)

        current_row_total = input_cost + output_cost + cached_cost
        current_group_total_cost += current_row_total
        grand_total_cost += current_row_total

        table.add_row([
            colored(date_str_row, "cyan"),
            colored(project_name_disp_row, "blue"),
            colored(model_row, "green"),
            colored(api_key_name_disp_row, "yellow"),
            colored(f"{input_cost:.4f}", "red"),
            colored(f"{output_cost:.4f}", "red"),
            colored(f"{cached_cost:.4f}", "red"),
            colored(f"{current_row_total:.4f}", color="red", attrs=["bold"]),
        ])

    if sorted_usage_details:
        table.add_row([
            colored(
                f"{group_label_prefix} "
                f"{current_primary_group_display_name}",
                "magenta",
                attrs=["bold"],
            ),
            "",
            "",
            "",
            "",
            "",
            "",
            colored(
                f"${current_group_total_cost:.4f}",
                "magenta",
                attrs=["bold"],
            ),
        ])
        table.add_divider()

    table.add_row([
        colored("GRAND TOTAL", "blue", attrs=["bold"]),
        "",
        "",
        "",
        "",
        "",
        "",
        colored(f"${grand_total_cost:.4f}", "blue", attrs=["bold"]),
    ])
    print(table)
