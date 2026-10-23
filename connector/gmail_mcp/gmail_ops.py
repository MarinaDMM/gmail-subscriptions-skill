"""Gmail operations, kept free of MCP and OAuth code so they can be tested with a fake service."""

import base64
import io
import os
import re
from pathlib import Path

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
METADATA_HEADERS = ["Subject", "From", "To", "Date"]
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 30
DEFAULT_MAX_CHARS = 20000


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
        "attachments": [
            {k: part[k] for k in ("attachment_id", "filename", "mime_type", "size")}
            for part in _attachment_parts(payload)
        ],
    }


def _attachment_parts(payload: dict) -> list[dict]:
    """Every MIME part that carries a file, with the ids needed to fetch it."""
    found = []

    def is_inline_image(part: dict) -> bool:
        # Logos and icons embedded in the HTML carry a Content-ID; they are not documents.
        has_cid = any(h.get("name", "").lower() in ("content-id", "x-attachment-id") for h in part.get("headers", []))
        return has_cid and part.get("mimeType", "").startswith("image/")

    def walk(part: dict) -> None:
        body = part.get("body", {})
        if part.get("filename") and (body.get("attachmentId") or body.get("data")) and not is_inline_image(part):
            found.append(
                {
                    "attachment_id": body.get("attachmentId", ""),
                    "part_id": part.get("partId", ""),
                    "inline_data": body.get("data"),
                    "filename": part["filename"],
                    "mime_type": part.get("mimeType", ""),
                    "size": body.get("size", 0),
                }
            )
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return found


def _pdf_text(data: bytes) -> tuple[str, int, str]:
    """Return (text, page_count, note). Needs a text layer; scanned PDFs yield an empty string."""
    from pypdf import PdfReader  # imported here so the rest of the module works without it

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        return "", 0, "PDF is password protected"

    pages = reader.pages[:MAX_PDF_PAGES]
    text = "\n".join((page.extract_text() or "") for page in pages).strip()
    note = ""
    if len(reader.pages) > MAX_PDF_PAGES:
        note = f"only the first {MAX_PDF_PAGES} of {len(reader.pages)} pages were read"
    if not text:
        note = "no text layer found (probably a scan); the amount cannot be read automatically"
    return text, len(reader.pages), note


def get_attachment_text(
    service, message_id: str, attachment_id: str = "", filename: str = "", max_chars: int = DEFAULT_MAX_CHARS
) -> dict:
    """Download one attachment and return its text. Select it by filename (stable) or attachment_id."""
    if not attachment_id and not filename:
        raise ValueError("give filename or attachment_id (both are listed by get_message)")

    meta = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    parts = _attachment_parts(meta.get("payload", {}))
    wanted = [
        part
        for part in parts
        if (attachment_id and part["attachment_id"] == attachment_id)
        or (filename and part["filename"].lower() == filename.lower())
    ]
    if not wanted:
        names = [part["filename"] for part in parts] or "none"
        raise ValueError(f"no matching attachment on this message; available: {names}")
    part = wanted[0]

    if part["size"] > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"attachment is {part['size']} bytes, over the {MAX_ATTACHMENT_BYTES} byte limit")

    if part["attachment_id"]:
        raw = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=part["attachment_id"])
            .execute()["data"]
        )
    else:
        raw = part["inline_data"]
    data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))

    pages, note = 0, ""
    if data.startswith(b"%PDF"):
        text, pages, note = _pdf_text(data)
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "filename": part["filename"],
                "mime_type": part["mime_type"],
                "size": len(data),
                "pages": 0,
                "text": "",
                "truncated": False,
                "note": "unsupported file type; only PDF and text attachments can be read",
            }

    truncated = len(text) > max_chars
    return {
        "filename": part["filename"],
        "mime_type": part["mime_type"],
        "size": len(data),
        "pages": pages,
        "text": text[:max_chars],
        "truncated": truncated,
        "note": note,
    }
