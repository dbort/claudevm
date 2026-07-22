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
claudevm secrets myproject                  # optional: GitHub deploy key + Claude token
claudevm up myproject                       # boot the VM
claudevm code myproject                     # open VS Code (Remote-SSH) into it
```

## Commands

| Command | What it does |
|---|---|
| `claudevm new <name> [dir]` | Create config for a new sandbox. `dir` defaults to the current directory. |
| `claudevm allow <name>` | Edit the domain allowlist (`$EDITOR`). Applied within 5 minutes, or immediately with `refresh`. |
| `claudevm secrets <name>` | Generate a dedicated deploy key and save a Claude Code token for this VM only. |
| `claudevm up <name>` | Boot (or resume) the VM, mounting the project at `/workspace`. |
| `claudevm down <name>` | Stop the VM. Disk state is kept. |
| `claudevm rm <name>` | Stop, delete the VM, and delete its config. Asks for confirmation. |
| `claudevm ssh <name>` | Shell into the VM. |
| `claudevm code <name>` | Open VS Code (Remote-SSH) at `/workspace` on the VM. |
| `claudevm refresh <name>` | Re-run the firewall/allowlist refresh immediately, instead of waiting for cron. |
| `claudevm ls` | List all Lima VMs. |

Resource sizing (defaults: 4 CPUs, 4 GiB memory, 60 GB disk) can be overridden with `CLAUDEVM_CPUS`, `CLAUDEVM_MEMORY`, `CLAUDEVM_DISK` environment variables before `claudevm up`.

## How it works

- **`claude-sandbox.yaml`** is a Lima template (based on `template://ubuntu-lts`) that:
  - installs `iptables`/`ipset`
  - pins DNS resolution to fixed resolvers (Quad9 `9.9.9.9` primary, Cloudflare `1.1.1.1` secondary) instead of whatever the DHCP-provided resolver happens to be
  - sets a default-deny egress policy, with DNS egress itself restricted to just those two resolver IPs
  - blocks all IPv6 egress outright (loopback only) — the allowlist mechanism only handles IPv4
  - installs a script that resolves your allowlist domains to IPs and refreshes them every 5 minutes via cron — a one-time DNS resolution isn't enough since services like npm and GitHub sit behind rotating CDN IPs
- **`default-allowlist.txt`** is the starting domain list (Anthropic API, GitHub, npm, PyPI, Ubuntu mirrors), copied per-project so you can tune it per sandbox.
- **`claudevm`** is the wrapper: it passes your project directory and per-instance config to `limactl start` via `--mount` flags, so the template itself stays generic across all projects.
- **`pre-push-branch-guard.sh`** is an optional git hook you can drop into a project to block direct pushes to protected branches, as a local backstop alongside GitHub branch protection rules.

## Credentials

None of your host credentials are ever mounted into a VM. Instead:

- **Claude Code**: `claudevm secrets <name>` prompts you to run `claude setup-token` on your *host* (it needs a browser, which the VM's firewall wouldn't allow anyway) and saves the result as a per-VM `CLAUDE_CODE_OAUTH_TOKEN` — scoped to inference only, not a full account session.
- **GitHub**: generates a fresh, dedicated ed25519 keypair per VM. Add the printed public key as a **deploy key on one repo only** — not an account-wide SSH key — so a compromised VM exposes at most one repository. Pair this with a branch protection rule requiring PRs into `main`, so the key can push feature branches but not merge directly.

See `claudevm secrets --help` output (run the command) for the exact steps it prints.

**This is proportionate protection for personal projects, not a hard security boundary.** If you're ever handling something high-stakes, the stronger pattern is a credential proxy that keeps the token on the host entirely and injects it into requests, so the VM never holds the secret at all.

## Repo layout

```
claude-sandbox.yaml         Lima VM template (firewall + secrets provisioning)
default-allowlist.txt       Starting domain allowlist
claudevm                    CLI wrapper
install.sh                  One-shot setup script
pre-push-branch-guard.sh    Optional git hook for protected branches
README.md                   This file
```

## Limitations

- The firewall filters by resolved IP, refreshed every 5 minutes — solid against casual misuse, but not a guarantee against traffic smuggled over an already-allowed domain.
- First `claudevm up` downloads the Ubuntu cloud image, so it's slower the first time on a given Mac; later VMs reuse the cache.
