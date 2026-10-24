from collections.abc import Iterable

from .base import ProviderResponse


class AnthropicProvider:
    """Anthropic adapter that imports the optional SDK when a request is made."""

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a nonempty string")
        self.model = model
        self.api_key = api_key

    def _client(self):
        try:
            import anthropic
        except ImportError as error:
            raise ImportError(
                "anthropic extra not installed: pip install 'llm-safecall[anthropic]'"
            ) from error
        return anthropic.Anthropic(api_key=self.api_key, max_retries=0)

    def complete(self, prompt: str, **params) -> ProviderResponse:
        self._check_params(params)
        with self._client() as client:
            message = client.messages.create(
                model=self.model,
                max_tokens=params.get("max_tokens", 512),
                messages=[{"role": "user", "content": prompt}],
                timeout=params.get("timeout_s", 20),
            )
            text = "".join(
                part.text for part in message.content if getattr(part, "type", "") == "text"
            )
            usage = getattr(message, "usage", None)
            return ProviderResponse(
                text=text,
                model=getattr(message, "model", None) or self.model,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
            )

    def stream(self, prompt: str, **params) -> Iterable[str]:
        self._check_params(params)
        with self._client() as client:
            with client.messages.stream(
                model=self.model,
                max_tokens=params.get("max_tokens", 512),
                messages=[{"role": "user", "content": prompt}],
                timeout=params.get("timeout_s", 20),
            ) as stream:
                for event in stream:
                    if getattr(event, "type", "") == "content_block_delta":
                        text = getattr(event.delta, "text", None)
                        if text:
                            yield text

    @staticmethod
    def _check_params(params):
        if {"temperature", "top_p", "top_k"}.intersection(params):
            raise ValueError("AnthropicProvider does not support temperature, top_p, or top_k")
