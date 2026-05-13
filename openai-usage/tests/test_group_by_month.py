from __future__ import annotations

from openai_usage.cli import _build_parser
from openai_usage.display import display_results


def test_group_by_accepts_month() -> None:
    args = _build_parser().parse_args(["--group-by", "month"])

    assert args.group_by == ["month"]


def test_display_results_shows_month_without_daily_dates(capsys) -> None:
    usage_details = [
        {
            "date": "2026-01-03",
            "project_id": "proj_1",
            "model": "gpt-test",
            "api_key_name": "key-a",
            "costs": {
                "input_cost": 1.0,
                "output_cost": 2.0,
                "cached_input_cost": 0.5,
            },
        },
        {
            "date": "2026-01-14",
            "project_id": "proj_1",
            "model": "gpt-test",
            "api_key_name": "key-a",
            "costs": {
                "input_cost": 0.5,
                "output_cost": 1.0,
                "cached_input_cost": 0.0,
            },
        },
    ]

    display_results(usage_details, {"proj_1": "Project One"}, ["month"])

    output = capsys.readouterr().out
    assert "2026-01" in output
    assert "Total for month 2026-01" in output
    assert "2026-01-03" not in output
    assert "2026-01-14" not in output
