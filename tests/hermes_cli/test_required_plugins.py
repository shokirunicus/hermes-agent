"""Tests for required-plugin runtime enforcement."""

from types import SimpleNamespace

import pytest

from hermes_cli import plugins


def _loaded(name: str, *, enabled: bool = True, error: str | None = None):
    manifest = plugins.PluginManifest(name=name, key=name)
    return plugins.LoadedPlugin(
        manifest=manifest,
        enabled=enabled,
        error=error,
    )


def test_no_required_plugins_is_a_noop(monkeypatch):
    monkeypatch.setattr(plugins, "_get_required_plugins", lambda: set())
    plugins.validate_required_plugins(SimpleNamespace(_plugins={}))


def test_enabled_required_plugin_passes(monkeypatch):
    monkeypatch.setattr(
        plugins,
        "_get_required_plugins",
        lambda: {"cognitive-governance"},
    )
    manager = SimpleNamespace(
        _plugins={"cognitive-governance": _loaded("cognitive-governance")}
    )
    plugins.validate_required_plugins(manager)


def test_missing_required_plugin_fails_agent_startup(monkeypatch):
    monkeypatch.setattr(
        plugins,
        "_get_required_plugins",
        lambda: {"cognitive-governance"},
    )
    with pytest.raises(plugins.RequiredPluginError, match="missing"):
        plugins.validate_required_plugins(SimpleNamespace(_plugins={}))


def test_disabled_or_failed_required_plugin_fails_agent_startup(monkeypatch):
    monkeypatch.setattr(
        plugins,
        "_get_required_plugins",
        lambda: {"cognitive-governance"},
    )
    manager = SimpleNamespace(
        _plugins={
            "cognitive-governance": _loaded(
                "cognitive-governance",
                enabled=False,
                error="registration failed",
            )
        }
    )
    with pytest.raises(plugins.RequiredPluginError, match="registration failed"):
        plugins.validate_required_plugins(manager)
