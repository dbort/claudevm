# cv-006: `claudevm firewall pause`/`resume`/`status`

## Status

Not started. Written up as a plan doc after a `/grill-me` design interview
that resolved every open branch below; nothing in this repo has been
changed yet for this task except a cross-note added to `cv-001`'s doc (see
"Relationship to cv-001" below).

## Background

`claude-sandbox.yaml`'s guest-side firewall (see `README.md`'s
"Limitations" section and `cv-001`'s background) is default-deny, enforced
entirely inside the guest by the guest's own root. Anything able to run
shell commands as that user can already disable it — that's the whole
premise `cv-001` exists to eventually close from the host side.

Separately from that vulnerability, there's a legitimate, recurring
operator need: while debugging a session (e.g. "is this curl failure
actually the firewall, or something else?"), the fastest way to find out is
to temporarily open the VM's egress wide open, retry, and see what changes
— without permanently disabling the firewall, and without a slower
edit-allowlist-then-wait-for-cron loop via `claudevm allow`/`refresh` for
something that might not even be a firewall issue.

Today there's no supported way to do this — the only option is to `claudevm
ssh` in and run the exact bypass command `cv-001`/`README.md` flag as the
vulnerability, by hand, with no easy way back to the exact prior state and
no auto-revert if you forget.

## Goal

Add `claudevm firewall pause <name> [--duration=X]`, `claudevm firewall
resume <name>`, and `claudevm firewall status <name>`, giving the host
operator an explicit, supported way to temporarily fully open a VM's
egress (both IPv4 and IPv6), with optional timed auto-resume, without
weakening the default-deny posture in any other way (it always comes back
on `resume`, on the scheduled timer, or — as a hard backstop — on the VM's
next reboot, since provisioning step 3 rebuilds the default-deny policy
from scratch every boot regardless of pause state).

This is a deliberate, host-issued escape hatch — not a fix for, or
justification of, the underlying guest-side self-bypass gap. See
"Relationship to README.md's Limitations section" below for how the two
should be framed distinctly.

## Why this isn't a one-line policy flip

The obvious-looking implementation — `iptables -P OUTPUT ACCEPT` /
`ip6tables -P OUTPUT ACCEPT`, matching the literal command
`README.md`/`cv-001` cite as the guest-side vulnerability — **would not
actually open anything for IPv4** as the firewall is built today. Since
`cv-002`, `update-firewall.sh` maintains an unconditional catch-all
`REJECT` rule as the last rule in the `OUTPUT` chain (re-appended on every
cron cycle, specifically so it can never end up ordered before the ipset
ACCEPT rule). A chain's default *policy* is only consulted when a packet
falls through without matching any rule — and this REJECT rule matches
every packet unconditionally. So flipping the policy alone leaves egress
exactly as blocked as before; the pre-existing REJECT rule intercepts
everything regardless of the policy value.

`pause` therefore needs to **flush** the `OUTPUT` chain (removing the
catch-all REJECT rule along with everything else), then set the policy to
ACCEPT — the same two-step version originally described when answering the
user's initial question in this session (`iptables -F OUTPUT; iptables -P
OUTPUT ACCEPT`), not the one-liner from the README's illustrative example.

`resume` has the mirror-image problem: it can't just flip the policy back
to DROP, because flushing removed every rule, including loopback,
established-connections, DNS-pinning, the ipset ACCEPT rule, and both
REJECT catch-alls (v4 and v6). `resume-firewall.sh` needs to fully rebuild
chain state, not just restore the policy value:

- Re-run `/usr/local/bin/update-firewall.sh` (already idempotent/self-
  correcting per `cv-002`) to rebuild the IPv4 side: loopback,
  established, DNS-pinning, ipset ACCEPT, and the REJECT catch-all, in the
  correct order, then set `iptables -P OUTPUT DROP`.
- Separately rebuild the IPv6 lockdown (loopback ACCEPT + REJECT
  catch-all + `ip6tables -P OUTPUT DROP`), since that logic currently only
  lives inline in `claude-sandbox.yaml` provisioning step 3 and has no
  reusable script the way IPv4's does. `resume-firewall.sh` needs its own
  copy of those same four lines (small enough that a shared script isn't
  worth the indirection).

## Proposed plan

1. **`pause-firewall.sh`** (new, provisioned into the guest alongside
   `update-firewall.sh`, run via `sudo`):
   - Disable the recurring refresh: `mv /etc/cron.d/claudevm-firewall
     /etc/cron.d/claudevm-firewall.paused` (rather than stopping cron
     globally — more targeted, doesn't affect any other cron job that
     might exist on the VM). Without this, the existing 5-minute cron tick
     would re-run `update-firewall.sh` mid-pause and silently re-lock
     everything regardless of `--duration`.
   - `iptables -F OUTPUT && iptables -P OUTPUT ACCEPT`;
     `ip6tables -F OUTPUT && ip6tables -P OUTPUT ACCEPT` (see above for why
     flush is required, not just policy).
   - If `--duration=X` was given: first defensively cancel any existing
     auto-resume timer (`systemctl stop claudevm-firewall-resume.timer
     2>/dev/null || true`), then schedule a fresh one:
     `systemd-run --on-active=X --unit=claudevm-firewall-resume
     /usr/local/bin/resume-firewall.sh`. `X` is passed through verbatim as
     systemd time-span syntax (`30min`, `1h`, ...) — no custom parsing
     owned by claudevm. Calling `pause` again while already paused always
     replaces any prior timer/duration rather than erroring or stacking.
   - Print a clear warning banner: that egress is fully open (v4 + v6),
     the exact `claudevm firewall resume <name>` command, and — if a
     duration was set — when it will auto-resume.
2. **`resume-firewall.sh`** (new, same provisioning treatment):
   - `systemctl stop claudevm-firewall-resume.timer 2>/dev/null || true`
     — always, even when resume is invoked manually before a scheduled
     timer fires, so a stray timer can't re-fire resume a second time
     later (harmless, but noisy/confusing).
   - Restore the cron file:
     `mv /etc/cron.d/claudevm-firewall.paused /etc/cron.d/claudevm-firewall
     2>/dev/null || true` (no-op if `pause` was never called, e.g. if this
     runs from the scheduled timer as intended).
   - Rebuild IPv4 (`update-firewall.sh`, then `iptables -P OUTPUT DROP`)
     and IPv6 (loopback ACCEPT + REJECT catch-all + `ip6tables -P OUTPUT
     DROP`) chain state, per the "why this isn't one-line" section above.
3. **`claudevm firewall status <name>`** (new, guest-side check invoked
   via `limactl shell`, no new provisioned script needed — a short inline
   command is enough): read the live `iptables -L OUTPUT -n` /
   `ip6tables -L OUTPUT -n` policy line as ground truth (ACCEPT = paused,
   DROP = enforced) rather than trusting a separate state file, consistent
   with this codebase's existing self-correcting style (`cv-002`'s
   idempotent rule management, `update-firewall.sh`'s re-derive-don't-trust
   approach). If paused, also check for a `claudevm-firewall-resume.timer`
   unit and report its remaining time if present, or "paused indefinitely"
   if not.
4. **`claudevm` CLI surface** (`cmd_firewall_pause`, `cmd_firewall_resume`,
   `cmd_firewall_status`, dispatched from a new `firewall` case in
   `main()`):
   - Syntax: `claudevm firewall <pause|resume|status> <name>
     [--duration=X]` — name stays a positional arg like every other
     subcommand (`allow <name>`, `secrets <name>`), `firewall` just adds
     one more level of verb nesting ahead of it.
   - Each subcommand calls `require_instance` (existing helper) plus a new
     explicit "is this VM running" check before invoking `limactl shell`,
     so a stopped VM gets a clear claudevm-specific error instead of a raw
     Lima failure.
   - `pause`/`resume` are thin wrappers around
     `limactl shell "$name" -- sudo /usr/local/bin/{pause,resume}-firewall.sh
     [--duration=X]`, matching `cmd_refresh`'s existing call style exactly.
5. **Update `README.md`**:
   - Add the three new subcommands to the Commands table.
   - Revise the "Limitations" bullet carefully: the guest's ability to
     disable its own firewall via a raw shell command **stays documented
     as a real gap**, unchanged in severity — `claudevm firewall
     pause`/`resume` do not close it or make it acceptable. Add a
     *separate* sentence noting that `claudevm firewall pause`/`resume`
     exist as a distinct, host-operator-issued mechanism for the same
     underlying action, explicitly not framed as mitigating the
     guest-side gap.
6. **Relationship to `cv-001`**: added a cross-note to `cv-001`'s doc (see
   `tasks/active/cv-001-host-side-firewall-enforcement.md`) so that when
   host-side `pf` enforcement is eventually designed, it preserves a
   host-issued pause/resume mechanism rather than just closing the gap
   with no escape hatch at all. Whether that means `cv-001`'s host-side
   layer grows its own pause/resume, or this guest-side one remains
   sufficient because host-side enforcement is a separate, independently
   toggleable layer, is left for `cv-001`'s implementation to decide.

## Design properties worth calling out explicitly

- **A pause can never outlive a reboot.** Provisioning step 3 in
  `claude-sandbox.yaml` rebuilds the default-deny policy unconditionally
  on every boot, with no awareness of any prior pause state. `claudevm
  down` + `up` (a full VM restart, not a suspend) is therefore a hard
  backstop against a forgotten indefinite pause — not a scenario this task
  needs to separately guard against.
- **No audit logging.** This is a single-user local dev tool; no other
  `claudevm` command logs its own actions today (not even `rm`, which is
  irreversible), so adding logging here would be new, unrequested scope.
- **No confirmation prompt on `pause`.** Matches the CLI's existing
  non-interactive style — only `rm` prompts today, because it's
  irreversible; `pause` is not (it self-heals on resume, on timer, or on
  reboot). A loud warning banner on every `pause` call substitutes for a
  prompt without adding friction to what's meant to be a fast debugging
  escape hatch.

## Open questions / risks to resolve during implementation

- Confirm `systemd-run` is present by default in whatever Ubuntu
  26.04 image variant claudevm actually provisions (server vs. minimal —
  `claude-sandbox.yaml` tries release images first, minimal as fallback,
  see its `images:` list). It ships as part of `systemd` on essentially
  all modern Ubuntu variants, but this project's own history (`cv-002`)
  has repeatedly found that "should work" needs empirical verification
  against a real instance before being trusted.
- Confirm `systemd-run --on-active=X --unit=NAME` is the correct
  incantation for a one-shot delayed job (as opposed to `--timer-property`
  variants or `.timer`/`.service` unit-naming subtleties) by testing
  against a real instance, not just `man systemd-run`.
- Double-check `resume-firewall.sh`'s rebuild order doesn't reopen the
  exact rule-ordering hazard `cv-002` fixed (ACCEPT must land before
  REJECT) — should be automatically fine since it delegates the IPv4 side
  entirely to the already-correct `update-firewall.sh`, but verify on a
  disposable test instance the same way `cv-002` did before trusting it.

## Non-goals

- Not eliminating the guest's own ability to self-bypass the firewall —
  that's `cv-001`'s job, still needed regardless of this task.
- Not building any host-side timer or state tracking — `--duration` is
  implemented entirely as a guest-side scheduled job, so a stopped host
  process, closed terminal, or sleeping Mac can't cause a missed
  auto-resume the way a host-side `sleep &` approach could have.
- Not adding audit logging, a confirmation prompt, or a maximum duration
  cap (see "Design properties" above for why each was ruled out).
- Not related to `cv-004` (command-tests) or `cv-005` (Docker/Golang
  provisioning) — independent work landed by other sessions in this repo
  in parallel with this one.
