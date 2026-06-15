"""Output-side PII sanitization for the final assistant message (issue #11).

The built-in ``PIIMiddleware`` redacts PII in the model output by calling
``str(message.content)`` and substituting ``[REDACTED_CPF]`` placeholders. When the
model returns structured content blocks (a list such as
``[{"type": "text", "text": "..."}]``), ``str()`` serializes the *whole list*, so the
client ends up seeing the raw Python structure **and** the internal ``[REDACTED_*]``
token (e.g. ``[{'text': '[REDACTED_CPF]', 'type': 'text'}]``) instead of clean prose.

This middleware owns output-side PII handling instead:
  1. Flattens content blocks into plain text — no serialized-list leak.
  2. Masks CPF/phone inline (``***.***.***-**``) so the message stays human-readable
     and never exposes the real value nor the internal redaction token.

CPF/phone redaction on *input* and *tool results* still uses the built-in
PIIMiddleware (those never reach the user directly); only output redaction moved
here. See ADR-029 and docs/learning-lessons/guardrails_langchain_middleware.md.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

# Single source of truth for CPF/phone patterns (also imported by middleware.py
# for the built-in input/tool-result detectors).
CPF_REGEX = r'\b\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b'
PHONE_REGEX = r'\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)(?:9\s?)?\d{4}[-\s]?\d{4}\b'

# Human-readable inline masks shown to the user instead of the real value or the
# internal [REDACTED_*] token.
CPF_MASK = "***.***.***-**"
PHONE_MASK = "(**) *****-****"

_CPF = re.compile(CPF_REGEX)
_PHONE = re.compile(PHONE_REGEX)
_REDACTED_CPF = "[REDACTED_CPF]"
_REDACTED_PHONE = "[REDACTED_PHONE]"


def _flatten_content(content: Any) -> str:
    """Collapse a message content (str or list of content blocks) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content) if content else ""


def _has_pii(text: str) -> bool:
    return bool(
        _REDACTED_CPF in text
        or _REDACTED_PHONE in text
        or _CPF.search(text)
        or _PHONE.search(text)
    )


def sanitize_pii_text(text: str) -> str:
    """Mask CPF/phone inline and replace any leaked [REDACTED_*] token with a mask.

    CPF is masked before phone: once a CPF becomes ``***.***.***-**`` it has no
    digits left for the phone pattern to match.
    """
    text = text.replace(_REDACTED_CPF, CPF_MASK).replace(_REDACTED_PHONE, PHONE_MASK)
    text = _CPF.sub(CPF_MASK, text)
    text = _PHONE.sub(PHONE_MASK, text)
    return text


class PIIOutputSanitizerMiddleware(AgentMiddleware):
    """Masks CPF/phone in the final assistant message without leaking content blocks.

    Runs only when the latest ``AIMessage`` actually contains CPF/phone (or a leaked
    ``[REDACTED_*]`` token), so normal content-block responses pass through untouched.
    """

    def _sanitize_last_ai(self, state: dict[str, Any]) -> dict[str, Any] | None:
        messages = state.get("messages") or []
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if not isinstance(msg, AIMessage) or not msg.content:
                continue

            flat = _flatten_content(msg.content)
            if not _has_pii(flat):
                return None

            sanitized = sanitize_pii_text(flat)
            logger.info("pii_redacted channel=output")
            new_messages = list(messages)
            new_messages[i] = AIMessage(
                content=sanitized,
                id=msg.id,
                name=msg.name,
                tool_calls=msg.tool_calls,
            )
            return {"messages": new_messages}
        return None

    def after_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        return self._sanitize_last_ai(state)

    async def aafter_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        return self._sanitize_last_ai(state)


pii_output_sanitizer = PIIOutputSanitizerMiddleware()
