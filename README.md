# claudevm

Per-project, isolated Linux VMs for running Claude Code sessions on Apple Silicon Macs and Linux hosts, built on [Lima](https://lima-vm.io).

Each project gets its own real virtual machine (its own kernel, not just a container namespace), mounted into VS Code over SSH. A VM sees only its project directory: none of your host credentials, and not your home directory.

## Why a VM instead of a container

Containers on macOS all run inside one shared Linux VM under the hood anyway (there's no native Linux kernel to run them on). On a Linux host, containers share the host's own kernel, so a kernel exploit in one reaches the host and every other project. If you want a real security boundary, a separate kernel per project rather than namespace isolation inside one shared kernel, you want dedicated VMs. Lima gives you that with near-container ergonomics: fast boot, simple mounts, native SSH.

## Requirements

One of:

- **macOS:** an Apple Silicon Mac on macOS 13+, with [Homebrew](https://brew.sh).
- **Linux:** an x86_64 or aarch64 host with [Lima](https://lima-vm.io/docs/installation/), QEMU for the host's architecture (`qemu-system-x86_64` or `qemu-system-aarch64`), `jq`, and read/write access to `/dev/kvm`. Tested on Fedora.

Optionally, VS Code with the Remote - SSH extension: `claudevm code` opens a Remote-SSH connection into the VM when the `code` CLI is on your `PATH`.

## Install

```bash
git clone <this-repo-url> claudevm-kit
cd claudevm-kit
./install.sh
```

On macOS, this installs Lima and `jq` via Homebrew if they're missing. On Linux, it installs nothing: if a dependency is missing, it lists everything missing, prints the steps to install it, and exits. With dependencies in place, it copies the VM template to `~/.config/claudevm/`, installs the `claudevm` command onto your `PATH`, and adds an `Include` line to `~/.ssh/config` so VS Code's Remote-SSH extension can see Lima-managed hosts.

Safe to re-run: it refreshes the shared template file but never touches your per-project VMs.

## Quick start

```bash
claudevm new myproject ~/code/myproject     # create config (doesn't boot yet)
claudevm up myproject                       # boot the VM
claudevm code myproject                     # open VS Code (Remote-SSH) into it
```

## Commands

| Command | What it does |
|---|---|
| `claudevm new <name> <dir>` | Create config for a new sandbox, mounting `dir` as `/workspace`. |
| `claudevm up <name>` | Boot (or resume) the VM, mounting the project at `/workspace`. |
| `claudevm down <name>` | Stop the VM. Disk state is kept. |
| `claudevm rm <name>` | Stop, delete the VM, and delete its config. Asks for confirmation. |
| `claudevm ssh <name> [-- cmd]` | Shell into the VM. With a trailing `-- cmd`, runs `cmd` non-interactively instead. |
| `claudevm code <name>` | Open VS Code (Remote-SSH) at `/workspace` on the VM. |
| `claudevm ls [--json]` | List claudevm-managed instances and their status (`Running`, `Stopped`, or `new` for one that's never been booted). `--json` for structured output. |

A new VM's CPU and memory defaults scale with the host: half its CPU threads and a quarter of its RAM, each held between a floor and a cap (`default_cpus` and `default_memory_gib` in `claudevm`). The disk default is `DISK` in `claudevm`. Set `CLAUDEVM_CPUS`, `CLAUDEVM_MEMORY` (GiB) or `CLAUDEVM_DISK` (GiB) before the first `claudevm up` to override them; a VM keeps its size after creation.

## How it works

- **`claude-sandbox.yaml`** is a Lima template (Ubuntu, self-contained — see the file header for why it doesn't use Lima's `base:` composition) that:
  - installs `python3` with `pip` and `venv`
  - turns on zram swap, so memory pressure slows a VM down instead of killing processes
  - seeds `~/.gitconfig` and `~/.vimrc` from your host's copies, if `claudevm new` found any — one-time only, so later in-VM edits aren't overwritten on reboot
- **`claudevm`** is the wrapper: at `up` time it renders a per-instance Lima config (template plus an explicit `mounts:` list for the project dir and per-instance config) so the shared template file stays generic across all projects.
- **`pre-push-branch-guard.sh`** is an optional git hook you can drop into a project to block direct pushes to protected branches, as a local backstop alongside GitHub branch protection rules.

## Repo layout

```
claude-sandbox.yaml         Lima VM template (packages, dotfiles)
claudevm                    CLI wrapper
install.sh                  One-shot setup script
pre-push-branch-guard.sh    Optional git hook for protected branches
test.sh                     Test entry point (see Testing below)
tests/                      pytest suite (unit + integration tiers)
tools/check                 Merge gate: shellcheck, tests, mypy
tools/task_status.py        Task backlog and next free task id
tasks/                      Task plans (active, completed, abandoned)
.claude/                    Claude Code task pipeline: skills, agents, rules
README.md                   This file
```

## Testing

```bash
./test.sh              # everything: unit + integration
./test.sh unit          # fast tier -- mocks limactl/code, no real VMs, seconds
./test.sh integration   # slow tier -- boots real, namespaced claudevm-test-* VMs
./test.sh unit -- -k test_new   # forward extra args straight to pytest
```

`tools/check` runs the whole gate: `shellcheck`, the full test suite, and `mypy`. The integration tier runs on macOS and Linux hosts with Lima. Pass `--no-vm` to skip it where Lima isn't installed, such as inside a claudevm guest.

`test.sh` manages its own virtualenv under `.venv/` (created and kept up to date automatically) — there's no separate setup step, and no need to invoke `pytest` directly.

The unit tier fakes `limactl`/`code` and isolates `$HOME`/config dirs, so it never touches your real instances or credentials. The integration tier drives the real `claudevm` script against real Lima VMs, but only ever creates/deletes instances named `claudevm-test-*`, cleaning them up even on failure — it never touches your actual project VMs. It's slower (VM boot time) and local-only; it never runs in CI.

## Migrating VMs created by older versions

Older versions of claudevm restricted VMs' outbound network access with an in-guest firewall and a domain allowlist. A VM created by one of those versions keeps those restrictions, because Lima stores each VM's provisioning when the VM is created and reapplies it on every boot. To drop them, recreate the VM: `claudevm rm <name>`, then `claudevm new` and `claudevm up`. `rm` deletes the VM's disk, so commit or copy out anything you need first; the project directory on the host is untouched.

## Limitations

- **Outbound network access is unrestricted.** Anything running in a VM, Claude Code itself or any dependency it installs via `npm`/`pip`/`go get`, can send that VM's project code anywhere on the internet. The boundary that holds is the VM itself: a compromised guest still can't reach your host credentials or other projects, only what's scoped to that one VM.
- First `claudevm up` downloads the Ubuntu cloud image, so it's slower the first time on a given host; later VMs reuse the cache.
