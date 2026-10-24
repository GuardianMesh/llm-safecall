from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from ..metrics import CallReport


@dataclass
class ProviderResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    cost: float | None = None

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise TypeError("Provider response text must be a string")
        CallReport(0, self.input_tokens, self.output_tokens, self.model, self.cost)


class Provider(Protocol):
    def complete(self, prompt: str, **params) -> ProviderResponse: ...
    def stream(self, prompt: str, **params) -> Iterable[str]: ...
