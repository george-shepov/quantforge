from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from scripts.refresh_vault_runtime_env import (
    AGENT_COMMAND_PREFIX,
    PROFILE,
    VaultRuntimeError,
    fetch_payload,
    validate_payload,
    write_runtime_env,
)


def payload() -> dict:
    return {
        "schema": 1,
        "profile": PROFILE,
        "secrets": {
            "AZURE_STORAGE_ACCOUNT_NAME": "quantforgeukweststorage",
            "AZURE_STORAGE_CONNECTION_STRING": (
                "DefaultEndpointsProtocol=https;"
                "AccountName=quantforgeukweststorage;AccountKey=test-key"
            ),
        },
    }


def test_validate_payload_requires_exact_regional_contract():
    assert set(validate_payload(payload())) == {
        "AZURE_STORAGE_ACCOUNT_NAME",
        "AZURE_STORAGE_CONNECTION_STRING",
    }

    invalid = payload()
    invalid["secrets"]["AZURE_STORAGE_ACCOUNT_KEY"] = "unexpected"
    with pytest.raises(VaultRuntimeError):
        validate_payload(invalid)


def test_validate_payload_rejects_wrong_account_or_connection():
    invalid = payload()
    invalid["secrets"]["AZURE_STORAGE_ACCOUNT_NAME"] = "other-account"
    with pytest.raises(VaultRuntimeError):
        validate_payload(invalid)


def test_fetch_payload_uses_strict_ssh_and_fixed_command(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE
        if command[-1].endswith("account-name"):
            value = "quantforgeukweststorage"
        else:
            value = payload()["secrets"]["AZURE_STORAGE_CONNECTION_STRING"]
        return subprocess.CompletedProcess(command, 0, (value + "\n").encode(), b"")

    result = fetch_payload(
        destination="vault-agent@example",
        identity_file=tmp_path / "id_ed25519",
        known_hosts=tmp_path / "known_hosts",
        runner=fake_run,
    )

    assert result["AZURE_STORAGE_ACCOUNT_NAME"] == "quantforgeukweststorage"
    assert calls[0][-1] == f"{AGENT_COMMAND_PREFIX} quantforge/eu-london/azure-storage-account-name"
    assert calls[1][-1] == f"{AGENT_COMMAND_PREFIX} quantforge/eu-london/azure-storage-connection-string"
    assert "StrictHostKeyChecking=yes" in calls[0]
    assert "IdentitiesOnly=yes" in calls[0]


def test_write_runtime_env_is_atomic_and_owner_only(tmp_path):
    output = tmp_path / "run" / "azure-storage.env"
    write_runtime_env(payload()["secrets"], output)

    assert output.read_text(encoding="utf-8").splitlines() == [
        "AZURE_STORAGE_ACCOUNT_NAME=quantforgeukweststorage",
        "AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=quantforgeukweststorage;AccountKey=test-key",
    ]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert not list(output.parent.glob(".*.tmp"))
