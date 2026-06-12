"""B6 (ADR-024): LLM resilience primitives — retry + circuit breaker.

Current implementation covers hard failures only (exceptions from OpenAI).
See learning-lessons for gap analysis vs. full Hannecke model (semantic/behavioral
failures, DEGRADED state, graduated half-open recovery).
"""

from __future__ import annotations

import logging
import time

import httpx
import openai
from langchain.agents.middleware import AgentMiddleware, ModelRetryMiddleware, ToolRetryMiddleware
from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Minimal asyncio circuit breaker for OpenAI calls.

    States: CLOSED (normal) → OPEN (blocking) → CLOSED (after reset_timeout).
    No HALF-OPEN or DEGRADED — see ADR-024 for upgrade path.

    Exported (not prefixed with _) so middleware and tests can import it.
    """

    def __init__(self, fail_max: int = 3, reset_timeout: float = 30) -> None:
        self._fail_max = fail_max
        self._reset_timeout = reset_timeout
        self._fails = 0
        self._opened_at: float | None = None

    def close(self) -> None:
        """Reset to CLOSED state — used by tests to isolate between runs."""
        self._fails = 0
        self._opened_at = None

    @property
    def is_open(self) -> bool:
        return (
            self._opened_at is not None
            and (time.monotonic() - self._opened_at) < self._reset_timeout
        )

    def _seconds_remaining(self) -> float:
        if self._opened_at is None:
            return 0.0
        return max(0.0, self._reset_timeout - (time.monotonic() - self._opened_at))

    def record_success(self, log_prefix: str = "circuit_breaker") -> None:
        if self._fails > 0:
            logger.info("%s=closed", log_prefix)
        self._fails = 0
        self._opened_at = None

    def record_failure(self, log_prefix: str = "circuit_breaker") -> None:
        self._fails += 1
        if self._fails >= self._fail_max:
            self._opened_at = time.monotonic()
            logger.warning(
                "%s=open fails=%d reset_in=%.0fs",
                log_prefix, self._fails, self._reset_timeout,
            )


llm_breaker = CircuitBreaker(fail_max=3, reset_timeout=30)
api_breaker = CircuitBreaker(fail_max=3, reset_timeout=30)

PT_BR_UNAVAILABLE = (
    "Desculpe, o assistente está temporariamente indisponível. "
    "Por favor, tente novamente em alguns instantes."
)
PT_BR_API_UNAVAILABLE = (
    "Serviço de agendamento temporariamente indisponível. "
    "Por favor, tente novamente em alguns instantes."
)

# Retryable exception groups.
RETRYABLE_LLM_EXCEPTIONS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
)
RETRYABLE_HTTP_EXCEPTIONS = (httpx.ConnectError, httpx.TimeoutException)

# Keep public alias for backwards-compatibility with existing imports.
RETRYABLE_EXCEPTIONS = RETRYABLE_LLM_EXCEPTIONS

# ── Middleware classes  ──────


class LLMCircuitBreakerMiddleware(AgentMiddleware):
    """Circuit breaker for LLM calls inside create_agent.

    Pairs with ModelRetryMiddleware (inner) so the circuit counts complete
    retry sequences, not individual attempts. On open circuit returns a
    pt-BR fallback AIMessage so create_agent exits its loop gracefully.
    """

    async def awrap_model_call(self, request, handler) -> AIMessage:
        if llm_breaker.is_open:
            logger.warning("circuit_breaker=blocked remaining=%.1fs", llm_breaker._seconds_remaining())
            return AIMessage(content=PT_BR_UNAVAILABLE)
        try:
            response = await handler(request)
            llm_breaker.record_success()
            return response
        except (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError):
            llm_breaker.record_failure()
            return AIMessage(content=PT_BR_UNAVAILABLE)


# LLM retry: 3 total attempts, re-raise on exhaustion so the outer circuit
# breaker can count the complete failure sequence.
_llm_retry_middleware = ModelRetryMiddleware(
    max_retries=2,
    retry_on=RETRYABLE_LLM_EXCEPTIONS,
    on_failure="error",
    initial_delay=2.0,
    backoff_factor=2.0,
    jitter=False,
)

# Tool retry: retries REST API transport failures (connect / timeout).
# on_failure="continue" returns a ToolMessage with the error so the LLM can
# recover gracefully instead of crashing the graph.
_tool_retry_middleware = ToolRetryMiddleware(
    max_retries=2,
    retry_on=RETRYABLE_HTTP_EXCEPTIONS,
    on_failure="continue",
    initial_delay=1.0,
    backoff_factor=2.0,
    jitter=False,
)

class APICircuitBreakerMiddleware(AgentMiddleware):
    """Circuit breaker for REST API tool calls inside create_agent.

    Sits inner to ToolRetryMiddleware so each individual retry attempt
    is counted. After fail_max=3 transport failures the circuit opens:
    awrap_tool_call returns a pt-BR ToolMessage immediately — ToolRetryMiddleware
    (outer) sees a successful return and stops retrying, achieving fast-fail.
    """

    async def awrap_tool_call(self, request, handler) -> ToolMessage:
        tool_name = request.tool.name if request.tool else request.tool_call["name"]
        tool_call_id = request.tool_call.get("id")

        if api_breaker.is_open:
            logger.warning("api_circuit_breaker=blocked remaining=%.1fs", api_breaker._seconds_remaining())
            return ToolMessage(content=PT_BR_API_UNAVAILABLE, tool_call_id=tool_call_id, name=tool_name, status="error")
        try:
            result = await handler(request)
            api_breaker.record_success(log_prefix="api_circuit_breaker")
            return result
        except (httpx.ConnectError, httpx.TimeoutException):
            api_breaker.record_failure(log_prefix="api_circuit_breaker")
            raise  # ToolRetryMiddleware (outer) handles the retry


# Module-level instances — exported so tests can call hooks directly.
llm_circuit_breaker_middleware = LLMCircuitBreakerMiddleware()
api_circuit_breaker_middleware = APICircuitBreakerMiddleware()
