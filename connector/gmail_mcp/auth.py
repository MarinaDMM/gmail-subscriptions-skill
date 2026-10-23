"""One-time OAuth consent per Gmail account. Run: python -m gmail_mcp.auth <account-name>"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from gmail_mcp.gmail_ops import READONLY_SCOPE, config_home, tokens_dir


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].replace("-", "").replace("_", "").isalnum():
        sys.exit("usage: python -m gmail_mcp.auth <account-name>   (e.g. personal)")
    name = sys.argv[1]

    client_secret = config_home() / "client_secret.json"
    if not client_secret.is_file():
        sys.exit(f"missing OAuth client file: {client_secret}")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), [READONLY_SCOPE])
    # Opens the browser; sign in with the Gmail address this account name stands for.
    creds = flow.run_local_server(port=0, prompt="select_account consent", access_type="offline")

    tokens_dir().mkdir(parents=True, exist_ok=True)
    target = tokens_dir() / f"{name}.json"
    target.write_text(creds.to_json())
    target.chmod(0o600)
    print(f"saved token for '{name}' to {target}")


if __name__ == "__main__":
    main()
