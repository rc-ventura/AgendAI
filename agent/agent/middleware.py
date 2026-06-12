"""Middleware composition root — assembles LLM_MIDDLEWARE for create_agent.

Each concern lives in its own module:
  resilience.py  → retries + circuit breakers (no guardrail knowledge)
  guardrails.py  → injection guard + off-scope filter (no resilience knowledge)

This file is the only place that knows about all concerns together.
Import LLM_MIDDLEWARE from here, not from resilience or guardrails.

Middleware ordering (outermost → innermost):
  Model call:  injection_guard → pii_email → pii_cpf → pii_phone → llm_cb → llm_retry → LLM
  Tool call:   tool_retry → api_cb → tool fn
  (PIIMiddleware uses before_model/after_model state hooks, orthogonal to awrap_model_call)
"""
from langchain.agents.middleware import PIIMiddleware

from agent.guardrails import injection_guard_middleware
from agent.resilience import (
    api_circuit_breaker_middleware,
    llm_circuit_breaker_middleware,
    _llm_retry_middleware,
    _tool_retry_middleware,
)

# ── PII middleware (built-in, custom detectors for CPF and phone) ─────────────

_CPF_REGEX = r'\b\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b'
_PHONE_REGEX = r'\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)(?:9\s?)?\d{4}[-\s]?\d{4}\b'

pii_email = PIIMiddleware(
    "email", strategy="redact",
    apply_to_input=True, apply_to_output=True, apply_to_tool_results=True,
)
pii_cpf = PIIMiddleware(
    "cpf", detector=_CPF_REGEX, strategy="redact",
    apply_to_input=True, apply_to_output=True, apply_to_tool_results=True,
)
pii_phone = PIIMiddleware(
    "phone", detector=_PHONE_REGEX, strategy="redact",
    apply_to_input=True, apply_to_output=True, apply_to_tool_results=True,
)

# ── Assembled stack ────────────────────────────────────────────────────────────

LLM_MIDDLEWARE = [
    injection_guard_middleware,   # injection + off-scope block
    pii_email,                    # email redaction (built-in PIIMiddleware)
    pii_cpf,                      # CPF redaction (custom detector)
    pii_phone,                    # phone redaction (custom detector)
    llm_circuit_breaker_middleware,
    _llm_retry_middleware,
    _tool_retry_middleware,
    api_circuit_breaker_middleware,
]
