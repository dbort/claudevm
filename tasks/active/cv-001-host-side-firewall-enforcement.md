# cv-001: Move firewall enforcement from guest to host

## Status

Not started. Written up as a design/plan doc after a research session; nothing in
this repo has been changed yet for this task.

## Background

claudevm boots per-project Lima VMs for running Claude Code sessions, with a
default-deny egress firewall meant to limit what a sandboxed session (or a
compromised dependency it installs) can reach on the network. The mechanism
today, entirely defined in `claude-sandbox.yaml`:

- `iptables`/`ip6tables` rules set a default-deny `OUTPUT` policy inside the
  guest, provisioned at every boot.
- A domain allowlist (`allowlist.txt`, per-instance, edited via `claudevm
  allow`) is mounted read-only into the guest at `/mnt/claudevm-config/allowlist.txt`.
- `/usr/local/bin/update-firewall.sh` (also provisioned into the guest)
  resolves each allowlisted domain to IPs and adds them to an ipset
  (`claudevm-allowed`), re-run every 5 minutes via cron since many services
  (npm, GitHub, PyPI...) sit behind rotating CDN IPs.
- DNS itself is pinned to fixed resolvers (Quad9/Cloudflare) and egress-restricted
  to just those two IPs, so the domain-to-IP resolution step can't be routed
  around via an arbitrary DNS server.

### The problem this task addresses

**All of this enforcement lives entirely inside the guest, running as the
guest's own root.** The iptables rules, the ipset, the refresh script, and
the cron job are all guest-side state. The *only* host-controlled piece is
the raw `allowlist.txt` source file itself (read-only mount) — but that's
just data, not enforcement.

The default VM user has passwordless `sudo` (required for the tool to work
non-interactively). That means anything able to run shell commands as that
user — Claude Code itself, or any dependency it installs via `npm`/`pip`/`go
get`/etc. — can disable the entire firewall with one command, e.g.:

```
sudo iptables -P OUTPUT ACCEPT
```

There is currently no host-side enforcement layer at all. This is
documented as a known limitation in `README.md` under "Limitations," but the
whole point of this task is to close the gap rather than just document it:
give claudevm a network boundary that a privileged process *inside* the
guest cannot touch, because it lives in a different kernel entirely.

What still holds today, even with the firewall fully defeated from inside
the guest: the VM boundary itself (a separate kernel from the host, per
`README.md`'s "Why a VM instead of a container" section). A guest that
disables its own firewall still can't reach the *host's* real credentials,
SSH keys, or other projects — only whatever's scoped to that one VM. This
task is about closing the remaining gap: right now the guest can reach
*anything on the internet* once it defeats its own firewall, which is a much
bigger blast radius than "whatever's scoped to that VM."

### Constraint from cv-006: preserve a host-issued pause/resume escape hatch

`cv-006` adds `claudevm firewall pause`/`resume` — a *deliberate,
host-operator-issued* way to temporarily fully open a VM's egress for
debugging, distinct from (and not a mitigation for) the guest-side
self-bypass gap this task exists to close. Whatever host-side enforcement
mechanism this task lands on must not eliminate that capability outright —
an operator still needs *some* supported way to temporarily open a VM's
egress from the host once host-side `pf` enforcement exists too, or
`cv-006`'s feature becomes silently ineffective (guest-side pause would
open the guest's own chain, but traffic would still be blocked at the host
`pf` layer, with no way to also pause that layer). This doesn't dictate the
mechanism — host-side enforcement could grow its own pause/resume, or
delegate to the guest-side one if `pf` rules end up scoped to be no more
restrictive than the guest's own state — just that the capability itself
must survive this task's implementation.

## Research findings (from a prior session — verify before relying on any of this)

Lima (which claudevm builds on) supports multiple networking backends. What
matters here is whether the guest's traffic passes through something the
*host* controls before reaching the real network.

- **Default networking** (what claudevm's VMs use today, unconfigured):
  `gvisor-tap-vsock`, a host-side userspace network stack. Traffic does pass
  through a host-side process, but the guest does **not** get a host-visible
  IP address for general traffic — only specific ports Lima explicitly
  forwards (e.g. SSH, visible in `~/.lima/<name>/ssh.config` as
  `Hostname 127.0.0.1`). This was confirmed empirically against a real
  claudevm instance (`partybot`) in the prior session: its SSH config showed
  a `127.0.0.1`-forwarded port, consistent with this being the active mode.
  There's no host-visible per-guest IP to point a host firewall at in this
  mode.

- **`vzNAT`**: available specifically for the `vz` VM driver (which claudevm
  already uses — confirmed via `limactl` log output referencing
  `internal VM driver \`vz\``). Backed by Apple's own
  Virtualization.framework NAT, built in with **no external dependencies**
  (no compiling anything, no `limactl sudoers` setup). Requires Lima ≥0.14
  and macOS ≥13.0 (both satisfied by this project's stated requirements).
  Per Lima's docs and secondary sources: assigns the guest its own real IP
  address that is **reachable from the host** (though not from other
  guests or the wider LAN). This is the property we need: a host-visible
  guest IP that a host-side firewall could target.

- **`socket_vmnet`**: also gives a host-visible guest IP (from a
  `192.168.105.0/24`-style subnet), but requires compiling `socket_vmnet`
  from source into `/opt/socket_vmnet`, a `limactl sudoers` configuration
  step, and group-permission setup. Ruled out in the prior session's
  research as the wrong choice here — `vzNAT` gets the same host-visible-IP
  property with none of that operational overhead.

**None of Lima's docs mention any built-in traffic filtering/allowlist
feature in Lima itself, `gvisor-tap-vsock`, or `socket_vmnet`.** Filtering
would need to be implemented as new claudevm-owned logic, using macOS's
native `pf` (packet filter) against whatever IP `vzNAT` assigns the guest.

**None of the above was empirically verified beyond checking the current
default mode's SSH config.** The `vzNAT`/`socket_vmnet` specifics come from
Lima's docs and web search summaries, not from actually standing up a vzNAT
instance and inspecting it. Treat those specifics as a starting hypothesis,
not verified fact — the first implementation step below is to verify them
directly.

## Goal

Enforce the domain allowlist from the host side, using a mechanism a
privileged process inside the guest cannot disable, while keeping (not
replacing) the existing guest-side firewall as a second layer of
defense-in-depth.

## Proposed plan

1. **Verify the networking-mode facts above empirically, first.** Stand up
   a scratch Lima instance with `--vm-type=vz --network=vzNAT` (or the
   equivalent YAML `networks:` config) and confirm:
   - It actually boots and SSH/`limactl shell` still work.
   - What IP address the guest is actually assigned, and whether it's
     genuinely reachable from the host (e.g. `ping`/`curl` from the Mac to
     the guest's IP).
   - Whether switching networking modes changes or breaks anything claudevm
     already depends on — in particular, re-test the SSH `ControlPersist`
     staleness behavior worked out in the prior session (see git log/`README.md`
     limitations for context: Lima's SSH connection to run provisioning is
     reused by later sessions, and `cmd_up` forces it closed via
     `close_ssh_control` after provisioning finishes — confirm this still
     works correctly under `vzNAT`).
   - Whether VS Code Remote-SSH (`claudevm code`) still works normally.

2. **Decide how `claudevm` requests `vzNAT`.** Given the CLI `--mount` flag
   turned out to have inconsistent behavior across Lima versions earlier in
   this project's history (see git log for "Fix host home directory
   leaking into VMs" — mounts are now rendered into the per-instance YAML
   file rather than passed as CLI flags, specifically to avoid this class of
   problem), lean toward expressing the network choice in the rendered
   per-instance YAML too, not a `limactl start` CLI flag, for the same
   reason: more predictable across Lima versions, and keeps `cmd_up`'s
   already-established "render a complete per-instance config" pattern
   consistent.

3. **Design the host-side enforcement mechanism.** This is the bulk of the
   new work:
   - A host-side script (new file, or logic added to `claudevm`) that reads
     each instance's `allowlist.txt` (same file already used by the guest's
     `update-firewall.sh` — no need for a second copy or a new format),
     resolves domains to IPs, and loads `pf` rules scoped to *that
     instance's specific vzNAT-assigned IP* as the source address.
   - Needs periodic re-resolution for the same reason the guest-side
     version does (rotating CDN IPs) — the guest-side script handles this
     with a 5-minute cron job; the host-side equivalent will need its own
     periodic trigger. A macOS `launchd` agent/daemon (the host analog of
     cron) is the natural fit — investigate `LaunchAgent` vs `LaunchDaemon`
     depending on whether this needs to run outside a logged-in user
     session.
   - `pf` rule loading requires `pfctl`, which needs root **on the host**.
     This is a new category of requirement — nothing in claudevm currently
     needs host-side `sudo` for anything. Needs careful design:
     - Use a `pf` anchor (e.g. `pfctl -a "claudevm/<instance-name>" -f ...`)
       scoped per-instance, rather than touching the user's main pf
       ruleset directly, so claudevm doesn't clobber or conflict with
       other pf users (Docker Desktop, VPN software, etc. commonly install
       their own pf anchors).
     - **Important pf subtlety to verify**: loading rules into an anchor via
       `pfctl -a ... -f` does not necessarily make them active unless the
       *main* ruleset (typically `/etc/pf.conf`) has a matching
       `anchor "claudevm/*"` reference point. macOS's default `/etc/pf.conf`
       may or may not already have a suitable anchor point for third-party
       tools to hook into (other tools like Docker Desktop and Little
       Snitch solve this in different ways — worth looking at how they
       do it before designing this from scratch). This needs research
       before implementation, not assumption.
   - Figure out what host-side privilege model to use for the `pfctl`
     calls — e.g., a one-time `sudo` setup step (similar in spirit to how
     `secrets` and provisioning already ask for one-time host input), vs.
     prompting for `sudo` on every `claudevm up`/`refresh`. Prompting every
     time would be poor UX for a tool that otherwise runs non-interactively;
     look at whether a narrowly-scoped `sudoers.d` entry (only permitting
     the specific `pfctl` invocation claudevm needs, analogous to how Lima's
     own `limactl sudoers` works for `socket_vmnet`) is workable.

4. **Decide the relationship between guest-side and host-side enforcement.**
   Recommendation: keep both. Host-side becomes the real security boundary;
   guest-side stays as-is, both as defense-in-depth (catches misconfigured
   or not-yet-loaded host rules) and because it already handles IPv6
   lockdown and DNS pinning, which are separate concerns from this task.
   Don't remove or weaken the existing `claude-sandbox.yaml` firewall
   provisioning as part of this work.

5. **Wire the lifecycle into `claudevm`'s existing commands:**
   - `claudevm up`: load/refresh the instance's pf anchor after the VM is
     up and its `vzNAT` IP is known.
   - `claudevm refresh`: also refresh the host-side rules immediately,
     matching what it already does for the guest-side ipset.
   - `claudevm down`/`rm`: consider whether the pf anchor should be torn
     down (probably yes for `rm`; for `down`, could go either way — a
     stopped VM has no traffic to filter, so it may not matter either way,
     but stale anchors accumulating across many `new`/`rm` cycles is worth
     avoiding).
   - `claudevm allow`: no change needed to the command itself, but note
     that after an edit, both the guest-side and host-side refresh paths
     need to pick up the change (today `claudevm allow`'s output tells the
     user to run `claudevm refresh` — that should cover both once this
     lands).

6. **Update `README.md`** once implemented: the "Limitations" section
   currently documents the guest-only-enforcement gap prominently (added in
   the same session this task doc came out of) — that documentation should
   be revised to reflect the new host-enforced reality, not just have a new
   bullet appended.

## Open questions / risks to resolve during implementation

- Whether macOS's default `pf.conf` actually supports hooking in a
  third-party anchor without the user having manually enabled `pf`
  or added an anchor reference first (see the "important pf subtlety"
  note above) — this could be a hard blocker or just an extra one-time
  setup step; unknown until researched.
- **Partially resolved**: under the *default* networking backend
  (`gvisor-tap-vsock`, unconfigured — not `vzNAT`), the guest gets **no real
  IPv6 connectivity at all**, confirmed empirically against a live instance
  (`deploy-pb`) while debugging an unrelated `cv-006` pause/resume test: `ip
  -6 addr show` on `eth0` shows only a link-local address (`fe80::.../64`),
  and `ip -6 route show` has no `default via ...` route — only on-link
  link-local routes. A blocked IPv6 attempt fails with `ENETUNREACH`
  ("Network unreachable") at the kernel routing layer, before packets ever
  reach `ip6tables` — confirmed by checking `claudevm firewall status
  deploy-pb` and seeing the IPv6 `OUTPUT` policy already `ACCEPT` (paused)
  at the time, so the block wasn't coming from the firewall at all. This
  means `claude-sandbox.yaml`'s `ip6tables` lockdown is currently inert
  defense-in-depth under the default backend — not actively restricting
  anything, since nothing gets through regardless of its rules. **Still
  open**: whether `vzNAT` specifically (this task's proposed backend for
  host-visible guest IPs) behaves the same way or actually routes IPv6 —
  this finding only covers the default backend, not `vzNAT`; the original
  open question stands for that mode and needs its own empirical check
  once a `vzNAT` instance exists (test step 1 above).
- Whether this should ship as the new default behavior, or as an opt-in
  (e.g. an env var or `claudevm new` flag) until it's proven reliable
  across a range of setups. Given this introduces a new host-side `sudo`
  requirement and a new failure mode (misconfigured pf rules silently
  under- or over-blocking), leaning toward opt-in initially is probably
  the safer rollout, but that's a judgment call for whoever implements this
  to revisit once the mechanism is working.
- Concrete verification step once implemented: actually simulate the
  threat this task exists to address — from inside a guest with a
  host-enforced anchor active, confirm that `sudo iptables -P OUTPUT
  ACCEPT` (or any other guest-side firewall bypass) does *not* restore
  access to a blocked domain, proving the host-side layer is the one
  actually doing the enforcing.

## Non-goals

- Not removing or weakening the existing guest-side firewall.
- Not redesigning secrets handling, dotfile seeding, or other unrelated
  parts of `claude-sandbox.yaml`/`claudevm`.
- Not attempting to support this on Intel Macs or the `qemu` `vmType`
  fallback mentioned in `claude-sandbox.yaml`'s commented-out note — this
  is `vz`-driver-specific (Apple Silicon).
