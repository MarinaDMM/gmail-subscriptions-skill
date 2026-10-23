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
