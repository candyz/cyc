#!/usr/bin/env bash
# ==============================================================================
# cyc One-Line Installer
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/candyz/cyc/main/install.sh | bash
# ==============================================================================

set -euo pipefail

CYC_REPO="git+https://github.com/candyz/cyc.git"

# Colors for terminal output
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info() {
    printf "${CYAN}${BOLD}==>${RESET} ${BOLD}%s${RESET}\n" "$1"
}

success() {
    printf "${GREEN}${BOLD}✓ %s${RESET}\n" "$1"
}

warn() {
    printf "${YELLOW}${BOLD}! %s${RESET}\n" "$1"
}

error() {
    printf "${RED}${BOLD}✗ %s${RESET}\n" "$1" >&2
}

# 1. Check / Install uv
ensure_uv() {
    # Check if uv is already in PATH
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi

    # Check common standalone uv install paths (~/.local/bin or ~/.cargo/bin)
    if [ -x "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
        return 0
    elif [ -x "$HOME/.cargo/bin/uv" ]; then
        export PATH="$HOME/.cargo/bin:$PATH"
        return 0
    fi

    info "uv is not found. Installing uv (modern Python package and tool manager)..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        error "Neither curl nor wget found. Please install curl or wget first."
        exit 1
    fi

    # Add to current shell PATH
    if [ -x "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    elif [ -x "$HOME/.cargo/bin/uv" ]; then
        export PATH="$HOME/.cargo/bin:$PATH"
    fi

    if ! command -v uv >/dev/null 2>&1; then
        error "Failed to locate uv after installation. Please restart your shell and try again."
        exit 1
    fi
    success "uv installed successfully!"
}

main() {
    printf "\n"
    printf "${CYAN}${BOLD}   ___ _   _  ___ ${RESET}\n"
    printf "${CYAN}${BOLD}  / __| | | |/ __|${RESET}  Autonomous Coding Agent & CLI Assistant\n"
    printf "${CYAN}${BOLD} | (__| |_| | (__ ${RESET}\n"
    printf "${CYAN}${BOLD}  \___|\__, |\___|${RESET}\n"
    printf "${CYAN}${BOLD}       |___/      ${RESET}\n\n"

    ensure_uv

    info "Installing cyc via 'uv tool'..."
    uv tool install --force "${CYC_REPO}"

    # Ensure ~/.local/bin is in PATH for current session advice
    local bin_dir="$HOME/.local/bin"
    case ":${PATH}:" in
        *:"${bin_dir}":*) ;;
        *)
            warn "${bin_dir} is not in your PATH."
            warn "Please add it to your shell configuration (e.g. ~/.bashrc or ~/.zshrc):"
            printf "\n    export PATH=\"\$HOME/.local/bin:\$PATH\"\n\n"
            ;;
    esac

    printf "\n"
    success "cyc has been installed successfully!"
    printf "\n"
    printf "To get started:\n"
    printf "  1. Initialize configuration : ${BOLD}cyc init${RESET}\n"
    printf "  2. Start autonomous agent   : ${BOLD}cyc${RESET}\n"
    printf "  3. Update anytime with      : ${BOLD}cyc -u${RESET}\n\n"
}

main "$@"
