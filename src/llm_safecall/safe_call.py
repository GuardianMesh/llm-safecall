from __future__ import annotations

import json
import math
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from .budget import Budget
from .cache import Cache
from .errors import (
    BudgetExceededError,
    CircuitOpenError,
    ModerationError,
    PolicyViolationError,
    RateLimitExceededError,
)
from .ids import new_call_id
from .logger import log_json
from .metrics import CallReport, time_it
from .moderation import check_input, check_output
from .policy import PolicyConfig, PolicyEngine
from .providers.base import Provider, ProviderResponse
from .rate_limit import TokenBucket
from .redact import redact_text


class LLMText(str):
    """String result with an attached call report."""

    def __new__(cls, value: str):
        return super().__new__(cls, value)


def _attach_report(result, report):
    if isinstance(result, str) and not isinstance(result, LLMText):
        result = LLMText(result)
    object.__setattr__(result, "_report", report)
    return result


def _retryable(error: BaseException) -> bool:
    if isinstance(
        error,
        (
            TypeError,
            ValueError,
            ImportError,
            AttributeError,
            RateLimitExceededError,
            BudgetExceededError,
            PolicyViolationError,
            ModerationError,
        ),
    ):
        return False
    status = getattr(error, "status_code", None)
    return status is None or (
        isinstance(status, int) and (status in {408, 409, 429} or status >= 500)
    )


def _sum_usage(responses, field):
    values = [getattr(response, field) for response in responses]
    return sum(values) if values and all(value is not None for value in values) else None


class _CompatCircuit:
    def __init__(self, parent):
        self._p = parent

    def record_success(self):
        self._p._record_success()

    def record_failure(self):
        self._p._record_failure()


class SafeCall:
    def __init__(
        self,
        llm: Provider,
        output: type[BaseModel] | None = None,
        moderation: bool = True,
        timeout_s: float = 20,
        retries: int = 2,
        redact: list[str] | None = None,
        cache: Cache | None = None,
        policy: PolicyEngine | None = None,
        budget: Budget | None = None,
        rate_limit: TokenBucket | None = None,
        org_name: str | None = None,
        fail_safe: bool = False,
        fail_safe_return: str = "",
        **params,
    ):
        if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 10:
            raise ValueError("retries must be an integer from 0 to 10")
        if (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, (int, float))
            or not math.isfinite(timeout_s)
            or timeout_s <= 0
        ):
            raise ValueError("timeout_s must be a finite positive number")
        if not isinstance(moderation, bool) or not isinstance(fail_safe, bool):
            raise ValueError("moderation and fail_safe must be booleans")
        if not isinstance(fail_safe_return, str):
            raise ValueError("fail_safe_return must be a string")
        if output is not None and (
            not isinstance(output, type) or not issubclass(output, BaseModel)
        ):
            raise TypeError("output must be a Pydantic model class")
        if redact is not None and (
            not isinstance(redact, list)
            or not all(isinstance(item, str) and item in {"email", "phone"} for item in redact)
        ):
            raise ValueError("redact must be a list containing email and/or phone")
        if not callable(getattr(llm, "complete", None)) or not callable(
            getattr(llm, "stream", None)
        ):
            raise TypeError("llm must implement complete() and stream()")
        self.llm, self.output, self.moderation = llm, output, moderation
        self.timeout_s, self.retries, self.params = timeout_s, retries, params
        self.redactors = list(redact or [])
        self.cache = cache if cache is not None else Cache()
        self._cache_namespace = uuid4().hex
        self.circuit_failures = 0
        self.circuit_threshold = 5
        self.policy = policy or PolicyEngine(PolicyConfig())
        self.budget = budget
        self.rate_limit = rate_limit
        self.org_name = org_name
        self.fail_safe = fail_safe
        self.fail_safe_return = fail_safe_return
        self.circuit = _CompatCircuit(self)

    def _circuit_open(self) -> bool:
        return self.circuit_failures >= self.circuit_threshold

    def _record_success(self):
        self.circuit_failures = 0

    def _record_failure(self):
        self.circuit_failures += 1

    def reset_circuit(self):
        """Allow another request after investigating the failures that opened the circuit."""
        self._record_success()

    def _clean_prompt(self, prompt: str) -> str:
        if not isinstance(prompt, str):
            raise TypeError("Prompt must be a string")
        if len(prompt) > self.policy.cfg.max_input_chars:
            raise PolicyViolationError("Prompt too long", {"max": self.policy.cfg.max_input_chars})
        cleaned = redact_text(prompt, self.redactors)
        if self.moderation:
            check_input(cleaned)
        return self.policy.pre_call(cleaned)

    def _call(self, prompt: str) -> ProviderResponse:
        # Every outbound request, including repairs, crosses the same input checks.
        cleaned = self._clean_prompt(prompt)
        response = None
        for attempt in Retrying(
            stop=stop_after_attempt(self.retries + 1),
            wait=wait_exponential_jitter(1, 4),
            retry=retry_if_exception(_retryable),
            reraise=True,
        ):
            with attempt:
                if self.budget:
                    self.budget.assert_available()
                if self.rate_limit:
                    self.rate_limit.take(1.0)
                response = self.llm.complete(cleaned, timeout_s=self.timeout_s, **self.params)
                if not isinstance(response, ProviderResponse):
                    raise TypeError("Provider.complete() must return ProviderResponse")
        if response is None:
            raise RuntimeError("Retry loop did not run")
        if self.budget and response.cost is not None:
            self.budget.add(response.model, response.cost)
        return response

    def _filter_output(self, text: str) -> str:
        text = self.policy.post_call(text, schema_expected=False)
        if self.moderation:
            check_output(text)
        if self.output is None:
            return text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        value = self.policy.check_value(parsed, output=True)
        if self.moderation:
            check_output(json.dumps(value, ensure_ascii=False))
        return json.dumps(value, ensure_ascii=False)

    def _validate_output(self, text: str):
        text = self._filter_output(text)
        if self.output is None:
            return text, text
        result = self.output.model_validate_json(text)
        self.policy.check_value(
            result, output=True, moderation=check_output if self.moderation else None
        )
        validated = result.model_dump(mode="json")
        if self.policy.check_value(validated, output=True) != validated:
            raise PolicyViolationError("Schema validation produced output that violates policy")
        if self.moderation:
            check_output(json.dumps(validated, ensure_ascii=False))
        return result, text

    def _generate_core(self, prompt: str):
        call_id = new_call_id()
        if self._circuit_open():
            raise CircuitOpenError("Circuit is open due to recent failures.")
        cleaned = self._clean_prompt(prompt)
        key = None
        try:
            key = self.cache.key(
                cleaned,
                {
                    "namespace": self._cache_namespace,
                    "params": self.params,
                    "model": getattr(self.llm, "model", None),
                },
                self.output,
            )
        except (TypeError, ValueError):
            pass
        hit = self.cache.get(key) if key is not None else None
        if hit is not None:
            try:
                if not isinstance(hit, dict) or not isinstance(hit.get("text"), str):
                    raise ValueError("Invalid cache record")
                result, _ = self._validate_output(hit["text"])
                report = CallReport(**hit["report"])
                result = _attach_report(result, report)
            except (KeyError, TypeError, ValueError, PolicyViolationError, ModerationError):
                pass
            else:
                self._record_success()
                log_json("cache_hit", call_id=call_id)
                return result, report
        request = cleaned
        schema = None
        if self.output:
            schema = json.dumps(self.output.model_json_schema(), ensure_ascii=False)
            request = f"Return only JSON matching this schema:\n{schema}\n\nRequest:\n{cleaned}"
        request = self._clean_prompt(request)
        responses = []
        with time_it() as timing:
            try:
                log_json("llm_call_start", call_id=call_id, model=getattr(self.llm, "model", None))
                response = self._call(request)
                responses.append(response)
                try:
                    result, text = self._validate_output(response.text)
                except (json.JSONDecodeError, ValidationError):
                    if not self.output:
                        raise
                    # Security rejections are not repairable. Only syntax/schema errors reach here.
                    repair = (
                        f"Repair this to valid JSON matching this schema:\n{schema}\n"
                        f"Return only JSON. Previous output:\n{self._filter_output(response.text)}"
                    )
                    response = self._call(repair)
                    responses.append(response)
                    result, text = self._validate_output(response.text)
            except (RateLimitExceededError, BudgetExceededError):
                raise
            except Exception as error:
                self._record_failure()
                log_json("llm_call_error", call_id=call_id, error=type(error).__name__)
                raise
        report = CallReport(
            latency_ms=timing.elapsed_ms,
            input_tokens=_sum_usage(responses, "input_tokens"),
            output_tokens=_sum_usage(responses, "output_tokens"),
            model=responses[-1].model or getattr(self.llm, "model", None),
            cost_estimate=_sum_usage(responses, "cost"),
        )
        result = _attach_report(result, report)
        if key is not None:
            self.cache.set(key, {"text": text, "report": report.model_dump()})
        self._record_success()
        log_json("llm_call_end", call_id=call_id, latency_ms=report.latency_ms)
        return result, report

    def generate(self, prompt: str):
        if not self.fail_safe:
            return self._generate_core(prompt)[0]
        try:
            return self._generate_core(prompt)[0]
        except Exception:
            fallback = LLMText(self.fail_safe_return)
            report = CallReport(latency_ms=0, model=getattr(self.llm, "model", None))
            return _attach_report(fallback, report)

    def stream_generate(self, prompt: str):
        """Yield filtered chunks; split patterns still require whole-response validation."""
        try:
            if self._circuit_open():
                raise CircuitOpenError("Circuit is open due to recent failures.")
            cleaned = self._clean_prompt(prompt)
            if self.budget:
                self.budget.assert_available()
            if self.rate_limit:
                self.rate_limit.take(1.0)
            total_chars = 0
            filtered_chars = 0
            try:
                stream = iter(self.llm.stream(cleaned, timeout_s=self.timeout_s, **self.params))
                try:
                    for chunk in stream:
                        if not isinstance(chunk, str):
                            raise TypeError("Provider.stream() must yield strings")
                        total_chars += len(chunk)
                        if total_chars > self.policy.cfg.max_output_chars:
                            raise PolicyViolationError("Stream exceeds max_output_chars")
                        text = self.policy.post_call(chunk, schema_expected=False)
                        filtered_chars += len(text)
                        if filtered_chars > self.policy.cfg.max_output_chars:
                            raise PolicyViolationError("Stream exceeds max_output_chars")
                        if self.moderation:
                            check_output(text)
                        yield text
                finally:
                    close = getattr(stream, "close", None)
                    if callable(close):
                        close()
            except Exception:
                self._record_failure()
                raise
            else:
                self._record_success()
        except Exception:
            if self.fail_safe:
                yield self.fail_safe_return
                return
            raise
