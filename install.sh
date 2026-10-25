#!/bin/sh
# Installs Slothshot on macOS or Linux and starts it.
#
#   curl -LsSf https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/install.sh | sh
#   sh install.sh --source ~/code/slothshot        (install from a local copy instead)
#
# What it does: installs uv if it's missing, offers to install Ollama, installs slothshot as a
# uv tool on Python 3.12, pulls the small model, then runs `slothshot up`.

set -eu

SOURCE="git+https://github.com/kavyasharma200-tech/slothshot"
MODEL="gemma3:1b"
START=1
while [ $# -gt 0 ]; do
    case "$1" in
        --source) SOURCE="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --no-start) START=0; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

say() { printf '  sloth  %s\n' "$1"; }
ask() {
    # Read from the terminal even when this script arrives through a pipe.
    printf '  sloth  %s ' "$1"
    read -r answer </dev/tty || answer="n"
    case "$answer" in ""|[Yy]*) return 0 ;; *) return 1 ;; esac
}

# 1. uv, which brings its own Python
if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv (Astral's Python tool manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Ollama, which runs the model that names your screenshots
if ! command -v ollama >/dev/null 2>&1; then
    if [ "$(uname -s)" = "Darwin" ]; then
        if ask "Ollama isn't installed. Open its download page now? [Y/n]"; then
            open "https://ollama.com/download/mac"
            printf '  sloth  Install it, open the Ollama app, then press Enter. '
            read -r _ </dev/tty || true
        fi
    elif ask "Ollama isn't installed. Install it with Ollama's official script? [Y/n]"; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        say "Skipping. Get it later from https://ollama.com/download; slothshot waits for it."
    fi
fi

# 3. slothshot itself, on Python 3.12 (its OCR engine doesn't support 3.13 yet)
say "Installing slothshot from $SOURCE ..."
uv tool install --force --python 3.12 "$SOURCE"
PATH="$(uv tool dir --bin):$PATH"
export PATH

# 4. the model (about 800 MB, once)
if command -v ollama >/dev/null 2>&1; then
    say "Pulling $MODEL (about 800 MB, only the first time)..."
    ollama pull "$MODEL" || say "Couldn't pull yet. Start Ollama, then run: slothshot pull $MODEL"
fi

say "Installed. Check it any time with: slothshot doctor"
if [ "$START" = 1 ]; then
    exec slothshot up
fi
