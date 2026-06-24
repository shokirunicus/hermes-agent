"""Trigger-gated max-output orchestration context for Hermes parent runs.

This module does not launch workers by itself.  It performs deterministic
trigger/config/tool preflight and returns an ephemeral context block that is
injected into the current user turn.  The Hermes parent remains the only
controller: it decides which tools to call, launches Hermes child agents via
``delegate_task``, and launches Claude/Codex CLI lanes via terminal tools.
"""

from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEFAULT_TRIGGER = "最強出力"
DEFAULT_CLAUDE_COMMAND = "claude"
DEFAULT_CODEX_COMMAND = "codex"


@dataclass(frozen=True)
class LaneCommand:
    """A launch command proposal owned by the Hermes parent."""

    lane: str
    command: str
    available: bool
    purpose: str


@dataclass(frozen=True)
class MaxOutputPlan:
    """Deterministic plan injected into the current turn when triggered."""

    enabled: bool
    triggered: bool
    trigger: str
    repo: str
    hermes_child_agents: bool
    claude: LaneCommand
    codex: LaneCommand

    def to_context_block(self) -> str:
        """Render a compact instruction block for the parent agent."""

        if not (self.enabled and self.triggered):
            return ""

        claude_status = "available" if self.claude.available else "missing"
        codex_status = "available" if self.codex.available else "missing"
        hermes_children = "enabled" if self.hermes_child_agents else "disabled"

        return (
            "<HERMES_PARENT_MAX_OUTPUT_ORCHESTRATION>\n"
            f"trigger: {self.trigger!r}\n"
            f"repo: {self.repo}\n"
            "controller: Hermes parent is the only top-level controller.\n"
            "hierarchy:\n"
            "  1. Hermes parent owns goal, scope, safety, lane launch, progress management, verification, git, and final synthesis.\n"
            "  2. Hermes parent may directly launch Hermes child agents with delegate_task for analysis/review/verification.\n"
            "  3. Hermes parent may directly launch Claude CLI as a subordinate implementation lane.\n"
            "  4. Claude CLI may use Dynamic Workflows / ultracode to run Claude subagents inside the Claude lane; those subagents are not top-level controllers.\n"
            "  5. Hermes parent may directly launch Codex CLI as a subordinate implementation/review lane.\n"
            "  6. Hermes parent must verify lane outputs itself; worker self-reports are not proof.\n"
            "cost_guard: This block appears only after the exact trigger phrase. Launch only useful lanes; do not waste duplicate work.\n"
            "required_parent_actions:\n"
            "  - State that max-output mode is active.\n"
            "  - Create a role map before launching lanes.\n"
            "  - Use delegate_task batch mode for Hermes child agents when they materially help.\n"
            "  - Use terminal/process tools for Claude CLI and Codex CLI lanes; track background processes if long-running.\n"
            "  - Keep destructive operations and external publish/deploy/send behind explicit user approval.\n"
            "  - Run real verification commands before reporting success.\n"
            "lanes:\n"
            f"  hermes_child_agents: {hermes_children}\n"
            f"  claude_cli: {claude_status}\n"
            f"    purpose: {self.claude.purpose}\n"
            f"    parent_launch_command: {self.claude.command}\n"
            f"  codex_cli: {codex_status}\n"
            f"    purpose: {self.codex.purpose}\n"
            f"    parent_launch_command: {self.codex.command}\n"
            "</HERMES_PARENT_MAX_OUTPUT_ORCHESTRATION>"
        )


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _quote_task(task: str) -> str:
    return shlex.quote(task.strip())


def _command_available(command: str) -> bool:
    if not command:
        return False
    executable = shlex.split(command)[0]
    return shutil.which(executable) is not None


def _repo_label(cwd: str | os.PathLike[str] | None) -> str:
    if not cwd:
        return str(Path.cwd())
    return str(Path(cwd).expanduser())


def _build_claude_command(command: str, task: str) -> str:
    prompt = (
        "ultracode: You are a subordinate Claude CLI implementation lane under Hermes parent control. "
        "Use Dynamic Workflows and Claude subagents only when they materially improve the result. "
        "Do not become the top-level controller. Return changed files, commands run, failures, and risks. "
        f"Task: {task}"
    )
    return (
        f"{command} -p {_quote_task(prompt)} "
        "--model opus --effort ultracode --permission-mode acceptEdits --max-turns 20 --output-format json"
    )


def _build_codex_command(command: str, task: str) -> str:
    prompt = (
        "You are a subordinate Codex CLI lane under Hermes parent control. "
        "Use the configured gpt-5.5 setup. Produce an independent implementation/review/fix, "
        "then report changed files, commands run, failures, and risks. "
        "Do not deploy, publish, force-push, read secrets, or perform destructive operations. "
        f"Task: {task}"
    )
    return f"{command} exec --full-auto {_quote_task(prompt)}"


def build_max_output_plan(
    user_message: str,
    config: Mapping[str, Any] | None,
    *,
    cwd: str | os.PathLike[str] | None = None,
) -> MaxOutputPlan:
    """Return the deterministic parent-owned orchestration plan for a turn.

    Config shape::

        max_output_orchestration:
          enabled: true
          trigger: "最強出力"
          hermes_child_agents: true
          claude:
            enabled: true
            command: "claude"
          codex:
            enabled: true
            command: "codex"
    """

    cfg = _as_mapping(config)
    orchestration = _as_mapping(cfg.get("max_output_orchestration"))
    enabled = _truthy(orchestration.get("enabled", False))
    trigger = _first_nonempty(orchestration.get("trigger"), DEFAULT_TRIGGER)
    text = user_message or ""
    triggered = bool(enabled and trigger and trigger in text)

    hermes_child_agents = _truthy(orchestration.get("hermes_child_agents", True))

    claude_cfg = _as_mapping(orchestration.get("claude"))
    codex_cfg = _as_mapping(orchestration.get("codex"))
    claude_enabled = _truthy(claude_cfg.get("enabled", True))
    codex_enabled = _truthy(codex_cfg.get("enabled", True))
    claude_command = _first_nonempty(claude_cfg.get("command"), DEFAULT_CLAUDE_COMMAND)
    codex_command = _first_nonempty(codex_cfg.get("command"), DEFAULT_CODEX_COMMAND)

    claude_lane = LaneCommand(
        lane="claude_cli",
        command=_build_claude_command(claude_command, text) if triggered and claude_enabled else "",
        available=bool(triggered and claude_enabled and _command_available(claude_command)),
        purpose="implementation lane; may run Claude Code Dynamic Workflows / ultracode and Claude subagents inside that lane",
    )
    codex_lane = LaneCommand(
        lane="codex_cli",
        command=_build_codex_command(codex_command, text) if triggered and codex_enabled else "",
        available=bool(triggered and codex_enabled and _command_available(codex_command)),
        purpose="independent gpt-5.5 implementation/reasoning/review lane under Hermes parent control",
    )

    return MaxOutputPlan(
        enabled=enabled,
        triggered=triggered,
        trigger=trigger,
        repo=_repo_label(cwd),
        hermes_child_agents=bool(triggered and hermes_child_agents),
        claude=claude_lane,
        codex=codex_lane,
    )


def build_max_output_context(
    user_message: str,
    config: Mapping[str, Any] | None,
    *,
    cwd: str | os.PathLike[str] | None = None,
) -> str:
    """Return an ephemeral user-message context block, or ``""`` when inactive."""

    return build_max_output_plan(user_message, config, cwd=cwd).to_context_block()
