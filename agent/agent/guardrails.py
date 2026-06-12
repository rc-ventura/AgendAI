"""B7 (ADR-029): Guardrail middleware — injection guard + off-scope filter.

PII redaction is handled by langchain's built-in PIIMiddleware (see middleware.py):
  PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True, ...)
  PIIMiddleware("cpf",   detector=CPF_REGEX, ...)
  PIIMiddleware("phone", detector=PHONE_REGEX, ...)

This module only provides the custom InjectionGuardMiddleware because:
  - Injection/off-scope are NOT supported by any built-in LangChain middleware
  - PIIMiddleware supports custom detector= regex so CPF can be added without a custom class

# ── Two guardrail paths — architectural decision record ──────────────────────
#
# PATH 1 — Deterministic (current)
#   Implementation : regex patterns compiled at import time
#   Latency        : ~0ms (pure Python, no I/O)
#   Cost           : zero (no model call per turn)
#   Coverage       : structural injection patterns + explicit off-scope keywords
#   Limitation     : misses semantically novel attacks (metaphors, indirect jailbreaks,
#                    paraphrases not in the pattern list)
#   Calibration    : add/update regex patterns; regression-tested via test_guardrails.py
#
# PATH 2 — Semantic / LLM-based (future upgrade path)
#   Implementation : call a small classifier model (e.g. Llama Guard, GPT-4o-mini with
#                    a binary "safe/unsafe" prompt, or NeMo Guardrails server)
#                    as a pre-filter before the main LLM
#   Latency        : +100–500ms per turn (one extra model round-trip)
#   Cost           : ~$0.0001–0.001 per message (depends on model/provider)
#   Coverage       : semantic understanding — catches paraphrases, metaphors, novel attacks
#   Limitation     : requires calibration on a representative pt-BR corpus before go-live;
#                    false-positive rate must be measured (legitimate scheduling phrases that
#                    coincidentally look "unsafe" to the classifier must be identified and
#                    handled via allowlist or threshold tuning); adds infra/latency budget
#   When to switch : if post-launch monitoring shows deterministic path being bypassed
#                    recurrently, or if the user base scales to general public (uncontrolled
#                    inputs). Trigger: >N bypass incidents per week in production logs.
#
# CURRENT CHOICE: PATH 1 (deterministic)
#   Rationale: clinic is a controlled-access domain (not open internet); corpus of
#   known attacks is small and well-defined; system prompt already serves as a semantic
#   backstop for edge cases; adding LLM cost + latency per turn is not justified yet.
#   Revisit condition: documented in ADR-029.
"""
from __future__ import annotations

import logging
import re

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)

# ── Injection patterns ────────────────────────────────────────────────────────

_INJECTION = re.compile(
    r'(?i)'
    r'('
    r'ignore\s+(\w+\s+){0,2}(instructions?|prompt|rules?)'
    r'|disregard\s+(\w+\s+){0,2}(instructions?|rules?|constraints?|guidelines?)'
    r'|forget\s+(\w+\s+){0,2}(instructions?|prompt)'
    r'|bypass\s+(instructions?|rules?|constraints?|safety)'
    r'|override\s+(\w+\s+){0,2}(instructions?|rules?|constraints?|safety)'
    r'|you\s+are\s+now\s+a(n)?\s+'
    r'|act\s+as\s+(a\s+|an\s+)?(different\s+|new\s+)?(ai|assistant|bot|model|character|human)\b'
    r'|pretend\s+(you\s+are|to\s+be)\s+'
    r'|\bjailbreak\b'
    r'|\bDAN\b'
    r'|do\s+anything\s+now'
    r'|<\s*(system|SYS)\s*>'
    r'|\[\[.{0,200}?\]\]'
    r')'
)

# ── Off-scope patterns ────────────────────────────────────────────────────────

_OFF_SCOPE = re.compile(
    r'(?i)'
    r'('
    r'(escrever|criar|gerar|codificar|programar)\s+(código|programa|script|função|classe|algoritmo)'
    r'|ajude.{0,20}(escrever|criar).{0,20}(código|programa|script)'
    r'|(write|create|generate|code|program)\s+(code|program|script|function|class|algorithm)\b'
    r'|help\s+me\s+write\s+a?\s*(python|javascript|java|c\+\+|rust|go|ruby)?\s*(script|program|code|function)'
    r')'
)

# ── Fallback messages ─────────────────────────────────────────────────────────

_PT_BR_INJECTION = (
    "Não posso processar essa solicitação. "
    "Estou aqui para ajudar com agendamentos médicos na Clínica Saúde."
)
_PT_BR_OFF_SCOPE = (
    "Desculpe, só posso ajudar com agendamentos médicos, consultas e pagamentos "
    "da Clínica Saúde. Para outros assuntos, por favor, consulte os recursos adequados."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_str_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    return str(content) if content else ""


def _is_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def _is_off_scope(text: str) -> bool:
    return bool(_OFF_SCOPE.search(text))


# ── Middleware ────────────────────────────────────────────────────────────────

class InjectionGuardMiddleware(AgentMiddleware):
    """Injection guard + off-scope filter via awrap_model_call.

    Placed outermost in LLM_MIDDLEWARE so injection/off-scope is blocked BEFORE
    any retry or circuit-breaker logic runs. PII redaction is handled separately
    by PIIMiddleware instances (see resilience.py).
    """

    async def awrap_model_call(self, request, handler) -> AIMessage:
        last_human_text = ""
        try:
            messages = getattr(request, "messages", None) or []
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    last_human_text = _extract_str_content(msg.content)
                    break
        except Exception:
            pass

        if last_human_text and _is_injection(last_human_text):
            logger.warning("guardrail=injection_blocked")
            return AIMessage(content=_PT_BR_INJECTION)

        if last_human_text and _is_off_scope(last_human_text):
            logger.warning("guardrail=off_scope_refused")
            return AIMessage(content=_PT_BR_OFF_SCOPE)

        return await handler(request)


injection_guard_middleware = InjectionGuardMiddleware()
