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

## Background

`claude-sandbox.yaml` provisions every new VM with a fixed, unconditional
set of base packages (`iptables`, `ipset`, `dnsutils`, `cron`, `python3` +
pip/venv) plus the firewall/DNS/secrets machinery described in the file's
own header comment. There's no Docker or Go toolchain in any VM today, and
no per-project mechanism to opt in to extra packages -- everything in the
template applies to every VM.

`default-allowlist.txt` already includes `go.dev`, `dl.google.com`,
`proxy.golang.org`, and `sum.golang.org` (added in a prior commit, "Add Go
sites to the allowlist"), apparently in anticipation of Go tooling being
used inside a VM -- but no Go toolchain is actually installed anywhere yet.
No Docker Hub domains exist in the allowlist at all.

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

**Docker containers bypass the existing firewall entirely.** The whole
default-deny/allowlist mechanism (`claude-sandbox.yaml` step 3's `OUTPUT`
policy, `update-firewall.sh`'s ipset, `cv-002`'s fast-fail `REJECT`) is built
on the `OUTPUT` chain -- traffic originated directly by host processes.
Docker container traffic instead goes out through the `docker0` bridge, NAT,
and the `FORWARD` chain, which Ubuntu leaves at its default policy of
`ACCEPT`. **A running container would get fully unrestricted internet
access, regardless of the allowlist**, even though every other process in
the VM stays locked down. This is a real, current gap in what the sandbox
promises, not a hypothetical.

## Goal

Install Docker (engine + CLI + Compose) and a current Go toolchain,
unconditionally, in every new VM -- matching the existing "no per-project
package selection" pattern -- while being explicit (not silent) about the
one significant gap this creates in the network sandbox.

## Decisions from the design interview

1. **Unconditional, every new VM** -- not opt-in. Matches the existing
   base-package pattern; this project has no per-instance package-selection
   mechanism anywhere today, and building one just for this would be new
   machinery beyond this task's actual ask.
2. **The `FORWARD`-chain gap ships as a documented limitation, not a fix.**
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
   `go.dev`/`dl.google.com` being pre-allowlisted supports this having been
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
8. **PATH additions go in `/etc/environment`**, not `~/.bashrc`/`~/.profile`
   -- reusing the exact precedent and rationale already in this file's
   secrets-provisioning step: VS Code's Remote-SSH extension host is a
   non-interactive background process that never sources `~/.bashrc`, so
   anything only added there silently wouldn't apply for one of claudevm's
   two primary usage modes. Adds `/usr/local/go/bin` (and Go's default
   `GOBIN`/module-cache location under `~/go/bin`) to `PATH`.
9. **Add Docker Hub domains to `default-allowlist.txt`**:
   `registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com`
   (the actual CDN image layers are served from, not `docker.io` itself).
   Docker's own *installation* needs no new domain (it comes through Ubuntu's
   already-allowlisted mirrors), but without these, `docker pull`/`docker
   build FROM ...` hit the same instant-REJECT wall as any other unlisted
   domain -- Docker would install successfully but be functionally useless
   until these are allowlisted, so they're part of the default set, not left
   for users to add per-project.
10. **VM resource defaults (4 CPU / 4 GiB / 60 GB) stay as-is.** The
    existing `CLAUDEVM_CPUS`/`CLAUDEVM_MEMORY`/`CLAUDEVM_DISK` override
    mechanism already covers projects that need more room; bumping the
    global default would raise the cost for every project, including ones
    that never touch Docker or Go.
11. **Verification bar before marking this "Done"**: automated integration
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
    - Explicitly **not** required: empirically reproducing the `FORWARD`-chain
      gap (i.e., proving a container can reach a non-allowlisted domain).
      The gap is accepted as a known, understood Linux/iptables behavior
      rather than something that needs its own proof step for this task.

## Proposed plan

1. **Confirm `cv-004` has landed** (or at least its integration-tier fixture
   infrastructure is usable) before starting this task's own test-writing
   work -- this task is blocked on that, not just "nice to sequence after."
2. **Add Docker + Compose + Go install to `claude-sandbox.yaml`**, placed
   before the firewall lockdown step (step 3 today), alongside/after the
   existing base-package step (step 1) -- not after the ipset allowlist is
   populated (step 4), since installation itself only needs Ubuntu's mirrors
   (already reachable pre-lockdown) and shouldn't have any dependency on the
   allowlist ipset being warm yet:
   - `apt-get install -y docker.io <compose-plugin-package>`.
   - `usermod -aG docker <default user>`.
   - Fetch the pinned Go tarball (URL + sha256 checksum verified against
     `go.dev/dl` at implementation time), extract to `/usr/local/go`, guarded
     by a version check so a routine reboot doesn't re-download.
   - Append `/usr/local/go/bin` (and `~/go/bin`) to `PATH` via
     `/etc/environment`, following the existing precedent exactly.
   - `systemctl enable --now docker`.
3. **Add the three Docker Hub domains to `default-allowlist.txt`**, under a
   new `# Docker Hub` comment section matching the file's existing
   per-service grouping style.
4. **Update `README.md`**:
   - Add Docker/Go to the "What this adds on top of stock Ubuntu" bullet
     list (`claude-sandbox.yaml`'s header comment, and/or the README's "How
     it works" section, whichever currently documents that list).
   - Add a new bullet to the Limitations section describing the
     `FORWARD`-chain gap plainly, cross-referencing `cv-001` as the fix path
     (decision #2 above).
5. **Write verification tests as new integration-tier test files under
   `tests/`**, once `cv-004`'s infrastructure is available, reusing its
   session-scoped real-VM fixture pattern (`claudevm-test-*` naming,
   explicit timeouts) rather than a one-off manual script: boot a fresh
   instance from the updated template, confirm clean provisioning, then
   confirm `docker run`, `docker compose up`, and `go build`/`go
   test`/`go mod download` all work as described in decision #11. These
   tests must run cleanly via `./test.sh integration` (or a bare
   `./test.sh`) -- if `./test.sh` can't pick them up automatically the same
   way it picks up `cv-004`'s own tests, that's a bug to fix before this
   task can be called done, not something to route around with a separate
   script.
6. **Manually verify the boot-time cost** of the new provisioning steps on a
   real fresh VM (first `claudevm up`, which now includes the Go tarball
   download and Docker's apt install) -- no specific budget was set for
   this, but worth a sanity check that it doesn't become unreasonably slow,
   given the resource-sizing defaults are staying unchanged (decision #10).

## Open questions / risks to resolve during implementation

- Exact compose-plugin package name and its availability in Ubuntu 26.04's
  repos (decision #4) -- verify directly against the real image, not
  assumed from an older Ubuntu release.
- Exact Go version, tarball URL, and sha256 checksum to pin (decision #7) --
  fetch and verify from `go.dev/dl` at implementation time.
- Whether Docker's own `docker.io` postinst already handles
  `net.ipv4.ip_forward=1` and its own iptables/NAT setup cleanly on top of
  this project's existing from-scratch `iptables -F OUTPUT` step, or whether
  ordering between Docker's own provisioning and step 3's firewall rebuild
  needs any explicit coordination -- verify empirically on a real boot
  rather than assuming no interaction.
- Total added boot-time cost (plan step 6) -- measure once implemented; no
  target budget was set going in.

## Non-goals

- Not extending the allowlist/REJECT firewall pattern to the `FORWARD`
  chain to actually restrict container egress -- documented gap only
  (decision #2), with `cv-001` noted as the natural fix path if/when that's
  picked up.
- Not making Docker/Go opt-in or configurable per project -- unconditional
  for every new VM (decision #1).
- Not adding a CLAUDE.md note for the in-VM agent about the container-
  network gap -- decided the README's Limitations section is the right
  place for this (decision #2).
- Not bumping default VM resource sizing -- existing env var overrides are
  considered sufficient (decision #10).
- Not wiring CI, and not testing `claudevm`'s own CLI wrapper commands --
  that's `cv-004`'s scope, not this task's.
- Not related to `cv-003` (menubar control) -- independent, no interaction
  between the two.
