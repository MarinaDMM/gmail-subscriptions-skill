import base64
import json

from gmail_mcp import gmail_ops


class _Call:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeMessages:
    def __init__(self, store):
        self.store = store
        self.last_list_kwargs = None

    def list(self, **kwargs):
        self.last_list_kwargs = kwargs
        return _Call({"messages": [{"id": mid} for mid in self.store]})

    def get(self, id, format, **kwargs):
        return _Call(self.store[id][format])


class FakeService:
    def __init__(self, store):
        self._messages = FakeMessages(store)

    def users(self):
        return self

    def messages(self):
        return self._messages


def _b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode()


STORE = {
    "m1": {
        "metadata": {
            "id": "m1",
            "threadId": "t1",
            "snippet": "Your invoice",
            "payload": {
                "headers": [
                    {"name": "subject", "value": "Invoice #1"},
                    {"name": "From", "value": "billing@example.com"},
                    {"name": "Date", "value": "Mon, 1 Sep 2026"},
                ]
            },
        },
        "full": {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "headers": [{"name": "Subject", "value": "Invoice #1"}],
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/html", "body": {"data": _b64("<p>Hi <b>there</b></p>")}},
                    {"mimeType": "text/plain", "body": {"data": _b64("Plain body")}},
                ],
            },
        },
    },
    "m2": {
        "metadata": {"id": "m2", "threadId": "t2", "snippet": "", "payload": {"headers": []}},
        "full": {
            "id": "m2",
            "payload": {
                "mimeType": "text/html",
                "body": {"data": _b64("<style>x{}</style><p>Only html</p>")},
            },
        },
    },
}


def test_search_returns_metadata_and_passes_query():
    service = FakeService(STORE)
    results = gmail_ops.search_messages(service, "invoice newer_than:1y", max_results=5)

    assert service._messages.last_list_kwargs == {"userId": "me", "q": "invoice newer_than:1y", "maxResults": 5}
    assert results[0] == {
        "id": "m1",
        "thread_id": "t1",
        "subject": "Invoice #1",
        "from": "billing@example.com",
        "date": "Mon, 1 Sep 2026",
        "snippet": "Your invoice",
    }


def test_get_message_prefers_plain_text():
    message = gmail_ops.get_message(FakeService(STORE), "m1")
    assert message["subject"] == "Invoice #1"
    assert message["body"] == "Plain body"


def test_get_message_strips_html_when_no_plain_part():
    message = gmail_ops.get_message(FakeService(STORE), "m2")
    assert message["body"] == "Only html"


def test_list_accounts_reads_token_files(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_MCP_HOME", str(tmp_path))
    assert gmail_ops.list_accounts() == []

    (tmp_path / "tokens").mkdir()
    (tmp_path / "tokens" / "work.json").write_text(json.dumps({}))
    (tmp_path / "tokens" / "personal.json").write_text(json.dumps({}))
    assert gmail_ops.list_accounts() == ["personal", "work"]


# --- attachments -----------------------------------------------------------


def make_pdf(text):
    """Smallest valid one-page PDF with a text layer."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


def _b64_bytes(data):
    return base64.urlsafe_b64encode(data).decode()


PDF_BYTES = make_pdf("Total amount due EUR 123.45")

ATTACHMENT_MESSAGE = {
    "id": "a1",
    "threadId": "ta1",
    "payload": {
        "headers": [{"name": "Subject", "value": "Your bill"}],
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64_bytes(b"See attachment")}},
            {
                "partId": "1",
                "filename": "Invoice-2026.PDF",
                "mimeType": "application/pdf",
                "body": {"attachmentId": "ATT1", "size": len(PDF_BYTES)},
            },
            {
                "partId": "2",
                "filename": "photo.png",
                "mimeType": "image/png",
                "body": {"attachmentId": "ATT2", "size": 4},
            },
            {
                "partId": "3",
                "filename": "note.txt",
                "mimeType": "text/plain",
                "body": {"data": _b64_bytes(b"inline note " * 10), "size": 120},
            },
        ],
    },
}

ATTACHMENT_DATA = {"ATT1": _b64_bytes(PDF_BYTES), "ATT2": _b64_bytes(b"\x89PNG")}


class _Attachments:
    def get(self, userId, messageId, id):
        return _Call({"data": ATTACHMENT_DATA[id]})


class _MessagesWithAttachments(FakeMessages):
    def attachments(self):
        return _Attachments()


class AttachmentService(FakeService):
    def __init__(self):
        super().__init__({"a1": {"full": ATTACHMENT_MESSAGE}})
        self._messages = _MessagesWithAttachments({"a1": {"full": ATTACHMENT_MESSAGE}})


def test_get_message_lists_attachments():
    message = gmail_ops.get_message(AttachmentService(), "a1")
    names = [a["filename"] for a in message["attachments"]]
    assert names == ["Invoice-2026.PDF", "photo.png", "note.txt"]
    assert message["attachments"][0]["attachment_id"] == "ATT1"


def test_get_message_without_attachments_has_empty_list():
    assert gmail_ops.get_message(FakeService(STORE), "m1")["attachments"] == []


def test_reads_pdf_text_by_filename_ignoring_case():
    result = gmail_ops.get_attachment_text(AttachmentService(), "a1", filename="invoice-2026.pdf")
    assert "Total amount due EUR 123.45" in result["text"]
    assert result["pages"] == 1
    assert result["truncated"] is False
    assert result["note"] == ""


def test_reads_pdf_text_by_attachment_id():
    result = gmail_ops.get_attachment_text(AttachmentService(), "a1", attachment_id="ATT1")
    assert "123.45" in result["text"]


def test_reads_inline_text_attachment():
    result = gmail_ops.get_attachment_text(AttachmentService(), "a1", filename="note.txt")
    assert result["text"].startswith("inline note")


def test_truncates_long_text():
    result = gmail_ops.get_attachment_text(AttachmentService(), "a1", filename="note.txt", max_chars=10)
    assert result["text"] == "inline not"
    assert result["truncated"] is True


def test_unsupported_binary_is_reported_not_crashed():
    result = gmail_ops.get_attachment_text(AttachmentService(), "a1", filename="photo.png")
    assert result["text"] == ""
    assert "unsupported" in result["note"]


def test_unknown_attachment_lists_available_names():
    try:
        gmail_ops.get_attachment_text(AttachmentService(), "a1", filename="missing.pdf")
    except ValueError as error:
        assert "Invoice-2026.PDF" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_requires_filename_or_id():
    try:
        gmail_ops.get_attachment_text(AttachmentService(), "a1")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_oversized_attachment_is_refused(monkeypatch):
    monkeypatch.setattr(gmail_ops, "MAX_ATTACHMENT_BYTES", 10)
    try:
        gmail_ops.get_attachment_text(AttachmentService(), "a1", filename="Invoice-2026.PDF")
    except ValueError as error:
        assert "limit" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_pdf_without_text_layer_gets_a_note():
    import io

    from pypdf import PdfWriter

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)
    text, pages, note = gmail_ops._pdf_text(buffer.getvalue())
    assert (text, pages) == ("", 1)
    assert "no text layer" in note


def test_inline_images_are_not_listed_as_attachments():
    payload = {
        "parts": [
            {"partId": "1", "filename": "logo.png", "mimeType": "image/png",
             "headers": [{"name": "Content-ID", "value": "<logo>"}],
             "body": {"attachmentId": "L1", "size": 100}},
            {"partId": "2", "filename": "scan.png", "mimeType": "image/png",
             "headers": [{"name": "Content-Disposition", "value": "attachment"}],
             "body": {"attachmentId": "S1", "size": 100}},
            {"partId": "3", "filename": "bill.pdf", "mimeType": "application/pdf",
             "body": {"attachmentId": "P1", "size": 100}},
        ]
    }
    names = [part["filename"] for part in gmail_ops._attachment_parts(payload)]
    assert names == ["scan.png", "bill.pdf"]
