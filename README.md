# gmail-subscriptions skill

A Claude skill plus a small local MCP server that searches several Gmail accounts at once (read-only)
and uses that to audit paid subscriptions and recurring charges.

- `SKILL.md`: the skill (audit workflow and output format).
- `connector/`: the local MCP server (`list_accounts`, `search`, `get_message`), scope `gmail.readonly` only.

## Install

```bash
git clone <this-repo-url> ~/.claude/skills/gmail-subscriptions
cd ~/.claude/skills/gmail-subscriptions && ./setup.sh
```

Then follow the printed steps. You need your own Google Cloud OAuth client (Desktop app) with the Gmail API
enabled and your Gmail addresses added as test users; see `connector/README.md`.

## Privacy

- Your OAuth client file and tokens live in `~/.config/gmail-mcp/`, outside this repository. Never commit them.
- The server only reads mail, and only on your machine. Nothing is sent anywhere except to Google's Gmail API.
- In Google's Testing mode, tokens expire after about 7 days; rerun the sign-in command when that happens.
