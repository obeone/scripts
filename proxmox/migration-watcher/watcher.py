import sys
import time
import re
import os
import collections  # For deque
from datetime import timedelta
import plotext as pltext  # Import de plotext

# --- Configuration ---
TASKS_ROOT = '/var/log/pve/tasks/'
ACTIVE_PATH = TASKS_ROOT + 'active'

# CLI display configuration
# Height of the throughput graph in text lines
PLOT_HEIGHT_LINES = 8
# Number of lines for stats, graph, logs etc.
# Stats (4) + Sep (1) + Graph (PLOT_HEIGHT_LINES) + Sep (1) + Log Title (1) + Logs (X)
# Let's say 2 lines of logs minimum
LINES_FOR_STATS_AND_HEADER = 4
LINES_FOR_GRAPH_BLOCK = PLOT_HEIGHT_LINES + 2  # Graph + 2 separators
LINE_FOR_LOG_TITLE = 1
MIN_LOG_LINES_TO_SHOW = 2

NUM_CLI_OUTPUT_LINES = LINES_FOR_STATS_AND_HEADER + \
    LINES_FOR_GRAPH_BLOCK + LINE_FOR_LOG_TITLE + MIN_LOG_LINES_TO_SHOW
# Adjusted for clarity, logs will take the remaining dynamic space
MAX_RECENT_LOG_HISTORY = MIN_LOG_LINES_TO_SHOW

# Width of the graph (number of data points/characters)
# We will try to adapt to terminal width, with a max.
try:
    TERM_WIDTH_CHARS = os.get_terminal_size().columns
except OSError:  # May fail if not in a real terminal (e.g. pipe)
    TERM_WIDTH_CHARS = 80  # Default
# Number of points in throughput history / graph width
PLOT_WIDTH_POINTS = min(TERM_WIDTH_CHARS - 10, 70)

first_cli_print_done = False

# --- Functions (parse_upid, read_active_tasks, find_task_logfile, etc. are the same as before) ---
# ... (Paste here the functions parse_upid, read_active_tasks, find_task_logfile (corrected),
#      parse_progress_line, follow_log from the previous CLI version) ...
# Ensure docstrings are present for each function.

# Utility functions (those unchanged can be omitted here for brevity,
# but must be present in your final .py file)


def parse_upid(line):
    '''
    Parse a UPID (Unique Process IDentifier) line to extract task information.

    Args:
        line (str): The UPID line string to parse.
                    Example: UPID:node:PID:STARTTIME:PSTART:TYPE:ID:USER: STATUS

    Returns:
        dict or None: A dictionary with parsed information (upid, action, vmid, user, status)
                      if parsing is successful, otherwise None.
    '''
    match = re.match(
        r'^(UPID:[^:]+:[0-9A-F]+:[0-9A-F]+:[0-9A-F]+:([a-zA-Z0-9\-_]+):([^:]*):([^:\s]+))(:?\s+(\S.*))?$',
        line)
    if match:
        upid_str = match.group(1)
        action_type = match.group(2)
        vmid_val = match.group(3) if match.group(3) else 'N/A'
        user_val = match.group(4)
        status_msg = (match.group(6) or '').strip()
        return {
            'upid': upid_str,
            'action': action_type,
            'vmid': vmid_val,
            'user': user_val,
            'status': status_msg
        }
    return None


def read_active_tasks():
    '''
    Read and parse the list of currently active Proxmox tasks from the active tasks file.

    Returns:
        list[dict]: A list of dictionaries, where each dictionary represents an active task.
                    Returns an empty list if the file doesn't exist or an error occurs.
    '''
    active_tasks_list = []
    try:
        with open(ACTIVE_PATH, 'r') as f:
            for current_line in f:
                current_line = current_line.strip()
                if current_line.startswith('UPID:'):
                    task_info = parse_upid(current_line)
                    if task_info:
                        active_tasks_list.append(task_info)
    except FileNotFoundError:
        print(
            f"Error: Active tasks file not found at {ACTIVE_PATH}", file=sys.stderr)
    except Exception as e:
        print(f"Error reading active tasks: {e}", file=sys.stderr)
    return active_tasks_list


def find_task_logfile(upid_str):
    '''
    Find the log file path for a given Proxmox task UPID.
    The subfolder is determined by the first character of the PSTART field (4th hex field) of the UPID.

    Args:
        upid_str (str): The UPID string of the task.
                        Example: UPID:node:PID:STARTTIME:PSTART:TYPE:ID:USER

    Returns:
        str or None: The absolute path to the task log file if found, otherwise None.
    '''
    try:
        pstart_hex = upid_str.split(':')[4]
        subfolder_char = pstart_hex[0].upper()
    except IndexError:
        return None

    expected_folder_path = os.path.join(TASKS_ROOT, subfolder_char)
    log_filename_candidate = upid_str if upid_str.endswith(
        ':') else upid_str + ':'

    if os.path.isdir(expected_folder_path):
        for filename in os.listdir(expected_folder_path):
            # Adjusted for flexibility
            if filename == log_filename_candidate or filename.startswith(upid_str):
                path = os.path.join(expected_folder_path, filename)
                if os.path.isfile(path):
                    return path
    # Fallback scan (optional, may be slow)
    for char_code_val in list(map(str, range(10))) + [chr(ord('A') + i) for i in range(6)]:
        current_scan_folder = os.path.join(TASKS_ROOT, char_code_val)
        if os.path.isdir(current_scan_folder):
            for filename in os.listdir(current_scan_folder):
                if filename == log_filename_candidate or filename.startswith(upid_str):
                    path = os.path.join(current_scan_folder, filename)
                    if os.path.isfile(path):
                        return path
    return None


def parse_progress_line(log_line):
    '''
    Parse a log line to find data transfer progress information.

    Args:
        log_line (str): A single line from the task log.
                        Example: 'drive-scsi0: transferred 5.5 GiB of 252.0 GiB (2.18%) in 1m 31s'

    Returns:
        tuple[int, float, float] or None: A tuple (elapsed_seconds, transferred_gib, total_gib)
                                         if progress information is found, otherwise None.
    '''
    match = re.search(
        r'transferred ([\d.]+) GiB of ([\d.]+) GiB \([\d.]+%\) in (\d+)m (\d+)s',
        log_line)
    if match:
        transferred_gib = float(match.group(1))
        total_gib = float(match.group(2))
        minutes = int(match.group(3))
        seconds = int(match.group(4))
        elapsed_seconds = minutes * 60 + seconds
        return elapsed_seconds, transferred_gib, total_gib
    return None


def follow_log(log_file_path):
    '''
    A generator that yields new lines appended to a log file.
    Starts reading from the end of the file for live monitoring.

    Args:
        log_file_path (str): The path to the log file.

    Yields:
        str: The next new line appended to the file, or "" on timeout.
    '''
    try:
        with open(log_file_path, 'r') as f:
            f.seek(0, 2)
            while True:
                current_line = f.readline()
                if not current_line:
                    time.sleep(0.1)
                    yield ""
                    continue
                yield current_line.strip()
    except FileNotFoundError:
        print(
            f"Error: Log file '{log_file_path}' not found during follow.", file=sys.stderr)
        yield None  # Signal exhaustion or error
    except Exception as e:
        print(
            f"Error following log file '{log_file_path}': {e}", file=sys.stderr)
        yield None  # Signal exhaustion or error


def calculate_eta_and_speed(times_data_list, progresses_data_list, current_total_gib_val):
    '''
    Calculate current transfer speed and Estimated Time of Arrival (ETA).

    Args:
        times_data_list (list[int]): List of elapsed times in seconds.
        progresses_data_list (list[float]): List of transferred data in GiB.
        current_total_gib_val (float or None): Total size of the transfer in GiB.

    Returns:
        tuple[float, float, float]: (current_speed_mib_s, eta_seconds_val, percent_complete_val)
    '''
    if not times_data_list or len(times_data_list) < 2 or current_total_gib_val is None:
        percent_val = 0.0
        if current_total_gib_val and progresses_data_list:
            percent_val = (
                progresses_data_list[-1] / current_total_gib_val * 100)
        return 0.0, float('inf'), percent_val

    window_points = min(10, len(times_data_list))
    if window_points < 2:
        percent_val = (progresses_data_list[-1] / current_total_gib_val * 100)
        return 0.0, float('inf'), percent_val

    relevant_times = times_data_list[-window_points:]
    relevant_progress = progresses_data_list[-window_points:]

    total_delta_time = 0
    total_delta_progress = 0
    for i in range(1, len(relevant_times)):
        dt = relevant_times[i] - relevant_times[i-1]
        dp = relevant_progress[i] - relevant_progress[i-1]
        if dt > 0:
            total_delta_time += dt
            total_delta_progress += dp

    current_speed_gib_s = 0.0
    if total_delta_time > 0:
        current_speed_gib_s = total_delta_progress / total_delta_time

    current_speed_mib_s = current_speed_gib_s * 1024
    percent_complete_val = (
        progresses_data_list[-1] / current_total_gib_val * 100)
    remaining_gib = current_total_gib_val - progresses_data_list[-1]
    eta_seconds_val = float('inf')

    if current_speed_gib_s > 1e-9:
        eta_seconds_val = int(remaining_gib / current_speed_gib_s)

    return current_speed_mib_s, eta_seconds_val, percent_complete_val


plotext_size_warning_shown = False


def update_cli_display(task_details, times_list, progresses_list, total_gib_val,
                       speed_history_q, recent_logs_q, status_str="Monitoring..."):
    '''
    Refresh the CLI display with current migration progress, speed graph, and status.
    Uses ANSI escape codes and plotext to update a fixed number of lines in place.
    Includes compatibility for plotext size setting.

    Args:
        task_details (dict): Dictionary containing details of the task being monitored.
        times_list (list[int]): List of time points.
        progresses_list (list[float]): List of progress points.
        total_gib_val (float or None): Total GiB to transfer.
        speed_history_q (collections.deque): Deque of recent speed values (MiB/s).
        recent_logs_q (collections.deque): Deque of recent log lines.
        status_str (str): Current status message for the task.
    '''
    global first_cli_print_done, plotext_size_warning_shown
    global NUM_CLI_OUTPUT_LINES, PLOT_WIDTH_POINTS, PLOT_HEIGHT_LINES
    # Ensure these constants are defined globally or passed as arguments
    global LINES_FOR_STATS_AND_HEADER, LINES_FOR_GRAPH_BLOCK, LINE_FOR_LOG_TITLE

    vm_id_str = task_details['vmid']
    node_str = task_details['upid'].split(':')[1]
    log_file_path_str = find_task_logfile(task_details['upid']) or "N/A"

    output_lines_list = []

    # --- Section 1: Stats --- (same as previous version)
    if not progresses_list or total_gib_val is None:
        output_lines_list.extend([
            f"VM: {vm_id_str} on {node_str} - Migration Progress ({status_str})",
            "-" * (PLOT_WIDTH_POINTS + 4),
            "Waiting for first progress update from log...",
            f"Log: {log_file_path_str[:PLOT_WIDTH_POINTS]}"
        ])
        while len(output_lines_list) < LINES_FOR_STATS_AND_HEADER:
            output_lines_list.append("")
    else:
        speed_val, eta_val, percent_val = calculate_eta_and_speed(
            times_list, progresses_list, total_gib_val)
        prog_str = f"{progresses_list[-1]:.2f}"
        total_str = f"{total_gib_val:.2f}"
        perc_str = f"{percent_val:.2f}%"
        speed_str = f"{speed_val:.1f} MiB/s"

        if eta_val == float('inf'):
            eta_str_val = "calculating..." if speed_val < 1e-9 and percent_val < 100 else "N/A"
        elif percent_val >= 100:
            eta_str_val = "Completed"
        else:
            eta_str_val = str(timedelta(seconds=int(eta_val)))

        output_lines_list.extend([
            f"VM: {vm_id_str} on {node_str} - Migration Progress ({status_str})",
            "-" * (PLOT_WIDTH_POINTS + 4),
            f"Progress: {prog_str} / {total_str} GiB ({perc_str})",
            f"Speed:    {speed_str:<20} ETA: {eta_str_val}",
        ])
    output_lines_list = output_lines_list[:LINES_FOR_STATS_AND_HEADER]

    # --- Section 2: Speed Graph (plotext) ---
    # Separator before graph
    output_lines_list.append("-" * (PLOT_WIDTH_POINTS + 4))

    graph_lines_generated = []
    if speed_history_q and len(speed_history_q) > 1:
        pltext.clear_figure()

        # Set graph size - compatibility handling
        try:
            # For plotext >= 5.x.x (figsize or plot_size are often aliases)
            pltext.figsize(PLOT_WIDTH_POINTS, PLOT_HEIGHT_LINES)
        except AttributeError:
            try:
                # For plotext ~4.x.x and some earlier 5.x versions
                pltext.plot_size(PLOT_WIDTH_POINTS, PLOT_HEIGHT_LINES)
            except AttributeError:
                # If no direct sizing method found
                if not plotext_size_warning_shown:
                    # Print warning outside refresh block to avoid alignment disruption
                    # sys.stderr is preferred for error/warning messages
                    # This warning will be shown only once.
                    # To display it properly, it should be done before main refresh loop.
                    # For now, we note it here. Could be moved higher.
                    # print("\nWarning: Could not set plotext size (figsize/plot_size not found). Graph may use default size. Consider `pip install --upgrade plotext`.", file=sys.stderr)
                    # plotext_size_warning_shown = True # Manage this global state if needed
                    pass  # plotext will use its default size or adapt

        pltext.plot(list(speed_history_q), marker="braille")
        pltext.title("Speed History (MiB/s)")
        graph_str_lines = pltext.build().splitlines()
        # Ensure graph does not exceed PLOT_HEIGHT_LINES
        graph_lines_generated.extend(graph_str_lines[:PLOT_HEIGHT_LINES])

    # Fill graph space even if empty or smaller than expected
    while len(graph_lines_generated) < PLOT_HEIGHT_LINES:
        # Empty line of graph width
        graph_lines_generated.append(" " * PLOT_WIDTH_POINTS)

    # Ensure no overflow
    output_lines_list.extend(graph_lines_generated[:PLOT_HEIGHT_LINES])

    # Separator after graph
    output_lines_list.append("-" * (PLOT_WIDTH_POINTS + 4))

    # --- Section 3: Recent Logs ---
    output_lines_list.append("Recent Logs:")

    remaining_lines_for_logs = NUM_CLI_OUTPUT_LINES - len(output_lines_list)
    if remaining_lines_for_logs > 0:
        for log_entry in list(recent_logs_q)[-remaining_lines_for_logs:]:
            output_lines_list.append(f"  {log_entry[:PLOT_WIDTH_POINTS + 2]}")

    while len(output_lines_list) < NUM_CLI_OUTPUT_LINES:
        output_lines_list.append("")
    output_lines_list = output_lines_list[:NUM_CLI_OUTPUT_LINES]

    # ANSI escape codes for in-place update
    if first_cli_print_done:
        sys.stdout.write(f"\033[{NUM_CLI_OUTPUT_LINES}A")
    else:
        first_cli_print_done = True

    for line_to_print in output_lines_list:
        sys.stdout.write(f"\033[2K{line_to_print}\n")
    sys.stdout.flush()


def print_final_summary(task_details, final_status_msg, log_file_path_str):
    '''
    Prints a final summary message when monitoring ends.
    Ensures this message is printed below the dynamic CLI block.

    Args:
        task_details (dict): Details of the monitored task.
        final_status_msg (str): The final status of the task (e.g., Completed, Failed, Interrupted).
        log_file_path_str (str or None): Path to the log file.
    '''
    global first_cli_print_done
    if first_cli_print_done:  # If dynamic block was active, ensure we are below it
        sys.stdout.write("\n")

    vm_id_str = task_details['vmid']
    node_str = task_details['upid'].split(':')[1]

    print("-" * 70)
    print(f"Monitoring for VM {vm_id_str} on {node_str} ended.")
    print(f"Final Status: {final_status_msg}")
    if log_file_path_str:
        print(f"Log file was: {log_file_path_str}")
    print("-" * 70)


def main():
    '''
    Main function to select a Proxmox qmigrate task and monitor its progress in the CLI,
    including a text-based graph of transfer speed.
    '''
    global first_cli_print_done, PLOT_WIDTH_POINTS
    first_cli_print_done = False

    active_qmigrate_tasks = [
        task for task in read_active_tasks()
        if task['action'] == "qmigrate" and (task['status'] == "0" or task['status'] == "")
    ]

    if not active_qmigrate_tasks:
        print("No qmigrate tasks appearing as ongoing were found.")
        return

    task_to_monitor_details = None
    if len(active_qmigrate_tasks) == 1:
        task_to_monitor_details = active_qmigrate_tasks[0]
        print(
            f"Auto-selecting task: VM {task_to_monitor_details['vmid']} on node {task_to_monitor_details['upid'].split(':')[1]}")
    else:
        # ... (task selection logic from previous version) ...
        print("Ongoing qmigrate tasks found:")
        for idx, task in enumerate(active_qmigrate_tasks):
            print(
                f"  {idx+1}. VM {task['vmid']} on node {task['upid'].split(':')[1]} (UPID: {task['upid']})")
        try:
            choice_idx = int(
                input(f"Select task [1-{len(active_qmigrate_tasks)}]: ")) - 1
            if not (0 <= choice_idx < len(active_qmigrate_tasks)):
                raise ValueError("Choice out of range.")
            task_to_monitor_details = active_qmigrate_tasks[choice_idx]
        except (ValueError, IndexError):
            print("Invalid selection.")
            return

    log_file_to_monitor = find_task_logfile(task_to_monitor_details['upid'])
    if not log_file_to_monitor:
        print(
            f"Error: Could not find log file for UPID {task_to_monitor_details['upid']}.")
        return

    print(f"Attempting to monitor log: {log_file_to_monitor}")
    print(f"Displaying progress with speed graph. Press Ctrl+C to stop.")
    time.sleep(1)

    log_lines_generator = follow_log(log_file_to_monitor)
    time_points = []
    progress_points = []
    # Store speed history for the plot (MiB/s)
    speed_history_for_plot = collections.deque(maxlen=PLOT_WIDTH_POINTS)
    current_total_transfer_gib = None

    recent_logs_queue = collections.deque(maxlen=max(
        1, NUM_CLI_OUTPUT_LINES // 3))  # Dynamic log history size

    current_task_status = "Initializing..."
    final_status_message_on_exit = "Monitoring ended"

    try:
        # Initial display before loop starts
        update_cli_display(task_to_monitor_details, time_points, progress_points,
                           current_total_transfer_gib, speed_history_for_plot,
                           recent_logs_queue, current_task_status)

        while True:
            any_new_log_activity = False
            task_log_ended = False

            for _ in range(5):
                log_line = next(log_lines_generator)

                # Generator exhausted (e.g. file not found initially or error)
                if log_line is None:
                    current_task_status = "Log Unavailable"
                    task_log_ended = True
                    break

                if log_line:
                    any_new_log_activity = True
                    recent_logs_queue.append(log_line)

                    if "TASK OK" in log_line or "migration status: completed" in log_line or "migration finished successfully" in log_line:
                        current_task_status = "Completed (TASK OK in log)"
                        task_log_ended = True
                        break
                    if "TASK ERROR" in log_line or "migration status: failed" in log_line or "migration aborted" in log_line:
                        err_msg = log_line.split(
                            'TASK ERROR', 1)[-1].strip() if "TASK ERROR" in log_line else "failure in log"
                        current_task_status = f"Failed ({err_msg})"
                        task_log_ended = True
                        break

                    progress_data = parse_progress_line(log_line)
                    if progress_data:
                        elapsed_t, transferred_g, total_g = progress_data
                        if not time_points or elapsed_t > time_points[-1]:
                            time_points.append(elapsed_t)
                            progress_points.append(transferred_g)
                            current_total_transfer_gib = total_g

                            # Calculate current speed and add to history for plotting
                            current_speed_mib, _, _ = calculate_eta_and_speed(
                                time_points, progress_points, current_total_transfer_gib)
                            if len(time_points) >= 2:  # Only add speed if it can be calculated
                                speed_history_for_plot.append(
                                    current_speed_mib)

                            current_task_status = "Monitoring..."

            update_cli_display(task_to_monitor_details, time_points, progress_points,
                               current_total_transfer_gib, speed_history_for_plot,
                               recent_logs_queue, current_task_status)

            if task_log_ended:
                final_status_message_on_exit = current_task_status
                break

            time.sleep(0.2 if any_new_log_activity else 1.0)

    except KeyboardInterrupt:
        final_status_message_on_exit = "Interrupted by user"
    except StopIteration:  # Should not happen if follow_log yields None
        final_status_message_on_exit = "Log stream ended"
    except Exception as e:
        final_status_message_on_exit = f"An error occurred: {type(e).__name__} - {e}"
    finally:
        print_final_summary(task_to_monitor_details,
                            final_status_message_on_exit, log_file_to_monitor)


if __name__ == '__main__':
    # Ensure TERM environment variable is set for plotext or terminal size detection
    if 'TERM' not in os.environ:
        # A common default that supports color
        os.environ['TERM'] = 'xterm-256color'
    main()
