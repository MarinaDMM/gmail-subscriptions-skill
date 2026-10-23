"""Gmail operations, kept free of MCP and OAuth code so they can be tested with a fake service."""

import base64
import os
import re
from pathlib import Path

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
METADATA_HEADERS = ["Subject", "From", "To", "Date"]


def config_home() -> Path:
    return Path(os.environ.get("GMAIL_MCP_HOME", Path.home() / ".config" / "gmail-mcp"))


def tokens_dir() -> Path:
    return config_home() / "tokens"


def list_accounts() -> list[str]:
    """Account names are the token file stems: tokens/<name>.json."""
    directory = tokens_dir()
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


def _header(headers: list[dict], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def search_messages(service, query: str, max_results: int = 10) -> list[dict]:
    listing = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    results = []
    for ref in listing.get("messages", []):
        meta = (
            service.users()
            .messages()
            .get(userId="me", id=ref["id"], format="metadata", metadataHeaders=METADATA_HEADERS)
            .execute()
        )
        headers = meta.get("payload", {}).get("headers", [])
        results.append(
            {
                "id": meta["id"],
                "thread_id": meta.get("threadId"),
                "subject": _header(headers, "Subject"),
                "from": _header(headers, "From"),
                "date": _header(headers, "Date"),
                "snippet": meta.get("snippet", ""),
            }
        )
    return results


def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_body(payload: dict) -> str:
    """Prefer text/plain anywhere in the MIME tree, fall back to text/html with tags stripped."""
    plain, html = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            html.append(_decode(data))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    if plain:
        return "\n".join(plain)
    return _strip_html("\n".join(html))


def get_message(service, message_id: str) -> dict:
    meta = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = meta.get("payload", {})
    headers = payload.get("headers", [])
    return {
        "id": meta["id"],
        "thread_id": meta.get("threadId"),
        "subject": _header(headers, "Subject"),
        "from": _header(headers, "From"),
        "to": _header(headers, "To"),
        "date": _header(headers, "Date"),
        "body": _extract_body(payload),
    }
