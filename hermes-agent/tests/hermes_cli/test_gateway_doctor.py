"""Tests for hermes gateway doctor diagnostics."""

from pathlib import Path
from types import SimpleNamespace

import hermes_cli.gateway as gateway_cli


class TestGatewayDoctorHelpers:
    def test_authoritative_gateway_state_path_uses_current_hermes_home(self, tmp_path, monkeypatch):
        current_home = tmp_path / ".hermes" / "profiles" / "orchestrator"
        current_home.mkdir(parents=True)

        monkeypatch.setattr(gateway_cli, "get_hermes_home", lambda: current_home)

        assert gateway_cli.get_authoritative_gateway_state_path() == current_home / "gateway_state.json"

    def test_duplicate_identity_groups_detect_shared_fingerprints(self, tmp_path):
        default_home = tmp_path / ".hermes"
        orchestrator_home = default_home / "profiles" / "orchestrator"
        default_home.mkdir(parents=True)
        orchestrator_home.mkdir(parents=True)

        (default_home / ".env").write_text(
            "SLACK_BOT_TOKEN=shared-bot\n"
            "SLACK_APP_TOKEN=shared-app\n",
            encoding="utf-8",
        )
        (orchestrator_home / ".env").write_text(
            "SLACK_BOT_TOKEN=shared-bot\n"
            "SLACK_APP_TOKEN=shared-app\n"
            "TELEGRAM_BOT_TOKEN=own-telegram\n",
            encoding="utf-8",
        )

        identity_rows = gateway_cli._gateway_identity_rows([
            {"profile": "default", "home": str(default_home)},
            {"profile": "orchestrator", "home": str(orchestrator_home)},
        ])
        collisions = gateway_cli._duplicate_identity_groups(identity_rows)
        collision_map = {
            item["resource"]: set(item["profiles"])
            for item in collisions
        }

        assert collision_map["slack_bot"] == {"default", "orchestrator"}
        assert collision_map["slack_app"] == {"default", "orchestrator"}
        assert "telegram" not in collision_map

    def test_gateway_command_dispatches_doctor(self, monkeypatch):
        calls = []

        monkeypatch.setattr(
            gateway_cli,
            "gateway_doctor",
            lambda json_output=False: calls.append(json_output),
        )

        gateway_cli.gateway_command(SimpleNamespace(gateway_command="doctor", json=True))

        assert calls == [True]

    def test_launchd_disabled_labels_parses_disabled_keyword(self, monkeypatch):
        monkeypatch.setattr(gateway_cli, "is_macos", lambda: True)
        monkeypatch.setattr(gateway_cli, "_launchd_domain", lambda: "gui/501")
        monkeypatch.setattr(
            gateway_cli.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout='                "ai.hermes.gateway" => disabled\n                "other.service" => disabled\n',
                stderr="",
            ),
        )

        assert gateway_cli._launchd_disabled_labels() == {"ai.hermes.gateway"}