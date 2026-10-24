from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from .errors import PolicyViolationError
from .policy import PolicyEngine


class ToolRunner:
    """Validate registered tool arguments and results in the current process.

    Policy checks cover strings in dictionaries and sequences. This does not
    isolate tool execution or inspect attributes on arbitrary custom objects.
    """

    def __init__(self, policy: PolicyEngine):
        self.policy = policy
        self._registry: dict[
            str, tuple[Callable[..., Any], type[BaseModel] | None, type[BaseModel] | None]
        ] = {}

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        args_schema: type[BaseModel] | None = None,
        result_schema: type[BaseModel] | None = None,
    ):
        self._registry[name] = (fn, args_schema, result_schema)

    def call(self, name: str, **kwargs) -> Any:
        if name not in self._registry:
            raise KeyError(f"Tool not found: {name}")
        fn, args_schema, result_schema = self._registry[name]

        # Filter before validation so the tool receives arguments satisfying its schema.
        checked_args = self.policy.check_value(kwargs, output=False)
        if args_schema:
            try:
                validated = args_schema(**checked_args)
            except ValidationError as e:
                raise ValueError(f"Invalid tool args for {name}: {e}") from e
            self.policy.check_value(validated, output=False)
            args = validated.model_dump()
            if self.policy.check_value(args, output=False) != args:
                raise PolicyViolationError(
                    "Argument validation produced values that violate policy"
                )
        else:
            args = checked_args

        out = fn(**args)

        if isinstance(out, BaseModel):
            self.policy.check_value(out, output=True)
            serialized = out.model_dump()
            if self.policy.check_value(serialized, output=True) != serialized:
                raise PolicyViolationError(
                    "Result serialization produced values that violate policy"
                )
            if result_schema is None:
                return out
            out = serialized
        out = self.policy.check_value(out, output=True)

        if result_schema:
            if isinstance(out, str):
                import json

                out = self.policy.check_value(json.loads(out), output=True)
            out = result_schema.model_validate(out)
            self.policy.check_value(out, output=True)
            if self.policy.check_value(out.model_dump(), output=True) != out.model_dump():
                raise PolicyViolationError("Result validation produced values that violate policy")

        return out
