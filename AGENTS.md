# Repository operating instructions

These instructions apply to the entire repository unless a more specific AGENTS.md exists below a subdirectory.

## Working rules

- Treat the repository's GitHub default branch as the source of truth. Fetch current remote state before editing and preserve existing user changes.
- Use a short-lived branch and a reviewable pull request for nontrivial changes. Do not force-push or rewrite default-branch history.
- Read the README, project documentation, and existing local instructions before architectural or deployment changes.
- Run the relevant tests, checks, or builds for the files changed. Report checks that could not run; never describe an unexecuted test as passing.
- Never commit credentials, API keys, tokens, private keys, vault material, customer data, database dumps, or generated runtime secret files.
- Preserve repository boundaries and existing ownership. Do not create a parallel repository or move functionality across repositories without checking the software-estate/control-plane guidance available to the working environment.
- Treat production, destructive cleanup, security-sensitive changes, secret rotation, repository archival/deletion, and automatic merges as review-required operations unless explicitly authorized.
- Respect this repository's existing versioning and deployment conventions rather than inventing a new release scheme.

## Automation

Mechanical fleet housekeeping may create a branch and pull request, but it must not overwrite an existing AGENTS.md or merge itself automatically.
