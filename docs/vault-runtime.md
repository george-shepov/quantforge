# QuantForge runtime secrets

QuantForge does not call the interactive Vault web UI and does not carry the
Vault master password. The London host refreshes the connection-string path
over a dedicated forced SSH command before starting Compose. The account name
is non-secret configuration and remains pinned to the expected Azure account:

```text
get quantforge/eu-london/azure-storage-connection-string
```

The generated runtime file contains only:

```text
AZURE_STORAGE_ACCOUNT_NAME
AZURE_STORAGE_CONNECTION_STRING
```

The refresh helper validates the pinned account name and the connection-string
account name, then atomically writes:

```text
/run/quantforge/azure-storage.env
```

The file and parent directory are created mode `0600` and `0700` respectively.
Compose passes that file only to the API and worker containers through
`QUANTFORGE_RUNTIME_ENV_FILE`. The application never fetches secrets during a
request, and the deployment exits before starting containers if the refresh
cannot complete.

## London host provisioning

The deployment user needs passwordless access to the following narrow root
operations:

```text
sudo install -d -o root -g root -m 700 /run/quantforge
sudo python3 /opt/quantforge/scripts/refresh_vault_runtime_env.py ...
```

Create the root-owned, mode-`0600` configuration file below on the London
host. It contains only connection metadata and filesystem paths, never secret
values:

```text
/etc/quantforge/vault-agent/config
```

```dotenv
VAULT_SSH_DEST=vault-agent@vault-host
VAULT_SSH_KEY_FILE=/etc/quantforge/vault-agent/id_ed25519
VAULT_SSH_KNOWN_HOSTS=/etc/quantforge/vault-agent/known_hosts
```

The private key is dedicated to this profile and is readable only by root.
The known-hosts file must pin the Vault host key. The SSH public key on the
Vault host must use the forced command from the Secrets Vault repository with
forwarding, agent forwarding, X11, and PTY disabled. Restrict its source IP
to the London host when possible.

The Vault master password remains only in the Vault host's existing Docker
secret. No value is written to GitHub Actions logs, process arguments, or the
QuantForge repository.
