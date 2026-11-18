# claudevm

Per-project, isolated Linux VMs for running Claude Code sessions on Apple Silicon Macs and Linux hosts, built on [Lima](https://lima-vm.io), with simple per-VM credential handling baked in.

Each project gets its own real virtual machine (its own kernel, not just a container namespace), mounted into VS Code over SSH. A VM sees only its project directory and its own scoped credentials: none of your host credentials, and not your home directory.

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

Safe to re-run: it refreshes the shared template file but never touches your per-project VMs or their secrets.

## Quick start

```bash
claudevm new myproject ~/code/myproject     # create config (doesn't boot yet)
claudevm secrets myproject                  # Claude token, optional GitHub token
claudevm up myproject                       # boot the VM
claudevm code myproject                     # open VS Code (Remote-SSH) into it
```

## Commands

| Command | What it does |
|---|---|
| `claudevm new <name> <dir>` | Create config for a new sandbox, mounting `dir` as `/workspace`. |
| `claudevm secrets <name>` | Save a Claude Code token, and optionally a GitHub token, for this VM only. |
| `claudevm up <name>` | Boot (or resume) the VM, mounting the project at `/workspace`. |
| `claudevm down <name>` | Stop the VM. Disk state is kept. |
| `claudevm rm <name>` | Stop, delete the VM, and delete its config. Asks for confirmation. |
| `claudevm ssh <name> [-- cmd]` | Shell into the VM. With a trailing `-- cmd`, runs `cmd` non-interactively instead. |
| `claudevm code <name>` | Open VS Code (Remote-SSH) at `/workspace` on the VM. |
| `claudevm ls [--json]` | List claudevm-managed instances and their status (`Running`, `Stopped`, or `new` for one that's never been booted). `--json` for structured output. |

Resource sizing (defaults: 4 CPUs, 4 GiB memory, 60 GB disk) can be overridden with `CLAUDEVM_CPUS`, `CLAUDEVM_MEMORY`, `CLAUDEVM_DISK` environment variables before `claudevm up`.

## How it works

- **`claude-sandbox.yaml`** is a Lima template (Ubuntu, self-contained — see the file header for why it doesn't use Lima's `base:` composition) that:
  - installs `python3` with `pip` and `venv`
  - seeds `~/.gitconfig` and `~/.vimrc` from your host's copies, if `claudevm new` found any — one-time only, so later in-VM edits aren't overwritten on reboot
  - wires up the per-VM secrets described under [Credentials](#credentials)
- **`claudevm`** is the wrapper: at `up` time it renders a per-instance Lima config (template plus an explicit `mounts:` list for the project dir and per-instance config/secrets) so the shared template file stays generic across all projects.
- **`pre-push-branch-guard.sh`** is an optional git hook you can drop into a project to block direct pushes to protected branches, as a local backstop alongside GitHub branch protection rules.

## Credentials

None of your host credentials are ever mounted into a VM. Instead:

- **Claude Code**: `claudevm secrets <name>` prompts you to run `claude setup-token` on your *host* (it needs a browser) and saves the result as a per-VM `CLAUDE_CODE_OAUTH_TOKEN`, scoped to inference only rather than a full account session.
- **GitHub (optional)**: `claudevm secrets <name>` can prompt for a fine-grained personal access token, saved as a per-VM `GH_TOKEN`. This is the VM's sole GitHub credential, covering git push/pull (over HTTPS — SSH-style remotes get rewritten transparently), opening/managing PRs, Issues, and, if needed, Projects, all scoped to **one repo only** in the token's repository permissions. Pair this with a branch protection rule requiring PRs into `main`, so the token can push feature branches but not merge directly. One exception to the one-repo scoping: Projects (v2) boards belong to the org/user account, not a repo, so GitHub has no way to scope that permission to a single project board — granting it applies to every project that account owns. Unlike an SSH key, this token has a mandatory expiration; re-run `claudevm secrets <name>` to replace it (it'll offer to overwrite an existing one), then `claudevm down <name> && claudevm up <name>` to pick it up — the mount already exists, so a restart is all it takes, no need to recreate the VM.

See `claudevm secrets --help` output (run the command) for the exact steps it prints.

**This is proportionate protection for personal projects, not a hard security boundary.** If you're ever handling something high-stakes, the stronger pattern is a credential proxy that keeps the token on the host entirely and injects it into requests, so the VM never holds the secret at all.

## Repo layout

```
claude-sandbox.yaml         Lima VM template (packages, dotfiles, secrets provisioning)
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

Older versions of claudevm restricted VMs' outbound network access with an in-guest firewall and a domain allowlist. A VM created by one of those versions keeps those restrictions, because Lima stores each VM's provisioning when the VM is created and reapplies it on every boot. To drop them, recreate the VM: `claudevm rm <name>`, then `claudevm new`, `claudevm secrets`, and `claudevm up`. `rm` deletes the VM's disk, so commit or copy out anything you need first; the project directory on the host is untouched.

## Limitations

- **Outbound network access is unrestricted.** Anything running in a VM, Claude Code itself or any dependency it installs via `npm`/`pip`/`go get`, can send that VM's project code and tokens anywhere on the internet. The boundary that holds is the VM itself: a compromised guest still can't reach your host credentials or other projects, only what's scoped to that one VM.
- First `claudevm up` downloads the Ubuntu cloud image, so it's slower the first time on a given host; later VMs reuse the cache.
