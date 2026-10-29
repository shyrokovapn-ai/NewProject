import json
from datetime import date
from types import SimpleNamespace as NS

import pytest

from app.ai import agenda as ag
from app.ai import agenda_lambda as lam

GOOD = {
    "title": "Sync",
    "items": [{"topic": "Pro pricing", "owner": "Олена", "minutes": 15}],
    "action_items": [{"task": "Compare competitors", "owner": "Taras", "due": "2026-10-23"}],
    "language": "uk",
}


def reply(tool_input, tid="t1"):
    block = NS(type="tool_use", id=tid, name="record_agenda", input=tool_input)
    return NS(content=[block], stop_reason="tool_use", usage=NS(input_tokens=100, output_tokens=50))


class Fake:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.messages = NS(create=self.create)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0)


def use(monkeypatch, fake):
    monkeypatch.setattr(ag, "client", lambda: fake)


def test_parse_ok(monkeypatch):
    use(monkeypatch, Fake(reply(GOOD)))
    parsed, usage = ag.parse_agenda("text", date(2026, 10, 19), "Europe/Kyiv")
    assert parsed.items[0].owner == "Олена"
    assert usage == {"input_tokens": 100, "output_tokens": 50}


def test_retry_once_on_invalid(monkeypatch):
    bad = dict(GOOD, items=[{"topic": "x", "minutes": 9999}])
    fake = Fake(reply(bad), reply(GOOD))
    use(monkeypatch, fake)
    parsed, usage = ag.parse_agenda("text", date(2026, 10, 19), "UTC")
    assert parsed.title == "Sync" and usage["input_tokens"] == 200
    assert fake.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_invalid_twice_raises(monkeypatch):
    bad = dict(GOOD, items=[{"topic": "x", "minutes": 9999}])
    use(monkeypatch, Fake(reply(bad), reply(bad)))
    with pytest.raises(ag.AgendaParseError):
        ag.parse_agenda("text", date(2026, 10, 19), "UTC")


def test_no_tool_call_raises(monkeypatch):
    refusal = NS(content=[], stop_reason="refusal", usage=NS(input_tokens=1, output_tokens=1))
    use(monkeypatch, Fake(refusal))
    with pytest.raises(ag.AgendaParseError):
        ag.parse_agenda("text", date(2026, 10, 19), "UTC")


def test_cost():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert ag.cost_usd("anthropic.claude-opus-5-5", usage) == 24.0
    assert ag.cost_usd("anthropic.claude-haiku-5-5", usage) == 0.6


def event(body, auth="Bearer x"):
    return {"headers": {"authorization": auth}, "body": json.dumps(body)}


OK_BODY = {"text": "hello", "today": "2026-10-19", "tz": "UTC"}


def test_handler_401(monkeypatch):
    def deny(_):
        raise lam.AuthError("no")

    monkeypatch.setattr(lam, "verify_cognito_token", deny)
    assert lam.handler(event(OK_BODY))["statusCode"] == 401


def test_handler_413_before_model(monkeypatch):
    monkeypatch.setattr(lam, "verify_cognito_token", lambda _: {"sub": "u"})

    def boom(*a):
        raise AssertionError("model must not be called")

    monkeypatch.setattr(ag, "parse_agenda", boom)
    big = dict(OK_BODY, text="a" * 10_001)
    assert lam.handler(event(big))["statusCode"] == 413


def test_handler_400_and_200(monkeypatch):
    monkeypatch.setattr(lam, "verify_cognito_token", lambda _: {"sub": "u"})
    assert lam.handler(event({"text": "x"}))["statusCode"] == 400
    use(monkeypatch, Fake(reply(GOOD)))
    r = lam.handler(event(OK_BODY))
    body = json.loads(r["body"])
    assert r["statusCode"] == 200 and body["prompt_version"] == "agenda-v1"
    assert body["agenda"]["items"][0]["topic"] == "Pro pricing"


def test_handler_422(monkeypatch):
    monkeypatch.setattr(lam, "verify_cognito_token", lambda _: {"sub": "u"})
    refusal = NS(content=[], stop_reason="end_turn", usage=NS(input_tokens=1, output_tokens=1))
    use(monkeypatch, Fake(refusal))
    assert lam.handler(event(OK_BODY))["statusCode"] == 422
