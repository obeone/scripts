"""
Pricing cache management and cost calculation.

Manages a local cache of OpenAI model pricing data, sourced from litellm's
community-maintained pricing database. All prices are stored in USD per 1M tokens.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

CACHE_FILENAME = "pricing.json"
CACHE_MAX_AGE_DAYS = 30

# Minimal fallback pricing for common models ($/1M tokens) used when both
# cache and network are unavailable.
FALLBACK_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached_input": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached_input": 0.075},
    "gpt-4.1": {"input": 2.00, "output": 8.00, "cached_input": 0.50},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60, "cached_input": 0.10},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40, "cached_input": 0.025},
    "o3": {"input": 2.00, "output": 8.00, "cached_input": 0.50},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o4-mini": {"input": 1.10, "output": 4.40, "cached_input": 0.275},
}


def _get_cache_dir() -> Path:
    """
    Return the cache directory path following XDG Base Directory spec.

    Returns
    -------
    Path
        The path to the cache directory. Defaults to ~/.cache/openai-usage
        when XDG_CACHE_HOME is not set.
    """
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        base = Path(xdg_cache)
    else:
        base = Path.home() / ".cache"
    return base / "openai-usage"


def _get_cache_path() -> Path:
    """
    Return the full path to the pricing cache file.

    Returns
    -------
    Path
        The path to pricing.json inside the cache directory.
    """
    return _get_cache_dir() / CACHE_FILENAME


def _convert_litellm_entry(entry: dict) -> dict:
    """
    Convert a single litellm model entry to our local pricing format.

    Litellm stores costs per-token (e.g. 2.5e-06 $/token). We convert
    to $/1M tokens by multiplying by 1_000_000.

    Parameters
    ----------
    entry : dict
        A litellm model pricing entry.

    Returns
    -------
    dict
        Pricing in $/1M tokens with keys: input, output, cached_input.
        Only keys with non-zero values are included.
    """
    result = {}

    input_cost = entry.get("input_cost_per_token")
    if input_cost is not None and input_cost > 0:
        result["input"] = round(input_cost * 1_000_000, 6)

    output_cost = entry.get("output_cost_per_token")
    if output_cost is not None and output_cost > 0:
        result["output"] = round(output_cost * 1_000_000, 6)

    cached_cost = entry.get("cache_read_input_token_cost")
    if cached_cost is not None and cached_cost > 0:
        result["cached_input"] = round(cached_cost * 1_000_000, 6)

    return result


def fetch_litellm_pricing() -> dict:
    """
    Fetch pricing data from litellm's GitHub repository.

    Downloads the full model pricing JSON, filters for OpenAI models
    (litellm_provider == "openai", mode == "chat"), and converts to
    our local format.

    Returns
    -------
    dict
        A dictionary mapping model names to their pricing dicts.

    Raises
    ------
    requests.RequestException
        If the HTTP request fails.
    json.JSONDecodeError
        If the response is not valid JSON.
    """
    logger.info("Fetching pricing data from litellm...")
    response = requests.get(LITELLM_PRICING_URL, timeout=30)
    response.raise_for_status()
    raw_data = response.json()

    models = {}
    for model_name, entry in raw_data.items():
        if not isinstance(entry, dict):
            continue
        provider = entry.get("litellm_provider", "")
        if provider != "openai":
            continue
        mode = entry.get("mode", "")
        if mode != "chat":
            continue

        converted = _convert_litellm_entry(entry)
        if converted:
            models[model_name] = converted

    logger.info("Fetched pricing for %d OpenAI models.", len(models))
    return models


def save_cache(models: dict) -> Path:
    """
    Write pricing data to the cache file.

    Parameters
    ----------
    models : dict
        The pricing data to cache.

    Returns
    -------
    Path
        The path to the written cache file.
    """
    cache_path = _get_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    cache_data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "litellm/model_prices_and_context_window.json",
        "models": models,
    }

    cache_path.write_text(json.dumps(cache_data, indent=2) + "\n", encoding="utf-8")
    logger.info("Pricing cache written to %s", cache_path)
    return cache_path


def load_cache() -> dict | None:
    """
    Load pricing data from the local cache file.

    If the cache is older than CACHE_MAX_AGE_DAYS, prints a warning to stderr
    but still returns the data.

    Returns
    -------
    dict or None
        The cached pricing data dict (with keys: updated_at, source, models),
        or None if the cache does not exist or is unreadable.
    """
    cache_path = _get_cache_path()
    if not cache_path.exists():
        logger.debug("No pricing cache found at %s", cache_path)
        return None

    try:
        cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read pricing cache: %s", exc)
        return None

    # Check staleness
    updated_at_str = cache_data.get("updated_at")
    if updated_at_str:
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            age_days = (datetime.now(timezone.utc) - updated_at).days
            if age_days > CACHE_MAX_AGE_DAYS:
                print(
                    f"Warning: Pricing cache is {age_days} days old. "
                    f"Run 'openai-usage --update-pricing' to refresh.",
                    file=sys.stderr,
                )
        except ValueError:
            pass

    return cache_data


def load_pricing() -> dict:
    """
    Load pricing data with auto-fetch and fallback.

    Attempts to load from cache. If no cache exists, fetches from litellm
    and writes the cache. If fetch fails, returns fallback hardcoded pricing.

    Returns
    -------
    dict
        A dictionary mapping model names to their pricing dicts.
    """
    cache_data = load_cache()
    if cache_data and cache_data.get("models"):
        return cache_data["models"]

    # No cache — try auto-fetch
    try:
        print("No pricing cache found. Fetching from litellm...", file=sys.stderr)
        models = fetch_litellm_pricing()
        save_cache(models)
        return models
    except Exception as exc:
        print(
            f"Warning: Failed to fetch pricing data: {exc}. "
            f"Using minimal fallback pricing.",
            file=sys.stderr,
        )
        return FALLBACK_PRICING.copy()


def update_pricing() -> None:
    """
    Fetch fresh pricing from litellm and update the local cache.

    Prints status messages to stderr. Intended to be called by the
    --update-pricing CLI command.

    Raises
    ------
    Exception
        Propagates any exception from fetch or save operations.
    """
    models = fetch_litellm_pricing()
    cache_path = save_cache(models)
    print(
        f"Pricing updated: {len(models)} models cached at {cache_path}",
        file=sys.stderr,
    )


def get_cache_info() -> str:
    """
    Return a human-readable summary of the pricing cache status.

    Returns
    -------
    str
        A multi-line string with cache path, last update date, and model count.
    """
    cache_path = _get_cache_path()
    if not cache_path.exists():
        return f"Cache path: {cache_path}\nStatus: No cache file found."

    try:
        cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return f"Cache path: {cache_path}\nStatus: Cache file is corrupt."

    updated_at = cache_data.get("updated_at", "unknown")
    model_count = len(cache_data.get("models", {}))
    source = cache_data.get("source", "unknown")
    return (
        f"Cache path: {cache_path}\n"
        f"Last updated: {updated_at}\n"
        f"Source: {source}\n"
        f"Models: {model_count}"
    )


def calculate_costs(usage: dict, model_name: str, pricing: dict) -> dict:
    """
    Calculate cost in dollars based on usage data and pricing for a model.

    Parameters
    ----------
    usage : dict
        Usage data containing keys like 'input_tokens', 'output_tokens',
        'cached_input_tokens'.
    model_name : str
        The model name to look up in the pricing dict.
    pricing : dict
        The full pricing dictionary (model_name -> price_dict).

    Returns
    -------
    dict
        Calculated costs in dollars for each metric (input_cost, output_cost,
        cached_input_cost).
    """
    model_pricing = pricing.get(model_name)
    if not model_pricing:
        if model_name and model_name.lower() != "unknown":
            print(
                f"Warning: Pricing for model '{model_name}' not found. "
                f"Costs will be $0.",
                file=sys.stderr,
            )
        return {}

    costs = {}

    # Token costs: price is $/1M tokens
    if "input_tokens" in usage and "input" in model_pricing:
        costs["input_cost"] = (usage["input_tokens"] / 1_000_000) * model_pricing["input"]
    if "output_tokens" in usage and "output" in model_pricing:
        costs["output_cost"] = (usage["output_tokens"] / 1_000_000) * model_pricing["output"]
    if "cached_input_tokens" in usage and "cached_input" in model_pricing:
        costs["cached_input_cost"] = (
            usage["cached_input_tokens"] / 1_000_000
        ) * model_pricing["cached_input"]

    return costs
