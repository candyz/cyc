"""Shell completion generation (Bash & Zsh) for cyc CLI."""

BASH_COMPLETION_SCRIPT = r"""# bash completion for cyc

_cyc_completion() {
    local cur prev opts providers
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="-v --version -p --provider -m --model -s --system -c --config --init -f --force --agent -y --yes --read-only -r --resume --sessions --trust --no-trust --completion init"
    providers="ollama openrouter omlx nvidia gemini agy opencode"

    case "${prev}" in
        -p|--provider)
            COMPREPLY=( $(compgen -W "${providers}" -- "${cur}") )
            return 0
            ;;
        -c|--config)
            COMPREPLY=( $(compgen -f -- "${cur}") )
            return 0
            ;;
        -r|--resume)
            local session_dir="${HOME}/.local/share/cyc/sessions"
            local sessions=""
            if [ -d "${session_dir}" ]; then
                sessions=$(find "${session_dir}" -name "*.json" -exec basename {} .json \; 2>/dev/null)
            fi
            COMPREPLY=( $(compgen -W "${sessions} LATEST agy claude pi opencode cyc" -- "${cur}") )
            return 0
            ;;
        --completion)
            COMPREPLY=( $(compgen -W "bash zsh" -- "${cur}") )
            return 0
            ;;
        -m|--model|-s|--system)
            # Cannot statically autocomplete freeform text/model
            return 0
            ;;
    esac

    if [[ "${cur}" == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi
}

complete -F _cyc_completion cyc
"""

ZSH_COMPLETION_SCRIPT = r"""#compdef cyc

_cyc() {
    local -a opts
    opts=(
        '(-v --version)'{-v,--version}'[Show version information]'
        '(-p --provider)'{-p,--provider}'[Specify provider]:provider:(ollama openrouter omlx nvidia gemini agy opencode)'
        '(-m --model)'{-m,--model}'[Specify model name]:model:'
        '(-s --system)'{-s,--system}'[Set system prompt]:system prompt:'
        '(-c --config)'{-c,--config}'[Custom config path]:config file:_files'
        '--init[Generate default configuration file]'
        '(-f --force)'{-f,--force}'[Force overwrite existing config during init]'
        '--agent[Enable autonomous Coding Agent mode]'
        '(-y --yes)'{-y,--yes}'[Auto-approve all tool actions without interactive prompt]'
        '--read-only[Block all mutation tools (write_file, replace, run_command)]'
        '(-r --resume)'{-r,--resume}'[Resume a previous session by ID/prefix (or latest)]'
        '--sessions[List all saved chat & agent sessions and exit]'
        '--trust[Explicitly trust current workspace without prompting]'
        '--no-trust[Explicitly restrict current workspace (force Read-Only mode)]'
        '--completion[Generate shell completion script (bash or zsh)]:shell:(bash zsh)'
        '*:prompt:_files'
    )
    _arguments -s $opts
}

_cyc "$@"
"""

def get_completion_script(shell: str = "bash") -> str:
    """Return completion script for the requested shell (bash or zsh)."""
    shell_lower = shell.lower().strip()
    if shell_lower == "zsh":
        return ZSH_COMPLETION_SCRIPT
    return BASH_COMPLETION_SCRIPT
