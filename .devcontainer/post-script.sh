#!/usr/bin/env bash

set -e
set -o pipefail

## Optional Environment Variables:

SKIP_INSTALL_COPILOT_CLI="${SKIP_INSTALL_COPILOT_CLI:-}" # Set to 'true' to skip installing Copilot CLI
COPILOT_CLI_VERSION="${COPILOT_CLI_VERSION:-}"           # Optional version (ex. 'v0.0.369'); defaults to latest when unset
COPILOT_CLI_PREFIX="${COPILOT_CLI_PREFIX:-}"             # Optional install prefix; defaults per official installer

log() {
	printf "========== %s ==========%s" "$1" $'\n'
}

err() {
	printf "[ ERROR ]: %s%s" "$1" $'\n' >&2
	exit 1
}

install_uv() {
	if command -v uv &>/dev/null; then
		return 0
	fi

	if ! command -v curl &>/dev/null; then
		err "'curl' is required to install 'uv'"
	fi

	log "Installing uv"

	curl -LsSf "https://astral.sh/uv/install.sh" | sh

	# uv installs to ~/.local/bin by default
	export PATH="$HOME/.local/bin:$PATH"

	if ! command -v uv &>/dev/null; then
		err "'uv' installation completed but 'uv' is still not on PATH"
	fi

	uv --version
}

install_uv

#Setup easy use of teambot
grep -qxF "alias teambot='uvx --from git+https://github.com/glav/teambot teambot'" ~/.bashrc \
	|| echo "alias teambot='uvx --from git+https://github.com/glav/teambot teambot'" >> ~/.bashrc

uvx --from git+https://github.com/glav/teambot teambot --version  # to ensure its initalised and cached

echo ----------------------------------------------
echo Type 'copilot' to use copilot CLI and login
echo Type 'teambot' to use teambot CLI
echo Type 'teambot init' to initialize teambot in this directory first time
echo ----------------------------------------------
