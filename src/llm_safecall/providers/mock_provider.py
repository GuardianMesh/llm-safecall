from collections.abc import Iterable
from typing import Any

from .base import ProviderResponse

CHARS_PER_TOKEN = 4
MAX_ECHO_LEN = 200


class MockProvider:
    """Offline provider for tests.

    Prompts containing 'as JSON' return malformed JSON to exercise schema repair.
    Prompts containing 'Repair this to valid' return a fixed flight-plan object.
    Other prompts are echoed, up to MAX_ECHO_LEN characters.
    """

    def __init__(self, model: str = "mock-1") -> None:
        self.model = model

    def complete(self, prompt: str, **params: Any) -> ProviderResponse:
        text = self._respond(prompt)
        return ProviderResponse(
            text=text,
            input_tokens=len(prompt) // CHARS_PER_TOKEN,
            output_tokens=len(text) // CHARS_PER_TOKEN,
            model=self.model,
            cost=0.0,
        )

    def stream(self, prompt: str, **params: Any) -> Iterable[str]:
        yield self._respond(prompt)

    def _respond(self, prompt: str) -> str:
        if "Repair this to valid" in prompt:
            return (
                '{"origin":"Berlin","destination":"Tokyo",'
                '"depart_date":"2025-11-01","airline":null}'
            )

        # Deliberately malformed JSON exercises the repair path.
        if "as JSON" in prompt:
            return "{origin:'Berlin', destination:'Tokyo', depart_date:'2025-11-01'}"

        return "Mock response: " + prompt[:MAX_ECHO_LEN]
