#!/usr/bin/env bash
set -euo pipefail

backup_remote="${1:-origin}"
default_ref="$(git symbolic-ref --quiet --short "refs/remotes/${backup_remote}/HEAD" 2>/dev/null || true)"
default_branch="${default_ref#${backup_remote}/}"

if [[ "${default_branch}" != "main" && "${default_branch}" != "master" ]]; then
  if git show-ref --verify --quiet "refs/remotes/${backup_remote}/main"; then
    default_branch="main"
  elif git show-ref --verify --quiet "refs/remotes/${backup_remote}/master"; then
    default_branch="master"
  else
    echo "Unable to resolve ${backup_remote}/main or ${backup_remote}/master." >&2
    exit 1
  fi
fi

git fetch "${backup_remote}" "${default_branch}"
default_sha="$(git rev-parse "${backup_remote}/${default_branch}")"
backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_branch="backup/${default_branch}-pre-codex-${backup_stamp}-${default_sha:0:8}"

git push "${backup_remote}" "${default_sha}:refs/heads/${backup_branch}"

echo "Created ${backup_remote}/${backup_branch} at ${default_sha}."
echo "Rollback source: ${backup_branch}"
