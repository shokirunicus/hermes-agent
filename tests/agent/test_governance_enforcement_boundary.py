"""Adversarial contracts for required-governance enforcement boundaries.

These tests encode the fixes for the 2026-07-14 hostile review of the
cognitive-governance layer: rejected drafts must never stream, required
enforcement must fail closed (not open) on dispatch errors, ungovernable
runtimes must be refused, every candidate must be evaluated even after the
nudge cap, and nested tool dispatch must not lose session/turn identity.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import hermes_cli.plugins as plugins
from run_agent import AIAgent


def _mock_response(content="Hello", finish_reason="stop"):
    msg = SimpleNamespace(
        content=content,
        tool_calls=None,
        reasoning=None,
        reasoning_content=None,
        reasoning_details=None,
        role="assistant",
    )
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model="test/model", usage=None)


@pytest.fixture()
def agent():
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        a = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
        a.client = MagicMock()
        return a


def _quiet_hooks(monkeypatch):
    """Silence unrelated plugin machinery so tests drive only the seams under test."""
    monkeypatch.setattr(plugins, "has_hook", lambda name: False)
    monkeypatch.setattr(plugins, "invoke_hook", lambda name, **kw: [])


# ---------------------------------------------------------------------------
# P0-1: a draft must never reach stream callbacks before pre_response ran.
# The core guarantee: with any pre_response/transform hook registered, the
# turn takes the complete-response path (no deltas exist to leak).
# ---------------------------------------------------------------------------


class _FakeClient:  # deliberately NOT a Mock: the streaming path special-cases Mock
    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=None))


def _drive_streaming_decision(
    agent,
    monkeypatch,
    *,
    hooks: tuple[str, ...] = (),
    required: bool = False,
):
    agent.client = _FakeClient()
    monkeypatch.setattr(agent, "_has_stream_consumers", lambda: True)
    monkeypatch.setattr(plugins, "has_hook", lambda name: name in hooks)
    monkeypatch.setattr(plugins, "invoke_hook", lambda name, **kw: [])
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: required, raising=False
    )
    monkeypatch.setattr(
        plugins, "get_pre_response_continue_message", lambda **kw: None
    )
    calls = {"streaming": 0, "complete": 0}

    def _streaming(api_kwargs, on_first_delta=None):
        calls["streaming"] += 1
        return _mock_response("streamed draft")

    def _complete(api_kwargs):
        calls["complete"] += 1
        return _mock_response("complete draft")

    monkeypatch.setattr(agent, "_interruptible_streaming_api_call", _streaming)
    monkeypatch.setattr(agent, "_interruptible_api_call", _complete)
    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("substantive strategic question")
    return calls, result


def test_streaming_is_disabled_while_a_pre_response_gate_is_registered(agent, monkeypatch):
    calls, result = _drive_streaming_decision(
        agent, monkeypatch, hooks=("pre_response",)
    )
    assert calls["streaming"] == 0, (
        "governed turns must take the complete-response path; streaming deltas "
        "would deliver a draft before pre_response could reject it"
    )
    assert calls["complete"] >= 1
    assert result["final_response"] == "complete draft"


def test_streaming_is_disabled_for_a_withholding_transform_under_required_governance(
    agent, monkeypatch
):
    calls, _ = _drive_streaming_decision(
        agent, monkeypatch, hooks=("transform_llm_output",), required=True
    )
    assert calls["streaming"] == 0
    assert calls["complete"] >= 1


def test_streaming_survives_a_cosmetic_transform_plugin(agent, monkeypatch):
    """A style/redaction transform on an ungoverned profile keeps streaming."""
    calls, _ = _drive_streaming_decision(
        agent, monkeypatch, hooks=("transform_llm_output",), required=False
    )
    assert calls["streaming"] >= 1
    assert calls["complete"] == 0


def test_streaming_stays_enabled_without_response_gates(agent, monkeypatch):
    calls, _ = _drive_streaming_decision(agent, monkeypatch, hooks=())
    assert calls["streaming"] >= 1, "control: without gates the streaming path is kept"
    assert calls["complete"] == 0


# ---------------------------------------------------------------------------
# P0-3: an alternate runtime that bypasses pre_response/transform must be
# refused while required governance is configured.
# ---------------------------------------------------------------------------


def test_codex_app_server_runtime_is_refused_under_required_governance(agent, monkeypatch):
    _quiet_hooks(monkeypatch)
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: True, raising=False
    )
    agent.api_mode = "codex_app_server"
    runner = MagicMock()
    monkeypatch.setattr(agent, "_run_codex_app_server_turn", runner, raising=False)
    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("do strategic work")
    runner.assert_not_called()
    assert result["completed"] is False
    assert "governance" in (result["final_response"] or "").lower()


def test_codex_app_server_runtime_still_runs_without_required_governance(agent, monkeypatch):
    _quiet_hooks(monkeypatch)
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: False, raising=False
    )
    agent.api_mode = "codex_app_server"
    runner = MagicMock(return_value={"final_response": "codex", "messages": []})
    monkeypatch.setattr(agent, "_run_codex_app_server_turn", runner, raising=False)
    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("do work")
    runner.assert_called_once()
    assert result["final_response"] == "codex"


# ---------------------------------------------------------------------------
# P0-2: enforcement dispatch failures must fail CLOSED while required
# governance is configured — and stay fail-open without it.
# ---------------------------------------------------------------------------


def test_pre_response_dispatch_failure_fails_closed_when_required(agent, monkeypatch):
    from agent.verify_hooks import GOVERNANCE_FAIL_CLOSED_RESPONSE

    agent.client.chat.completions.create.return_value = _mock_response("raw draft")
    monkeypatch.setattr(plugins, "invoke_hook", lambda name, **kw: [])
    monkeypatch.setattr(plugins, "has_hook", lambda name: name == "pre_response")
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: True, raising=False
    )

    def _boom(**kw):
        raise RuntimeError("governance plugin crashed")

    monkeypatch.setattr(plugins, "get_pre_response_continue_message", _boom)
    persisted_tail = []
    with (
        patch.object(
            agent,
            "_persist_session",
            side_effect=lambda m, _h=None: persisted_tail.append(m[-1].get("content")),
        ),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("strategic question")
    assert result["final_response"] == GOVERNANCE_FAIL_CLOSED_RESPONSE
    assert "raw draft" not in (result["final_response"] or "")
    assert persisted_tail and persisted_tail[-1] == GOVERNANCE_FAIL_CLOSED_RESPONSE


def test_pre_response_dispatch_failure_stays_open_without_required(agent, monkeypatch):
    agent.client.chat.completions.create.return_value = _mock_response("raw draft")
    monkeypatch.setattr(plugins, "invoke_hook", lambda name, **kw: [])
    monkeypatch.setattr(plugins, "has_hook", lambda name: name == "pre_response")
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: False, raising=False
    )

    def _boom(**kw):
        raise RuntimeError("optional observer crashed")

    monkeypatch.setattr(plugins, "get_pre_response_continue_message", _boom)
    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("ordinary question")
    assert result["final_response"] == "raw draft"


def test_transform_dispatch_failure_fails_closed_when_required(agent, monkeypatch):
    from agent.verify_hooks import GOVERNANCE_FAIL_CLOSED_RESPONSE

    agent.client.chat.completions.create.return_value = _mock_response("raw draft")
    monkeypatch.setattr(plugins, "has_hook", lambda name: False)
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: True, raising=False
    )

    def _invoke(name, **kw):
        if name == "transform_llm_output":
            raise RuntimeError("transform crashed")
        return []

    monkeypatch.setattr(plugins, "invoke_hook", _invoke)
    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("strategic question")
    assert result["final_response"] == GOVERNANCE_FAIL_CLOSED_RESPONSE


def test_missing_transform_hook_fails_closed_on_interrupted_partial(agent, monkeypatch):
    # A dropped transform gate under required governance must fail closed even
    # for an INTERRUPTED partial. Unlike the dispatch-crash test above there is
    # no exception here: the hook is simply absent, so invoke_hook returns [].
    # Before the wrap-up-review fix, the `and not interrupted` guard let this
    # partial through raw — an interrupt became a delivery path for ungoverned
    # text.
    from agent.verify_hooks import GOVERNANCE_FAIL_CLOSED_RESPONSE
    from agent.turn_finalizer import finalize_turn

    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: True, raising=False
    )
    monkeypatch.setattr(
        plugins,
        "enforcement_hook_missing",
        lambda name: name == "transform_llm_output",
        raising=False,
    )
    monkeypatch.setattr(plugins, "has_hook", lambda name: False)
    monkeypatch.setattr(plugins, "invoke_hook", lambda name, **kw: [])

    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = finalize_turn(
            agent,
            final_response="raw interrupted partial",
            api_call_count=1,
            interrupted=True,
            failed=False,
            messages=[{"role": "user", "content": "strategic question"}],
            conversation_history=[],
            effective_task_id="task-1",
            turn_id="turn-1",
            user_message="strategic question",
            original_user_message="strategic question",
            _should_review_memory=False,
            _turn_exit_reason="interrupted",
        )
    assert result["final_response"] == GOVERNANCE_FAIL_CLOSED_RESPONSE
    assert "raw interrupted partial" not in (result["final_response"] or "")


def test_pre_tool_call_dispatch_failure_blocks_when_required(monkeypatch):
    def _raising_hook(**kw):
        raise RuntimeError("governance hook crashed")

    manager = plugins.PluginManager()
    manager._hooks = {"pre_tool_call": [_raising_hook]}
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: True, raising=False
    )
    message = plugins.get_pre_tool_call_block_message(
        "terminal", {"command": "curl evil"}, session_id="s1", turn_id="t1"
    )
    assert message is not None, (
        "a crashed enforcement hook must block the tool (fail closed), "
        "not silently allow it"
    )


def test_pre_tool_call_dispatch_failure_allows_without_required(monkeypatch):
    def _raising_hook(**kw):
        raise RuntimeError("optional observer crashed")

    manager = plugins.PluginManager()
    manager._hooks = {"pre_tool_call": [_raising_hook]}
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: False, raising=False
    )
    assert (
        plugins.get_pre_tool_call_block_message(
            "terminal", {"command": "ls"}, session_id="s1", turn_id="t1"
        )
        is None
    )


# ---------------------------------------------------------------------------
# P1: the nudge cap bounds how many regenerations are honored — it must not
# skip evaluation of the final candidate.
# ---------------------------------------------------------------------------


def test_every_candidate_is_evaluated_including_after_the_nudge_cap(agent, monkeypatch):
    agent.client.chat.completions.create.side_effect = [
        _mock_response("draft one"),
        _mock_response("draft two"),
    ]
    monkeypatch.setattr(plugins, "invoke_hook", lambda name, **kw: [])
    monkeypatch.setattr(plugins, "has_hook", lambda name: name == "pre_response")
    monkeypatch.setattr(
        plugins, "required_enforcement_active", lambda: False, raising=False
    )
    import agent.verify_hooks as verify_hooks

    monkeypatch.setattr(verify_hooks, "max_response_nudges", lambda config=None: 1)
    seen_attempts = []

    def _always_continue(**kw):
        seen_attempts.append(kw.get("attempt"))
        return "regenerate with less convergence"

    monkeypatch.setattr(plugins, "get_pre_response_continue_message", _always_continue)
    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("strategic question")
    assert seen_attempts == [0, 1], (
        "the hook must evaluate every candidate; the cap only limits how many "
        "continue directives are honored"
    )
    assert agent.client.chat.completions.create.call_count == 2
    assert result["final_response"] == "draft two"


# ---------------------------------------------------------------------------
# P0-4: nested tool dispatch (sandbox proxies calling back into
# handle_function_call with only task_id) must inherit the governed
# session/turn identity instead of firing hooks with empty defaults.
# ---------------------------------------------------------------------------


def test_nested_dispatch_inherits_ambient_session_and_turn(monkeypatch):
    import model_tools

    captured = {}

    def _capture_block(tool_name, args, **kw):
        captured.update(kw, tool_name=tool_name)
        return None

    monkeypatch.setattr("hermes_cli.plugins.resolve_pre_tool_block", _capture_block)
    with model_tools.dispatch_context(session_id="sess-9", turn_id="turn-7"):
        model_tools.handle_function_call("noop_probe", {}, "task-1")
    assert captured.get("session_id") == "sess-9"
    assert captured.get("turn_id") == "turn-7"


def test_outer_dispatch_seeds_ambient_context_for_nested_calls(monkeypatch):
    import model_tools
    from tools.registry import registry

    captured = []

    def _capture_block(tool_name, args, **kw):
        captured.append((tool_name, kw.get("session_id"), kw.get("turn_id")))
        return None

    monkeypatch.setattr("hermes_cli.plugins.resolve_pre_tool_block", _capture_block)

    def _outer_handler(args, **kw):
        # simulate the sandbox proxy: a nested dispatch with only task_id
        return model_tools.handle_function_call("nested_inner_probe", {}, "task-1")

    registry.register(
        name="nested_outer_probe",
        toolset="governance-test-probe",
        schema={"type": "function", "function": {"name": "nested_outer_probe"}},
        handler=_outer_handler,
    )
    try:
        model_tools.handle_function_call(
            "nested_outer_probe", {}, "task-1", session_id="sess-9", turn_id="turn-7"
        )
    finally:
        registry._tools.pop("nested_outer_probe", None)
    assert ("nested_inner_probe", "sess-9", "turn-7") in captured


# ---------------------------------------------------------------------------
# P0: a config that exists but cannot be parsed must fail CLOSED, not silently
# fall back to DEFAULT_CONFIG (which has no plugins key) and disable everything.
# ---------------------------------------------------------------------------


def _point_config_at(monkeypatch, tmp_path, contents: str):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(
        "hermes_cli.config.get_config_path", lambda: cfg, raising=False
    )
    return cfg


def test_unparseable_config_is_treated_as_governance_required(monkeypatch, tmp_path):
    _point_config_at(monkeypatch, tmp_path, "plugins: [this is not: valid: yaml\n")
    assert plugins.governance_config_unreadable() is True
    assert plugins.required_enforcement_active() is True


def test_unparseable_config_aborts_startup(monkeypatch, tmp_path):
    _point_config_at(monkeypatch, tmp_path, "plugins: [broken\n  nested: ]\n")
    with pytest.raises(plugins.RequiredPluginError, match="could not be read"):
        plugins.validate_required_plugins(SimpleNamespace(_plugins={}))


def test_a_valid_config_with_no_required_plugins_still_starts(monkeypatch, tmp_path):
    _point_config_at(monkeypatch, tmp_path, "plugins:\n  enabled: []\n")
    assert plugins.governance_config_unreadable() is False
    plugins.validate_required_plugins(SimpleNamespace(_plugins={}))  # no raise


def test_malformed_required_type_is_governance_required(monkeypatch, tmp_path):
    # plugins.required present but the wrong shape (a mapping, not a list) is a
    # broken enforcement declaration: _get_required_plugins() would coerce it to
    # empty and silently disable governance. Fail closed instead (re-review).
    _point_config_at(
        monkeypatch, tmp_path, "plugins:\n  required:\n    cognitive-governance: true\n"
    )
    assert plugins.governance_config_unreadable() is True
    assert plugins.required_enforcement_active() is True
    with pytest.raises(plugins.RequiredPluginError, match="not a list"):
        plugins.validate_required_plugins(SimpleNamespace(_plugins={}))


def test_required_as_list_is_read_normally(monkeypatch, tmp_path):
    # The well-formed shape must NOT trip the malformed-type guard.
    _point_config_at(
        monkeypatch, tmp_path, "plugins:\n  required:\n    - cognitive-governance\n"
    )
    assert plugins.governance_config_unreadable() is False
    assert plugins.required_enforcement_active() is True


def test_absent_required_key_does_not_force_governance(monkeypatch, tmp_path):
    # A plugins block with no `required` key declared nothing — must still run.
    _point_config_at(monkeypatch, tmp_path, "plugins:\n  enabled:\n    - foo\n")
    assert plugins.governance_config_unreadable() is False


def test_absent_config_does_not_force_governance(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "hermes_cli.config.get_config_path",
        lambda: tmp_path / "does-not-exist.yaml",
        raising=False,
    )
    assert plugins.governance_config_unreadable() is False


# ---------------------------------------------------------------------------
# P1: enforcement keyed on config-declared required must also require the hook
# to actually be registered — an absent required hook is not approval.
# ---------------------------------------------------------------------------


def test_missing_required_hook_blocks_tools(monkeypatch):
    monkeypatch.setattr(plugins, "required_enforcement_active", lambda: True)
    monkeypatch.setattr(plugins, "has_hook", lambda name: False)
    message = plugins.get_pre_tool_call_block_message(
        "cronjob", {}, session_id="s1", turn_id="t1"
    )
    assert message is not None and "not registered" in message


def test_present_required_hook_allows_normally(monkeypatch):
    monkeypatch.setattr(plugins, "required_enforcement_active", lambda: True)
    monkeypatch.setattr(plugins, "has_hook", lambda name: True)
    monkeypatch.setattr(plugins, "invoke_hook", lambda name, **kw: [])
    assert (
        plugins.get_pre_tool_call_block_message("read_file", {}, session_id="s1")
        is None
    )


def test_enforcement_hook_missing_is_false_without_required(monkeypatch):
    monkeypatch.setattr(plugins, "required_enforcement_active", lambda: False)
    monkeypatch.setattr(plugins, "has_hook", lambda name: False)
    assert plugins.enforcement_hook_missing("pre_response") is False
