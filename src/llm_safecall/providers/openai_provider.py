from collections.abc import Iterable

from .base import ProviderResponse


class OpenAIProvider:
    """OpenAI adapter that imports the optional SDK when a request is made."""

    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a nonempty string")
        self.model = model
        self.api_key = api_key

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as error:
            raise ImportError(
                "openai extra not installed: pip install 'llm-safecall[openai]'"
            ) from error
        return OpenAI(api_key=self.api_key, max_retries=0)

    def complete(self, prompt: str, **params) -> ProviderResponse:
        with self._client() as client:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=params.get("temperature", 0.2),
                max_tokens=params.get("max_tokens", 512),
                timeout=params.get("timeout_s", 20),
            )
            if not response.choices:
                raise ValueError("OpenAI response has no completion choices")
            usage = getattr(response, "usage", None)
            return ProviderResponse(
                text=response.choices[0].message.content or "",
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
                model=getattr(response, "model", None) or self.model,
            )

    def stream(self, prompt: str, **params) -> Iterable[str]:
        with self._client() as client:
            with client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                timeout=params.get("timeout_s", 20),
                temperature=params.get("temperature", 0.2),
                max_tokens=params.get("max_tokens", 512),
            ) as stream:
                for chunk in stream:
                    if chunk.choices:
                        text = chunk.choices[0].delta.content
                        if text:
                            yield text
