#!/usr/bin/env bash

# Simple CLI client for transfer.sh
# Supports send, receive, delete and info commands with optional
# encryption and archive handling.

set -u

TRANSFERSH_URL="${TRANSFERSH_URL:-https://transfer.sh}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Detect pv availability for optional progress support
PV_AVAILABLE=false
command -v pv >/dev/null 2>&1 && PV_AVAILABLE=true

COLOR_RED='\e[31m'
COLOR_GRN='\e[32m'
COLOR_YLW='\e[33m'
COLOR_RST='\e[0m'

log() {
    local level="$1"; shift
    local levels=(ERROR WARN INFO DEBUG)
    local want=-1 lvl=-1
    for i in "${!levels[@]}"; do
        [[ ${levels[$i]} == "$LOG_LEVEL" ]] && want=$i
        [[ ${levels[$i]} == "$level" ]] && lvl=$i
    done
    [[ $lvl -lt 0 || $want -lt 0 || $lvl -gt $want ]] && return
    local color="$COLOR_GRN"
    [[ $level == ERROR ]] && color="$COLOR_RED"
    [[ $level == WARN ]] && color="$COLOR_YLW"
    echo -e "${color}[$level]${COLOR_RST} $*" >&2
}

require_cmd() {
    for c in "$@"; do
        command -v "$c" >/dev/null 2>&1 || { log ERROR "$c not installed"; exit 1; }
    done
}

send() {
    local max_days="" max_dl="" key="" auth="" pass=""
    while [[ $# -gt 0 ]]; do
        case $1 in
            -D|--max-days) max_days=$2; shift 2;;
            -d|--max-downloads) max_dl=$2; shift 2;;
            -k|--key) key=$2; shift 2;;
            -u|--user) auth=$2; shift 2;;
            -p|--password) pass=$2; shift 2;;
            -h|--help) help send; return 0;;
            *) break;;
        esac
    done
    [[ $# -eq 0 ]] && { log ERROR "No files given"; help send; return 1; }

    local tmp="" file="$1"
    if [[ $# -gt 1 || -d $1 ]]; then
        tmp=$(mktemp --suffix=.zip)
        zip -r "$tmp" "$@" >/dev/null || { log ERROR "zip failed"; return 1; }
        file="$tmp"
    fi

    local upload_name
    upload_name=$(basename "$file")
    if [[ -n $key ]]; then
        local enc
        enc=$(mktemp --suffix=.enc)
        openssl enc -aes-256-cbc -pbkdf2 -salt -in "$file" -out "$enc" -pass pass:"$key" || return 1
        file="$enc"
        upload_name+=".enc"
    fi

    local args=(-s --fail)
    [[ -n $max_dl ]] && args+=( -H "Max-Downloads: $max_dl" )
    [[ -n $max_days ]] && args+=( -H "Max-Days: $max_days" )
    [[ -n $auth && -n $pass ]] && args+=( --user "$auth:$pass" )

    log INFO "Uploading $upload_name..."
    if $PV_AVAILABLE; then
        local size
        size=$(stat -c %s "$file" 2>/dev/null || echo 0)
        if ! pv -pterb -s "$size" "$file" | \
             curl "${args[@]}" --upload-file - "$TRANSFERSH_URL/$upload_name"; then
            log ERROR "upload failed"
            return 1
        fi
    else
        if ! curl "${args[@]}" --upload-file "$file" "$TRANSFERSH_URL/$upload_name"; then
            log ERROR "upload failed"
            return 1
        fi
    fi

    [[ -n $tmp ]] && rm -f "$tmp"
    [[ -n ${enc-} ]] && rm -f "$enc"
}

receive() {
    local key="" unzip=false
    while [[ $# -gt 0 ]]; do
        case $1 in
            -k|--key) key=$2; shift 2;;
            -u|--unzip) unzip=true; shift;;
            -h|--help) help receive; return 0;;
            *) break;;
        esac
    done
    [[ $# -lt 1 ]] && { log ERROR "URL missing"; help receive; return 1; }
    local url=$1 dest=${2:-.}
    local out
    out="${dest%/}/$(basename "$url")"
    log INFO "Downloading $url"
    if ! curl -L --progress-bar -o "$out" --fail "$url"; then
        log ERROR "download failed"
        return 1
    fi
    if [[ $out == *.enc ]]; then
        [[ -z $key ]] && { read -rsp "Decryption key: " key; echo; }
        local dec
        dec="${out%.enc}"
        openssl enc -d -aes-256-cbc -pbkdf2 -in "$out" -out "$dec" -pass pass:"$key" || return 1
        mv "$dec" "$out" && rm -f "$out".enc 2>/dev/null
        out="$dec"
    fi
    if $unzip && [[ $out == *.zip ]]; then
        unzip -o "$out" -d "$(dirname "$out")" && rm "$out"
    fi
    log INFO "Saved to $out"
}

delete() {
    [[ $# -ne 1 ]] && { help delete; return 1; }
    log INFO "Deleting $1"
    if curl -X DELETE -s --fail "$1"; then
        echo "Deleted"
    else
        log ERROR "delete failed"
        return 1
    fi
}

info() {
    [[ $# -ne 1 ]] && { help info; return 1; }
    local headers
    if ! headers=$(curl -I -s --fail "$1"); then
        log ERROR "request failed"; return 1
    fi
    echo "$headers"
}

help() {
    local topic=${1:-}
    case $topic in
        send)
            cat <<EOT
Usage: transfer.sh send [options] <files...>
  -d, --max-downloads N   Limit downloads
  -D, --max-days N        Limit days stored
  -k, --key KEY           Encrypt with KEY
  -u, --user USER         Basic auth user
  -p, --password PASS     Basic auth password
EOT
            ;;
        receive)
            cat <<EOT
Usage: transfer.sh receive [options] <url> [dest]
  -k, --key KEY   Decrypt with KEY
  -u, --unzip     Unzip if zip file
EOT
            ;;
        delete)
            echo "Usage: transfer.sh delete <delete-url>" ;;
        info)
            echo "Usage: transfer.sh info <url>" ;;
        *)
            cat <<EOT
Usage: transfer.sh <command> [options]
Commands: send receive delete info
Environment:
  TRANSFERSH_URL (default https://transfer.sh)
  LOG_LEVEL      ERROR|WARN|INFO|DEBUG
EOT
            ;;
    esac
}

main() {
    require_cmd curl zip openssl
    local cmd=${1:-}; shift || true
    case $cmd in
        send) send "$@";;
        receive) receive "$@";;
        delete) delete "$@";;
        info) info "$@";;
        -h|--help|'') help ;;
        *) log ERROR "Unknown command: $cmd"; help; return 1;;
    esac
}

main "$@"
