#!/usr/bin/env python3
"""Refresh QuantForge's root-owned runtime environment from the Vault agent."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


AGENT_COMMAND_PREFIX = "quantforge-vault-read"
PROFILE = "quantforge/eu-london/azure-storage"
EXPECTED_ACCOUNT_NAME = "quantforgeukweststorage"
EXPECTED_ENV_NAMES = frozenset(
    {"AZURE_STORAGE_ACCOUNT_NAME", "AZURE_STORAGE_CONNECTION_STRING"}
)


class VaultRuntimeError(RuntimeError):
    """A safe, user-facing runtime refresh failure."""


def _connection_account_name(connection_string: str) -> str | None:
    for component in connection_string.split(";"):
        name, separator, value = component.partition("=")
        if separator and name.strip().lower() == "accountname":
            return value
    return None


def validate_payload(payload: Any) -> dict[str, str]:
    """Validate the exact profile contract without logging any values."""

    if not isinstance(payload, dict):
        raise VaultRuntimeError("Vault agent returned an invalid payload")
    if payload.get("schema") != 1 or payload.get("profile") != PROFILE:
        raise VaultRuntimeError("Vault agent returned an unsupported profile")
    secrets = payload.get("secrets")
    if not isinstance(secrets, dict) or frozenset(secrets) != EXPECTED_ENV_NAMES:
        raise VaultRuntimeError("Vault agent returned an incomplete profile")
    if any(
        not isinstance(value, str) or not value or "\x00" in value or "\n" in value or "\r" in value
        for value in secrets.values()
    ):
        raise VaultRuntimeError("Vault agent returned an invalid secret value")
    if secrets["AZURE_STORAGE_ACCOUNT_NAME"] != EXPECTED_ACCOUNT_NAME:
        raise VaultRuntimeError("Vault agent returned the wrong storage account")
    if _connection_account_name(secrets["AZURE_STORAGE_CONNECTION_STRING"]) != EXPECTED_ACCOUNT_NAME:
        raise VaultRuntimeError("Vault agent returned a mismatched connection string")
    return {name: secrets[name] for name in sorted(EXPECTED_ENV_NAMES)}


def fetch_payload(
    *,
    destination: str,
    identity_file: Path,
    known_hosts: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, str]:
    """Fetch the fixed profile over strict, non-interactive SSH."""

def fetch_secret(
    *,
    destination: str,
    identity_file: Path,
    known_hosts: Path,
    path: str,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> str:
    """Fetch one allowlisted path over strict, non-interactive SSH."""

    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ConnectTimeout=15",
        "-i",
        str(identity_file),
        destination,
        f"{AGENT_COMMAND_PREFIX} {path}",
    ]
    result = runner(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise VaultRuntimeError("Vault agent request failed")
    try:
        value = result.stdout.decode("utf-8").rstrip("\n")
    except UnicodeDecodeError as exc:
        raise VaultRuntimeError("Vault agent returned invalid text") from exc
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise VaultRuntimeError("Vault agent returned an invalid secret")
    return value


def fetch_payload(
    *,
    destination: str,
    identity_file: Path,
    known_hosts: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, str]:
    """Fetch the two Azure paths needed by the current runtime."""

    account_name = fetch_secret(
        destination=destination,
        identity_file=identity_file,
        known_hosts=known_hosts,
        path="quantforge/eu-london/azure-storage-account-name",
        runner=runner,
    )
    connection_string = fetch_secret(
        destination=destination,
        identity_file=identity_file,
        known_hosts=known_hosts,
        path="quantforge/eu-london/azure-storage-connection-string",
        runner=runner,
    )
    return validate_payload(
        {
            "schema": 1,
            "profile": PROFILE,
            "secrets": {
                "AZURE_STORAGE_ACCOUNT_NAME": account_name,
                "AZURE_STORAGE_CONNECTION_STRING": connection_string,
            },
        }
    )


def write_runtime_env(secrets: dict[str, str], output: Path) -> None:
    """Atomically install a mode-0600 dotenv file."""

    validated = validate_payload(
        {"schema": 1, "profile": PROFILE, "secrets": secrets}
    )
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for name, value in validated.items():
                handle.write(f"{name}={value}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        os.chmod(output, 0o600)
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, help="Vault agent SSH destination")
    parser.add_argument("--identity-file", required=True, type=Path)
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/run/quantforge/azure-storage.env"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        secrets = fetch_payload(
            destination=args.destination,
            identity_file=args.identity_file,
            known_hosts=args.known_hosts,
        )
        write_runtime_env(secrets, args.output)
    except VaultRuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError:
        print("could not install Vault runtime environment", file=sys.stderr)
        return 1
    print(f"installed {shlex.quote(str(args.output))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
