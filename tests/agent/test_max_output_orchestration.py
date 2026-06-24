from __future__ import annotations

from agent.max_output_orchestration import build_max_output_context, build_max_output_plan


def _config(enabled: bool = True):
    return {
        "max_output_orchestration": {
            "enabled": enabled,
            "trigger": "最強出力",
            "hermes_child_agents": True,
            "claude": {"enabled": True, "command": "claude"},
            "codex": {"enabled": True, "command": "codex"},
        }
    }


def test_max_output_does_not_trigger_for_normal_request():
    plan = build_max_output_plan("実装して", _config(), cwd="/tmp/repo")

    assert plan.enabled is True
    assert plan.triggered is False
    assert plan.to_context_block() == ""
    assert plan.claude.command == ""
    assert plan.codex.command == ""


def test_max_output_disabled_even_when_trigger_phrase_present():
    context = build_max_output_context("最強出力で実装して", _config(enabled=False), cwd="/tmp/repo")

    assert context == ""


def test_max_output_context_encodes_hermes_parent_hierarchy():
    context = build_max_output_context("最強出力で実装して", _config(), cwd="/tmp/repo")

    assert "<HERMES_PARENT_MAX_OUTPUT_ORCHESTRATION>" in context
    assert "controller: Hermes parent is the only top-level controller." in context
    assert "Hermes parent may directly launch Hermes child agents with delegate_task" in context
    assert "Hermes parent may directly launch Claude CLI" in context
    assert "Claude CLI may use Dynamic Workflows / ultracode" in context
    assert "Hermes parent may directly launch Codex CLI" in context
    assert "Hermes parent must verify lane outputs itself" in context


def test_max_output_builds_subordinate_cli_lane_commands():
    plan = build_max_output_plan("最強出力: fix the bug", _config(), cwd="/tmp/repo")

    assert plan.triggered is True
    assert plan.hermes_child_agents is True
    assert "claude -p" in plan.claude.command
    assert "ultracode:" in plan.claude.command
    assert "under Hermes parent control" in plan.claude.command
    assert "codex exec --full-auto" in plan.codex.command
    assert "subordinate Codex CLI lane under Hermes parent control" in plan.codex.command
