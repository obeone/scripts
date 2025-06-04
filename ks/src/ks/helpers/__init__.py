import atexit
import logging
import shutil
import subprocess
import sys
from typing import List, Tuple, Any, Dict, Optional

logger = logging.getLogger(__name__)

cleanup_tasks: List[Tuple[Any, Tuple, Dict]] = []


def run_command(
    command: List[str],
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    input_data: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Execute an external command and return the CompletedProcess."""
    logger.debug("Running external command: %s", " ".join(command))
    try:
        result = subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=text,
            input=input_data,
        )
        if capture_output and result.stderr and result.stderr.strip() and logger.isEnabledFor(logging.DEBUG):
            logger.debug("External command stderr: %s", result.stderr.strip())
        if capture_output and result.stdout and logger.isEnabledFor(logging.DEBUG):
            logger.debug("External command stdout: %s", result.stdout.strip())
        return result
    except FileNotFoundError:
        logger.error("Command not found: %s. Please ensure it is installed and in your PATH.", command[0])
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        stderr_info = f" Stderr: {e.stderr.strip()}" if e.stderr and capture_output else ""
        logger.error("External command failed: %s (Exit code: %s).%s", " ".join(command), e.returncode, stderr_info)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Unexpected error running external command %s: %s", " ".join(command), e)
        sys.exit(1)


def fzf_select(items: List[str], prompt: str) -> Optional[str]:
    """Use fzf to allow the user to select an item from a list."""
    if not items:
        return None
    if not shutil.which("fzf"):
        logger.error("'fzf' command not found. Please install fzf to use this feature.")
        sys.exit(1)
    try:
        fzf_cmd = ["fzf", "--height", "20%", "--prompt", prompt]
        input_str = "\n".join(items)
        process = subprocess.run(fzf_cmd, input=input_str, capture_output=True, text=True, check=False)
        if process.returncode == 0:
            return process.stdout.strip()
        if process.returncode == 130:
            logger.info("Selection cancelled by user (fzf exit code 130).")
            return None
        if process.returncode == 1:
            logger.info("No item selected or matched in fzf (fzf exit code 1).")
            return None
        logger.error(
            "fzf exited with unexpected code %s. Stderr: %s",
            process.returncode,
            process.stderr.strip(),
        )
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Unexpected error during fzf execution: %s", e)
        sys.exit(1)


def register_cleanup(func, *args, **kwargs) -> None:
    """Register a cleanup function to be executed on exit."""
    cleanup_tasks.append((func, args, kwargs))


def run_cleanup() -> None:
    """Run all registered cleanup tasks."""
    logger.debug("Running cleanup tasks...")
    for func, args, kwargs in reversed(cleanup_tasks):
        try:
            func(*args, **kwargs)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Error during cleanup task %s: %s", getattr(func, '__name__', 'unknown_function'), e)

atexit.register(run_cleanup)
