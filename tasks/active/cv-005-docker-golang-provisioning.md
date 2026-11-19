---
id: cv-005
title: "Install Docker and Go in new VM sandboxes"
blocked_by: [cv-004, cv-009]
legacy_format: true
---

# cv-005: Install Docker and Go in new VM sandboxes

## Status

Not started. Written up as a plan doc before implementation, following a
design interview (`/grill-me`). Nothing in this repo has been changed yet
for this task.

**Blocked by `cv-004`** (add tests for all existing `claudevm` commands):
this task's verification step needs `cv-004`'s integration-tier pytest
infrastructure (session-scoped, `claudevm-test-*`-namespaced real VM
fixtures) to exist first, so this task's own new tests can be written
against that harness instead of hand-rolled one-off scripts. Note this is a
small scope stretch beyond what `cv-004` itself commits to -- `cv-004`
explicitly lists "testing `claude-sandbox.yaml`'s own provisioning logic" as
a non-goal, since it's scoped to the `claudevm` CLI wrapper's 10 commands,
not guest-side provisioning. This task reuses `cv-004`'s fixture
*infrastructure* (the real-VM lifecycle machinery) for a different purpose
than `cv-004` itself covers: verifying new guest-side provisioning (Docker,
Go) actually works, the same way `cv-002` verified firewall behavior
manually before this project had any test suite at all.

**Blocked by `cv-009`** (remove outbound network restrictions): amended
during cv-009's planning. This plan assumes VMs have unrestricted egress,
so it no longer adds Docker Hub domains to an allowlist (decision #9) or
documents a container-firewall gap (decision #2). Landing it before cv-009
would leave `docker pull` blocked by the firewall.

## Background

`claude-sandbox.yaml` provisions every new VM with a fixed, unconditional
set of base packages (`python3` + pip/venv once cv-009 lands) plus the
dotfile provisioning described in the file's own header
comment. There's no Docker or Go toolchain in any VM today, and
no per-project mechanism to opt in to extra packages -- everything in the
template applies to every VM.

After cv-009, VMs have unrestricted outbound network access, so Go's
module proxy and Docker Hub are reachable with no extra configuration.

### Why this isn't just "add two apt-get lines"

**Provisioning re-runs on every boot, not just at creation.** Per this
file's own comments (e.g. step 3, "rebuilt fresh every boot") and Lima's own
docs, every `provision:` script runs on every VM boot, not once at instance
creation. `apt-get install -y <already-installed-package>` is a fast no-op,
so this mostly isn't a problem -- but it does mean any install approach that
isn't naturally idempotent (e.g. "always fetch whatever's currently
'latest'") would behave very differently on a fresh boot vs. a routine
restart, which matters directly for how Go's install is designed (see
below).

**Per-instance config is frozen at first boot, not live.** `cmd_new`/`cmd_up`
in `claudevm` render `claude-sandbox.yaml` into a per-instance `.lima.yaml`
copy only once -- on that specific instance's first-ever `claudevm up`.
Already-booted instances never re-read the shared template again, even
across later `down`/`up` cycles (`cmd_up` just calls `limactl start "$name"`
for those, with no template involved). So this task's changes will only ever
reach brand-new instances (or ones `claudevm new`'d but never yet booted) --
matching this task's own "new VMs" framing exactly, with no migration path
needed or possible for already-running instances short of `rm` + `new`.


## Goal

Install Docker (engine + CLI + Compose) and a current Go toolchain,
unconditionally, in every new VM -- matching the existing "no per-project
package selection" pattern.

## Decisions from the design interview

1. **Unconditional, every new VM** -- not opt-in. Matches the existing
   base-package pattern; this project has no per-instance package-selection
   mechanism anywhere today, and building one just for this would be new
   machinery beyond this task's actual ask.
2. **Superseded by cv-009**: with no outbound restrictions there is no
   container-firewall gap to document; drop the README Limitations bullet
   and the cv-001 cross-reference below. Original decision, kept for the
   record: **The `FORWARD`-chain gap ships as a documented limitation, not a fix.**
   Extending the allowlist/REJECT pattern to the `FORWARD` chain (so
   container egress is restricted the same way host egress is) would be
   real, non-trivial work on its own -- explicitly out of scope here.
   Instead: add a bullet to `README.md`'s Limitations section, cross-
   referencing `cv-001` (host-side `pf` enforcement from outside the guest
   kernel) as the natural fix path -- `cv-001`'s design filters by the VM's
   own IP at the VM's network boundary, so it wouldn't care whether traffic
   originated from a host process or a container inside it. Whoever picks up
   `cv-001` later should know it also closes this hole.
   - Explicitly **not** adding a CLAUDE.md note for the in-VM agent about
     this gap (unlike `cv-002`'s CLAUDE.md addition about the host
     firewall's REJECT behavior) -- decided the README's Limitations section
     is sufficient, since the human operator (not the in-VM agent) is the
     one who needs to reason about trusting the sandbox boundary.
3. **Docker Engine via Ubuntu's `docker.io` apt package**, not Docker's
   official `download.docker.com` repo. Simpler, no new trusted domain, and
   consistent with this project's stated "no PPA/version pinning, whatever
   Ubuntu currently ships" philosophy for base packages (`claude-sandbox.yaml`'s
   own header comment). Trades away currency of the Docker version for that
   consistency.
4. **Docker Compose included** via Ubuntu's own compose plugin package
   (`docker-compose-v2` on recent Ubuntu releases, providing the `docker
   compose` subcommand alongside `docker.io` -- exact package name to be
   confirmed empirically at implementation time against Ubuntu 26.04's
   actual repo contents, not assumed from an older release). Most
   Docker-based dev workflows are multi-container via Compose, not bare
   `docker run`.
5. **Default VM user added to the `docker` group** (no `sudo` needed for
   `docker` commands). The VM already has passwordless `sudo` for this user,
   so group membership grants no privilege beyond what's already effectively
   available -- pure ergonomics, no incremental security cost given the
   existing posture.
6. **Go via the official tarball from `go.dev/dl`, to `/usr/local/go`** --
   not apt's `golang-go`. Ubuntu's packaged Go version typically lags well
   behind current stable, which matters more for Go than most languages
   since toolchain version ties directly to module/build compatibility.
   `go.dev`/`dl.google.com` once being pre-allowlisted suggests this was
   the intent already.
7. **Go version is pinned to one specific release** (exact version + tarball
   URL + sha256 checksum, verified against `go.dev/dl` at implementation
   time -- not guessed now), refreshed manually over time, mirroring how
   this file already pins the Ubuntu cloud images to specific dated releases
   with explicit digests. Given provisioning re-runs every boot, "always
   fetch latest" would mean a VM's Go version could silently change on any
   routine restart with no changelog signal -- pinning avoids that, and the
   install script should check the pinned version against what's already
   present before re-fetching, so a normal reboot doesn't re-download
   anything.
8. **PATH needs three parts, not just `/etc/environment`** -- discovered by
   manually running this task's install steps against a real VM ahead of
   implementation, using the same `/etc/environment`-only approach this
   decision originally specified: it left `go`/`gofmt` reachable for VS
   Code Remote-SSH but **absent from `PATH` in a plain interactive SSH
   session**, even after a fresh login. Root cause: Ubuntu's `/etc/profile`
   unconditionally reassigns `PATH="/usr/local/sbin:/usr/local/bin:..."` for
   non-root interactive shells, which runs *after* PAM applies
   `/etc/environment` at login and clobbers it completely -- a known
   Debian/Ubuntu gotcha, not specific to this project. `/etc/environment`
   itself wasn't wrong (PAM does apply it, and it's still the only thing
   that reaches VS Code Remote-SSH's non-interactive session, which never
   sources `/etc/profile` at all), it's just insufficient alone for
   interactive shells. Fixed with three complementary pieces, none of which
   replaces `/etc/environment`:
   - **Keep `/etc/environment`** with `/usr/local/go/bin` and `~/go/bin`
     appended to `PATH`, exactly as before -- still required for VS Code
     Remote-SSH.
   - **Symlink `/usr/local/go/bin/go` and `gofmt` into `/usr/local/bin`**,
     which is already on `PATH` in every context (interactive shells,
     non-interactive SSH, sudo) and isn't touched by `/etc/profile`'s
     reassignment since it's already part of what that reassignment sets.
     Covers the two Go binaries themselves regardless of which PATH
     mechanism is in effect.
   - **Add `/etc/profile.d/99-go-gobin.sh`** appending `$HOME/go/bin` to
     `PATH`. `/etc/profile.d/*.sh` scripts run at the *end* of
     `/etc/profile`, after its own unconditional `PATH=` assignment, so an
     append here survives where an `/etc/environment` entry alone didn't.
     Needed because `$HOME/go/bin` (where `go install` puts binaries) is a
     directory of binaries that changes over time, so it can't be handled
     with a fixed set of symlinks the way `go`/`gofmt` themselves can.
9. **Superseded by cv-009**: there is no allowlist, so Docker Hub needs
   no configuration. Original decision, kept for the record: **Add Docker
   Hub domains to `default-allowlist.txt`**:
   `registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com`
   (the actual CDN image layers are served from, not `docker.io` itself).
   Docker's own *installation* needs no new domain (it comes through Ubuntu's
   already-allowlisted mirrors), but without these, `docker pull`/`docker
   build FROM ...` hit the same instant-REJECT wall as any other unlisted
   domain -- Docker would install successfully but be functionally useless
   until these are allowlisted, so they're part of the default set, not left
   for users to add per-project.
10. **Disable IPv6 in the Docker daemon config**
    (`/etc/docker/daemon.json` → `{"ipv6": false}`, written before
    `systemctl enable --now docker`). This is a Docker-daemon-level
    setting, not anything about a given image/compose file -- it affects
    every container this VM's Docker ever runs, regardless of what they
    are. Confirmed necessary and sufficient by a manual fix applied
    directly to a live project VM (`deploy-pb`, Docker installed ad hoc
    ahead of this task landing): without it, containers get handed an IPv6
    address that can never actually route anywhere under this project's
    current networking backend (`gvisor-tap-vsock` -- the VM itself has
    only a link-local IPv6 address and no default route, confirmed
    during cv-001's research, commit 9dd43b4), causing avoidable `Network unreachable`
    failures before falling back to IPv4. Applying `{"ipv6": false}` and
    restarting Docker on `deploy-pb` verified the fix directly.
11. **VM resource defaults (4 CPU / 4 GiB / 60 GB) stay as-is.** The
    existing `CLAUDEVM_CPUS`/`CLAUDEVM_MEMORY`/`CLAUDEVM_DISK` override
    mechanism already covers projects that need more room; bumping the
    global default would raise the cost for every project, including ones
    that never touch Docker or Go.
    *2026-11-19: superseded by cv-012, which scales the CPU and memory
    defaults with the host (`default_cpus` and `default_memory_gib` in
    `claudevm`). The disk default and the overrides are unchanged.*
12. **Verification bar before marking this "Done"**: automated integration
    tests written against `cv-004`'s pytest integration-tier infrastructure
    (the session-scoped, `claudevm-test-*`-namespaced real-VM fixtures), run
    through `cv-004`'s `./test.sh` entry point (`./test.sh integration`, or
    a bare `./test.sh`) -- never raw `pytest`, matching `cv-004` decision
    #12's rule that `test.sh` is the one and only documented way to run any
    of this repo's tests. Not manual, ad hoc checking. This task is not
    "Done" until those tests exist under `tests/`, run clean via
    `./test.sh integration`, and are checked in; a human manually running
    `docker run` once against a real VM and eyeballing the result does not
    satisfy this bar, even if `cv-004` has landed. Required coverage:
    - A fresh VM boots and provisions cleanly from the updated template.
    - `docker run` and `docker compose up` actually work end to end against
      a real image/compose file.
    - `go build`/`go test`/`go mod download` actually work end to end,
      including fetching a real dependency through the module proxy.
    - `go` and `gofmt` are on `PATH` in a **plain interactive SSH session**
      specifically (not just checked via their absolute
      `/usr/local/go/bin` path) -- the regression check for decision #8's
      `/etc/profile`-clobbering bug, found by manual testing before this
      task had any automated coverage at all.

## Proposed plan

1. **Confirm `cv-004` has landed** (or at least its integration-tier fixture
   infrastructure is usable) before starting this task's own test-writing
   work -- this task is blocked on that, not just "nice to sequence after."
2. **Add Docker + Compose + Go install to `claude-sandbox.yaml`**, after
   the existing base-package step (step 1):
   - `apt-get install -y docker.io docker-compose-v2`.
   - `usermod -aG docker <default user>`.
   - Write `/etc/docker/daemon.json` with `{"ipv6": false}` (decision #10),
     before Docker is started -- avoids a redundant restart just to pick up
     a setting that could've been in place from the daemon's first start.
   - Fetch the pinned Go tarball (URL + sha256 checksum verified against
     `go.dev/dl` at implementation time), extract to `/usr/local/go`, guarded
     by a version check so a routine reboot doesn't re-download.
   - PATH, per decision #8's three-part fix: append `/usr/local/go/bin` and
     `~/go/bin` to `PATH` via `/etc/environment` (for VS Code Remote-SSH);
     symlink `/usr/local/go/bin/{go,gofmt}` into `/usr/local/bin` (for
     interactive shells and everything else); drop
     `/etc/profile.d/99-go-gobin.sh` appending `~/go/bin` to `PATH` (also
     for interactive shells, covering future `go install`ed binaries).
   - `systemctl enable --now docker`.
3. *(Removed by cv-009: no allowlist to add Docker Hub domains to.)*
4. **Update `README.md`**:
   - Add Docker/Go to the "What this adds on top of stock Ubuntu" bullet
     list (`claude-sandbox.yaml`'s header comment, and/or the README's "How
     it works" section, whichever currently documents that list).
5. **Write verification tests as new integration-tier test files under
   `tests/`**, once `cv-004`'s infrastructure is available, reusing its
   session-scoped real-VM fixture pattern (`claudevm-test-*` naming,
   explicit timeouts) rather than a one-off manual script: boot a fresh
   instance from the updated template, confirm clean provisioning, then
   confirm `docker run`, `docker compose up`, and `go build`/`go
   test`/`go mod download` all work as described in decision #12. These
   tests must run cleanly via `./test.sh integration` (or a bare
   `./test.sh`) -- if `./test.sh` can't pick them up automatically the same
   way it picks up `cv-004`'s own tests, that's a bug to fix before this
   task can be called done, not something to route around with a separate
   script.
6. **Manually verify the boot-time cost** of the new provisioning steps on a
   real fresh VM (first `claudevm up`, which now includes the Go tarball
   download and Docker's apt install) -- no specific budget was set for
   this, but worth a sanity check that it doesn't become unreasonably slow,
   given the resource-sizing defaults are staying unchanged (decision #11).

## Open questions / risks to resolve during implementation

- **Resolved**: `docker-compose-v2` is a real, installable package for
  Ubuntu 26.04 ("resolute") -- confirmed directly against
  `packages.ubuntu.com/resolute/docker-compose-v2` (200 response), not
  assumed from an older release.
- **Resolved**: pinned Go version is `1.26.5`, verified live against
  `go.dev/dl/?mode=json` (not the summarized HTML page, to avoid
  transcription error in a checksum that's about to gate a `sha256sum -c`
  check): `go1.26.5.linux-amd64.tar.gz` /
  `5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053`,
  `go1.26.5.linux-arm64.tar.gz` /
  `fe4789e92b1f33358680864bbe8704289e7bb5fc207d80623c308935bd696d49`. Since
  this is a *pinned* version (decision #7), these values go directly into
  the provisioning script rather than being re-fetched at boot -- re-verify
  and bump deliberately when this gets stale, same as the Ubuntu image
  digests.
- **Resolved**: the `/etc/environment`-only PATH approach was insufficient
  for interactive shells -- see decision #8's rewrite for the root cause
  (`/etc/profile` clobbering) and the three-part fix. This was found by
  manually running the install steps against a real VM before
  implementation, exactly the kind of "real behavior diverges from
  assumption" bug `cv-004`'s Background section calls out as the norm for
  this project -- worth an explicit integration test asserting `go` is
  actually on `PATH` in a fresh, plain interactive SSH session (not just
  reachable via absolute path), so this doesn't silently regress.
- **Resolved by cv-009**: there is no firewall step left to coordinate
  with. Original question: whether Docker's own `docker.io` postinst already handles
  `net.ipv4.ip_forward=1` and its own iptables/NAT setup cleanly on top of
  this project's existing from-scratch `iptables -F OUTPUT` step, or whether
  ordering between Docker's own provisioning and step 3's firewall rebuild
  needs any explicit coordination -- verify empirically on a real boot
  rather than assuming no interaction.
- Total added boot-time cost (plan step 6) -- measure once implemented; no
  target budget was set going in.

## Non-goals

- Not making Docker/Go opt-in or configurable per project -- unconditional
  for every new VM (decision #1).
- Not bumping default VM resource sizing -- existing env var overrides are
  considered sufficient (decision #11).
- Not wiring CI, and not testing `claudevm`'s own CLI wrapper commands --
  that's `cv-004`'s scope, not this task's.
- Not related to `cv-003` (menubar control) -- independent, no interaction
  between the two.
- A separate task (`cv-007`) was briefly opened to address "VMs don't have
  real IPv6 connectivity" as a general VM/kernel-level concern, decoupled
  from Docker. It was folded back into this task (decision #10) once the
  concrete problem turned out to be entirely Docker-daemon-scoped -- no
  evidence of a non-container process on the VM hitting the same issue, so
  there was nothing left for a broader VM-wide fix to cover. `cv-007` was
  deleted rather than kept as an empty placeholder.

## Checklist

## Review log
