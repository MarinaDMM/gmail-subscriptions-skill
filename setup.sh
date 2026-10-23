#!/usr/bin/env bash
# Builds the connector's virtual environment and prints the Claude Desktop config entry.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONNECTOR="$HERE/connector"

python3 -m venv "$CONNECTOR/.venv"
"$CONNECTOR/.venv/bin/pip" install -q -r "$CONNECTOR/requirements.txt"
"$CONNECTOR/.venv/bin/python" -m pytest -q "$CONNECTOR/tests"

cat <<MSG

Environment ready. Next:
  1. Save your Google OAuth client JSON as ~/.config/gmail-mcp/client_secret.json
  2. For each Gmail account:
       cd "$CONNECTOR" && ./.venv/bin/python -m gmail_mcp.auth <account-name>
  3. Add this under "mcpServers" in claude_desktop_config.json, then restart Claude Desktop:

  "gmail": {
    "command": "$CONNECTOR/.venv/bin/python",
    "args": ["-m", "gmail_mcp.server"],
    "env": { "PYTHONPATH": "$CONNECTOR" }
  }
MSG
