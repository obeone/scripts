# -*- coding: utf-8 -*-
"""
Generates and prints shell completion scripts for bash, zsh, and fish.

This module provides the necessary functions to output completion scripts,
enabling dynamic autocompletion for the command-line tool. The scripts
are designed to query the tool itself to fetch live data, such as Kubernetes
contexts, namespaces, and pods.
"""

import sys
import logging

# Initialize logger for the module
logger = logging.getLogger(__name__)

# Shell Completion Templates
BASH_COMPLETION_TEMPLATE = '''\
#!/usr/bin/env bash
# Bash completion script for {script_name}
_ks_py_completions() {{
    local cur prev words cword split=false
    _get_comp_words_by_ref -n : cur prev words cword

   # Stop trying to complete options after --
   local i
   for ((i=1; i<cword; i++)); do
       if [[ "${{words[i]}}" == "--" ]]; then
           # Delegate to default file completion
           _filedir
           return 0
       fi
   done

    case "$prev" in
        -C|--context)
            COMPREPLY=($(compgen -W "$({script_name} --_list-contexts)" -- "$cur"))
            return 0
            ;;
        -n|--namespace)
            local kcontext=$(_get_kcontext_from_cmdline)
            COMPREPLY=($(compgen -W "$({script_name} $kcontext --_list-namespaces)" -- "$cur"))
            return 0
            ;;
        -p|--pod)
            local kcontext=$(_get_kcontext_from_cmdline)
            local knamespace=$(_get_knamespace_from_cmdline)
            if [[ -n "$knamespace" ]]; then
                COMPREPLY=($(compgen -W "$({script_name} $kcontext --namespace "$knamespace" --_list-pods)" -- "$cur"))
            fi
            return 0
            ;;
        -c|--container)
            local kcontext=$(_get_kcontext_from_cmdline)
            local knamespace=$(_get_knamespace_from_cmdline)
            local kpod=$(_get_kpod_from_cmdline)
            if [[ -n "$knamespace" && -n "$kpod" ]]; then
                COMPREPLY=($(compgen -W "$({script_name} $kcontext --namespace "$knamespace" --pod "$kpod" --_list-containers)" -- "$cur"))
            fi
            return 0
            ;;
        -i|--image)
            _filedir
            return 0
            ;;
        -l|--log-level)
            COMPREPLY=($(compgen -W 'debug info warn error' -- "$cur"))
            return 0
            ;;
        --profile)
            _filedir
            return 0
            ;;
    esac

    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W '-C --context -n --namespace -p --pod -c --container -i --image --profile --dry-run -l --log-level -h --help' -- "$cur"))
        return 0
    fi
}}

_get_kcontext_from_cmdline() {{
    local i=1
    while [[ $i -lt $cword ]]; do
        if [[ ${{words[i]}} == "-C" || ${{words[i]}} == "--context" ]]; then
            local j=$((i + 1))
            if [[ $j -lt $cword ]]; then
                echo "--context ${{words[j]}}"
                return
            fi
        fi
        i=$((i + 1))
    done
    echo ""
}}

_get_knamespace_from_cmdline() {{
    local i=1
    while [[ $i -lt $cword ]]; do
        if [[ ${{words[i]}} == "-n" || ${{words[i]}} == "--namespace" ]]; then
            local j=$((i + 1))
            if [[ $j -lt $cword ]]; then
                echo "${{words[j]}}"
                return
            fi
        fi
        i=$((i + 1))
    done
    echo ""
}}

_get_kpod_from_cmdline() {{
    local i=1
    while [[ $i -lt $cword ]]; do
        if [[ ${{words[i]}} == "-p" || ${{words[i]}} == "--pod" ]]; then
            local j=$((i + 1))
            if [[ $j -lt $cword ]]; then
                echo "${{words[j]}}"
                return
            fi
        fi
        i=$((i + 1))
    done
    echo ""
}}

complete -F _ks_py_completions {script_name}
'''

ZSH_COMPLETION_TEMPLATE = r'''#compdef {script_name}
# Zsh completion script for {script_name}

_ks_py_get_contexts() {{
    compadd $( {script_name} --_list-contexts )
}}

_ks_py_get_namespaces() {{
    local kcontext_arg=$(echo $words | sed -n -E 's/.* (--context|-C) ([^ ]*).*/\1 \2/p')
    compadd $( {script_name} $kcontext_arg --_list-namespaces )
}}

_ks_py_get_pods() {{
    local kcontext_arg=$(echo $words | sed -n -E 's/.* (--context|-C) ([^ ]*).*/\1 \2/p')
    local knamespace_val=$(echo $words | sed -n -E 's/.* (--namespace|-n) ([^ ]*).*/\2/p')
    if [[ -n "$knamespace_val" ]]; then
        compadd $( {script_name} $kcontext_arg --namespace "$knamespace_val" --_list-pods )
    fi
}}

_ks_py_get_containers() {{
    local kcontext_arg=$(echo $words | sed -n -E 's/.* (--context|-C) ([^ ]*).*/\1 \2/p')
    local knamespace_val=$(echo $words | sed -n -E 's/.* (--namespace|-n) ([^ ]*).*/\2/p')
    local kpod_val=$(echo $words | sed -n -E 's/.* (--pod|-p) ([^ ]*).*/\2/p')
    if [[ -n "$knamespace_val" && -n "$kpod_val" ]]; then
        compadd $( {script_name} $kcontext_arg --namespace "$knamespace_val" --pod "$kpod_val" --_list-containers )
    fi
}}

_ks_py_completions() {{
    local context state state_descr line=() ret=1
    
    # Stop completing options after --
   if [[ -n "${{words[(I)--]}}" ]]; then
       return 0
   fi

    local -a log_levels
    log_levels=(
        'debug:Log level for detailed debugging'
        'info:Log level for informational messages'
        'warn:Log level for warnings (default)'
        'error:Log level for errors only'
    )

    _arguments -C -s -S \
        '(- *)'{{-C,--context=}}'[Specify kube context]:Kubernetes context:_ks_py_get_contexts' \
        '(- *)'{{-n,--namespace=}}'[Specify namespace]:Kubernetes namespace:_ks_py_get_namespaces' \
        '(- *)'{{-p,--pod=}}'[Specify pod name]:Pod name:_ks_py_get_pods' \
        '(- *)'{{-c,--container=}}'[Specify container name]:Container name:_ks_py_get_containers' \
        '(- *)'{{-i,--image=}}'[Specify debug image]:Debug container image:_files' \
        '(- *)'{{--profile=}}'[Specify security profile]:Security profile:_files' \
        '--dry-run[Only print the command without running it]' \
        '(- *)'{{-l,--log-level=}}'[Set log level]:Log level: _values "Log Level" $log_levels' \
        '(-h --help)'{{-h,--help}}'[Show help message]' \
        '*::Args: ' && ret=0

    return $ret
}}

_ks_py_completions "$@"
'''

FISH_COMPLETION_TEMPLATE = '''\
# Fish completion script for {script_name}

function __ks_py_get_contexts
    {script_name} --_list-contexts
end

function __ks_py_get_namespaces
    set -l kcontext_arg (commandline -opc | string match -r -- '(--context=|-C)([^ ]+)' | string replace -r -- '(--context=|-C)' '')
    set -l context_option
    if test -n "$kcontext_arg"
        set context_option --context $kcontext_arg
    end
    {script_name} $context_option --_list-namespaces
end

function __ks_py_get_pods
    set -l kcontext_arg (commandline -opc | string match -r -- '(--context=|-C)([^ ]+)' | string replace -r -- '(--context=|-C)' '')
    set -l knamespace_arg (commandline -opc | string match -r -- '(--namespace=|-n)([^ ]+)' | string replace -r -- '(--namespace=|-n)' '')
    set -l context_option
    set -l namespace_option
    if test -n "$kcontext_arg"
        set context_option --context $kcontext_arg
    end
    if test -n "$knamespace_arg"
        set namespace_option --namespace $knamespace_arg
    end
    if test -n "$namespace_option"
        {script_name} $context_option $namespace_option --_list-pods
    end
end

function __ks_py_get_containers
    set -l kcontext_arg (commandline -opc | string match -r -- '(--context=|-C)([^ ]+)' | string replace -r -- '(--context=|-C)' '')
    set -l knamespace_arg (commandline -opc | string match -r -- '(--namespace=|-n)([^ ]+)' | string replace -r -- '(--namespace=|-n)' '')
    set -l kpod_arg (commandline -opc | string match -r -- '(--pod=|-p)([^ ]+)' | string replace -r -- '(--pod=|-p)' '')
    set -l context_option
    set -l namespace_option
    set -l pod_option
    if test -n "$kcontext_arg"
        set context_option --context $kcontext_arg
    end
    if test -n "$knamespace_arg"
        set namespace_option --namespace $knamespace_arg
    end
    if test -n "$kpod_arg"
        set pod_option --pod $kpod_arg
    end
    if test -n "$namespace_option" && test -n "$pod_option"
        {script_name} $context_option $namespace_option $pod_option --_list-containers
    end
end

complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l context -s C -d "Specify kube context" -a "(__ks_py_get_contexts)"
complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l namespace -s n -d "Specify namespace" -a "(__ks_py_get_namespaces)"
complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l pod -s p -d "Specify pod name" -a "(__ks_py_get_pods)"
complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l container -s c -d "Specify container name" -a "(__ks_py_get_containers)"
complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l image -s i -d "Specify debug image" -r -F
complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l profile -d "Specify security profile" -r -F
complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l dry-run -d "Only print the command without running it"
complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l log-level -s l -d "Set log level" -a "debug info warn error"
complete -c {script_name} -n "not __fish_seen_subcommand_from --" -l help -s h -d "Show help message"
'''


def print_completion_script(shell: str, script_name: str) -> None:
    """
    Prints the completion script for the specified shell.

    This function selects the appropriate template based on the shell type
    and formats it with the provided script name. If the shell is not
    supported, it logs an error and exits.

    Args:
        shell: The target shell for the completion script (e.g., 'bash', 'zsh', 'fish').
        script_name: The name of the script for which to generate completion.

    Raises:
        SystemExit: If the specified shell is not supported.
    """
    script_content = ""
    if shell == 'bash':
        script_content = BASH_COMPLETION_TEMPLATE.format(script_name=script_name)
    elif shell == 'zsh':
        script_content = ZSH_COMPLETION_TEMPLATE.format(script_name=script_name)
    elif shell == 'fish':
        script_content = FISH_COMPLETION_TEMPLATE.format(script_name=script_name)
    else:
        logger.error(
            "Unsupported shell for completion: %s. Choose from 'bash', 'zsh', or 'fish'.", shell
        )
        sys.exit(1)
    print(script_content)