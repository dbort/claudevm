---
id: cv-010
title: "Support Linux hosts"
---

# cv-010: Support Linux hosts

## Summary
claudevm runs on Linux hosts with KVM as well as Apple Silicon Macs, using
the same template and the same commands. Lima picks QEMU with KVM and 9p
mounts on Linux, so most of the work is in `install.sh`, a KVM check, one
macOS-only test path, and docs. Because the integration tier now has two
host platforms, the pipeline also requires a full check on both before a
VM-affecting branch ships. Testing happens on Fedora 45 (AMD Ryzen 7 2700).

## Must Have
- [ ] On Linux, `install.sh` checks for `limactl`, `qemu-system-$(uname -m)`
  and `jq`, plus read/write access to `/dev/kvm`. If any are missing, it
  exits nonzero before installing anything and names every missing item,
  not just the first. When `dnf` is on `PATH` it prints one
  `sudo dnf install ...` line for the missing packages. A missing
  `limactl` gets a pointer to Lima's install instructions. It never runs
  `sudo`, `dnf` or `brew` itself.
- [ ] On Linux with every dependency present, `install.sh` installs the
  template, the command and the SSH `Include` the same way it does on
  macOS.
- [ ] On macOS, `install.sh` still installs a missing Lima via Homebrew,
  and it also installs a missing `jq` the same way.
- [ ] On Linux, `claudevm up` exits nonzero with a message naming
  `/dev/kvm` when that device is not readable and writable, on both the
  create and resume paths, and never invokes `limactl`. On macOS it makes
  no such check.
- [ ] `claudevm code` behaves the same on both platforms. Without `code` on
  `PATH` it prints the current error message, word for word.
- [ ] The integration tier's isolated `LIMA_HOME` lives under a directory
  that exists on both macOS and Linux and stays short enough for Lima's SSH
  control socket path.
- [ ] `tools/check` passes in full, integration tier included, on the Mac
  and on the Fedora 45 host at the approved commit, recorded per the new
  host-check rule below.
- [ ] `.claude/docs/pipeline.md` § Checks, the `work` and `ship` skills,
  and `CLAUDE.md` adopt the host-check rule. When `git diff --name-only
  main...cv-XXX` touches `claudevm`, `claude-sandbox.yaml`, `install.sh` or
  `tests/`: after an APPROVED round, `/work` asks the user to run the full
  `tools/check` on a macOS host and on a Linux host at the approved commit,
  and appends `Host checks at <sha>: macOS green, Linux green` to
  `## Review log`. `/ship` refuses when that line is missing, or when the
  diff from `<sha>` to the branch head at `/ship` start touches anything
  besides the task file. `/ship` runs `tools/check --no-vm` on the merged
  tree, on its own host only, and no longer asks for a Mac run there.
- [ ] The README lists both supported hosts: Apple Silicon Mac on macOS 13+
  with Homebrew, and Linux (x86_64 or aarch64) with Lima, QEMU, `jq` and
  read/write access to `/dev/kvm`, tested on Fedora. It says `install.sh`
  prints install steps on Linux rather than installing anything, and that
  `claudevm code` opens a VS Code Remote-SSH connection when `code` is on
  `PATH`. Its "why a VM" section covers Linux hosts too, and its
  Limitations line about the first boot downloading the image no longer
  says "Mac".
- [ ] `CLAUDE.md`'s project description and Tests bullet name macOS and
  Linux hosts.
- [ ] Manual QA on Fedora 45: `claudevm new`, `secrets`, `up`, `ssh` and
  `code` work, and VS Code Remote-SSH reaches `/workspace`. `/workspace` is
  writable, and files the guest creates there are owned by the host user.
  `git status` and `npm install` in a real project finish in usable time.
  `ausearch -m avc -ts recent` shows no denials from the run.

## Decisions
- On Linux, `install.sh` checks dependencies and prints the steps to fix
  them, and never installs anything. Running sudo from a script is out,
  and printing steps keeps it distro-neutral.
- Support any Linux host with KVM, not just Fedora. The README says
  Fedora is the tested distro, and `dnf` hints appear only when `dnf`
  exists.
- Leave `vmType` and `mountType` unset in `claude-sandbox.yaml`, so each
  host gets Lima's default: QEMU with 9p on Linux, vz on macOS. virtiofs on
  Linux hosts is experimental and needs the Rust `virtiofsd`. 9p speed is
  checked in manual QA, and nothing about virtiofs is planned.
- Check for KVM in both `install.sh` and `claudevm up`. Without KVM, Lima
  falls back to TCG emulation without saying so, and that is too slow to
  use.
- `claudevm code` says nothing about how to install VS Code on either
  platform, and its missing-`code` error keeps its current text,
  `Cmd+Shift+P` included. The user does not want install guidance for VS
  Code.
- Both hosts must pass the full check on the branch. The merge itself
  gets only a `--no-vm` check on the host running `/ship`, because the
  full runs already happened on the branch, and a hygiene edit at ship
  time only touches prose.
- No follow-up Linux tasks: no tray app to match cv-003's macOS menubar,
  and no virtiofs task.
- The research notes in `/tmp/cv-007-linux-fedora-host.md` about
  host-side egress enforcement (nftables, cgroups, `lima:shared`, proxies,
  Incus) are moot: cv-009 removed every network restriction.
- 2026-11-17: Fedora 45 does not package Lima (`dnf info lima` finds
  nothing; the user installed upstream Lima 2.3.0 by hand). A missing
  `limactl` gets only the upstream install link, and the `dnf` line
  never names Lima. A missing `qemu-system-<arch>` adds `qemu-kvm
  qemu-img` to it: `qemu-kvm` pulls in the host-arch emulator and its
  firmware on both arches, and Lima needs `qemu-img` for disks.
- 2026-11-17: Key each test venv by hostname too (`uname -n`, reduced to
  `[A-Za-z0-9._-]`), at the user's request: the guest and host can mount
  the repo at different paths, and venv scripts carry absolute shebangs.

## Notes
- Platform-specific code found so far: `install.sh` (Homebrew-only Lima
  install, a header comment that says "this Mac", a `~/.zshrc` hint where
  Fedora's default shell is bash), `tests/conftest.py` `real_lima_home`
  (`mkdtemp(dir="/private/tmp")`; the socket-length reason holds on Linux
  too, where the limit is 108 characters), and `test.sh`'s Homebrew hint
  for python3 (cosmetic). The `/opt/homebrew/bin` candidate in `install.sh`
  falls through harmlessly on Linux.
- Unverified whether Fedora 45 packages Lima, or at what version. Ask the
  user to run `dnf info lima` on the Fedora box early. If it is packaged
  at or above `minimumLimaVersion`, the Linux hint can name it. Otherwise,
  point to upstream's release tarball.
- The unit tier runs on Linux, including inside claudevm guests that may
  have no `/dev/kvm`. The new KVM check in `cmd_up` would then fail the
  existing `up` unit tests unless the fixtures control both the platform
  and the device. One option is a fake `uname` in `tests/fakes/` plus a
  device-path override like the existing `CLAUDEVM_DOTFILES_SOURCE`.
  Tests for the macOS-only branches must also be able to run on Linux.
- `install.sh` has no tests yet. Its new branches carry documented rules
  and error messages, so they need unit tests with `HOME`, `PATH` and the
  platform isolated. It writes `~/.ssh/config` and a bin dir.
- Files that state the gate rule: `.claude/docs/pipeline.md` § Checks
  (`--no-vm`), `.claude/skills/work/SKILL.md` (steps 4-5),
  `.claude/skills/ship/SKILL.md` (steps 1 and 4), `CLAUDE.md` (Tests
  bullet), and the README's Testing paragraph. `.claude/agents/reviewer.md`
  and `.claude/skills/doc-hygiene/SKILL.md` point to § Checks and only need
  edits if their wording conflicts with the new rule. Once a host check
  goes red, the next step is fixing and another review round. Say so in
  pipeline.md.
- The commented Intel-Mac `vmType: qemu` note in `claude-sandbox.yaml`
  stays. The git `credential.helper` unset already covers Linux helpers
  such as libsecret.
- This task changes the gate it ships under. Apply the new host-check
  rule to cv-010 itself.

## Checklist
- [x] `install.sh`: Linux dependency report with `dnf` hint; macOS brew
  install of Lima and `jq`; platform-neutral PATH and `code` notes.
- [x] `claudevm up`: `require_kvm` before any `limactl` call, Linux only,
  device overridable through `CLAUDEVM_KVM_DEVICE`.
- [x] Fake `uname` in `tests/fakes/`; `run_claudevm` pins platform and
  KVM device; `run_real_claudevm` fakes only `code`.
- [x] `real_lima_home` under the resolved `/tmp`.
- [x] Tests: `tests/test_install.py`, KVM cases in `test_up.py`, both
  platforms in `test_code.py`.
- [x] Host-check rule in `pipeline.md`, `work` and `ship` skills,
  `CLAUDE.md`.
- [x] README and `CLAUDE.md` name both hosts; `test.sh` python3 hint.
- [x] `tools/check --no-vm` green, review.
- [x] Per-host venvs under `.venv/` (`tools/venv`): the first Fedora host
  check failed because the guest-built `.venv` resolved to Fedora's
  Python and found no site-packages.
- [x] Round 3 notes: hostname in the venv key, `tools/venv` in the Stack
  bullet, `pipeline.md` paragraph placement and status caveat.
- [ ] Host checks on macOS and Fedora 45; manual QA on Fedora 45.

## Review log

### Round 1: REJECTED
- **F1: Only the missing-device case of the KVM rule is tested** (`tests/test_up.py:91`, `tests/test_install.py:117`, `tests/test_install.py:142`): every `kvm=False` case points `CLAUDEVM_KVM_DEVICE` at a nonexistent path, so an existing but inaccessible device (root:kvm 0660, user not in `kvm`) is untested; `[ ! -e ]` would pass every test. Add an existing-but-inaccessible case to `test_up.py` and `test_install.py`, skipped as root.
- **N1: Darwin-only `code` hint in install.sh is untested** (`install.sh:84`): non-blocking.
- **N2: Em-dash in a changed header line** (`install.sh:3`): a colon fits § Writing style.
- **N3: Stale fake lists in conftest docstrings** (`tests/conftest.py:5`, `tests/conftest.py:111`): still say only `limactl`/`code` are faked.
- **N4: Integration `LIMA_HOME` on tmpfs on Fedora** (`tests/conftest.py:215`): test VM disks take RAM on Fedora's tmpfs `/tmp`; look here first if the Fedora host check hits ENOSPC.
- **N5: install.sh re-matches its own `missing` string with `case` globs** (`install.sh:62-75`): a flag per check is simpler.

`tools/check --no-vm` (no `limactl` in this guest): passed.

### Round 2: APPROVED
- **N1: The general check-running paragraph now sits under the Host checks heading** (`.claude/docs/pipeline.md:98`): "Run a slow check once per checkpoint..." applies to all of § Checks; move it under `## Checks` or after the `--no-vm` bullets.
- **N2: The derived status skips the pending host checks** (`.claude/docs/pipeline.md:111`): § Status and `tools/task_status.py` report "awaiting `/ship`" once the last round is APPROVED, before the `Host checks` line exists.

All round 1 findings addressed. `tools/check --no-vm` (no `limactl` in this guest): passed.

### Round 3: APPROVED
- **N1: Same-version Linux guest and host still share a venv** (`tools/venv:21`): the key omits the repo path, so a guest and host on the same Python minor version share a venv whose absolute shebangs fail loudly ("bad interpreter") when the mount path differs. Calling `"$VENV_DIR/bin/python3" -m pytest|mypy|pip`, or adding the repo path to the key, avoids it.
- **N2: The Stack bullet's bash 3.2 list leaves out `tools/venv`** (`CLAUDE.md:31-32`).
- **N3: Round 2's notes are still open** (`.claude/docs/pipeline.md:98`, `.claude/docs/pipeline.md:111`).
- **N4: Existing checkouts keep a stale root venv** (`tools/venv:21`): harmless; `rm -rf .venv` clears it.

`tools/check --no-vm` (no `limactl` in this guest): passed.

Host checks at 406ad2447135965c5927ff0fc9e12b361c82905c: macOS green, Linux green

### Round 4: APPROVED
- **N1: The Stack bullet's rewrap left an overlong line** (`CLAUDE.md:32`): 88 characters where the paragraph wraps near 76.
- **N2: A macOS hostname can change from network to network** (`tools/venv:36-39`): a DHCP-assigned name leaves an old venv behind; harmless clutter that `rm -rf .venv` clears.

Round 3's notes addressed. `tools/check --no-vm` (no `limactl` in this guest): passed.

Host checks at 6d566eeab6adca05c4ea8c37c15833a153c02b2e: macOS green, Linux green
