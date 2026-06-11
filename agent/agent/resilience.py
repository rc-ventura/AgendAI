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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised by CircuitBreaker.call_async when the circuit is open."""


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

    async def call_async(self, func, *args, **kwargs):
        if self.is_open:
            logger.warning(
                "circuit_breaker=blocked remaining=%.1fs",
                self._seconds_remaining(),
            )
            raise CircuitOpenError()
        try:
            result = await func(*args, **kwargs)
            if self._fails > 0:
                logger.info("circuit_breaker=closed")
            self._fails = 0
            self._opened_at = None
            return result
        except Exception:
            self._fails += 1
            if self._fails >= self._fail_max:
                self._opened_at = time.monotonic()
                logger.warning(
                    "circuit_breaker=open fails=%d reset_in=%.0fs",
                    self._fails,
                    self._reset_timeout,
                )
            raise


# Singleton used by llm_core — also importable by future AgentMiddleware.
llm_breaker = CircuitBreaker(fail_max=3, reset_timeout=30)

# Tenacity retry — async-safe because _base_invoke is async def.
_RETRYABLE = retry_if_exception_type((
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
))


async def _base_invoke(llm_instance, messages):
    return await llm_instance.ainvoke(messages)


retried_invoke = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=_RETRYABLE,
    reraise=True,
)(_base_invoke)


async def invoke_with_resilience(llm_instance, messages):
    """Call llm_instance.ainvoke with retry + circuit breaker.

    Retries up to 3× on transient OpenAI errors (connection, timeout, rate limit).
    After 3 consecutive call failures the circuit opens for 30s and raises
    CircuitOpenError — callers should return a graceful fallback message.
    """
    return await llm_breaker.call_async(retried_invoke, llm_instance, messages)


PT_BR_UNAVAILABLE = (
    "Desculpe, o assistente está temporariamente indisponível. "
    "Por favor, tente novamente em alguns instantes."
)

# HTTP retry — for calls from api_client to the REST API internal.
http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    reraise=True,
)

# Exports public — retryable exceptions for external use.
RETRYABLE_EXCEPTIONS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
)
