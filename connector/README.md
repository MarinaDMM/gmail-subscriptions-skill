# gmail-mcp

Local, read-only MCP server that searches several Gmail accounts at once.
Tools: `list_accounts`, `search(account, query, max_results)`, `get_message(account, message_id)`,
`get_attachment(account, message_id, filename)`.
`account` can be an account name or `all`.

## Setup

1. **Google Cloud OAuth client** (once)
   - Enable the Gmail API in a Google Cloud project.
   - Create an OAuth client of type *Desktop app*, download the JSON.
   - Save it as `~/.config/gmail-mcp/client_secret.json`.
   - Keep the consent screen in *Testing* mode and add each Gmail address as a test user.
     Refresh tokens expire after about 7 days in Testing mode, so re-run step 2 when searches start failing with an auth error.

2. **Authorize each account** (repeat per account)

   ```bash
   cd /path/to/gmail-mcp
   ./.venv/bin/python -m gmail_mcp.auth personal
   ```

   Sign in with the matching Gmail address. The account name is what you pass to the tools.

3. **Install**

   ```bash
   python3 -m venv .venv
   ./.venv/bin/pip install -r requirements.txt
   ```

   `mcp` is pinned below 2.0 because v2 renamed `FastMCP`.

4. **Register with Claude Desktop** (`claude_desktop_config.json`)

   ```json
   {
     "mcpServers": {
       "gmail": {
         "command": "/absolute/path/to/gmail-mcp/.venv/bin/python",
         "args": ["-m", "gmail_mcp.server"],
         "cwd": "/absolute/path/to/gmail-mcp"
       }
     }
   }
   ```

## Notes

- Scope is `gmail.readonly`. The server cannot send, modify, or delete mail.
- Tokens live in `~/.config/gmail-mcp/tokens/<name>.json` (mode 600). Set `GMAIL_MCP_HOME` to use another folder.
- Tests: `./.venv/bin/python -m pytest -q tests`

## Attachments

`get_message` lists the files attached to a message (inline logos and icons are hidden).
`get_attachment` downloads one in memory, never to disk, and returns its text:

- PDFs with a text layer: text of the first 30 pages (pypdf, pure Python).
- Plain-text attachments: the text.
- Scanned PDFs: empty text plus a note, because there is no OCR.
- Limit: 15 MB per file; output is cut at `max_chars` (default 20000).

Attachment text is untrusted input. The skills treat it as data, never as instructions.
