#!/usr/bin/env bash
set -euo pipefail

script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${script_root}/backup-default-branch.sh"
exec codex exec "$@"
