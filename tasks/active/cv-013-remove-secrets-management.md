---
id: cv-013
title: "Remove secrets management"
---

# cv-013: Remove secrets management

## Summary
claudevm stops handling credentials at all. The `secrets` command, the
per-instance secrets mount, and the provisioning that injects a Claude
token and a GitHub token into the VM go away, along with the git HTTPS
rewrite and credential helper that served the GitHub token. A VM still
gets none of the host's credentials; how a user authenticates inside a VM
is their own business, and the repo no longer mentions it.

## Must Have
- [ ] `claudevm secrets <name>` fails with the same unknown-command error and usage text as any other unknown command, and `secrets` is absent from `claudevm`'s usage text and header comment.
- [ ] The per-instance config `claudevm up` renders for a new instance has no `/mnt/claudevm-secrets` mount, and `up` creates no `secrets` directory under the instance config dir (unit test).
- [ ] A new VM's provisioning writes no `CLAUDE_CODE_OAUTH_TOKEN` or `GH_TOKEN` to `/etc/environment` and sets no `url.https://github.com/.insteadOf` or `credential.https://github.com.helper` git config; the dotfile seeding step still runs.
- [ ] `tests/test_secrets.py` is deleted, and no test asserts on a secrets mount or directory.
- [ ] Outside `tasks/completed/` and `tasks/abandoned/`, `git grep -i -E 'secret|claude_oauth|gh_api_token|GH_TOKEN|setup-token'` finds nothing that refers to claudevm's secrets handling. The repo reads as though the feature never existed: no migration note, no mention of existing VMs that still have a secrets mount.

## Decisions
- No replacement credential mechanism and no doc guidance on in-VM auth. The user treats authentication inside a VM as outside claudevm's scope.
- Leave existing VMs alone, with no code or doc for them. Their frozen config keeps the secrets mount and provisioning, and that keeps working off whatever token files remain on the host; the user handles those VMs by hand.
- Remove the `git@github.com` to HTTPS rewrite and the token credential helper along with the tokens. They exist only to serve `GH_TOKEN`, and without it the rewrite would break SSH-key setups made inside the VM.
- Keep the `/mnt/claudevm-config` mount and dotfile seeding; they are unrelated to credentials.
- Keep the statement that no host credentials are mounted into a VM. That is the isolation property, not secrets management.
- `secrets` falls through to the existing unknown-command branch, with no special removal message, so the CLI shows no trace of the feature.

## Notes
- Known dependents of the names being removed, from a grep at plan time:
  - `claudevm`: header comment, `usage`, `cmd_secrets`, the `main` dispatch, and `cmd_up`'s secrets dir creation and mount (plus its comment).
  - `claude-sandbox.yaml`: header comment (the mounts line and item 3), provisioning step 3, and the step 2 comment that mentions the secrets helper.
  - `install.sh`: the quick-start echo line for `claudevm secrets`.
  - `README.md`: intro paragraphs, install's "or their secrets" line, Quick start, Commands table, How it works, the whole Credentials section (including the "proportionate protection" and credential-proxy paragraph), Repo layout, the migration section's `claudevm secrets` step, and the Limitations bullet's "and tokens".
  - `CLAUDE.md`: the opening description ("with per-VM credentials and none of the host's").
  - Tests: `tests/test_secrets.py`, `tests/test_up.py` (secrets dir and mount assertions), `tests/test_new.py` (integration check for `/mnt/claudevm-secrets`), and the `tests/conftest.py` docstrings that list secrets.
- Leave `tasks/completed/` and `tasks/abandoned/` as they are: they are the historical record. `.claude/docs/github-actions-hardening.md` mentions tokens and secrets in the GitHub Actions sense, which is unrelated.
- cv-012's migration script re-renders old VMs from the current template; once this task lands, that re-render drops the secrets mount and provisioning. Its Must Have checks the per-instance mounts `cmd_up` renders, which covers either order. Values a migrated VM already has in `/etc/environment` and its git config stay behind, which matches the decision to leave existing VMs alone.
- cv-011 is independent: the Claude CLI's first-run login is the user's own step.
- 2026-11-19: Also dropped the secrets mentions in `tasks/active/cv-003-menubar-vm-control.md` (Non-goals) and `tasks/active/cv-005-docker-golang-provisioning.md` (Background), which the Must Have grep covers. Kept cv-012's Notes line about cv-013: it is the cross-task dependency record `CLAUDE.md` requires, about this task rather than the feature.
- 2026-11-19: Fixed `run_claudevm(include_code=False)` in `tests/conftest.py`, a defect already on `main` that the Linux host check hit: it dropped every PATH dir holding a real `code`, and on a host where `code` sits in `/usr/bin` that took `bash` with it. It now links those dirs' other commands into its bin dir. Fixed here because the host checks this task needs cannot go green without it.

## Checklist
- [x] Remove `cmd_secrets`, its dispatch, usage and header lines, and `cmd_up`'s secrets dir and mount from `claudevm`.
- [x] Remove provisioning step 3 and secrets mentions from `claude-sandbox.yaml`.
- [x] Drop the `claudevm secrets` line from `install.sh`.
- [x] Remove secrets from `README.md` (intro, install, Quick start, Commands, How it works, Credentials section, Repo layout, migration step, Limitations) and `CLAUDE.md`'s opening.
- [x] Delete `tests/test_secrets.py`; update `tests/test_up.py`, `tests/test_new.py`, `tests/conftest.py`; add `tests/test_cli.py` for the unknown-command fall-through.
- [x] Drop secrets mentions from cv-003 and cv-005 task files.
- [x] `tools/check` green.

## Review log

### Round 1: APPROVED
- **N1: ` -- ` dashes left in rewritten comment lines** (`claudevm:127`, `tests/conftest.py:133`): both rewritten lines keep their old ` -- ` asides, which § Writing style forbids; swap each for a colon or a new sentence in the next round, or leave to `/ship`'s doc-hygiene sweep.
- **N2: Mount-count assertion depends on the template's text** (`tests/test_up.py:41`): `rendered.count("mountPoint:") == 2` counts across the whole rendered file, template included; it would fail loudly, not silently, so it is acceptable as written.

`tools/check --no-vm` green (`limactl` not on `PATH`).

Linux host check at 4889a0cf8035b9164e37d494dd8f88ad0c413c43: red. `test_code_errors_clearly_when_cli_missing` failed on a fixture defect already on `main` (fixed in 5c53c89); `test_down_then_up_resumes_real_instance` failed when `limactl start` died with `failed to unmarshal ... as events.Event: unexpected end of JSON input`, suspected an upstream Lima race.

### Round 2: APPROVED
- **N1: ` -- ` dashes still in comment lines from round 1** (`claudevm:127`, `tests/conftest.py:133`): round 1's N1 is still open; fix on the branch or leave to `/ship`'s doc-hygiene sweep.
- **N2: Linked commands now come before earlier PATH entries** (`tests/conftest.py:156-168`): with `include_code=False`, commands linked into `bin_dir` can shadow ones from earlier PATH entries such as Homebrew; only the missing-CLI tests use it and they need only `bash` and basic shell tools, so acceptable as written.

`tools/check --no-vm` green (`limactl` not on `PATH`).
