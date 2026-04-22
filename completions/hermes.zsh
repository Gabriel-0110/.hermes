#compdef hermes
# Hermes Agent profile completion
# Add to ~/.zshrc: eval "$(hermes completion zsh)"

_hermes() {
    local -a profiles
    profiles=(default)
    if [[ -d "$HOME/.hermes/profiles" ]]; then
        profiles+=("${(@f)$(ls $HOME/.hermes/profiles 2>/dev/null)}")
    fi

    _arguments \
        '-p[Profile name]:profile:($profiles)' \
        '--profile[Profile name]:profile:($profiles)' \
        '1:command:(chat model gateway setup status cron doctor dump config skills tools mcp sessions profile update version)' \
        '*::arg:->args'

    case $words[1] in
        profile)
            _arguments '1:action:(list use create delete show alias rename export import)' \
                        '2:profile:($profiles)'
            ;;
    esac
}

_hermes "$@"

