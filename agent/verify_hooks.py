"""Verification and response-loop helpers for round-end policy gates.

``pre_verify`` lets user/plugin policy continue a coding turn after edits.
``pre_response`` is the generic equivalent for reviewing any draft before it is
returned. Both loops are bounded so a broken plugin cannot spin forever.
"""

from __future__ import annotations

from typing import Any, Optional

from utils import is_truthy_value

DEFAULT_MAX_VERIFY_NUDGES = 3
DEFAULT_MAX_RESPONSE_NUDGES = 2

# Returned instead of the model's draft when required governance could not
# evaluate it (enforcement dispatch crashed). Profiles that configure
# ``plugins.required`` opt into fail-closed delivery: an unaudited draft is
# never returned or persisted.
GOVERNANCE_FAIL_CLOSED_RESPONSE = (
    "この回答は認知統治の監査を実行できなかったため配信を止めました。"
    "もう一度、依頼を言い換えて送ってください。"
    "(governance fail-closed: an unaudited draft is never delivered)"
)

# Shipped guidance appended to the verification-stop nudge when code lacks fresh
# verification evidence. Wording mirrors the user-facing "clean your work"
# workflow, but does not create its own extra model turn.
CODING_VERIFY_GUIDANCE = (
    "[Coding] Before you run tests/linters or call this done: if this is "
    "creative UI/visual work, hold off on tests and linters until the user says "
    "they like the result or you're about to commit. And before every commit, "
    "clean your work: keep it KISS/DRY, match the surrounding code style, and be "
    "elitist, shorthand, clever, concise, efficient, and elegant."
)


def max_verify_nudges(config: Optional[dict[str, Any]] = None) -> int:
    """Bound on consecutive ``pre_verify`` continue directives per turn (>= 0)."""
    agent_cfg = _agent_cfg(config)
    raw = agent_cfg.get("max_verify_nudges")
    if raw is None:
        return DEFAULT_MAX_VERIFY_NUDGES
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_VERIFY_NUDGES


def max_response_nudges(config: Optional[dict[str, Any]] = None) -> int:
    """Bound on consecutive ``pre_response`` continuations per turn (>= 0)."""
    agent_cfg = _agent_cfg(config)
    raw = agent_cfg.get("max_response_nudges")
    if raw is None:
        return DEFAULT_MAX_RESPONSE_NUDGES
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_RESPONSE_NUDGES


def coding_verify_guidance(config: Optional[dict[str, Any]] = None) -> Optional[str]:
    """Return the optional guidance appended to verification-stop nudges."""
    if not is_truthy_value(_agent_cfg(config).get("verify_guidance", True), default=True):
        return None
    return CODING_VERIFY_GUIDANCE


def _agent_cfg(config: Optional[dict[str, Any]]) -> dict[str, Any]:
    if config is None:
        try:
            from hermes_cli.config import load_config

            config = load_config()
        except Exception:
            config = {}
    agent_cfg = (config or {}).get("agent") if isinstance(config, dict) else None
    return agent_cfg if isinstance(agent_cfg, dict) else {}


__all__ = [
    "CODING_VERIFY_GUIDANCE",
    "DEFAULT_MAX_RESPONSE_NUDGES",
    "DEFAULT_MAX_VERIFY_NUDGES",
    "GOVERNANCE_FAIL_CLOSED_RESPONSE",
    "coding_verify_guidance",
    "max_response_nudges",
    "max_verify_nudges",
]
