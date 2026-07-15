"""Regression tests for multiplex profile-aware own-policy authorization."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.session import SessionSource


def _clear_auth_env(monkeypatch) -> None:
    for key in (
        "WECOM_ALLOWED_USERS",
        "GATEWAY_ALLOWED_USERS",
        "GATEWAY_ALLOW_ALL_USERS",
        "WECOM_ALLOW_ALL_USERS",
    ):
        monkeypatch.delenv(key, raising=False)


def _make_multiplex_runner(monkeypatch):
    """Runner with default allowlist WeCom and secondary open-policy WeCom."""
    from gateway.run import GatewayRunner

    _clear_auth_env(monkeypatch)

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(multiplex_profiles=True)

    default_adapter = SimpleNamespace(
        send=AsyncMock(),
        enforces_own_access_policy=True,
        _dm_policy="allowlist",
        _group_policy="pairing",
    )
    secondary_adapter = SimpleNamespace(
        send=AsyncMock(),
        enforces_own_access_policy=True,
        _dm_policy="open",
        _group_policy="open",
    )

    runner.adapters = {Platform.WECOM: default_adapter}
    runner._profile_adapters = {
        "coder": {Platform.WECOM: secondary_adapter},
    }
    runner.pairing_store = MagicMock()
    runner.pairing_store.is_approved.return_value = False
    return runner, default_adapter, secondary_adapter


def test_secondary_open_policy_not_authorized_by_default_allowlist(monkeypatch):
    """Secondary-profile open intake must not inherit default allowlist trust."""
    runner, _default_adapter, _secondary_adapter = _make_multiplex_runner(monkeypatch)

    source = SessionSource(
        platform=Platform.WECOM,
        user_id="attacker",
        chat_id="dm-chat",
        user_name="attacker",
        chat_type="dm",
        profile="coder",
    )

    assert runner._adapter_dm_policy(Platform.WECOM, profile="coder") == "open"
    assert runner._adapter_dm_policy(Platform.WECOM) == "allowlist"
    assert runner._is_user_authorized(source) is False


def test_default_profile_still_trusts_own_allowlist(monkeypatch):
    """Default-profile allowlist trust is unchanged when profile is unstamped."""
    runner, _default_adapter, _secondary_adapter = _make_multiplex_runner(monkeypatch)

    source = SessionSource(
        platform=Platform.WECOM,
        user_id="allowed-user",
        chat_id="dm-chat",
        user_name="allowed-user",
        chat_type="dm",
        profile=None,
    )

    assert runner._is_user_authorized(source) is True


def test_secondary_allowlist_still_authorized(monkeypatch):
    """Secondary profile with allowlist policy is trusted on its own adapter."""
    runner, _default_adapter, secondary_adapter = _make_multiplex_runner(monkeypatch)
    secondary_adapter._dm_policy = "allowlist"

    source = SessionSource(
        platform=Platform.WECOM,
        user_id="allowed-user",
        chat_id="dm-chat",
        user_name="allowed-user",
        chat_type="dm",
        profile="coder",
    )

    assert runner._is_user_authorized(source) is True


def test_adapter_authorization_callback_stamps_profile(monkeypatch):
    """Per-profile adapters must authorize inside their own profile scope."""
    runner, _default_adapter, _secondary_adapter = _make_multiplex_runner(
        monkeypatch
    )
    seen = []
    monkeypatch.setattr(
        runner,
        "_is_user_authorized",
        lambda source: seen.append(source) or True,
    )

    check = runner._make_adapter_auth_check(Platform.WECOM, profile="coder")

    assert check("allowed-user", "dm", "dm-chat") is True
    assert seen[0].profile == "coder"


def test_adapter_for_source_resolves_secondary_profile_adapter(monkeypatch):
    """Ingress adapter lookup must use the stamped profile's adapter map."""
    runner, default_adapter, secondary_adapter = _make_multiplex_runner(monkeypatch)

    source = SessionSource(
        platform=Platform.WECOM,
        user_id="attacker",
        chat_id="dm-chat",
        user_name="attacker",
        chat_type="dm",
        profile="coder",
    )

    assert runner._adapter_for_source(source) is secondary_adapter
    assert runner._adapter_for_source(
        SessionSource(
            platform=Platform.WECOM,
            user_id="allowed-user",
            chat_id="dm-chat",
            user_name="allowed-user",
            chat_type="dm",
            profile=None,
        )
    ) is default_adapter


def test_secondary_allowlist_dm_behavior_ignores_unauthorized(monkeypatch):
    """Unauthorized-DM behavior must read the secondary adapter's dm_policy."""
    runner, _default_adapter, secondary_adapter = _make_multiplex_runner(monkeypatch)
    secondary_adapter._dm_policy = "allowlist"

    assert runner._get_unauthorized_dm_behavior(
        Platform.WECOM,
        profile="coder",
    ) == "ignore"
    assert runner._get_unauthorized_dm_behavior(Platform.WECOM) == "ignore"


def test_secondary_open_policy_fails_startup_guard(monkeypatch):
    """Secondary profiles must pass the same open-policy startup guard."""
    from gateway.run import _own_policy_open_startup_violation

    _clear_auth_env(monkeypatch)

    secondary_cfg = GatewayConfig(multiplex_profiles=True)
    secondary_cfg.platforms = {
        Platform.WECOM: PlatformConfig(
            enabled=True,
            extra={"dm_policy": "open"},
        ),
    }

    violation = _own_policy_open_startup_violation(secondary_cfg)
    assert violation is not None
    assert "wecom" in violation
    assert "open policy" in violation


def test_secondary_authorization_reads_only_its_profile_env(
    monkeypatch, tmp_path
):
    runner, _default_adapter, secondary_adapter = _make_multiplex_runner(
        monkeypatch
    )
    secondary_adapter._dm_policy = "allowlist"
    monkeypatch.setenv("WECOM_ALLOWED_USERS", "default-owner")
    profile_home = tmp_path / "coder"
    profile_home.mkdir()
    (profile_home / ".env").write_text(
        "WECOM_ALLOWED_USERS=coder-owner\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        runner, "_resolve_profile_home_for_source", lambda _source: profile_home
    )

    coder_source = SessionSource(
        platform=Platform.WECOM,
        user_id="coder-owner",
        chat_id="dm-chat",
        chat_type="dm",
        profile="coder",
    )
    default_source = SessionSource(
        platform=Platform.WECOM,
        user_id="default-owner",
        chat_id="dm-chat",
        chat_type="dm",
    )

    assert runner._is_user_authorized(coder_source) is True
    assert runner._is_user_authorized(default_source) is True


def test_simplex_display_name_does_not_match_global_allowlist(monkeypatch):
    from gateway.platform_registry import PlatformEntry, platform_registry
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig()
    runner.adapters = {}
    runner.pairing_store = MagicMock()
    runner.pairing_store.is_approved.return_value = False
    platform_registry.register(PlatformEntry(
        name="simplex",
        label="SimpleX Chat",
        adapter_factory=lambda _cfg: None,
        check_fn=lambda: True,
        allowed_users_env="SIMPLEX_ALLOWED_USERS",
        allow_all_env="SIMPLEX_ALLOW_ALL_USERS",
    ))
    simplex = Platform("simplex")
    monkeypatch.delenv("SIMPLEX_ALLOWED_USERS", raising=False)
    monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "same-display-name")

    source = SessionSource(
        platform=simplex,
        user_id="different-contact-id",
        user_name="same-display-name",
        chat_id="dm-chat",
        chat_type="dm",
    )

    assert runner._is_user_authorized(source) is False
