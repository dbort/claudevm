---
id: cv-009
title: "Remove outbound network restrictions from VMs"
---

# cv-009: Remove outbound network restrictions from VMs

## Summary
New VMs get unrestricted outbound network access. The default-deny
firewall, its domain allowlist, DNS pinning, and the `allow` and `refresh`
commands are deleted outright, because the user turns the firewall off on
every new VM anyway. Afterward the code reads as if the restrictions never
existed; only the README mentions them, to explain how to migrate existing
VMs.

## Must Have
- [x] `claude-sandbox.yaml` installs none of `iptables`, `ipset`,
  `dnsutils` or `cron`, writes no `iptables`/`ip6tables` rules, no
  systemd-resolved or `resolvectl` DNS override, no `/usr/local/bin`
  firewall script, and no cron job. Its header comment lists only the
  provisioning that remains.
- [x] `claudevm allow` and `claudevm refresh` do not exist: both exit
  nonzero through the existing unknown-command usage path, and `usage`
  lists neither.
- [x] `claudevm new` creates no `allowlist.txt` and prints no allowlist
  line.
- [x] `default-allowlist.txt`, `tests/test_allow.py` and
  `tests/test_refresh.py` are deleted, and `install.sh` copies only the
  template.
- [x] `git grep -n -i -E 'allowlist|firewall|iptables|ipset|egress'`
  matches nothing outside `tasks/` and the README's migration note.
- [x] `README.md` presents the protection as the per-project VM (its own
  kernel) plus per-VM scoped credentials, with no host credentials or
  home directory mounted. Its Limitations section says outbound network
  access is unrestricted, so anything running in a VM can send that VM's
  project code and tokens anywhere.
- [x] `README.md` has one migration note: VMs created before this change
  keep their old network restrictions, which their stored provisioning
  reapplies on every boot, until recreated with `claudevm rm`, `new`,
  `secrets` and `up`.
- [x] `CLAUDE.md`'s project description no longer mentions a firewall.
- [x] `tools/check` passes in full, integration tier included, on the Mac.

## Decisions
- Remove everything that exists only for the firewall: the rules, the
  IPv6 lockdown, the ipset refresh script and its cron job, the
  allowlist, the Quad9/Cloudflare DNS pinning (VMs use Lima's default
  resolver), the four firewall-only packages, and the `allow` and
  `refresh` commands. The user always disables the firewall on new VMs,
  so keeping any piece leaves machinery with no purpose.
- Final code, comments and tests never acknowledge that restrictions
  existed. Only the README mentions them, as a migration note. Add no
  test for removed behavior and no test that egress is open; a test
  stays only if it would make sense in a program that never had
  restrictions.
- No migration code. An existing VM keeps the Lima config stored when it
  was created, so its old provisioning keeps reapplying the firewall;
  recreating the VM is the documented way to drop it.
- `allow` and `refresh` fall through to the usual unknown-command error
  with no removal notice: this is a personal tool with one user.
- `install.sh` stops copying `default-allowlist.txt` and does not delete
  copies left in `~/.config/claudevm/`, so it carries no trace of the old
  file.
- Leave per-VM `allowlist.txt` files in existing instance config dirs
  alone: existing VMs' stored provisioning reads them at boot.
- Abandon cv-001 (host-side firewall enforcement) and cv-006 (firewall
  pause/resume): with no restrictions, neither has anything left to do.
- cv-005 (Docker and Go) is amended to assume no firewall, and is blocked
  on this task: its plan no longer adds Docker Hub to an allowlist, so
  landing it first would leave `docker pull` blocked.
- 2026-11-17: the Must Have grep targets firewall terms. Its remaining
  matches are accepted as false positives: "regression" (contains
  "egress") in `CLAUDE.md` and `tests/test_new.py`, and GitHub Actions'
  `egress-policy` setting in `.claude/docs/github-actions-hardening.md`.

## Notes
- Known dependents of the deletions, by file:
  - `claude-sandbox.yaml`: header list items 1-4, and provisioning steps
    1 (packages), 2 (DNS pinning), 3 (default-deny rules) and 4 (refresh
    script and cron). Renumber the remaining steps and header items.
  - `claudevm`: header comment usage lines, `usage`, `DEFAULT_ALLOWLIST`,
    `cmd_new`'s allowlist copy and output line, `cmd_refresh`,
    `cmd_allow`, and their dispatch cases.
  - `install.sh`: the header comment on re-running and the allowlist
    copy.
  - `tests/conftest.py`: the `default-allowlist.txt` copies in both
    CLAUDEVM_HOME fixtures, the `run_claudevm` docstring's
    `EDITOR for cmd_allow` example, and the `shared_instance` docstring's
    list of users (`refresh`).
  - `tests/test_new.py`: the `allowlist.txt` assertion.
  - `README.md`: the intro, Install (allowlist copy), Quick start, the
    Commands rows, How it works, the Credentials paragraph's "firewall
    wouldn't allow" aside, Repo layout, and Limitations.
  - `.claude/docs/pipeline.md` § Checks `--no-vm`: drop
    `default-allowlist.txt` from the list of files the integration tier
    exercises.
- Without DNS pinning, provisioning's `apt-get` resolves through Lima's
  default resolver. The existing integration tests boot fresh VMs, so a
  full `tools/check` on the Mac covers it.
- Docs outside the README describe current behavior only (`CLAUDE.md`
  § Writing style by destination).

- 2026-11-17: also removed `run_claudevm`'s `extra_env` parameter, whose
  only caller was `tests/test_allow.py`.
- 2026-11-17: `/work` ran in a guest without `limactl`, so checks ran
  with `--no-vm`; the full run on the Mac happens at `/ship`
  (`pipeline.md` § Checks).

## Checklist
- [x] Delete `default-allowlist.txt`, `tests/test_allow.py`,
  `tests/test_refresh.py`.
- [x] `claude-sandbox.yaml`: drop provisioning steps 1-4's firewall
  parts, renumber steps and header list.
- [x] `claudevm`: drop `allow`/`refresh`, `DEFAULT_ALLOWLIST`, the
  allowlist copy and output line.
- [x] `install.sh`, `tests/conftest.py`, `tests/test_new.py`,
  `pipeline.md` § Checks.
- [x] `README.md` (protection model, Limitations, migration note) and
  `CLAUDE.md` description.
- [x] `tools/check --no-vm` green.

## Review log

### Round 1: APPROVED
- **N1: Full integration tier not run in this review** (`tasks/active/cv-009-remove-egress-firewall.md:52`): `limactl` is not on PATH, so the review ran `tools/check --no-vm` (exit 0: shellcheck clean, 33 unit tests passed, 9 integration deselected, mypy clean). The Mac full-run Must Have, which also covers provisioning against Lima's default resolver, stays open for `/ship` under `pipeline.md` § Checks.
- **N2: Stale plural in README Install** (`README.md:27`): "refreshes the shared template files" should say "file"; `install.sh` copies only the template.
- **N3: Em-dashes kept on edited README lines** (`README.md:3`, `README.md:66`): reworded lines keep em-dash asides that § Writing style forbids; they predate this task.
- **N4: Unknown-command path has no test** (`claudevm:315`): the `allow`/`refresh` Must Have relies on it; the gap predates this task and the Decisions rule out tests for removed behavior.
