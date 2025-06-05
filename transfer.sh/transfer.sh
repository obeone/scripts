#!/usr/bin/env bash

###################################################################
# Script Name   : transfer.sh
# Description   : A script to manage file transfers using Transfer.sh service.
#                 It supports operations like send, receive, delete,
#                 and get information about files and directories.
# Args          : [OPTIONS] <command>
# Author        : GPT-3.5 and GPT-4, assisted by obeone
# Version       : 1.3
# Date          : 2025-06-04
# License       : MIT License
# Usage         : ./transfer.sh [OPTIONS] <command>
# Notes         : Ensure you have the necessary permissions to execute
#                 and that your terminal supports ANSI color codes for
#                 the best experience.
#                 TMPDIR environment variable can be set using --tmp-dir option.
###################################################################

set -u

PV_AVAILABLE=false
command -v pv >/dev/null 2>&1 && PV_AVAILABLE=true

# Create a temporary file with an optional suffix in a portable way.
# GNU mktemp supports --suffix, but BSD mktemp (macOS) does not.
# If gmktemp is available, use it; otherwise fall back to renaming.
mktemp_with_suffix() {
    local suffix="$1"
    local tmpfile

    if tmpfile=$(mktemp --suffix="$suffix" 2>/dev/null); then
        echo "$tmpfile"
        return 0
    fi

    if command -v gmktemp >/dev/null 2>&1 && \
       tmpfile=$(gmktemp --suffix="$suffix" 2>/dev/null); then
        echo "$tmpfile"
        return 0
    fi

    tmpfile=$(mktemp -t transfer.sh.XXXXXX)
    mv "$tmpfile" "${tmpfile}${suffix}"
    echo "${tmpfile}${suffix}"
}

# Environment defaults
: "${TRANSFERSH_URL:=https://transfer.obeone.cloud}"
: "${TRANSFERSH_MAX_DAYS:=}"
: "${TRANSFERSH_MAX_DOWNLOADS:=}"
: "${LOG_LEVEL:=INFO}"
: "${AUTH_USER:=}"
: "${AUTH_PASS:=}"

COMMAND="$(basename "$0")"

# Color codes
RED='\e[31m'
GREEN='\e[32m'
YELLOW='\e[33m'
BLUE='\e[34m'
MAGENTA='\e[35m'
CYAN='\e[36m'
RESET='\e[0m'
BOLD='\e[1m'

# Logs messages based on the defined LOG_LEVEL.
#
# Args:
#   level (str): The log level (ERROR, WARN, INFO, DEBUG).
#   message (str): The message to log.
log() {
    local level="$1"
    shift
    local message="$*"
    local levels=("ERROR" "WARN" "INFO" "DEBUG")
    local current_level_index=-1
    local target_level_index=-1

    exec 3>&1 # Save stdout to fd 3

    # Find index for current LOG_LEVEL
    for i in "${!levels[@]}"; do
        if [[ "${levels[$i]}" == "$LOG_LEVEL" ]]; then
            current_level_index="${i}"
            break
        fi
    done

    # Find index for message's level
    for i in "${!levels[@]}"; do
        if [[ "$level" == "${levels[$i]}" ]]; then
            target_level_index="${i}"
            break
        fi
    done

    if [[ "$target_level_index" -ne -1 ]] && [[ "$target_level_index" -le "$current_level_index" ]]; then
        case "$level" in
            DEBUG)
                echo -e "${YELLOW}[DEBUG] ${message}${RESET}" >&3
                ;;
            INFO)
                echo -e "${GREEN}[INFO] ${message}${RESET}" >&3
                ;;
            WARN)
                echo -e "${YELLOW}[WARN] ${message}${RESET}" >&3
                ;;
            ERROR)
                echo -e "${RED}[ERROR] ${message}${RESET}" >&3
                ;;
        esac
    fi
}

# Checks if required commands are installed.
# Exits if any requirement is missing.
check_requirements() {
    for cmd in curl openssl zip unzip tar; do
        if ! command -v "$cmd" &> /dev/null; then
            log ERROR "$cmd is not installed."
            exit 1
        fi
    done
}

# Executes a curl command and logs it for debugging.
# Logs an error if curl command fails.
#
# Args:
#   ... (any curl arguments)
#
# Displays help messages for the script or specific commands.
#
# Args:
#   command_name (str, optional): The specific command to display help for.
display_help() {
    local command_name="${1:-}"
    case "$command_name" in
        send)
            echo -e "${GREEN}Usage: $COMMAND send [OPTIONS] <file|directory> [<file|directory>...]${RESET}"
            echo -e "Options:"
            echo -e "  ${CYAN}-h, --help${RESET}                  Display help message"
            echo -e "  ${CYAN}-d, --max-downloads <value>${RESET} Set the maximum number of downloads (optional)"
            echo -e "  ${CYAN}-D, --max-days <value>${RESET}      Set the maximum number of days the file is stored (optional)"
            echo -e "  ${CYAN}-k, --key <value>${RESET}           Encryption key (optional)"
            echo -e "  ${CYAN}-u, --user <value>${RESET}          Username for basic auth (optional)"
            echo -e "  ${CYAN}-p, --password <value>${RESET}      Password for basic auth (optional)"
            echo -e "  ${CYAN}-y${RESET}                         Bypass confirmation"
            echo -e "Environment Variables for send:"
            echo -e "  ${CYAN}TRANSFERSH_ENCRYPTION_KEY${RESET}  Encryption key"
            echo -e "  ${CYAN}TRANSFERSH_MAX_DAYS${RESET}        Maximum number of days the file is stored"
            echo -e "  ${CYAN}TRANSFERSH_MAX_DOWNLOADS${RESET}   Maximum number of downloads"
            ;;
        receive)
            echo -e "${GREEN}Usage: $COMMAND receive [OPTIONS] <URL> [destination]${RESET}"
            echo -e "Options:"
            echo -e "  ${CYAN}-h, --help${RESET}                  Display help message"
            echo -e "  ${CYAN}-k, --key <value>${RESET}           Decryption key (optional)"
            echo -e "  ${CYAN}-u, --unzip${RESET}                 Offer to unzip file on receive (optional)"
            echo -e "Environment Variables for receive:"
            echo -e "  ${CYAN}TRANSFERSH_ENCRYPTION_KEY${RESET}  Decryption key"
            ;;
        delete)
            echo -e "${GREEN}Usage: $COMMAND delete <X-URL-Delete>${RESET}"
            ;;
        info)
            echo -e "${GREEN}Usage: $COMMAND info <URL>${RESET}"
            ;;
        *)
            echo -e "${GREEN}Usage: $COMMAND [OPTIONS] <command>${RESET}"
            echo -e "Global Options:"
            echo -e "  ${CYAN}-h, --help${RESET}                  Display help"
            echo -e "  ${CYAN}--log-level <level>${RESET}       Set the logging level (ERROR, WARN, INFO, DEBUG) (default: INFO)"
            echo -e "  ${CYAN}--tmp-dir <directory>${RESET}     Set a custom temporary directory (default: system's TMPDIR or /tmp)"
            echo -e "Commands:"
            echo -e "  ${CYAN}send${RESET}                       Send a file or directory"
            echo -e "  ${CYAN}receive${RESET}                    Receive a file or directory"
            echo -e "  ${CYAN}delete${RESET}                     Delete a file or directory"
            echo -e "  ${CYAN}info${RESET}                       Get information about a file or directory"
            echo -e "Common Environment Variables:"
            echo -e "  ${CYAN}TRANSFERSH_URL${RESET}             URL of the Transfer.sh service (default: https://transfer.obeone.cloud)"
            echo -e "  ${CYAN}AUTH_USER${RESET}                  Username for basic authentication"
            echo -e "  ${CYAN}AUTH_PASS${RESET}                  Password for basic authentication"
            ;;
    esac
}

# Encrypts a file using AES-256-CBC.
#
# Args:
#   file (str): Path to the input file.
#   key (str): Encryption key.
#
# Returns:
#   str: Path to the encrypted temporary file, or empty if failed.
#        Exits with 1 on failure.
encrypt_file() {
    local file="$1"
    local key="$2"
    local outfile

    outfile="$(mktemp_with_suffix .enc)" # Will use TMPDIR if set
    log DEBUG "Temporary encrypted file will be: $outfile"

    if openssl enc -aes-256-cbc -salt -pbkdf2 -in "$file" -out "$outfile" -pass pass:"$key"; then
        echo "$outfile"
    else
        log ERROR "Encryption failed for file: $file"
        rm -f "$outfile"
        return 1
    fi
}

# Decrypts a file using AES-256-CBC.
#
# Args:
#   file (str): Path to the encrypted input file.
#   key (str): Decryption key.
#   outfile (str): Path for the decrypted output file.
#
# Returns:
#   int: Return code of the openssl command (0 for success, non-zero for failure).
decrypt_file() {
    local file="$1"
    local key="$2"
    local outfile="$3"

    log DEBUG "Decrypting file '$file' to '$outfile'"
    if openssl enc -d -aes-256-cbc -pbkdf2 -in "$file" -out "$outfile" -pass pass:"$key"; then
        return 0
    else
        log ERROR "Decryption failed for file: $file"
        return 1
    fi
}

# Sends one or more files/directories to the Transfer.sh service.
# Handles zipping multiple files/directories and optional encryption.
#
# Args:
#   ... : Options (-d, -D, -k, -u, -p, -y, -h) followed by file/directory paths.
send_file_or_directory() {
    local max_downloads="${TRANSFERSH_MAX_DOWNLOADS}"
    local max_days="${TRANSFERSH_MAX_DAYS}"
    local headers=()
    local encryption_key="${TRANSFERSH_ENCRYPTION_KEY:-}"
    local request_confirmation=true
    local should_zip=false
    local temp_file_to_upload="" # Renamed to avoid confusion
    local original_file_name=""
    local auth_set_in_args=false # Flag to check if auth was set via args

    # Parse options specific to send command
    while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--max-downloads)
                max_downloads="$2"
                log DEBUG "Max downloads set to: $max_downloads"
                shift 2
                ;;
            -D|--max-days)
                max_days="$2"
                log DEBUG "Max days set to: $max_days"
                shift 2
                ;;
            -k|--key)
                encryption_key="$2"
                log DEBUG "Encryption key provided via argument."
                shift 2
                ;;
            -u|--user)
                AUTH_USER="$2"
                auth_set_in_args=true
                log DEBUG "Basic auth username provided via argument."
                shift 2
                ;;
            -p|--password)
                AUTH_PASS="$2"
                auth_set_in_args=true
                log DEBUG "Basic auth password provided via argument."
                shift 2
                ;;
            -h|--help)
                display_help send
                return 0
                ;;
            -y)
                log DEBUG "Bypassing confirmation."
                request_confirmation=false
                shift
                ;;
            *) # First non-option argument is the start of file/directory list
                break
                ;;
        esac
    done

    if [ $# -eq 0 ]; then
        log ERROR "No files or directories specified to send."
        display_help send
        return 1
    fi

    # --- Helper function to create zip ---
    # Creates a ZIP archive.
    #
    # Args:
    #   output_zip_file (str): The path for the output ZIP file.
    #   ... (str): One or more files or directories to add to the ZIP.
    #
    # Returns:
    #   0 if successful, 1 on failure.
    create_zip() {
        local output_zip_file="$1"
        shift
        log DEBUG "Creating ZIP file: $output_zip_file with content: $*"
        if zip -r "$output_zip_file" "$@"; then
            return 0
        else
            log ERROR "Failed to create ZIP file: $output_zip_file"
            return 1
        fi
    }

    # --- Helper function to extract URLs from curl response ---
    # Extracts the delete and download URLs from the curl response headers and body.
    #
    # Args:
    #   content (str): The full response from curl (headers + body).
    #
    # Returns:
    #   str: "DELETE_URL;DOWNLOAD_URL"
    extract_urls_from_response() {
        local content="$1"
        # Capture the delete URL (case-insensitive header)
        local url_delete
        url_delete=$(echo "$content" | grep -i '^x-url-delete:' | awk '{$1=""; print $0}' | sed 's/^[ \t]*//;s/[ \t\r]*$//')
        # Capture the final download URL (usually the last line of the body, stripping progress meter if any)
        local url_download
        url_download=$(echo "$content" | awk '/^HTTP\// {body=0} body {print} NF==0 {body=1}' | tail -n 1 | sed 's/^.*[0-9][0-9\.]*%//' | sed 's/[\r\n]*$//')

        log DEBUG "Extracted delete URL: '$url_delete'"
        log DEBUG "Extracted download URL: '$url_download'"
        echo "$url_delete;$url_download"
    }


    if [ -z "$encryption_key" ] && [ "$request_confirmation" = true ]; then # Only ask if not bypassing and not already set
        echo -ne "${CYAN}Enter encryption key (leave empty for no encryption, press Enter): ${RESET}"
        read -rs encryption_key_input # Read silently
        echo # Newline after input
        # Only set encryption_key if user actually typed something
        if [ -n "$encryption_key_input" ]; then
            encryption_key="$encryption_key_input"
            log DEBUG "Encryption key provided interactively."
        else
            log DEBUG "No encryption key provided interactively."
        fi
    fi

    if $request_confirmation; then
        echo -e "${CYAN}You are about to send the following files/directories:${RESET}"
        for item in "$@"; do
            echo -e "${BLUE}$(basename "$item")${RESET}"
        done
        if [ -n "$encryption_key" ]; then
            echo -e "${YELLOW}These will be encrypted.${RESET}"
        fi
        if [ -n "$max_downloads" ]; then
            echo -e "${MAGENTA}Max downloads: $max_downloads${RESET}"
        fi
        if [ -n "$max_days" ]; then
            echo -e "${MAGENTA}Max days: $max_days${RESET}"
        fi
        read -r -p $'\e[1;35mAre you sure you want to proceed? (Y/n): \e[0m' confirm
        confirm=${confirm:-y}
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            log INFO "Upload cancelled by user."
            return 1
        fi
    fi

    [[ -n "$max_downloads" ]] && headers+=("-H" "Max-Downloads: $max_downloads")
    [[ -n "$max_days" ]] && headers+=("-H" "Max-Days: $max_days")

    if [[ $# -gt 1 ]] || [[ -d "$1" ]]; then # Multiple files or a single directory
        should_zip=true
        temp_file_to_upload="$(mktemp_with_suffix .zip)" # Will use TMPDIR
        log DEBUG "Temporary zip file will be: $temp_file_to_upload"
        if ! create_zip "$temp_file_to_upload" "$@"; then
            rm -f "$temp_file_to_upload" # Clean up on failure
            return 1
        fi
        original_file_name="transfer_archive.zip"
    else # Single file
        temp_file_to_upload="$1"
        original_file_name=$(basename "$1")
    fi

    local response
    local return_code
    local auth_options=()

    if [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASS" ]; then
        auth_options=("--user" "$AUTH_USER:$AUTH_PASS")
        log DEBUG "Using Basic Auth credentials from environment or arguments."
    elif $auth_set_in_args; then # if -u or -p was used but one is missing
        log WARN "Username or password for basic auth is missing. Auth will not be used."
    fi

    local final_file_to_upload="$temp_file_to_upload" # This is what actually gets uploaded
    local upload_filename="$original_file_name"      # Filename sent to server

    if [ -n "$encryption_key" ]; then
        upload_filename="$original_file_name.enc"
        log INFO "Encrypting '$original_file_name' to '$upload_filename'..."
        local encrypted_temp_file
        if ! encrypted_temp_file=$(encrypt_file "$temp_file_to_upload" "$encryption_key"); then
            log ERROR "Encryption failed. Cannot upload."
            [ "$should_zip" = true ] && [ -f "$temp_file_to_upload" ] && rm "$temp_file_to_upload"
            return 1
        fi
        if [ ! -f "$encrypted_temp_file" ]; then
            log ERROR "Encryption failed. Cannot upload."
            [ "$should_zip" = true ] && [ -f "$temp_file_to_upload" ] && rm "$temp_file_to_upload"
            return 1
        fi
        final_file_to_upload="$encrypted_temp_file" # Upload this encrypted file
    fi

    local file_size
    file_size=$(du -k "$final_file_to_upload" | cut -f1) # Size in KB for pv
    file_size=$((file_size * 1024)) # Size in Bytes for pv -s

    log INFO "Uploading '$upload_filename' (size: $(numfmt --to=iec-i --suffix=B "$file_size"))..."

    local header_pipe
    header_pipe=$(mktemp -u) # Create a unique name for the named pipe
    mkfifo "$header_pipe" # Create the named pipe

    # stderr of curl (which includes progress bar with --progress-bar) is redirected to /dev/null
    # to keep the main 'response' variable clean for download/delete URLs.
    # Headers are dumped to the named pipe.
    if $PV_AVAILABLE; then
        response=$( (pv -pterbN "Uploading" -s "$file_size" "$final_file_to_upload" | \
                     command curl --dump-header "$header_pipe" "${auth_options[@]}" "${headers[@]}" \
                               --upload-file - "${TRANSFERSH_URL}/${upload_filename}" --silent --show-error --fail \
                               2>/dev/null ); \
                   cat "$header_pipe" )
    else
        response=$( command curl --progress-bar --dump-header "$header_pipe" "${auth_options[@]}" "${headers[@]}" \
                       --upload-file "$final_file_to_upload" "${TRANSFERSH_URL}/${upload_filename}" --silent --show-error --fail; \
                   cat "$header_pipe" )
    fi

    return_code=$? # Return code of the subshell (effectively curl)

    rm "$header_pipe" # Clean up pipe

    # Clean up temporary files
    if [ "$final_file_to_upload" != "$temp_file_to_upload" ] && [ -f "$final_file_to_upload" ]; then
        rm "$final_file_to_upload" # Remove encrypted temp file
    fi
    if [ "$should_zip" = true ] && [ -f "$temp_file_to_upload" ]; then
        rm "$temp_file_to_upload" # Remove original zip temp file
    fi

    log DEBUG "Raw cURL Response Block (headers and body if any):"
    log DEBUG "${response}"

    if echo "$response" | grep -qi "Not authorized"; then # Case-insensitive check
        log ERROR "Authorization failed. Please check your credentials."
        return 1
    fi
    if echo "$response" | grep -qi "HTTP.* 401"; then # Check for HTTP 401 status in headers
        log ERROR "HTTP 401 Unauthorized. Please check your credentials."
        return 1
    fi

    if [ $return_code -ne 0 ]; then
        # Curl's --fail option makes it return 22 on HTTP errors (4xx, 5xx)
        # Other non-zero codes can be network issues, etc.
        log ERROR "Failed to upload file. Upload command exited with code: $return_code."
        return 1
    fi

    local url_delete url_download
    IFS=";" read -r url_delete url_download <<< "$(extract_urls_from_response "$response")"

    if [ -n "$url_download" ]; then
        echo -e "\n${GREEN}${BOLD}Upload successful.${RESET}"
        echo ""
        echo -e "${GREEN}${BOLD}Link to the file:${RESET} ${GREEN}${url_download}${RESET}"
        local receive_cmd_suffix=""
        if [ -n "$encryption_key" ]; then
            receive_cmd_suffix=" --key YOUR_KEY_HERE" # Remind user about the key
        fi
        if [[ "$original_file_name" == *.zip || "$original_file_name" == *.tar.gz || "$original_file_name" == *.tgz ]]; then # Added tar.gz
             receive_cmd_suffix="$receive_cmd_suffix --unzip" # Suggest --unzip for common archive types
        fi
        echo -e "${BLUE}${BOLD}Receive command:${RESET} ${BLUE}${COMMAND} receive${receive_cmd_suffix} ${url_download}${RESET}"
        echo ""
        if [ -n "$url_delete" ]; then
            echo -e "${RED}${BOLD}Delete command:${RESET} ${RED}${COMMAND} delete ${url_delete}${RESET}"
        else
            log WARN "Could not extract delete URL from the response."
        fi
    else
        log ERROR "Could not extract download URL from the response. Upload may have failed silently or response format changed."
        log ERROR "Full response for analysis:\n$response"
        return 1
    fi
}

# Receives a file from the Transfer.sh service.
# Handles optional decryption and unzipping.
#
# Args:
#   ... : Options (-k, -u, -h) followed by URL and optional destination path.
receive_file_or_directory() {
    local encryption_key="${TRANSFERSH_ENCRYPTION_KEY:-}"
    local offer_unzip="false"
    local destination_path="." # Default to current directory

    # Parse options specific to receive command
    while [[ $# -gt 0 ]]; do
        case $1 in
            -k|--key)
                encryption_key="$2"
                log DEBUG "Decryption key provided via argument."
                shift 2
                ;;
            -u|--unzip)
                offer_unzip="true"
                log DEBUG "Will offer to unzip after download."
                shift
                ;;
            -h|--help)
                display_help receive
                return 0
                ;;
            *) # First non-option argument is the URL
                break
                ;;
        esac
    done

    if [ $# -eq 0 ]; then
        log ERROR "No URL specified to receive."
        display_help receive
        return 1
    fi

    local url="$1"
    # If a second non-option argument is provided, it's the destination
    if [ -n "$2" ]; then
        destination_path="$2"
    fi

    local downloaded_file_name
    downloaded_file_name=$(basename "$url")
    local final_file_name_on_disk="$downloaded_file_name"

    local output_file_path
    if [ -d "$destination_path" ]; then
        output_file_path="$destination_path/$downloaded_file_name"
    else
        output_file_path="$destination_path"
        final_file_name_on_disk=$(basename "$output_file_path")
        local output_dir
        output_dir=$(dirname "$output_file_path")
        if [ ! -d "$output_dir" ];  then
            log INFO "Destination directory '$output_dir' does not exist. Creating it."
            if ! mkdir -p "$output_dir"; then
                 log ERROR "Failed to create destination directory '$output_dir'."
                 return 1
            fi
        fi
    fi


    local is_encrypted="false"
    if [[ "$downloaded_file_name" == *.enc ]]; then
        is_encrypted="true"
        # Adjust final name and path if it was derived from a .enc name
        local base_name_no_enc="${final_file_name_on_disk%.enc}"
        if [ -d "$destination_path" ] || [[ "$output_file_path" == */*.enc ]]; then # If dest was dir, or full path ended .enc
            final_file_name_on_disk="$base_name_no_enc"
            output_file_path="$(dirname "$output_file_path")/$final_file_name_on_disk"
        fi


        if [ -z "$encryption_key" ]; then
            echo -ne "${CYAN}File appears to be encrypted. Enter decryption key: ${RESET}"
            read -rs encryption_key_input
            echo
            if [ -z "$encryption_key_input" ]; then
                log ERROR "No decryption key provided for an encrypted file. Aborting."
                return 1
            fi
            encryption_key="$encryption_key_input"
        fi
    fi

    log INFO "Downloading file from $url"
    local temp_download_target
    local curl_target_path="$output_file_path" # Where curl will initially save the file

    if [ "$is_encrypted" = "true" ]; then
        temp_download_target="$(mktemp)" # Temp file for encrypted download
        curl_target_path="$temp_download_target"
        log DEBUG "Encrypted file will be temporarily downloaded to: $temp_download_target"
    fi

    log INFO "Attempting to save to: $curl_target_path (final name on disk: $final_file_name_on_disk)"

    # Using command curl directly for download part to ensure --progress-bar goes to tty
    # and does not interfere with error checking or output redirection of the script itself.
    if ! command curl -L --fail --show-error -o "$curl_target_path" "$url" --progress-bar; then
        log ERROR "Download failed for URL: $url."
        [ -f "$curl_target_path" ] && rm "$curl_target_path" # Clean up partial download if any
        return 1
    fi

    if [ "$is_encrypted" = "true" ]; then
        log INFO "Decrypting '$downloaded_file_name' to '$output_file_path'..."
        if ! decrypt_file "$temp_download_target" "$encryption_key" "$output_file_path"; then
            log ERROR "Decryption failed. The downloaded encrypted file is at: $temp_download_target"
            # Do not delete temp_download_target if decryption fails, user might want it.
            return 1
        fi
        rm "$temp_download_target" # Clean up temp encrypted file after successful decryption
        log INFO "Decryption successful. Output: $output_file_path"
    else
        # If not encrypted, file is already at output_file_path (curl_target_path was output_file_path)
        log INFO "Download successful (not encrypted). Output: $output_file_path"
    fi

    local file_to_potentially_unzip="$output_file_path"

    if [ "$offer_unzip" = "true" ] && [[ "$final_file_name_on_disk" == *.zip || "$final_file_name_on_disk" == *.tar.gz || "$final_file_name_on_disk" == *.tgz ]]; then
        echo -e "${CYAN}Downloaded file appears to be an archive: $final_file_name_on_disk${RESET}"
        read -r -p $'\e[1;35mDo you want to extract it? (Y/n): \e[0m' confirm_unzip
        confirm_unzip=${confirm_unzip:-y}
        if [[ "$confirm_unzip" =~ ^[Yy]$ ]]; then
            local extract_dir
            extract_dir=$(dirname "$file_to_potentially_unzip")
            log INFO "Extracting '$file_to_potentially_unzip' into '$extract_dir'..."
            local extract_success=false
            if [[ "$final_file_name_on_disk" == *.zip ]]; then
                if unzip -o "$file_to_potentially_unzip" -d "$extract_dir"; then extract_success=true; fi
            elif [[ "$final_file_name_on_disk" == *.tar.gz || "$final_file_name_on_disk" == *.tgz ]]; then
                if tar -xzf "$file_to_potentially_unzip" -C "$extract_dir"; then extract_success=true; fi
            fi

            if $extract_success; then
                log INFO "Extraction successful."
                read -r -p $'\e[1;35mDo you want to delete the original archive file? (Y/n): \e[0m' confirm_delete_archive
                confirm_delete_archive=${confirm_delete_archive:-y}
                if [[ "$confirm_delete_archive" =~ ^[Yy]$ ]]; then
                    rm "$file_to_potentially_unzip"
                    log INFO "Original archive file '$file_to_potentially_unzip' deleted."
                fi
            else
                log ERROR "Failed to extract '$file_to_potentially_unzip'."
            fi
        fi
    fi
    log INFO "File successfully received at '$output_file_path'."
}

# Deletes a file from the Transfer.sh service using its delete URL.
#
# Args:
#   delete_url (str): The X-URL-Delete URL.
delete_file_or_directory() {
    if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
        display_help delete
        return 0
    fi

    if [ -z "$1" ]; then
        log ERROR "No delete URL specified."
        display_help delete
        return 1
    fi

    local delete_url="$1"
    log INFO "Attempting to delete file using URL: $delete_url"
    local response
    response=$(curl -s -w "%{http_code}" -X DELETE "$delete_url")
    local http_code="${response: -3}"
    local response_body="${response::-3}"


    log DEBUG "Delete response body: $response_body"
    log DEBUG "Delete response HTTP code: $http_code"

    if [[ "$http_code" == "200" ]] || [[ "$http_code" == "204" ]]; then # 200 or 204 No Content are typical success
        log INFO "File delete request sent successfully (HTTP $http_code)."
        if [ -n "$response_body" ]; then
            log INFO "Server response: $response_body"
        fi
    else
        log ERROR "Failed to delete file (HTTP $http_code)."
        if [ -n "$response_body" ]; then
            log ERROR "Server response: $response_body"
        fi
        return 1
    fi
}

# Retrieves and displays information about a file on Transfer.sh service.
#
# Args:
#   url (str): The URL of the file.
info_command() {
    if [ -z "$1" ]; then
        log ERROR "No URL specified for info."
        display_help info
        return 1
    fi
    local url="$1"
    log INFO "Retrieving information for URL: $url"
    local headers
    if ! headers=$(command curl -I "$url" -s); then
        log ERROR "Failed to retrieve headers from $url"
        return 1
    fi
    if [[ -z "$headers" ]]; then
        log ERROR "No headers received from $url. URL might be invalid or server unresponsive."
        return 1
    fi


    log DEBUG "Headers received:\n$headers"

    local remaining_days
    remaining_days=$(echo "$headers" | grep -i '^x-remaining-days:' | awk '{print $2}' | tr -d '\r')
    local remaining_downloads
    remaining_downloads=$(echo "$headers" | grep -i '^x-remaining-downloads:' | awk '{print $2}' | tr -d '\r')
    local file_size
    file_size=$(echo "$headers" | grep -i '^Content-Length:' | awk '{print $2}' | tr -d '\r')
    local mime_type
    mime_type=$(echo "$headers" | grep -i '^Content-Type:' | awk '{$1=""; print $0}' | sed 's/^[ \t]*//;s/[ \t\r]*$//')

    echo -e "${GREEN}File Information for:${RESET} ${CYAN}$url${RESET}"
    if [ -n "$file_size" ]; then
        echo -e "  ${BLUE}File Size:${RESET} $(numfmt --to=iec-i --suffix=B "$file_size") ($file_size bytes)"
    else
        echo -e "  ${BLUE}File Size:${RESET} Not available"
    fi
    if [ -n "$mime_type" ]; then
        echo -e "  ${BLUE}Mime-Type:${RESET} $mime_type"
    else
        echo -e "  ${BLUE}Mime-Type:${RESET} Not available"
    fi
    if [ -n "$remaining_days" ]; then
        echo -e "  ${BLUE}Remaining Days:${RESET} $remaining_days"
    else
        echo -e "  ${BLUE}Remaining Days:${RESET} Not available or unlimited"
    fi
    if [ -n "$remaining_downloads" ]; then
        echo -e "  ${BLUE}Remaining Downloads:${RESET} $remaining_downloads"
    else
        echo -e "  ${BLUE}Remaining Downloads:${RESET} Not available or unlimited"
    fi
}

# --- Main script execution ---
check_requirements

# Store flags for deferred logging if needed, though current direct logging is mostly fine.

# Pre-parse global options. This loop consumes global options.
# The remaining arguments are for the command.
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            display_help
            exit 0
            ;;
        --log-level)
            if [ -z "$2" ]; then
                # Use direct echo to stderr as log function might not be fully configured if LOG_LEVEL itself is being set.
                echo -e "${RED}[ERROR] Option --log-level requires an argument.${RESET}" >&2
                display_help
                exit 1
            fi
            if [[ ! "$2" =~ ^(ERROR|WARN|INFO|DEBUG)$ ]]; then
                echo -e "${RED}[ERROR] Invalid log level: $2. Must be ERROR, WARN, INFO, or DEBUG.${RESET}" >&2
                display_help
                exit 1
            fi
            LOG_LEVEL="$2"
            log INFO "Log level set to: $LOG_LEVEL"
            shift 2
            continue
            ;;
        --tmp-dir)
            if [ -z "$2" ]; then
                echo -e "${RED}[ERROR] Option --tmp-dir requires an argument.${RESET}" >&2
                display_help
                exit 1
            fi
            if [ ! -d "$2" ] || [ ! -w "$2" ]; then
                echo -e "${RED}[ERROR] Temporary directory '$2' does not exist or is not writable.${RESET}" >&2
                exit 1
            fi
            export TMPDIR="$2"
            log INFO "Using custom temporary directory: $TMPDIR"
            shift 2
            continue
            ;;
        *) # Not a global option, must be the command or its arguments
            break
            ;;
    esac
done

if [[ $# -eq 0 ]]; then
    log ERROR "No command specified." # log() is now safe to use
    display_help
    exit 1
fi

# Now, process the command
COMMAND_NAME="$1"
shift # Remove command name from argument list, pass the rest to the function

case "$COMMAND_NAME" in
    send)
        send_file_or_directory "$@"
        exit $?
        ;;
    receive)
        receive_file_or_directory "$@"
        exit $?
        ;;
    delete)
        delete_file_or_directory "$@"
        exit $?
        ;;
    info)
        info_command "$@"
        exit $?
        ;;
    *)
        log ERROR "Invalid command: $COMMAND_NAME"
        display_help
        exit 1
        ;;
esac
