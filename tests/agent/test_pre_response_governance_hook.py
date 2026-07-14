"""Behavior contracts for the generic pre-response continuation gate."""

from __future__ import annotations

import sys

import hermes_cli.plugins as plugins
from agent import verify_hooks


def test_pre_response_is_a_supported_hook():
    assert "pre_response" in plugins.VALID_HOOKS


def test_continue_directive_preserves_turn_scope(monkeypatch):
    seen = {}

    def capture(hook_name, **kwargs):
        seen["hook_name"] = hook_name
        seen.update(kwargs)
        return [
            {"action": "allow"},
            {"action": "continue", "message": "  reframe before answering  "},
            {"action": "continue", "message": "ignored"},
        ]

    monkeypatch.setattr(plugins, "invoke_hook", capture)

    assert plugins.get_pre_response_continue_message(
        session_id="s1",
        turn_id="t1",
        platform="cli",
        model="m1",
        attempt=2,
        user_message="design this",
        final_response="I will build a tool",
    ) == "reframe before answering"
    assert seen == {
        "hook_name": "pre_response",
        "session_id": "s1",
        "turn_id": "t1",
        "platform": "cli",
        "model": "m1",
        "attempt": 2,
        "user_message": "design this",
        "final_response": "I will build a tool",
    }


def test_claude_stop_shape_is_accepted(monkeypatch):
    monkeypatch.setattr(
        plugins,
        "invoke_hook",
        lambda hook_name, **kwargs: [
            {"decision": "block", "reason": "run the cognition audit"}
        ],
    )
    assert plugins.get_pre_response_continue_message() == "run the cognition audit"


def test_invalid_directives_fail_open(monkeypatch):
    monkeypatch.setattr(
        plugins,
        "invoke_hook",
        lambda hook_name, **kwargs: [
            "noise",
            {"action": "continue"},
            {"action": "continue", "message": "   "},
            {"action": "continue", "message": 42},
        ],
    )
    assert plugins.get_pre_response_continue_message() is None


def test_response_nudge_bound_is_configurable():
    assert verify_hooks.max_response_nudges({}) == verify_hooks.DEFAULT_MAX_RESPONSE_NUDGES
    assert verify_hooks.max_response_nudges(
        {"agent": {"max_response_nudges": "2"}}
    ) == 2
    assert verify_hooks.max_response_nudges(
        {"agent": {"max_response_nudges": -1}}
    ) == 0
    assert verify_hooks.max_response_nudges(
        {"agent": {"max_response_nudges": "bad"}}
    ) == verify_hooks.DEFAULT_MAX_RESPONSE_NUDGES


def _fresh_run_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    for module_name in list(sys.modules):
        if (
            module_name == "run_agent"
            or module_name.startswith("agent.")
            or module_name.startswith("tools.")
            or module_name.startswith("hermes_")
        ):
            del sys.modules[module_name]
    import run_agent

    return run_agent


def test_pre_response_scaffolding_is_never_durable(monkeypatch, tmp_path):
    run_agent = _fresh_run_agent(monkeypatch, tmp_path)

    assert "_pre_response_synthetic" in run_agent._EPHEMERAL_SCAFFOLDING_FLAGS
    assert run_agent._is_ephemeral_scaffolding(
        {
            "role": "assistant",
            "content": "premature draft",
            "_pre_response_synthetic": True,
        }
    )
    assert run_agent._is_ephemeral_scaffolding(
        {
            "role": "user",
            "content": "[System: reframe]",
            "_pre_response_synthetic": True,
        }
    )
