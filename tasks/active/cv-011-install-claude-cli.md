---
id: cv-011
title: "Install the Claude Code CLI in new VMs"
---

# cv-011: Install the Claude Code CLI in new VMs

## Summary
New VMs get the token for Claude Code but not the `claude` command itself,
so there is nothing to run from `claudevm ssh` or VS Code's integrated
terminal without a manual install. This task makes `claude-sandbox.yaml`
install it with Anthropic's native installer, on `PATH` in every shell
context, and kept current by Claude Code's own auto-updater.

## Must Have
- [ ] A freshly created VM has a working `claude`: `claudevm ssh <name> -- claude --version` exits 0 (non-interactive, bare command name).
- [ ] Bare `claude` also resolves in an interactive login shell in the VM (`bash -lic 'command -v claude'` via `claudevm ssh`).
- [ ] A reboot (`claudevm down` then `up`) does not reinstall: the resolved `claude` binary's path and mtime are unchanged across the restart.
- [ ] When the installer download fails, provisioning prints a warning naming the failure, the VM still finishes booting (`claudevm up` exits 0), and the next boot retries the install. Manual-QA case: no test can make the guest's download fail without new test machinery.
- [ ] `README.md` lists the Claude Code CLI among what the template installs, and gives the one-line installer command for VMs created before this change.
- [ ] `claude-sandbox.yaml`'s header list of what the template adds includes the CLI.

## Decisions
- Install only; no `claudevm claude` subcommand. The user runs `claude` from `claudevm ssh` or the VS Code terminal.
- Use the native installer (`curl -fsSL https://claude.ai/install.sh | bash`) as the VM user, not npm: no Node dependency in every VM, and it ships its own auto-updater. Confirm the install location and auto-update behavior against the installer at /work; do not assume `~/.local/bin`.
- Install only if `claude` is missing, then rely on the built-in auto-updater. Provisioning re-runs every boot, so an unconditional install would re-download on each restart; pinning would duplicate the auto-updater's job.
- Leave the stock first-run onboarding; do not pre-seed `~/.claude.json`. The user clicks through it once per VM.
- Bare `claude` must resolve in interactive SSH, non-interactive `claudevm ssh <name> -- cmd`, and VS Code's integrated terminal. A user-local bin dir is on `PATH` only in login shells, and `limactl shell -- cmd` is not one.
- A failed download warns and continues booting. The CLI is a convenience; a VM with no network on one boot is still usable, and install-if-missing retries next boot.
- README tells owners of existing VMs to run the installer once inside the VM. Lima freezes provisioning at creation, and a manual install avoids the `rm`/recreate the migration section otherwise requires.

## Notes
- Provisioning lives in `claude-sandbox.yaml` § `provision:`; existing steps show the system-vs-user mode split. The installer must run as the VM user so the auto-updater can write its own install dir without root.
- For non-interactive `PATH`, a `/usr/local/bin/claude` symlink to the user-local launcher is one option; check it still points at the current version after an auto-update.
- Integration tests: reuse `shared_instance` (`tests/conftest.py`) for the version and interactive-shell checks; `tests/test_up.py::test_down_then_up_resumes_real_instance` shows the down/up pattern for the reboot check.
- cv-005 also edits `claude-sandbox.yaml` provisioning and `PATH` (its decision 8 documents Ubuntu's `/etc/profile` resetting `PATH` for interactive shells). Independent tasks, but whichever lands second rebases its provisioning step around the other.

## Checklist

## Review log
