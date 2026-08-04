# claudevm

Per-project, isolated Linux VMs for running Claude Code sessions on Apple Silicon Macs — built on [Lima](https://lima-vm.io), with a default-deny firewall and simple credential handling baked in.

Each project gets its own real virtual machine (its own kernel, not just a container namespace), mounted into VS Code over SSH, with network access restricted to an allowlist of domains you control.

## Why a VM instead of a container

Containers on macOS all run inside one shared Linux VM under the hood anyway (there's no native Linux kernel to run them on). If you want a real security boundary — a separate kernel per project, not just namespace isolation inside one shared kernel — you want dedicated VMs. Lima gives you that with near-container ergonomics: fast boot, simple mounts, native SSH.

## Requirements

- Apple Silicon Mac, macOS 13+
- [Homebrew](https://brew.sh)
- VS Code, with the Remote - SSH extension (optional, only needed for `claudevm code`)

## Install

```bash
git clone <this-repo-url> claudevm-kit
cd claudevm-kit
./install.sh
```

This installs Lima (via Homebrew, if not already present), copies the VM template and default firewall allowlist to `~/.config/claudevm/`, installs the `claudevm` command onto your `PATH`, and adds an `Include` line to `~/.ssh/config` so VS Code's Remote-SSH extension can see Lima-managed hosts.

Safe to re-run — it refreshes the shared template files but never touches your per-project VMs or their secrets.

## Quick start

```bash
claudevm new myproject ~/code/myproject     # create config (doesn't boot yet)
claudevm allow myproject                    # optional: edit the domain allowlist
claudevm secrets myproject                  # Claude token, optional GitHub token
claudevm up myproject                       # boot the VM
claudevm code myproject                     # open VS Code (Remote-SSH) into it
```

## Commands

| Command | What it does |
|---|---|
| `claudevm new <name> <dir>` | Create config for a new sandbox, mounting `dir` as `/workspace`. |
| `claudevm allow <name>` | Edit the domain allowlist (`$EDITOR`). Applied within 5 minutes, or immediately with `refresh`. |
| `claudevm secrets <name>` | Save a Claude Code token, and optionally a GitHub token, for this VM only. |
| `claudevm up <name>` | Boot (or resume) the VM, mounting the project at `/workspace`. |
| `claudevm down <name>` | Stop the VM. Disk state is kept. |
| `claudevm rm <name>` | Stop, delete the VM, and delete its config. Asks for confirmation. |
| `claudevm ssh <name> [-- cmd]` | Shell into the VM. With a trailing `-- cmd`, runs `cmd` non-interactively instead. |
| `claudevm code <name>` | Open VS Code (Remote-SSH) at `/workspace` on the VM. |
| `claudevm refresh <name>` | Re-run the firewall/allowlist refresh immediately, instead of waiting for cron. |
| `claudevm ls [--json]` | List claudevm-managed instances and their status (`Running`, `Stopped`, or `new` for one that's never been booted). `--json` for structured output. |

Resource sizing (defaults: 4 CPUs, 4 GiB memory, 60 GB disk) can be overridden with `CLAUDEVM_CPUS`, `CLAUDEVM_MEMORY`, `CLAUDEVM_DISK` environment variables before `claudevm up`.

## How it works

- **`claude-sandbox.yaml`** is a Lima template (Ubuntu, self-contained — see the file header for why it doesn't use Lima's `base:` composition) that:
  - installs `iptables`/`ipset`
  - pins DNS resolution to fixed resolvers (Quad9 `9.9.9.9` primary, Cloudflare `1.1.1.1` secondary) instead of whatever the DHCP-provided resolver happens to be
  - sets a default-deny egress policy, with DNS egress itself restricted to just those two resolver IPs
  - blocks all IPv6 egress outright (loopback only) — the allowlist mechanism only handles IPv4
  - installs a script that resolves your allowlist domains to IPs and refreshes them every 5 minutes via cron — a one-time DNS resolution isn't enough since services like npm and GitHub sit behind rotating CDN IPs
  - seeds `~/.gitconfig` and `~/.vimrc` from your host's copies, if `claudevm new` found any — one-time only, so later in-VM edits aren't overwritten on reboot
- **`default-allowlist.txt`** is the starting domain list (Anthropic API, GitHub, npm, PyPI, Ubuntu mirrors), copied per-project so you can tune it per sandbox.
- **`claudevm`** is the wrapper: at `up` time it renders a per-instance Lima config (template plus an explicit `mounts:` list for the project dir and per-instance config/secrets) so the shared template file stays generic across all projects.
- **`pre-push-branch-guard.sh`** is an optional git hook you can drop into a project to block direct pushes to protected branches, as a local backstop alongside GitHub branch protection rules.

## Credentials

None of your host credentials are ever mounted into a VM. Instead:

- **Claude Code**: `claudevm secrets <name>` prompts you to run `claude setup-token` on your *host* (it needs a browser, which the VM's firewall wouldn't allow anyway) and saves the result as a per-VM `CLAUDE_CODE_OAUTH_TOKEN` — scoped to inference only, not a full account session.
- **GitHub (optional)**: `claudevm secrets <name>` can prompt for a fine-grained personal access token, saved as a per-VM `GH_TOKEN`. This is the VM's sole GitHub credential, covering git push/pull (over HTTPS — SSH-style remotes get rewritten transparently), opening/managing PRs, Issues, and, if needed, Projects, all scoped to **one repo only** in the token's repository permissions. Pair this with a branch protection rule requiring PRs into `main`, so the token can push feature branches but not merge directly. One exception to the one-repo scoping: Projects (v2) boards belong to the org/user account, not a repo, so GitHub has no way to scope that permission to a single project board — granting it applies to every project that account owns. Unlike an SSH key, this token has a mandatory expiration; re-run `claudevm secrets <name>` to replace it (it'll offer to overwrite an existing one), then `claudevm down <name> && claudevm up <name>` to pick it up — the mount already exists, so a restart is all it takes, no need to recreate the VM.

See `claudevm secrets --help` output (run the command) for the exact steps it prints.

**This is proportionate protection for personal projects, not a hard security boundary.** If you're ever handling something high-stakes, the stronger pattern is a credential proxy that keeps the token on the host entirely and injects it into requests, so the VM never holds the secret at all.

## Repo layout

```
claude-sandbox.yaml         Lima VM template (firewall + secrets provisioning)
default-allowlist.txt       Starting domain allowlist
claudevm                    CLI wrapper
install.sh                  One-shot setup script
pre-push-branch-guard.sh    Optional git hook for protected branches
test.sh                     Test entry point (see Testing below)
tests/                      pytest suite (unit + integration tiers)
README.md                   This file
```

## Testing

```bash
./test.sh              # everything: unit + integration
./test.sh unit          # fast tier -- mocks limactl/code, no real VMs, seconds
./test.sh integration   # slow tier -- boots real, namespaced claudevm-test-* VMs
./test.sh unit -- -k test_new   # forward extra args straight to pytest
```

`test.sh` manages its own virtualenv under `.venv/` (created and kept up to date automatically) — there's no separate setup step, and no need to invoke `pytest` directly.

The unit tier fakes `limactl`/`code` and isolates `$HOME`/config dirs, so it never touches your real instances or credentials. The integration tier drives the real `claudevm` script against real Lima VMs, but only ever creates/deletes instances named `claudevm-test-*`, cleaning them up even on failure — it never touches your actual project VMs. It's slower (VM boot time) and local-only; it never runs in CI.

## Limitations

- **The firewall is enforced entirely inside the guest, by the guest's own root — not from the host.** The iptables rules, the allowed-IP set, and the refresh script all live on the VM's own disk. The default user has passwordless `sudo`, so anything able to run shell commands as that user — Claude Code itself, or any dependency it installs via `npm`/`pip`/`go get` — can disable the firewall entirely with one command (e.g. `sudo iptables -P OUTPUT ACCEPT`). It's defense-in-depth against casual or accidental exfiltration, not a hard boundary against a deliberately malicious or compromised process running inside the VM. The boundary that does hold regardless: the VM itself. Even a fully firewall-defeated guest still can't reach your real host credentials or other projects — only whatever's scoped to that one VM (its own tokens, its own project code).
- The firewall filters by resolved IP, refreshed every 5 minutes — solid against casual misuse, but not a guarantee against traffic smuggled over an already-allowed domain.
- First `claudevm up` downloads the Ubuntu cloud image, so it's slower the first time on a given Mac; later VMs reuse the cache.
