import pytest
from pydantic import BaseModel, Field, SecretBytes, SecretStr, field_validator

from llm_safecall import MockProvider, PolicyConfig, PolicyEngine, SafeCall, ToolRunner
from llm_safecall.errors import PolicyViolationError
from llm_safecall.providers.base import ProviderResponse


@pytest.mark.parametrize("container", [set, frozenset])
def test_tool_set_arguments_are_checked_before_execution(container):
    runner = ToolRunner(PolicyEngine(PolicyConfig(redact_secrets=False)))
    calls = []
    runner.register("save", lambda values: calls.append(values))
    with pytest.raises(PolicyViolationError):
        runner.call("save", values=container(["Bearer synthetic-token"]))
    assert calls == []


@pytest.mark.parametrize("container", [set, frozenset])
def test_tool_set_results_are_filtered_without_changing_container_type(container):
    runner = ToolRunner(PolicyEngine())
    runner.register("read", lambda: container(["Bearer synthetic-token", "ordinary"]))
    result = runner.call("read")
    assert type(result) is container
    assert result == container(["[REDACTED_GENERIC_BEARER]", "ordinary"])


@pytest.mark.parametrize("key", [b"Bearer synthetic-token", ("Bearer synthetic-token",)])
def test_non_string_dictionary_keys_are_checked_before_tool_execution(key):
    runner = ToolRunner(PolicyEngine())
    calls = []
    runner.register("save", lambda values: calls.append(values))
    with pytest.raises(PolicyViolationError):
        runner.call("save", values={key: "ordinary"})
    assert calls == []


def test_excluded_set_fields_created_by_validation_are_checked():
    class Result(BaseModel):
        values: set[str] = Field(exclude=True)

        @field_validator("values")
        @classmethod
        def decode(cls, value):
            return {"Bearer synthetic-token"}

    class Provider(MockProvider):
        def complete(self, prompt, **params):
            return ProviderResponse('{"values": ["encoded"]}')

    with pytest.raises(PolicyViolationError):
        SafeCall(Provider(), output=Result, retries=0).generate("Hello")


def test_set_values_count_toward_the_structured_character_limit():
    policy = PolicyEngine(PolicyConfig(max_output_chars=10))
    with pytest.raises(PolicyViolationError, match="character limit"):
        policy.check_value({"aaaaaa", "bbbbbb"}, output=True)


@pytest.mark.parametrize("output", [False, True])
def test_structured_limit_includes_expansion_from_redaction_markers(output):
    policy = PolicyEngine(PolicyConfig(max_input_chars=30, max_output_chars=30))
    with pytest.raises(PolicyViolationError, match="character limit"):
        policy.check_value(["Bearer a", "Bearer b"], output=output)


@pytest.mark.parametrize("secret_type", [SecretStr, SecretBytes])
def test_pydantic_secret_fields_do_not_hide_validator_generated_credentials(secret_type):
    class Result(BaseModel):
        value: secret_type

        @field_validator("value")
        @classmethod
        def decode(cls, value):
            raw = "Bearer synthetic-token"
            return secret_type(raw.encode() if secret_type is SecretBytes else raw)

    class Provider(MockProvider):
        def complete(self, prompt, **params):
            return ProviderResponse('{"value": "encoded"}')

    with pytest.raises(PolicyViolationError):
        SafeCall(Provider(), output=Result, retries=0).generate("Hello")

    runner = ToolRunner(PolicyEngine())
    runner.register("read", lambda: {"value": "encoded"}, result_schema=Result)
    with pytest.raises(PolicyViolationError):
        runner.call("read")
