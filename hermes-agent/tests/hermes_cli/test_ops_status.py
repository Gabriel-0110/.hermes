"""Tests for hermes_cli.ops_status."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import hermes_cli.ops_status as ops_status


def test_normalize_trading_mode_prefers_explicit_mode() -> None:
    assert ops_status._normalize_trading_mode("paper", live_enabled=True, ack_present=True, paper_mode=False) == "paper"
    assert ops_status._normalize_trading_mode("approval_required", live_enabled=False, ack_present=False, paper_mode=False) == "approval-required"
    assert ops_status._normalize_trading_mode("live", live_enabled=False, ack_present=False, paper_mode=False) == "live"


def test_normalize_trading_mode_falls_back_to_flags() -> None:
    assert ops_status._normalize_trading_mode("", live_enabled=True, ack_present=True, paper_mode=False) == "live"
    assert ops_status._normalize_trading_mode(None, live_enabled=False, ack_present=False, paper_mode=True) == "paper"
    assert ops_status._normalize_trading_mode(None, live_enabled=False, ack_present=False, paper_mode=False) == "disabled"


def test_stale_lock_rows_detect_dead_pids(tmp_path, monkeypatch) -> None:
    lock_dir = tmp_path / "gateway-locks"
    lock_dir.mkdir(parents=True)
    stale_lock = lock_dir / "telegram-dead.lock"
    stale_lock.write_text(json.dumps({"pid": 999999, "scope": "telegram"}), encoding="utf-8")

    monkeypatch.setattr("gateway.status._get_lock_dir", lambda: lock_dir)

    rows = ops_status._stale_lock_rows()

    assert rows
    assert rows[0]["alive"] is False
    assert rows[0]["reason"] == "telegram"


def test_latest_smoke_artifact_reports_not_available(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ops_status, "WORKSPACE_ROOT", tmp_path)

    result = ops_status._latest_smoke_artifact("telegram")

    assert result.summary == "not available"
    assert result.status == ops_status.STATUS_INFO


def test_platform_runtime_check_fails_when_enabled_profile_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(ops_status, "get_env_value", lambda key: {"TELEGRAM_ENABLED_PROFILES": "orchestrator"}.get(key, ""))

    result = ops_status._platform_runtime_check(
        platform="telegram",
        token_env="TELEGRAM_BOT_TOKEN",
        enabled_profiles_env="TELEGRAM_ENABLED_PROFILES",
        current_profile="orchestrator",
        authoritative_platforms={},
        gateway_running=False,
    )

    assert result.status == ops_status.STATUS_FAIL
    assert result.critical is True
    assert "token is missing" in result.summary


def test_platform_runtime_check_reports_not_configured_without_enable_list(monkeypatch) -> None:
    monkeypatch.setattr(ops_status, "get_env_value", lambda key: "")

    result = ops_status._platform_runtime_check(
        platform="telegram",
        token_env="TELEGRAM_BOT_TOKEN",
        enabled_profiles_env="TELEGRAM_ENABLED_PROFILES",
        current_profile="default",
        authoritative_platforms={},
        gateway_running=False,
    )

    assert result.status == ops_status.STATUS_INFO
    assert result.summary == "not configured"


def test_show_ops_status_returns_nonzero_for_critical_failures(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        ops_status,
        "build_ops_status_report",
        lambda: [
            ops_status.Section(
                "Runtime",
                checks=[ops_status.CheckResult("Gateway service status", ops_status.STATUS_FAIL, "stopped", critical=True)],
            )
        ],
    )

    exit_code = ops_status.show_ops_status(SimpleNamespace())
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Gateway service status" in output
    assert "Critical issues detected" in output


def test_show_ops_status_renders_authoritative_gateway_state_path(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        ops_status,
        "build_ops_status_report",
        lambda: [
            ops_status.Section(
                "Profile & runtime",
                checks=[
                    ops_status.CheckResult("Active profile", ops_status.STATUS_INFO, "orchestrator"),
                    ops_status.CheckResult(
                        "Authoritative gateway_state",
                        ops_status.STATUS_INFO,
                        "/Users/test/.hermes/profiles/orchestrator/gateway_state.json",
                    ),
                ],
            )
        ],
    )

    exit_code = ops_status.show_ops_status(SimpleNamespace())
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "/Users/test/.hermes/profiles/orchestrator/gateway_state.json" in output


def test_cmd_doctor_defaults_to_ops_status(monkeypatch) -> None:
    import hermes_cli.main as main_mod

    monkeypatch.setattr(ops_status, "show_ops_status", lambda args: 7)

    with pytest.raises(SystemExit) as exc:
        main_mod.cmd_doctor(SimpleNamespace(setup=False, fix=False))

    assert exc.value.code == 7


def test_cmd_doctor_setup_uses_legacy_doctor(monkeypatch) -> None:
    import hermes_cli.doctor as legacy_doctor
    import hermes_cli.main as main_mod

    seen: dict[str, object] = {}

    monkeypatch.setattr(legacy_doctor, "run_doctor", lambda args: seen.setdefault("args", args))

    main_mod.cmd_doctor(SimpleNamespace(setup=True, fix=False))

    assert isinstance(seen["args"], SimpleNamespace)


def test_cmd_doctor_fix_implies_legacy_doctor(monkeypatch) -> None:
    import hermes_cli.doctor as legacy_doctor
    import hermes_cli.main as main_mod

    seen: dict[str, object] = {}

    monkeypatch.setattr(legacy_doctor, "run_doctor", lambda args: seen.setdefault("args", args))

    main_mod.cmd_doctor(SimpleNamespace(setup=False, fix=True))

    assert isinstance(seen["args"], SimpleNamespace)