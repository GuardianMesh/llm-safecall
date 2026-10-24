import sys
from types import SimpleNamespace

import pytest

from llm_safecall import AnthropicProvider, OpenAIProvider


class Stream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def __iter__(self):
        yield from self.events


class Client:
    def __init__(self, response, stream):
        self.response = response
        self.stream_result = stream
        self.calls = []
        self.closed = False
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.messages = SimpleNamespace(create=self.create, stream=self.stream)

    def create(self, **params):
        self.calls.append(params)
        return self.stream_result if params.get("stream") else self.response

    def stream(self, **params):
        self.calls.append(params)
        return self.stream_result

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


def install_client(monkeypatch, module, factory_name, client):
    factory_calls = []

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return client

    monkeypatch.setitem(sys.modules, module, SimpleNamespace(**{factory_name: factory}))
    return factory_calls


def test_openai_request_usage_timeout_and_lifecycle(monkeypatch):
    stream = Stream(
        [
            SimpleNamespace(choices=[]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="text"))]),
        ]
    )
    client = Client(
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="result"))],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=7),
            model="served-model",
        ),
        stream,
    )
    calls = install_client(monkeypatch, "openai", "OpenAI", client)
    provider = OpenAIProvider(model="requested-model", api_key="test-key")
    response = provider.complete("Hello", timeout_s=2.5, max_tokens=42, temperature=0)
    assert (response.text, response.input_tokens, response.output_tokens, response.model) == (
        "result",
        3,
        7,
        "served-model",
    )
    assert client.calls[0]["timeout"] == 2.5
    assert client.calls[0]["max_tokens"] == 42
    assert client.calls[0]["temperature"] == 0
    assert client.closed
    assert calls == [{"api_key": "test-key", "max_retries": 0}]
    assert list(provider.stream("Hello", timeout_s=3)) == ["text"]
    assert client.calls[1]["timeout"] == 3
    assert stream.closed


def test_openai_closes_stream_when_consumer_stops_early(monkeypatch):
    stream = Stream(
        [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="first"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="second"))]),
        ]
    )
    client = Client(None, stream)
    install_client(monkeypatch, "openai", "OpenAI", client)
    iterator = OpenAIProvider().stream("Hello")
    assert next(iterator) == "first"
    iterator.close()
    assert stream.closed and client.closed


def test_anthropic_request_usage_timeout_and_lifecycle(monkeypatch):
    stream = Stream(
        [
            SimpleNamespace(type="message_start"),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text="text")),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(partial_json="{}")),
        ]
    )
    client = Client(
        SimpleNamespace(
            content=[SimpleNamespace(type="text", text="result"), SimpleNamespace(type="tool_use")],
            usage=SimpleNamespace(input_tokens=3, output_tokens=7),
            model="served-model",
        ),
        stream,
    )
    calls = install_client(monkeypatch, "anthropic", "Anthropic", client)
    provider = AnthropicProvider(model="requested-model", api_key="test-key")
    response = provider.complete("Hello", timeout_s=2.5, max_tokens=42)
    assert (response.text, response.input_tokens, response.output_tokens, response.model) == (
        "result",
        3,
        7,
        "served-model",
    )
    assert client.calls[0]["timeout"] == 2.5
    assert client.calls[0]["max_tokens"] == 42
    assert calls == [{"api_key": "test-key", "max_retries": 0}]
    assert client.closed
    assert list(provider.stream("Hello", timeout_s=3)) == ["text"]
    assert stream.closed


@pytest.mark.parametrize(
    "module,provider", [("openai", OpenAIProvider), ("anthropic", AnthropicProvider)]
)
def test_missing_optional_sdk_has_install_guidance(monkeypatch, module, provider):
    monkeypatch.setitem(sys.modules, module, None)
    with pytest.raises(ImportError, match="extra not installed"):
        provider().complete("Hello")


def test_anthropic_uses_supported_default_without_removed_sampling_parameters(monkeypatch):
    client = Client(SimpleNamespace(content=[], usage=None), Stream([]))
    install_client(monkeypatch, "anthropic", "Anthropic", client)
    provider = AnthropicProvider()
    provider.complete("Hello")
    assert list(provider.stream("Hello")) == []
    assert all(call["model"] == "claude-sonnet-4-6" for call in client.calls)
    assert all("temperature" not in call for call in client.calls)
    for name in ("temperature", "top_p", "top_k"):
        with pytest.raises(ValueError, match="does not support"):
            provider.complete("Hello", **{name: 0.1})
        with pytest.raises(ValueError, match="does not support"):
            list(provider.stream("Hello", **{name: 0.1}))
    assert len(client.calls) == 2
