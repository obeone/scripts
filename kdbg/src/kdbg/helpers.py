# -*- coding: utf-8 -*-
"""
General helper functions for command execution, user interaction, and cleanup.

This module provides utilities for:
- Checking the availability of system commands.
- Running external shell commands and capturing their output.
- Facilitating interactive user selection using fzf.
- Registering and executing cleanup tasks upon script exit.
"""

import atexit
import logging
import shutil
import subprocess
import sys
from typing import List, Tuple, Any, Dict, Optional, Union

from iterfzf import iterfzf

# Initialize logger for the module
logger = logging.getLogger(__name__)

# Global state to store cleanup tasks
cleanup_tasks: List[Tuple[Any, Tuple[Any, ...], Dict[str, Any]]] = []

def check_command_availability(command: str) -> None:
    """
    Checks if a specified command is available in the system's PATH.

    If the command is not found, an error message is logged, and the script exits.

    Args:
        command: The name of the command to check (e.g., "kubectl", "fzf").

    Raises:
        SystemExit: If the required command is not found in the system's PATH.
    """
    if not shutil.which(command):
        logger.error("Required command not found: '%s'. Please install it and ensure it's in your PATH.", command)
        sys.exit(1)

def run_command(command: List[str], capture_output: bool = False, **kwargs: Any) -> Tuple[int, str, str]:
    """
    Executes a shell command, with options to capture output or run interactively.

    Args:
        command: A list of strings representing the command and its arguments.
        capture_output: If True, capture stdout and stderr. If False, the
                        subprocess inherits stdin, stdout, and stderr from the parent,
                        making it suitable for interactive commands.
        **kwargs: Additional keyword arguments to pass to `subprocess.run`.

    Returns:
        A tuple containing the exit code, stdout, and stderr.
        Stdout and stderr will be empty strings if `capture_output` is False.
    """
    logger.debug("Running command: %s", " ".join(command))
    try:
        # For interactive commands, we should not capture the output streams.
        # Instead, we let the subprocess inherit the parent's stdin, stdout, and stderr.
        if capture_output:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                **kwargs
            )
            stdout, stderr = process.stdout, process.stderr
        else:
            # For interactive sessions, allow the subprocess to use the parent's TTY
            process = subprocess.run(
                command,
                check=False,
                **kwargs
            )
            stdout, stderr = "", "" # Output was not captured

        logger.debug("Command finished with exit code %d", process.returncode)
        if stdout:
            logger.debug("stdout:\n%s", stdout)
        if stderr:
            logger.debug("stderr:\n%s", stderr)
            
        return process.returncode, stdout, stderr

    except FileNotFoundError:
        logger.error("Command not found: %s", command[0])
        sys.exit(1)
    except Exception as e:
        logger.error("An unexpected error occurred while running command '%s': %s", " ".join(command), e, exc_info=True)
        sys.exit(1)

def fzf_select(items: List[str], prompt: str) -> Optional[str]:
    """
    Uses `iterfzf` to present a list of items for interactive user selection.

    This function provides a fuzzy-finding interface for the user to select
    a single item from a given list.

    Args:
        items: A list of strings from which the user can select.
        prompt: The prompt message to display to the user in fzf.

    Returns:
        The selected item as a string, or None if no item was selected or an error occurred.
    """
    if not items:
        logger.warning("No items to select from for: %s", prompt)
        return None
    
    try:
        # iterfzf returns a string for single selection or None if cancelled
        selection = iterfzf(items, prompt=f"{prompt}> ")
        return str(selection) if selection is not None else None
    except Exception as e:
        logger.error("fzf selection failed: %s", e, exc_info=True)
        return None

def register_cleanup(func: Any, *args: Any, **kwargs: Any) -> None:
    """
    Registers a function to be called automatically upon script exit.

    Cleanup tasks are stored and executed in reverse order of registration
    when the script terminates.

    Args:
        func: The function to register for cleanup.
        *args: Positional arguments to pass to the cleanup function.
        **kwargs: Keyword arguments to pass to the cleanup function.
    """
    logger.debug("Registering cleanup task: %s", func.__name__)
    cleanup_tasks.append((func, args, kwargs))

def run_cleanup() -> None:
    """
    Executes all registered cleanup tasks.

    This function iterates through the `cleanup_tasks` list in reverse order
    and calls each registered function with its associated arguments.
    Errors during cleanup tasks are logged but do not prevent other tasks from running.
    """
    if cleanup_tasks:
        logger.info("Running cleanup tasks...")
    for func, args, kwargs in reversed(cleanup_tasks):
        try:
            logger.debug("Executing cleanup task: %s", func.__name__)
            func(*args, **kwargs)
        except Exception as e:
            logger.error("Error during cleanup task %s: %s", func.__name__, e, exc_info=True)

# Register the cleanup handler to be called automatically on script exit
atexit.register(run_cleanup)